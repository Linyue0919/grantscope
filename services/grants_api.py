
import requests

API_URL = "https://api.grants.gov/v1/api/search2"


def get_grants(keyword="water", rows=10):
    payload = {
        "keyword": keyword,
        "rows": rows,
        "oppStatuses": "forecasted|posted"
    }

    response = requests.post(
        API_URL,
        json=payload,
        timeout=30
    )

    response.raise_for_status()
    result = response.json()

    if result.get("errorcode") != 0:
        raise RuntimeError(
            result.get("msg", "Grants.gov API error")
        )

    data = result.get("data") or {}
    return data.get("oppHits", [])
