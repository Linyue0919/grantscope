"""Grants.gov opportunity search adapter.

The search endpoint returns summary records, not complete eligibility or award
details. Never treat a search hit as proof of agency eligibility.
"""
import requests
from html import unescape
from html.parser import HTMLParser


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "li", "div"):
            self.parts.append(" ")


def plain_official_text(value):
    """Remove HTML markup from Grants.gov text without rendering it as HTML."""
    parser = _TextOnly()
    parser.feed(str(value or ""))
    parser.close()
    return " ".join(unescape("".join(parser.parts)).split())

API_URL = "https://api.grants.gov/v1/api/search2"


class GrantsAPIError(RuntimeError):
    """An actionable error while fetching or validating Grants.gov data."""


def get_grants(keyword="water", rows=100):
    keyword = str(keyword).strip()
    if not keyword:
        return []
    rows = max(1, min(int(rows), 100))
    payload = {
        "keyword": keyword,
        "rows": rows,
        "oppStatuses": "forecasted|posted",
    }
    try:
        response = requests.post(API_URL, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
    except requests.Timeout as exc:
        raise GrantsAPIError("Grants.gov timed out. Please retry.") from exc
    except requests.RequestException as exc:
        raise GrantsAPIError(f"Grants.gov request failed: {exc}") from exc
    except ValueError as exc:
        raise GrantsAPIError("Grants.gov returned an invalid JSON response.") from exc

    if not isinstance(result, dict):
        raise GrantsAPIError("Unexpected Grants.gov response format.")
    error_code = result.get("errorcode")
    if error_code is not None and str(error_code) != "0":
        raise GrantsAPIError(str(result.get("msg") or "Grants.gov reported an error."))
    data = result.get("data")
    if not isinstance(data, dict):
        raise GrantsAPIError("Grants.gov response did not contain opportunity data.")
    hits = data.get("oppHits")
    if not isinstance(hits, list):
        raise GrantsAPIError("Grants.gov response did not contain an opportunity list.")

    seen = set()
    unique = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        identifier = str(hit.get("id") or hit.get("number") or "").strip()
        key = identifier or (str(hit.get("title")), str(hit.get("closeDate")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return unique


DETAIL_API_URL = "https://api.grants.gov/v1/api/fetchOpportunity"


def _amount(value):
    """Convert an official amount to a number, or None if unavailable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        raw = str(value).replace(",", "").replace("$", "").strip()
        return float(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _first_amount(record, *keys):
    for key in keys:
        amount = _amount(record.get(key))
        if amount is not None:
            return amount
    return None


def get_grant_details(opportunity_id):
    """Fetch official details on demand, rather than 100 API requests at once."""
    try:
        identifier = int(opportunity_id)
    except (TypeError, ValueError) as exc:
        raise GrantsAPIError("Invalid opportunity identifier.") from exc
    try:
        response = requests.post(
            DETAIL_API_URL, json={"opportunityId": identifier}, timeout=30
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise GrantsAPIError(f"Opportunity details request failed: {exc}") from exc
    except ValueError as exc:
        raise GrantsAPIError("Opportunity details were not valid JSON.") from exc
    if not isinstance(payload, dict) or str(payload.get("errorcode")) != "0":
        raise GrantsAPIError(
            str(payload.get("msg") if isinstance(payload, dict) else "")
            or "Grants.gov could not provide opportunity details."
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise GrantsAPIError("Missing official opportunity detail data.")
    synopsis = data.get("synopsis") or data.get("forecast") or {}
    if not isinstance(synopsis, dict):
        synopsis = {}
    applicant_types = synopsis.get("applicantTypes") or []
    types = [
        str(item.get("description", "")).strip()
        for item in applicant_types if isinstance(item, dict)
    ]
    return {
        "award_floor": _amount(synopsis.get("awardFloor")),
        "award_ceiling": _amount(synopsis.get("awardCeiling")),
        "total_funding": _first_amount(
            synopsis, "estimatedFunding", "estimatedFundingAmount",
            "totalFunding", "totalFundingAmount",
        ),
        "applicant_types": [t for t in types if t],
        "eligibility_description": plain_official_text(synopsis.get("applicantEligibilityDesc")),
        "description": plain_official_text(synopsis.get("synopsisDesc") or synopsis.get("forecastDesc")),
        "detail_source_url": f"https://www.grants.gov/search-results-detail/{identifier}",
    }
