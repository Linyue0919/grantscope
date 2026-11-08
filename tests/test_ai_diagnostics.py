"""Offline tests for credential-safe Azure OpenAI diagnostics (no network, no real credentials).

Run: python -m unittest discover -s tests -v
"""
import json
import socket
import unittest
from types import SimpleNamespace

from services.ai_diagnostics import (
    classify_exception, format_report, redact, secrets_from_config, validate_config_format,
)
from services.ai_matching import AzureFitEvaluator

FAKE = {"endpoint": "https://grantscope-team07.openai.azure.com/", "api_key": "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6",
        "deployment": "grantscope-gpt4o", "api_version": "2024-10-21"}
SECRETS = secrets_from_config(FAKE)


# Duck-typed stand-ins for openai SDK exceptions (class names match the SDK).
class APIStatusError(Exception):
    def __init__(self, message, status_code, body=None, headers=None, request_id=None):
        super().__init__(message)
        self.status_code, self.body, self.request_id = status_code, body, request_id
        self.response = SimpleNamespace(status_code=status_code, headers=headers or {})


class NotFoundError(APIStatusError):
    pass


class AuthenticationError(APIStatusError):
    pass


class APIConnectionError(Exception):
    pass


class APITimeoutError(APIConnectionError):
    pass


def no_secret(testcase, text):
    for secret in ("a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6", "grantscope-team07", "openai.azure.com"):
        testcase.assertNotIn(secret, text)


class ClassifyTests(unittest.TestCase):
    def test_deployment_not_found(self):
        exc = NotFoundError(
            "Error code: 404 - The API deployment for this resource does not exist at "
            "https://grantscope-team07.openai.azure.com/openai/deployments/x",
            404, body={"code": "DeploymentNotFound", "message": "The API deployment for this resource does not "
                       "exist. Resource grantscope-team07."}, headers={"apim-request-id": "7f3e-11aa"})
        info = classify_exception(exc, SECRETS)
        self.assertEqual(info["exception"], "NotFoundError")
        self.assertEqual(info["http_status"], 404)
        self.assertEqual(info["error_code"], "DeploymentNotFound")
        self.assertEqual(info["request_id"], "7f3e-11aa")
        self.assertIn("deployment name", info["hint"])
        no_secret(self, json.dumps(info))

    def test_authentication_error_with_key_in_message(self):
        exc = AuthenticationError(f"Access denied due to invalid subscription key {FAKE['api_key']}", 401,
                                  body={"error": {"code": "401", "message": "Access denied due to invalid "
                                                  "subscription key or wrong API endpoint."}})
        info = classify_exception(exc, SECRETS)
        self.assertEqual(info["http_status"], 401)
        self.assertIn("subscription key", info["hint"].lower() + info["message"].lower())
        no_secret(self, format_report(info))

    def test_connection_error_reports_cause_chain(self):
        try:
            try:
                raise socket.gaierror(-2, "Name or service not known")
            except socket.gaierror as inner:
                raise APIConnectionError("Connection error.") from inner
        except APIConnectionError as exc:
            info = classify_exception(exc, SECRETS)
        self.assertIsNone(info["http_status"])
        self.assertIn("gaierror", info["cause"])
        self.assertIn("DNS", info["hint"])

    def test_timeout(self):
        info = classify_exception(APITimeoutError("Request timed out."), SECRETS)
        self.assertEqual(info["exception"], "APITimeoutError")
        self.assertIn("respond in time", info["hint"])

    def test_rate_limit_and_server_errors(self):
        self.assertIn("Rate limited", classify_exception(APIStatusError("x", 429), SECRETS)["hint"])
        self.assertIn("internal error", classify_exception(APIStatusError("x", 502), SECRETS)["hint"])

    def test_inner_error_code(self):
        exc = APIStatusError("bad", 400, body={"error": {"code": "BadRequest",
                                                        "innererror": {"code": "unsupported_api_version"}}})
        info = classify_exception(exc, SECRETS)
        self.assertEqual(info["error_code"], "BadRequest / unsupported_api_version")
        self.assertIn("API version", info["hint"])


