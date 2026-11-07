"""Offline tests for the results-first Search presentation helpers."""
import unittest

from modules.search import (
    apply_search_filters,
    decision_csv,
    eligibility_summary,
    relevance_summary,
    sort_results,
)
from services.agency_directory import AGENCIES


class SearchPresentationTests(unittest.TestCase):
    def test_unknown_eligibility_is_needs_review(self):
        summary = eligibility_summary({}, "Department of Environmental Quality")
        self.assertEqual(summary["status"], "Needs Review")
        self.assertFalse(summary["excluded"])
        self.assertIn("not been loaded", summary["explanation"])

    def test_excluded_opportunity_is_explicit_and_actionable(self):
        summary = eligibility_summary(
            {
                "description": (
                    "Eligible applicants are federally recognized Tribes and "
                    "intertribal consortia."
                )
            },
            "Department of Environmental Quality",
        )
        self.assertEqual(summary["status"], "Ineligible")
        self.assertTrue(summary["excluded"])
        self.assertIn("Do not apply", summary["next_action"])

    def test_relevance_summary_does_not_claim_eligibility(self):
        summary = relevance_summary({
            "match_score": 17,
            "match_reasons": [
                {"goal": "Strengthen environmental infrastructure"},
            ],
        })
        self.assertIn("17/100", summary)
        self.assertIn("infrastructure", summary)
        self.assertNotIn("eligible", summary.lower())

    def test_excluded_results_are_deprioritized_but_retained(self):
        grants = [{"id": 1, "_excluded": True}, {"id": 2, "_excluded": False}]
        ordered = sort_results(grants, "Recommended match")
        self.assertEqual([grant["id"] for grant in ordered], [2, 1])

    def test_all_33_agency_options_are_preserved(self):
        self.assertEqual(len(AGENCIES), 33)

    def test_sorting_by_award_ceiling_and_closing_date(self):
        grants = [
            {"id": 1, "_award_ceiling": 100, "closeDate": "12/31/2026"},
            {"id": 2, "_award_ceiling": 500, "closeDate": "11/30/2026"},
        ]
        self.assertEqual(
            [grant["id"] for grant in sort_results(grants, "Award ceiling: high to low")],
            [2, 1],
        )
        self.assertEqual(
            [grant["id"] for grant in sort_results(grants, "Closing date: soonest")],
            [2, 1],
        )
        excluded = [dict(grants[1], _excluded=True), dict(grants[0], _excluded=False)]
        self.assertEqual(
            [grant["id"] for grant in sort_results(excluded, "Award ceiling: high to low")],
            [1, 2],
        )

    def test_filters_status_agency_goal_and_award_ceiling(self):
        grants = [
            {
                "id": 1,
                "agency": "EPA",
                "oppStatus": "posted",
                "_eligibility_status": "Needs Review",
                "_award_ceiling": 100000,
                "match_reasons": [{"goal": "Water quality"}],
            },
            {
                "id": 2,
                "agency": "USDA",
                "oppStatus": "forecasted",
                "_eligibility_status": "Ineligible",
                "_award_ceiling": 50000,
                "match_reasons": [{"goal": "Agriculture"}],
            },
        ]
        result = apply_search_filters(
            grants,
            agency_filter="EPA",
            statuses={"Posted"},
            eligibility_filter="Needs Review",
            goal_filter="Water quality",
            min_ceiling=75000,
        )
        self.assertEqual([grant["id"] for grant in result], [1])

    def test_confirmed_exclusion_remains_visible_under_funding_filter(self):
        grants = [{
            "id": 3,
            "agency": "EPA",
            "_eligibility_status": "Ineligible",
            "_award_ceiling": None,
            "match_reasons": [],
        }]
        result = apply_search_filters(grants, min_ceiling=1000000)
        self.assertEqual([grant["id"] for grant in result], [3])

    def test_csv_export_contains_decision_and_distinguishes_amounts(self):
        content = decision_csv(
            [{
                "id": 7,
                "title": "Water grant",
                "agency": "EPA",
                "oppStatus": "posted",
                "closeDate": "12/31/2026",
                "_award_ceiling": 250000,
                "_total_funding": 1000000,
                "match_score": 17,
                "match_reasons": [],
                "_eligibility_status": "Needs Review",
            }],
            {"7": {"decision": "Maybe", "notes": "Verify NOFO"}},
        )
        self.assertIn("award_ceiling", content)
        self.assertIn("total_program_funding", content)
        self.assertIn("Maybe", content)
        self.assertIn("Verify NOFO", content)


if __name__ == "__main__":
    unittest.main()
