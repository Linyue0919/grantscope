"""Regression tests for two observed GrantScope false positives.

Run: python -m unittest discover -s tests -v
"""
import unittest
from services.matching import rank_grants
from services.eligibility import screen_eligibility
from services.grants_api import plain_official_text


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

    def test_official_detail_description_contributes_to_match(self):
        grant = {"id": 777, "title": "Infrastructure Assistance"}
        without_details = rank_grants([grant], DEQ)[0]
        with_details = rank_grants(
            [grant], DEQ,
            detail_cache={"777": {"description": "Drinking water and wastewater infrastructure improvements"}},
        )[0]
        self.assertEqual(without_details["match_score"], 0)
        self.assertGreater(with_details["match_score"], 0)

    def test_unverified_agency_is_unscored_not_zero(self):
        grant = {"id": 778, "title": "Public Safety Grants"}
        result = rank_grants([grant], "Department of Public Safety")[0]
        self.assertIsNone(result["match_score"])

    def test_tribal_only_nofO_excludes_deq_direct_application(self):
        details = {
            "applicant_types": [],
            "description": (
                "Eligible applicants to this Notice of Funding Opportunity (NOFO) "
                "are federally recognized Tribes and intertribal consortia that "
                "meet the eligibility requirements described in Section 2.A."
            ),
        }
        result = screen_eligibility(details, DEQ)
        self.assertEqual(result["status"], "Ineligible")
        self.assertIn("federally recognized Tribes", result["evidence"])

    def test_incidental_tribal_reference_does_not_exclude_deq(self):
        details = {
            "applicant_types": ["State governments"],
            "description": "Projects may benefit Tribes and intertribal consortia.",
        }
        self.assertEqual(screen_eligibility(details, DEQ)["status"], "Needs Review")

    def test_html_is_plain_text_not_rendered_markup(self):
        text = plain_official_text("<p>Eligible applicants are Tribes &amp; consortia.</p><p>See Section 2.A.</p>")
        self.assertEqual(text, "Eligible applicants are Tribes & consortia. See Section 2.A.")

    def test_no_details_means_review(self):
        self.assertEqual(screen_eligibility({}, DEQ)["status"], "Needs Review")


if __name__ == "__main__":
    unittest.main()
