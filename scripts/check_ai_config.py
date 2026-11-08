"""Diagnose the Azure OpenAI configuration WITHOUT revealing credentials.

Reads the same settings as the app (environment variables first, then the
gitignored .streamlit/secrets.toml) and runs staged checks:

  1. settings present        4. DNS lookup of the endpoint host
  2. setting formats         5. plain chat call (no JSON mode)
  3. openai package          6. JSON-mode call (used by GrantScope)
                             7. optional: NOAA eligibility sample (--sample)

Output is sanitized: the API key, endpoint URL, host and resource name are never
printed (the endpoint is masked), and error messages are redacted. Failures show
exception type, HTTP status, Azure error code, request id, cause and a hint.
No raw tracebacks are printed. Safe to paste the output into a chat or ticket.

Usage:
  python scripts/check_ai_config.py
  python scripts/check_ai_config.py --sample

Exit codes: 0 OK, 2 not configured, 3 config/DNS problem, 4 auth/permission,
5 deployment/API version not found, 6 other failure.
"""
import json
import os
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.ai_diagnostics import (  # noqa: E402
    classify_exception, format_report, redact, secrets_from_config, validate_config_format,
)
from services.ai_matching import describe_config, load_ai_config  # noqa: E402

SECRETS = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
KEYS = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION")
NOAA_DETAILS = {
    "applicant_types": [{"id": "25", "description": "Others (see text field entitled \"Additional Information on "
                                                    "Eligibility\" for clarification)"}],
    "eligibility_text": (
        "Eligible applicants are: Institutions of higher education; Other nonprofits; Commercial organizations; "
        "Local and federally recognized Tribal governments; Federal agencies that possess the statutory authority "
        "to receive transfers of funds. Foreign or international institutions are not eligible to apply."),
}


def load_settings():
    """Return (settings, {key: source}). Values are never printed."""
    settings, sources = {}, {}
    for key in KEYS:
        if os.environ.get(key):
            settings[key], sources[key] = os.environ[key], "environment"
    if SECRETS.exists():
        try:
            import tomllib
            with open(SECRETS, "rb") as fh:
                secrets = tomllib.load(fh)
        except Exception as exc:  # noqa: BLE001 - never echo file contents
            print(f"[1] secrets.toml could not be parsed ({type(exc).__name__}); check TOML syntax "
                  "(quotes around values, one KEY = \"value\" per line).")
            secrets = {}
        for key in KEYS:
            if key not in settings and secrets.get(key):
                settings[key], sources[key] = str(secrets[key]), ".streamlit/secrets.toml"
    return settings, sources


def exit_code_for(info):
    status = info.get("http_status")
    if status in (401, 403):
        return 4
    if status == 404:
        return 5
    if info["exception"] in ("APIConnectionError", "APITimeoutError") or "gaierror" in (info.get("cause") or ""):
        return 3
    return 6


def fail(stage, exc, secret_values):
    info = classify_exception(exc, secret_values)
    print(f"[{stage}] FAILED")
    print(format_report(info))
    return exit_code_for(info)


def main():
    settings, sources = load_settings()
    print("[1] Settings present:")
    for key in KEYS:
        where = sources.get(key)
        default = " (will use default)" if key in KEYS[2:] and not where else ""
        print(f"      {key:<26} {'yes, from ' + where if where else 'no'}{default}")
    config = load_ai_config(settings)
    if not config:
        print("    Missing endpoint and/or key. Add them to .streamlit/secrets.toml (see secrets.toml.example).")
        return 2
    secret_values = secrets_from_config(config)
    info = describe_config(config)
    print(f"    endpoint (masked): {info['endpoint']} | deployment: {info['deployment']} | "
          f"api_version: {info['api_version']} | api_key: {info['api_key']}")

    warnings = validate_config_format(config)
    print("[2] Format checks:", "OK" if not warnings else "")
    for warning in warnings:
        print(f"      - {warning}")

    try:
        import openai
        from openai import AzureOpenAI
        print(f"[3] openai package: OK (version {openai.__version__})")
    except ImportError as exc:
        print(f"[3] openai package: MISSING ({type(exc).__name__}). Run: pip install -r requirements.txt")
        return 6

    host = config["endpoint"].split("://", 1)[-1].split("/")[0]
    try:
        socket.getaddrinfo(host, 443)
        print("[4] DNS lookup of endpoint host: OK")
    except OSError as exc:
        print(f"[4] DNS lookup of endpoint host: FAILED ({type(exc).__name__}). "
              "The host name is wrong or DNS/network is unavailable.")
        return 3

    try:
        client = AzureOpenAI(azure_endpoint=config["endpoint"], api_key=config["api_key"],
                             api_version=config["api_version"], max_retries=0, timeout=20)
    except Exception as exc:  # noqa: BLE001
        return fail("5", exc, secret_values)

    messages = [{"role": "user", "content": "Reply with the single word OK."}]
    start = time.time()
    try:
        response = client.chat.completions.create(model=config["deployment"], messages=messages,
                                                  max_tokens=5, temperature=0)
        model = redact(getattr(response, "model", "") or "unknown", secret_values)
        print(f"[5] Plain chat call: OK ({time.time() - start:.1f}s, model reported: {model})")
    except Exception as exc:  # noqa: BLE001
        return fail("5", exc, secret_values)

    start = time.time()
    try:
        response = client.chat.completions.create(
            model=config["deployment"], max_tokens=10, temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": 'Reply with the JSON object {"ok": true}.'},
                      {"role": "user", "content": "ping"}])
        ok = json.loads(response.choices[0].message.content).get("ok") is True
        print(f"[6] JSON-mode call: {'OK' if ok else 'unexpected reply'} ({time.time() - start:.1f}s)")
    except Exception as exc:  # noqa: BLE001
        code = fail("6", exc, secret_values)
        print("    Plain calls work but JSON mode failed: use a newer AZURE_OPENAI_API_VERSION (e.g. 2024-10-21).")
        return code

    if "--sample" in sys.argv:
        from services.ai_eligibility import AzureEligibilityEvaluator
        evaluator = AzureEligibilityEvaluator(config, client=client)
        record = {"title": "Climate Program Office FY 2027 (NOAA example)"}
        profile = {"name": "Department of Environmental Quality", "applicant_categories": ["State governments"]}
        result = evaluator(record, profile, NOAA_DETAILS)
        print(f"[7] NOAA eligibility sample: status={result['status']}")
        if result["status"] == "ok":
            print(f"      verdict  : {result['verdict']} (expected: likely_ineligible)")
            print(f"      reasoning: {redact(result['reasoning'], secret_values)}")
            print(f"      quote    : “{result['quote']}”")
        else:
            print(f"      details  : {redact('; '.join(result.get('errors') or []), secret_values)}")
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 - last resort: never print a raw traceback
        print("Unexpected failure in the diagnostic script:")
        print(format_report(classify_exception(exc)))
        sys.exit(6)
