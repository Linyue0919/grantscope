"""Offline tests for bounded Azure semantic evaluation."""
import unittest
from unittest.mock import Mock

import requests

from services.semantic_matching import (
    EVALUATED,
    NOT_EVALUATED,
    SemanticEvaluationError,
    evaluate_semantic_match,
    select_ai_candidates,
)


PROFILE = {
    "plan_url": "https://example.gov/plan",
    "goals": [
        {"text": "Protect water quality", "page": 4, "terms": ["water"]},
        {"text": "Improve resilience", "page": 6, "terms": ["resilience"]},
    ],
}
GRANT = {"id": 123, "title": "Water infrastructure"}
DETAILS = {
    "description": "Official water infrastructure opportunity.",
    "eligibility_description": "State governments may apply.",
    "applicant_types": ["State governments"],
}
CONFIG = {
    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
    "AZURE_OPENAI_API_KEY": "test-key",
    "AZURE_OPENAI_DEPLOYMENT": "grantscope-gpt4o",
    "AZURE_OPENAI_API_VERSION": "2024-10-21",
}


def response(payload, usage=None, finish_reason=None, refusal=None):
    message = {"content": payload}
    if refusal is not None:
        message["refusal"] = refusal
    result = {
        "choices": [{"message": message}],
    }
    if finish_reason is not None:
        result["choices"][0]["finish_reason"] = finish_reason
    if usage is not None:
        result["usage"] = usage
    mock = Mock()
    mock.json.return_value = result
    return mock


