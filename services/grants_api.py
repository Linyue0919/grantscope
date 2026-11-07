"""Grants.gov opportunity search adapter.

The search endpoint returns summary records, not complete eligibility or award
details. Never treat a search hit as proof of agency eligibility.
"""
import requests

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
