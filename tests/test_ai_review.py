"""Offline tests for opt-in Azure review guardrails; no network calls."""
import unittest
from services.ai_review import review_grant, AIReviewError


class AIReviewGuardrailTests(unittest.TestCase):
    def test_missing_secrets_prevents_request(self):
        with self.assertRaises(AIReviewError):
            review_grant("Agency", {"goals": [{"text": "Water", "page": 1}]},
                         {"title": "Grant"}, {"description": "Water work"}, {})

    def test_missing_official_details_prevents_request(self):
        config = {
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_DEPLOYMENT": "test",
            "AZURE_OPENAI_API_KEY": "local-placeholder",
            "AZURE_OPENAI_API_VERSION": "2024-10-21",
        }
        with self.assertRaises(AIReviewError):
            review_grant("Agency", {"goals": [{"text": "Water", "page": 1}]},
                         {"title": "Grant"}, {}, config)

    def test_unverified_agency_prevents_request(self):
        config = {
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_DEPLOYMENT": "test",
            "AZURE_OPENAI_API_KEY": "local-placeholder",
            "AZURE_OPENAI_API_VERSION": "2024-10-21",
        }
        with self.assertRaises(AIReviewError):
            review_grant("Agency", None, {"title": "Grant"},
                         {"description": "Water work"}, config)


if __name__ == "__main__":
    unittest.main()