class RedactionTests(unittest.TestCase):
    def test_redacts_key_host_urls_and_tokens(self):
        text = (f"key={FAKE['api_key']} host grantscope-team07.openai.azure.com url "
                "https://other.example.com/path Authorization: Bearer abc.def token ZXhhbXBsZXRva2VuMTIzNDU2Nzg5MA")
        out = redact(text, SECRETS)
        no_secret(self, out)
        self.assertNotIn("other.example.com", out)
        self.assertNotIn("ZXhhbXBsZXRva2VuMTIzNDU2Nzg5MA", out)
        self.assertNotIn("abc.def", out)

    def test_redact_handles_none_and_long_text(self):
        self.assertEqual(redact(None), "")
        self.assertLessEqual(len(redact("x " * 1000)), 300)


class FormatValidationTests(unittest.TestCase):
    def test_good_config(self):
        self.assertEqual(validate_config_format(FAKE), [])

    def test_common_mistakes_without_echoing_values(self):
        bad = dict(FAKE, endpoint="https://grantscope-team07.openai.azure.com/openai/deployments/grantscope-gpt4o",
                   api_key=" <your-key>\n", api_version="latest")
        warnings = validate_config_format(bad)
        joined = " ".join(warnings)
        self.assertIn("path", joined)
        self.assertIn("whitespace", joined)
        self.assertIn("placeholder", joined)
        self.assertIn("API version", joined)
        self.assertNotIn("grantscope-team07", joined)


class AppErrorReportingTests(unittest.TestCase):
    def test_app_error_includes_status_and_code_but_no_secrets(self):
        exc = NotFoundError(f"deployment missing at {FAKE['endpoint']}", 404, body={"code": "DeploymentNotFound"})

        class Client:
            chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(exc)))

        profile = {"name": "DEQ", "short_name": "DEQ", "plan_url": "u",
                   "goals": [{"goal_id": "g1", "label": "Goal 1", "quote": "Protect water", "page": 1}]}
        record = {"id": "1", "title": "Water grant"}
        out = AzureFitEvaluator(FAKE, client=Client())(record, profile, {"description": "water"})
        self.assertEqual(out["status"], "error")
        self.assertIn("HTTP 404", out["errors"][0])
        self.assertIn("DeploymentNotFound", out["errors"][0])
        no_secret(self, json.dumps(out))


if __name__ == "__main__":
    unittest.main()


class ValidationScriptOfflineTests(unittest.TestCase):
    """Exercise scripts/validate_ai_integration.py reporting with a fake client (no credentials)."""

    def test_summarize_and_evidence_check_with_fake_ai(self):
        import contextlib
        import io
        from datetime import date

        from scripts.validate_ai_integration import check_evidence, summarize
        from services.agency_profiles import get_agency_profile
        from services.ai_eligibility import AzureEligibilityEvaluator
        from services.match_engine import MatchSettings, run_matching

        deq = get_agency_profile("DEQ")
        notes = "Applications are accepted from regional fishery management councils established under the Act."
        det = {"applicant_types": [{"id": "25", "description": "Others"}], "eligibility_text": notes,
               "award_ceiling": 500000.0, "award_floor": None, "estimated_funding": None, "number_of_awards": None,
               "description": "Funds wastewater treatment upgrades for small towns.", "close_date_text": None,
               "cost_sharing": False, "attachments": []}
        hits = [{"id": "1", "title": "Drinking Water Grants", "agency": "EPA", "closeDate": "01/31/2027",
                 "oppStatus": "posted"}]
        fit_reply = json.dumps({"relevance": 70, "goal_ids": ["deq-1"],
                                "evidence": [{"source_id": "D", "quote": "wastewater treatment upgrades"}],
                                "explanation": "Supports wastewater upgrades."})
        elig_reply = json.dumps({"verdict": "likely_ineligible", "reasoning": "Only fishery councils may apply.",
                                 "quote": "accepted from regional fishery management councils"})

        class Client:
            def __init__(self, reply):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])))

        cache = {"1": det}
        kwargs = dict(search_fn=lambda k, r: hits, details_fn=lambda g: det, details_cache=cache,
                      today=date(2026, 11, 7))
        off = run_matching(deq, MatchSettings(), **kwargs)
        on = run_matching(deq, MatchSettings(), **kwargs,
                          ai_evaluator=AzureFitEvaluator(FAKE, client=Client(fit_reply)),
                          eligibility_evaluator=AzureEligibilityEvaluator(FAKE, client=Client(elig_reply)))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            problems = summarize("DEQ", off, on, deq, cache)
        self.assertEqual(problems, [])
        self.assertIn("Eligibility changed by AI: 1", out.getvalue())
        checked, problems = check_evidence(on, deq, cache)
        self.assertEqual((checked, problems), (2, []))
        no_secret(self, out.getvalue())
