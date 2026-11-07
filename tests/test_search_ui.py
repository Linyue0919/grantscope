"""Offline tests for the results-first Search presentation helpers."""
import unittest

from modules.search import eligibility_summary, relevance_summary, _sort_excluded_last


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
        ordered = _sort_excluded_last(grants)
        self.assertEqual([grant["id"] for grant in ordered], [2, 1])


if __name__ == "__main__":
    unittest.main()