class SemanticMatchingTests(unittest.TestCase):
    def test_structured_response_is_validated_and_sources_are_verified(self):
        request = Mock(return_value=response(
            '{"semantic_relevance_score": 82, "confidence": "High", '
            '"matched_goal_ids": ["goal-4"], '
            '"evidence_grounded_explanation": "Water is directly supported.", '
            '"relevant_opportunity_evidence": ["Official water infrastructure opportunity."], '
            '"eligibility_concerns": [], '
            '"recommended_next_action": "Verify the NOFO.", '
            '"evaluation_model": "ignored", "evaluated_at": "ignored", "usage": {}}',
            {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        ))
        result = evaluate_semantic_match(
            "Agency", PROFILE, GRANT, DETAILS, CONFIG, request_post=request
        )
        self.assertEqual(result["status"], EVALUATED)
        self.assertEqual(result["semantic_relevance_score"], 82)
        self.assertEqual(result["matched_goal_ids"], ["goal-4"])
        self.assertEqual(result["verified_source_references"][0]["page"], 4)
        self.assertEqual(result["evaluation_model"], "grantscope-gpt4o")
        self.assertEqual(result["usage"]["total_tokens"], 30)
        self.assertEqual(
            request.call_args.kwargs["json"]["response_format"],
            {"type": "json_object"},
        )

    def test_missing_goals_and_details_do_not_call_azure(self):
        request = Mock()
        self.assertEqual(
            evaluate_semantic_match("Agency", None, GRANT, DETAILS, CONFIG, request_post=request)["status"],
            NOT_EVALUATED,
        )
        self.assertEqual(
            evaluate_semantic_match("Agency", PROFILE, GRANT, {}, CONFIG, request_post=request)["status"],
            NOT_EVALUATED,
        )
        request.assert_not_called()

    def test_project_only_evaluation_allows_unverified_agency_without_strategic_score(self):
        request = Mock(return_value=response(
            '{"semantic_relevance_score": 74, "project_relevance_score": 74, '
            '"strategic_relevance_score": null, "confidence": "Medium", '
            '"matched_goal_ids": [], "evidence_grounded_explanation": "Official project evidence.", '
            '"relevant_opportunity_evidence": ["Official water infrastructure opportunity."], "eligibility_concerns": [], '
            '"recommended_next_action": "Review.", "evaluation_model": "", "usage": {}}'
        ))
        result = evaluate_semantic_match(
            "Unverified Agency", None, GRANT, DETAILS, CONFIG,
            request_post=request, project_description="Cybersecurity awareness training",
        )
        self.assertEqual(result["status"], EVALUATED)
        self.assertEqual(result["project_relevance_score"], 74)
        self.assertIsNone(result["strategic_relevance_score"])

    def test_candidate_selection_includes_zero_overlap_and_is_capped(self):
        grants = [
            {"id": 1, "match_score": 90, "match_reasons": [{"goal": "x"}]},
            {"id": 2, "match_score": 80, "match_reasons": [{"goal": "x"}]},
            {"id": 3, "match_score": 0, "match_reasons": []},
            {"id": 4, "match_score": 0, "match_reasons": []},
            {"id": 5, "match_score": 20, "match_reasons": [{"goal": "y"}]},
            {"id": 6, "match_score": 10, "match_reasons": [{"goal": "z"}]},
        ]
        selected = select_ai_candidates(grants)
        self.assertEqual(len(selected), 5)
        self.assertIn(3, [grant["id"] for grant in selected])
        self.assertIn(4, [grant["id"] for grant in selected])

    def test_project_candidate_priority_is_retrieval_aid_not_ai_evidence(self):
        grants = [
            {"id": 1, "title": "Solar System Science for K-12", "match_score": 90},
            {"id": 2, "title": "Cybersecurity Education for School Faculty", "match_score": 10},
            {"id": 3, "title": "STEM Teacher Training", "match_score": 0},
        ]
        selected = select_ai_candidates(
            grants,
            max_candidates=2,
            project_description="Cybersecurity awareness training for K-12 school faculty",
        )
        self.assertEqual(selected[0]["id"], 2)
        self.assertIn(3, [grant["id"] for grant in selected])

    def test_explicit_exclusion_overrides_action(self):
        request = Mock(return_value=response(
            '{"semantic_relevance_score": 99, "confidence": "High", '
            '"matched_goal_ids": ["goal-4"], "evidence_grounded_explanation": "Relevant.", '
            '"relevant_opportunity_evidence": ["Official water infrastructure opportunity."], "eligibility_concerns": [], '
            '"recommended_next_action": "Apply now.", "evaluation_model": "", "usage": {}}'
        ))
        result = evaluate_semantic_match(
            "Agency", PROFILE, GRANT, DETAILS, CONFIG,
            exclusion={"excluded": True, "reason": "Tribal-only applicants."},
            request_post=request,
        )
        self.assertIn("Tribal-only applicants.", result["eligibility_concerns"])
        self.assertIn("Do not apply directly", result["recommended_next_action"])

    def test_successful_evaluation_is_cached(self):
        request = Mock(return_value=response(
            '{"semantic_relevance_score": 50, "confidence": "Medium", '
            '"matched_goal_ids": [], "evidence_grounded_explanation": "Some overlap.", '
            '"relevant_opportunity_evidence": ["Official water infrastructure opportunity."], "eligibility_concerns": [], '
            '"recommended_next_action": "Review.", "evaluation_model": "", "usage": {}}'
        ))
        cache = {}
        first = evaluate_semantic_match("Agency", PROFILE, GRANT, DETAILS, CONFIG, cache=cache, request_post=request)
        second = evaluate_semantic_match("Agency", PROFILE, GRANT, DETAILS, CONFIG, cache=cache, request_post=request)
        self.assertEqual(first, second)
        request.assert_called_once()

    def test_project_description_is_sent_to_semantic_evaluator_and_cache_keyed(self):
        request = Mock(return_value=response(
            '{"semantic_relevance_score": 91, "confidence": "High", '
            '"matched_goal_ids": ["goal-4"], "evidence_grounded_explanation": "The official notice supports the project.", '
            '"relevant_opportunity_evidence": ["Official water infrastructure opportunity."], "eligibility_concerns": [], '
            '"recommended_next_action": "Review.", "evaluation_model": "", "usage": {}}'
        ))
        cache = {}
        result = evaluate_semantic_match(
            "Agency", PROFILE, GRANT, DETAILS, CONFIG, cache=cache,
            request_post=request, project_description="Replace unsafe drinking water pipes.",
        )
        self.assertEqual(result["semantic_relevance_score"], 91)
        payload = request.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn("Replace unsafe drinking water pipes.", payload)
        evaluate_semantic_match(
            "Agency", PROFILE, GRANT, DETAILS, CONFIG, cache=cache,
            request_post=request, project_description="Build a public safety training center.",
        )
        self.assertEqual(request.call_count, 2)

    def test_invalid_response_and_api_failure_are_sanitized(self):
        invalid = Mock(return_value=response('{"semantic_relevance_score": 101}'))
        with self.assertRaises(SemanticEvaluationError):
            evaluate_semantic_match("Agency", PROFILE, GRANT, DETAILS, CONFIG, request_post=invalid)
        failing = Mock(side_effect=requests.Timeout())
        with self.assertRaises(SemanticEvaluationError):
            evaluate_semantic_match("Agency", PROFILE, GRANT, DETAILS, CONFIG, request_post=failing)

    def test_malformed_json_reports_sanitized_diagnostic(self):
        request = Mock(return_value=response("{not-json"))
        with self.assertRaisesRegex(SemanticEvaluationError, "malformed JSON"):
            evaluate_semantic_match("Agency", PROFILE, GRANT, DETAILS, CONFIG, request_post=request)

    def test_truncation_and_refusal_report_sanitized_diagnostics(self):
        truncated = Mock(return_value=response("{}", finish_reason="length"))
        with self.assertRaisesRegex(SemanticEvaluationError, "truncated"):
            evaluate_semantic_match("Agency", PROFILE, GRANT, DETAILS, CONFIG, request_post=truncated)
        refused = Mock(return_value=response("", refusal="safety refusal"))
        with self.assertRaisesRegex(SemanticEvaluationError, "refusal"):
            evaluate_semantic_match("Agency", PROFILE, GRANT, DETAILS, CONFIG, request_post=refused)

    def test_missing_required_fields_reports_schema_mismatch(self):
        request = Mock(return_value=response(
            '{"semantic_relevance_score": 50, "confidence": "Medium", '
            '"matched_goal_ids": [], "eligibility_concerns": []}'
        ))
        with self.assertRaisesRegex(SemanticEvaluationError, "missing evidence"):
            evaluate_semantic_match("Agency", PROFILE, GRANT, DETAILS, CONFIG, request_post=request)


if __name__ == "__main__":
    unittest.main()
