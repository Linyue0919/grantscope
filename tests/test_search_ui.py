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
from services.calendar_export import grants_to_ics
from services.grant_store import LocalGrantStore
from services.discovery import (
    AIRecommendationCache,
    DashboardShortlistCache,
    cached_semantic_results,
    classify_recommendation,
    classify_recommendations,
    diversified_retrieval_queries,
    generate_dashboard_shortlist,
    get_cached_ai_shortlist,
    prepare_ai_recommendations,
)
from tempfile import TemporaryDirectory


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

    def test_persistent_store_namespaces_and_removes_records(self):
        with TemporaryDirectory() as directory:
            store = LocalGrantStore(f"{directory}/grants.json")
            store.save("Agency A", "7", {
                "title": "Official title", "decision": "Pursue", "notes": "Review"
            })
            store.save("Agency B", "7", {"title": "Other title"})
            self.assertEqual(store.get("Agency A", "7")["decision"], "Pursue")
            self.assertEqual(len(store.list_records()), 2)
            store.save("Agency A", "7", {"title": "Do not replace"})
            self.assertEqual(store.get("Agency A", "7")["title"], "Official title")
            self.assertTrue(store.remove("Agency A", "7"))
            self.assertIsNone(store.get("Agency A", "7"))
            self.assertEqual(len(store.list_records()), 1)

    def test_calendar_export_skips_missing_or_invalid_deadlines(self):
        content = grants_to_ics([
            {
                "agency": "DEQ", "opportunity_id": "1", "title": "Water",
                "close_date": "12/31/2026",
                "official_url": "https://www.grants.gov/opportunity/1",
            },
            {"agency": "DEQ", "opportunity_id": "2", "title": "Unknown"},
            {"agency": "DEQ", "opportunity_id": "3", "title": "Invalid", "close_date": "soon"},
        ])
        self.assertIn("DTSTART;VALUE=DATE:20261231", content)
        self.assertIn("SUMMARY:Water", content)
        self.assertNotIn("SUMMARY:Unknown", content)
        self.assertNotIn("SUMMARY:Invalid", content)

    def test_dashboard_shortlist_uses_verified_goals_and_caches_official_evidence(self):
        grants = [
            {"id": 10, "title": "Water grant", "closeDate": "12/31/2026"},
            {"id": 11, "title": "Other grant", "closeDate": "12/31/2026"},
        ]
        def fake_details(identifier):
            return {
                "description": "Official water opportunity",
                "eligibility_description": "State governments may apply.",
                "applicant_types": ["State governments"],
                "award_ceiling": 100000,
                "detail_source_url": f"https://example/{identifier}",
            }
        with TemporaryDirectory() as directory:
            cache = DashboardShortlistCache(f"{directory}/dashboard.json")
            result = generate_dashboard_shortlist(
                "Department of Environmental Quality",
                cache=cache,
                fetch_grants=lambda query, rows: grants,
                fetch_details=fake_details,
                limit=2,
            )
            self.assertEqual(len(result["records"]), 2)
            self.assertEqual(cache.get("Department of Environmental Quality"), result)
            self.assertEqual(result["records"][0]["official_url"], "https://example/10")

    def test_dashboard_cache_empty_state_is_not_an_automatic_refresh(self):
        with TemporaryDirectory() as directory:
            cache = DashboardShortlistCache(f"{directory}/dashboard.json")
            self.assertIsNone(cache.get("Department of Environmental Quality"))

    def test_dashboard_ai_shortlist_is_explicitly_unavailable_without_cached_ai_results(self):
        with TemporaryDirectory() as directory:
            cache = DashboardShortlistCache(f"{directory}/dashboard.json")
            self.assertEqual(
                get_cached_ai_shortlist("Department of Environmental Quality", cache)["status"],
                "pending",
            )
            cache.save("Department of Environmental Quality", [], "now")
            result = get_cached_ai_shortlist("Department of Environmental Quality", cache)
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["records"], [])

    def test_ai_recommendations_use_diversified_queries_and_persist(self):
        profile = {
            "goals": [
                {"text": "Water quality", "terms": ["water", "wastewater"]},
                {"text": "Flood resilience", "terms": ["flood", "resilience"]},
            ]
        }
        queries = diversified_retrieval_queries(profile, "Community health clinic")
        self.assertGreaterEqual(len(queries), 3)
        self.assertEqual(len(queries), len(set(queries)))
        calls = []
        grants = [{"id": "1", "title": "Opportunity"}]

        def fetch_grants(query, rows):
            calls.append((query, rows))
            return grants

        def evaluate(*args, **kwargs):
            return {
                "status": "Evaluated",
                "semantic_relevance_score": 88,
                "strategic_relevance_score": 80,
                "project_relevance_score": 88,
                "evidence_grounded_explanation": "Official evidence supports the project.",
            }

        with TemporaryDirectory() as directory:
            cache = AIRecommendationCache(f"{directory}/ai.json")
            result = prepare_ai_recommendations(
                "Department of Environmental Quality",
                project_description="Community health clinic",
                cache=cache,
                fetch_grants=fetch_grants,
                fetch_details=lambda identifier: {"description": "Official opportunity"},
                evaluate=evaluate,
                config={"AZURE_OPENAI_DEPLOYMENT": "test"},
                max_candidates=5,
            )
            self.assertEqual(result["status"], "ready")
            self.assertEqual(len(calls), 8)
            self.assertEqual(cache.get(
                "Department of Environmental Quality", "Community health clinic"
            )["ai_status"], "evaluated")
            loaded = cached_semantic_results(
                cache, "Department of Environmental Quality", "Community health clinic"
            )
            self.assertEqual(loaded["status"], "ready")
            self.assertEqual(
                loaded["results"]["Department of Environmental Quality::1"][
                    "project_relevance_score"
                ],
                88,
            )

    def test_cached_recommendation_read_does_not_invoke_generation(self):
        with TemporaryDirectory() as directory:
            cache = AIRecommendationCache(f"{directory}/ai.json")
            self.assertIsNone(cache.get("Department of Environmental Quality"))

    def test_project_recommendation_cache_isolated_from_agency_only_cache(self):
        with TemporaryDirectory() as directory:
            cache = AIRecommendationCache(f"{directory}/ai.json")
            cache.save("Department of Environmental Quality", "", [], "agency-time")
            cache.save("Department of Environmental Quality", "clinic", [], "project-time")
            self.assertEqual(
                cache.get("Department of Environmental Quality", "")["refreshed_at"],
                "agency-time",
            )
            self.assertEqual(
                cache.get("Department of Environmental Quality", "clinic")["refreshed_at"],
                "project-time",
            )

    def test_ai_threshold_boundaries_and_project_score_selection(self):
        record = {"opportunity_id": "1", "eligibility_status": "Needs Review"}
        semantic = {
            "status": "Evaluated",
            "strategic_relevance_score": 59,
            "project_relevance_score": 81,
        }
        self.assertEqual(
            classify_recommendation(record, semantic, minimum_score=60)["classification"],
            "Below AI threshold",
        )
        self.assertEqual(
            classify_recommendation(
                record, semantic, minimum_score=80,
                project_description="new clinic",
            )["classification"],
            "Recommended",
        )
        self.assertEqual(
            classify_recommendation(
                record, semantic, minimum_score=82,
                project_description="new clinic",
            )["classification"],
            "Below AI threshold",
        )

    def test_confirmed_ineligible_is_excluded_even_with_high_ai_score(self):
        records = [{
            "opportunity_id": "1",
            "eligibility_status": "Ineligible",
            "eligibility_reason": "Official applicant restriction",
        }]
        result = classify_recommendations(
            records,
            {"1": {"status": "Evaluated", "strategic_relevance_score": 100}},
            minimum_score=0,
        )
        self.assertEqual(result["records"], [])
        self.assertEqual(result["counts"]["confirmed_ineligible"], 1)
        included = classify_recommendations(
            records,
            {"1": {"status": "Evaluated", "strategic_relevance_score": 100}},
            minimum_score=0,
            exclude_confirmed_ineligible=False,
        )
        self.assertEqual(len(included["records"]), 1)

    def test_uncertain_and_missing_ai_scores_are_not_below_threshold(self):
        records = [
            {"opportunity_id": "1", "eligibility_status": "Needs Review"},
            {"opportunity_id": "2", "eligibility_status": "Needs Review"},
        ]
        result = classify_recommendations(
            records,
            {"1": {"status": "Not AI Evaluated"}, "2": {"status": "Evaluated"}},
            minimum_score=60,
            include_uncertain=True,
        )
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["counts"]["not_evaluated"], 2)
        hidden = classify_recommendations(
            records, {}, minimum_score=60, include_uncertain=False
        )
        self.assertEqual(hidden["records"], [])


if __name__ == "__main__":
    unittest.main()
