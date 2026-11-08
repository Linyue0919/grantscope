"""Offline tests for the results-first Search presentation helpers."""
import unittest

from modules.search import (
    apply_search_filters,
    decision_csv,
    eligibility_summary,
    partition_recommendation_results,
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
    merge_cached_opportunities,
    prepare_ai_recommendations,
    research_depth_limit,
)
from tempfile import TemporaryDirectory


class SearchPresentationTests(unittest.TestCase):
    def test_research_depth_limits_are_bounded(self):
        self.assertEqual(research_depth_limit("Quick"), 10)
        self.assertEqual(research_depth_limit("Balanced"), 30)
        self.assertEqual(research_depth_limit("Deep"), 50)
        self.assertEqual(research_depth_limit("Custom", 37), 35)
        self.assertEqual(research_depth_limit("Custom", 1000), 100)

    def test_progressive_batches_persist_after_each_batch(self):
        grants = [{"id": str(index), "title": f"Grant {index}"} for index in range(10)]
        evaluations = []

        class RecordingCache(AIRecommendationCache):
            def __init__(self, path):
                super().__init__(path)
                self.save_sizes = []

            def save(self, agency, project_description, records, refreshed_at):
                self.save_sizes.append(len(records))
                super().save(agency, project_description, records, refreshed_at)

        def evaluate(*args, **kwargs):
            evaluations.append(args[2]["id"])
            return {
                "status": "Evaluated",
                "semantic_relevance_score": 80,
                "project_relevance_score": 80,
                "evidence_verified": True,
            }

        with TemporaryDirectory() as directory:
            cache = RecordingCache(f"{directory}/ai.json")
            result = prepare_ai_recommendations(
                "Department of Environmental Quality",
                project_description="water quality",
                cache=cache,
                seed_grants=grants,
                fetch_grants=lambda query, rows: [],
                fetch_details=lambda identifier: {"description": "Official water opportunity"},
                evaluate=evaluate,
                config={"AZURE_OPENAI_DEPLOYMENT": "test"},
                max_new_evaluations=10,
                batch_size=5,
            )
        self.assertEqual(len(evaluations), 10)
        self.assertEqual(cache.save_sizes, [5, 10])
        self.assertEqual(result["summary"]["succeeded"], 10)

    def test_resume_only_evaluates_new_opportunities(self):
        grants = [{"id": str(index), "title": f"Grant {index}"} for index in range(6)]
        calls = []

        def evaluate(*args, **kwargs):
            calls.append(args[2]["id"])
            return {"status": "Evaluated", "semantic_relevance_score": 70}

        with TemporaryDirectory() as directory:
            cache = AIRecommendationCache(f"{directory}/ai.json")
            prepare_ai_recommendations(
                "Department of Environmental Quality",
                project_description="water quality",
                cache=cache,
                seed_grants=grants,
                fetch_grants=lambda query, rows: [],
                fetch_details=lambda identifier: {"description": "Official water opportunity"},
                evaluate=evaluate,
                config={"AZURE_OPENAI_DEPLOYMENT": "test"},
                max_new_evaluations=2,
            )
            prepare_ai_recommendations(
                "Department of Environmental Quality",
                project_description="water quality",
                cache=cache,
                seed_grants=grants,
                fetch_grants=lambda query, rows: [],
                fetch_details=lambda identifier: {"description": "Official water opportunity"},
                evaluate=evaluate,
                config={"AZURE_OPENAI_DEPLOYMENT": "test"},
                max_new_evaluations=4,
            )
        self.assertEqual(len(calls), 6)
        self.assertEqual(len(set(calls[:2]).intersection(calls[2:])), 0)

    def test_ineligible_candidates_are_screened_before_ai(self):
        grants = [
            {"id": "excluded", "title": "Water tribal-only grant"},
            {"id": "eligible", "title": "Water grant"},
        ]
        calls = []

        def evaluate(*args, **kwargs):
            calls.append(args[2]["id"])
            return {"status": "Evaluated", "semantic_relevance_score": 75}

        def details(identifier):
            if identifier == "excluded":
                return {
                    "description": (
                        "Eligible applicants are federally recognized Tribes "
                        "and intertribal consortia."
                    )
                }
            return {"description": "Official water opportunity"}

        with TemporaryDirectory() as directory:
            result = prepare_ai_recommendations(
                "Department of Environmental Quality",
                project_description="water quality",
                cache=AIRecommendationCache(f"{directory}/ai.json"),
                seed_grants=grants,
                fetch_grants=lambda query, rows: [],
                fetch_details=details,
                evaluate=evaluate,
                config={"AZURE_OPENAI_DEPLOYMENT": "test"},
                max_new_evaluations=1,
            )
        self.assertEqual(calls, ["eligible"])
        self.assertEqual(result["summary"]["skipped_ineligible"], 1)

    def test_partial_ai_failures_are_reported_without_fabricated_scores(self):
        grants = [{"id": str(index), "title": f"Grant {index}"} for index in range(3)]

        def evaluate(*args, **kwargs):
            if args[2]["id"] == "1":
                return {"status": "Not AI Evaluated", "semantic_relevance_score": None}
            return {"status": "Evaluated", "semantic_relevance_score": 75}

        with TemporaryDirectory() as directory:
            result = prepare_ai_recommendations(
                "Department of Environmental Quality",
                project_description="water quality",
                cache=AIRecommendationCache(f"{directory}/ai.json"),
                seed_grants=grants,
                fetch_grants=lambda query, rows: [],
                fetch_details=lambda identifier: {"description": "Official water opportunity"},
                evaluate=evaluate,
                config={"AZURE_OPENAI_DEPLOYMENT": "test"},
                max_new_evaluations=3,
            )
        self.assertEqual(result["summary"]["failed"], 1)
        failed = next(record for record in result["records"] if record["opportunity_id"] == "1")
        self.assertIsNone(failed["semantic"]["semantic_relevance_score"])
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
        cyber_queries = diversified_retrieval_queries(
            {}, "Cybersecurity awareness training for K-12 school faculty"
        )
        self.assertIn("cybersecurity education", cyber_queries)
        self.assertIn("school safety", cyber_queries)
        self.assertIn("teacher training", cyber_queries)
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

    def test_repeated_search_preparation_reuses_cached_evaluations(self):
        grants = [{"id": "1", "title": "Cybersecurity education"}]
        calls = []

        def evaluate(*args, **kwargs):
            calls.append(args[2]["id"])
            return {
                "status": "Evaluated",
                "semantic_relevance_score": 90,
                "strategic_relevance_score": None,
                "project_relevance_score": 90,
                "evidence_verified": True,
                "evidence_grounded_explanation": "Official evidence supports training.",
            }

        with TemporaryDirectory() as directory:
            cache = AIRecommendationCache(f"{directory}/ai.json")
            for _ in range(2):
                prepare_ai_recommendations(
                    "Department of Environmental Quality",
                    project_description="Cybersecurity education",
                    cache=cache,
                    seed_grants=grants,
                    fetch_grants=lambda query, rows: [],
                    fetch_details=lambda identifier: {
                        "description": "Official cybersecurity education opportunity."
                    },
                    evaluate=evaluate,
                    config={"AZURE_OPENAI_DEPLOYMENT": "test"},
                    max_candidates=5,
                )
        self.assertEqual(calls, ["1"])

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
        record = {"opportunity_id": "1", "eligibility_status": "Needs Review", "opportunity_status": "Posted", "close_date": "2027-01-25"}
        semantic = {
            "status": "Evaluated",
            "strategic_relevance_score": 59,
            "project_relevance_score": 81,
            "evidence_verified": True,
            "funding_purpose_status": "Supported", "funding_purpose_fit": "Official activities support this purpose.",
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
            {"opportunity_id": "1", "eligibility_status": "Needs Review", "opportunity_status": "Posted", "close_date": "2027-01-25"},
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

    def test_only_evaluated_records_meeting_threshold_are_recommended(self):
        records = [
            {"opportunity_id": "1", "eligibility_status": "Needs Review", "opportunity_status": "Posted", "close_date": "2027-01-25"},
            {"opportunity_id": "2", "eligibility_status": "Needs Review"},
            {"opportunity_id": "3", "eligibility_status": "Ineligible"},
        ]
        result = classify_recommendations(
            records,
            {
                "1": {"status": "Evaluated", "project_relevance_score": 85, "evidence_verified": True, "funding_purpose_status": "Supported", "funding_purpose_fit": "Official activities support this purpose."},
                "2": {"status": "Not AI Evaluated"},
                "3": {"status": "Evaluated", "project_relevance_score": 100, "evidence_verified": True},
            },
            minimum_score=60,
            include_uncertain=False,
            project_description="Cybersecurity awareness training",
        )
        self.assertEqual(
            [record["opportunity_id"] for record in result["records"]],
            ["1"],
        )
        self.assertEqual(result["counts"]["recommended"], 1)
        self.assertEqual(result["counts"]["not_evaluated"], 1)
        self.assertEqual(result["counts"]["confirmed_ineligible"], 1)

    def test_k12_project_review_keeps_thirteen_unevaluated_out_of_primary_results(self):
        grants = [
            {"id": str(index), "title": "K-12 opportunity"}
            for index in range(13)
        ]
        result = classify_recommendations(
            [
                {"opportunity_id": grant["id"], "eligibility_status": "Needs Review"}
                for grant in grants
            ],
            {},
            minimum_score=60,
            project_description="Educations for cybersecurity awareness within faculty",
        )
        recommended, review = partition_recommendation_results(grants, result)
        self.assertEqual(recommended, [])
        self.assertEqual(len(review), 13)

    def test_confirmed_ineligible_is_hidden_from_primary_and_other_results(self):
        grants = [
            {"id": "eligible", "title": "Good fit"},
            {"id": "excluded", "title": "Restricted"},
            {"id": "pending", "title": "Pending"},
        ]
        result = classify_recommendations(
            [
                {"opportunity_id": "eligible", "eligibility_status": "Needs Review", "opportunity_status": "Posted", "close_date": "2027-01-25"},
                {"opportunity_id": "excluded", "eligibility_status": "Ineligible"},
                {"opportunity_id": "pending", "eligibility_status": "Needs Review"},
            ],
            {
                "eligible": {
                    "status": "Evaluated", "project_relevance_score": 90,
                    "evidence_verified": True, "funding_purpose_status": "Supported", "funding_purpose_fit": "Official activities support this purpose.",
                },
                "pending": {"status": "Not AI Evaluated"},
            },
            minimum_score=60,
            project_description="Good fit",
        )
        primary, other = partition_recommendation_results(grants, result)
        self.assertEqual([item["id"] for item in primary], ["eligible"])
        self.assertEqual([item["id"] for item in other], ["pending"])

    def test_cached_evaluations_are_merged_when_outside_initial_search_pool(self):
        merged = merge_cached_opportunities(
            [{"id": "seed", "title": "Initial result"}],
            [{
                "opportunity_id": "ai-1",
                "title": "Diversified result",
                "federal_agency": "Agency",
                "close_date": "12/31/2026",
            }],
        )
        self.assertEqual(
            [grant["id"] for grant in merged],
            ["seed", "ai-1"],
        )
        self.assertEqual(merged[1]["title"], "Diversified result")

    def test_cached_merge_deduplicates_by_official_opportunity_id(self):
        merged = merge_cached_opportunities(
            [{"id": "1", "title": "Current title", "agency": "Current agency"}],
            [{
                "opportunity_id": "1",
                "title": "Cached title",
                "federal_agency": "Cached agency",
            }],
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["title"], "Current title")


if __name__ == "__main__":
    unittest.main()
