"""Regression tests for two observed GrantScope false positives.

Run: python -m unittest discover -s tests -v
"""
import unittest
from services.matching import rank_grants
from services.eligibility import screen_eligibility


DEQ = "Department of Environmental Quality"


class EvaluationRegressionTests(unittest.TestCase):
    def test_recovery_land_does_not_match_disaster_recovery(self):
        grant = {
            "title": "F26AS00030 Cooperative Endangered Species Conservation Fund: Recovery Land Acquisition Grant Program",
            "id": 123,
        }
        result = rank_grants([grant], DEQ)[0]
        self.assertEqual(result["match_score"], 0)
        self.assertEqual(result["match_reasons"], [])

    def test_disaster_recovery_matches_correct_goal(self):
        grant = {"title": "Disaster Recovery and Flood Resilience Program", "id": 124}
        result = rank_grants([grant], DEQ)[0]
        self.assertGreater(result["match_score"], 0)
        self.assertTrue(any("disaster recovery" in r["keywords"] for r in result["match_reasons"]))

    def test_water_research_institute_exclusion(self):
        details = {
            "applicant_types": ["Others"],
            "eligibility_description": (
                "Only Water Resources Research Institutes established under the "
                "Water Resources Research Act of 1984 are eligible to apply."
            ),
        }
        result = screen_eligibility(details, DEQ)
        self.assertEqual(result["status"], "Ineligible")
        self.assertIn("Water Resources Research Institutes", result["evidence"])

    def test_no_unjustified_positive_eligibility(self):
        details = {
            "applicant_types": ["State governments"],
            "eligibility_description": "State governments may apply subject to additional restrictions.",
        }
        self.assertEqual(screen_eligibility(details, DEQ)["status"], "Needs Review")

    def test_no_details_means_review(self):
        self.assertEqual(screen_eligibility({}, DEQ)["status"], "Needs Review")


if __name__ == "__main__":
    unittest.main()
