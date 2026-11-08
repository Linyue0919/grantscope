"""Opt-in Azure OpenAI connectivity smoke test.

Run manually with:
    python scripts/azure_openai_smoke.py
"""
import sys
from urllib.parse import quote

import requests
import streamlit as st


EXPECTED_DEPLOYMENT = "grantscope-gpt4o"


def run_smoke_test():
    """Send one minimal request and return a sanitized result message."""
    try:
        endpoint = str(st.secrets["AZURE_OPENAI_ENDPOINT"]).rstrip("/")
        api_key = str(st.secrets["AZURE_OPENAI_API_KEY"])
        deployment = str(st.secrets["AZURE_OPENAI_DEPLOYMENT"])
        api_version = str(st.secrets["AZURE_OPENAI_API_VERSION"])
    except (KeyError, FileNotFoundError, TypeError, ValueError):
        return False, "Azure OpenAI smoke test failed: required Streamlit secrets are unavailable."

    if deployment != EXPECTED_DEPLOYMENT:
        return False, "Azure OpenAI smoke test failed: configured deployment is not grantscope-gpt4o."
    if not endpoint or not api_key or api_key == "PASTE_YOUR_KEY_HERE":
        return False, "Azure OpenAI smoke test failed: API credentials are not configured."

    url = (
        f"{endpoint}/openai/deployments/{quote(deployment, safe='')}"
        f"/chat/completions?api-version={quote(api_version, safe='')}"
    )
    try:
        response = requests.post(
            url,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 2,
                "temperature": 0,
            },
            timeout=30,
        )
        response.raise_for_status()
    except requests.Timeout:
        return False, "Azure OpenAI smoke test failed: request timed out."
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        return False, f"Azure OpenAI smoke test failed: HTTP status {status}."
    except requests.RequestException:
        return False, "Azure OpenAI smoke test failed: request could not be completed."

    return True, "Azure OpenAI connectivity smoke test succeeded."


if __name__ == "__main__":
    success, message = run_smoke_test()
    print(message)
    sys.exit(0 if success else 1)
