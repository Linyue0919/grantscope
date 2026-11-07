"""Official Grants.gov opportunity details (award amounts, applicant eligibility).

The search endpoint (services/grants_api.py) returns summary records only. This
module calls the public ``fetchOpportunity`` endpoint for one opportunity and
normalizes the fields the matching engine needs. Missing values stay ``None``;
nothing is guessed.
"""
import html
import re

import requests

DETAIL_API_URL = "https://api.grants.gov/v1/api/fetchOpportunity"
GRANT_URL = "https://www.grants.gov/search-results-detail/{id}"


class OpportunityDetailsError(RuntimeError):
    """Raised when official details cannot be retrieved or understood."""


def grant_url(opportunity_id):
    return GRANT_URL.format(id=opportunity_id)


def _amount(value):
    """Parse an official dollar amount; return None when it is not reported."""
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).replace(",", "").replace("$", "").strip()
    if not raw or raw.lower() in {"none", "null", "n/a"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "y"}:
        return True
    if text in {"false", "no", "n"}:
        return False
    return None


def strip_html(value):
    """Turn the HTML used in Grants.gov descriptions into plain text."""
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_details(payload, opportunity_id):
    """Normalize a fetchOpportunity JSON payload (synopsis or forecast)."""
    if not isinstance(payload, dict):
        raise OpportunityDetailsError("Unexpected Grants.gov details format.")
    if str(payload.get("errorcode")) != "0":
        raise OpportunityDetailsError(
            str(payload.get("msg") or "Grants.gov could not provide opportunity details.")
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise OpportunityDetailsError("Grants.gov details response had no data.")

    is_forecast = not isinstance(data.get("synopsis"), dict) and isinstance(data.get("forecast"), dict)
    section = data.get("forecast") if is_forecast else data.get("synopsis")
    section = section if isinstance(section, dict) else {}

    applicant_types = []
    for item in section.get("applicantTypes") or []:
        if isinstance(item, dict):
            applicant_types.append({
                "id": str(item.get("id") or "").strip(),
                "description": str(item.get("description") or "").strip(),
            })

    description = section.get("forecastDesc") if is_forecast else section.get("synopsisDesc")
    close_text = (
        section.get("estApplicationResponseDateStr") or section.get("estApplicationResponseDate")
        if is_forecast else section.get("responseDateStr") or section.get("responseDate")
    )
    return {
        "id": str(opportunity_id),
        "is_forecast": is_forecast,
        "award_floor": _amount(section.get("awardFloor")),
        "award_ceiling": _amount(section.get("awardCeiling")),
        "estimated_funding": _amount(section.get("estimatedFunding")),
        "number_of_awards": _amount(section.get("numberOfAwards")),
        "cost_sharing": _bool(section.get("costSharing")),
        "applicant_types": applicant_types,
        "eligibility_text": strip_html(section.get("applicantEligibilityDesc")),
        "description": strip_html(description),
        "close_date_text": str(close_text).strip() if close_text else None,
        "source_url": grant_url(opportunity_id),
    }


def fetch_opportunity_details(opportunity_id, timeout=20):
    """Fetch and normalize official details for one opportunity id."""
    try:
        identifier = int(str(opportunity_id).strip())
    except (TypeError, ValueError) as exc:
        raise OpportunityDetailsError(f"Invalid opportunity id: {opportunity_id!r}") from exc
    try:
        response = requests.post(DETAIL_API_URL, json={"opportunityId": identifier}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise OpportunityDetailsError(f"Details request failed: {exc}") from exc
    except ValueError as exc:
        raise OpportunityDetailsError("Details response was not valid JSON.") from exc
    return parse_details(payload, identifier)
