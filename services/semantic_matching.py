"""Bounded Azure semantic relevance evaluation for verified grant evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Callable

import requests


CONFIDENCES = {"High", "Medium", "Low"}
EVALUATED = "Evaluated"
NOT_EVALUATED = "Not AI Evaluated"


class SemanticEvaluationError(RuntimeError):
    """A safe, user-facing semantic evaluation failure."""


def _goal_id(goal, index):
    return str(goal.get("id") or f"goal-{goal.get('page', index + 1)}")


def agency_id(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")


def _goal_records(profile):
    return [
        {
            "id": _goal_id(goal, index),
            "text": str(goal.get("text") or ""),
            "page": goal.get("page"),
            "terms": goal.get("terms") or [],
        }
        for index, goal in enumerate((profile or {}).get("goals", []))
    ]


def _source_references(profile, goal_ids):
    by_id = {_goal_id(goal, index): goal for index, goal in enumerate((profile or {}).get("goals", []))}
    return [
        {
            "goal_id": goal_id,
            "page": by_id[goal_id].get("page"),
            "url": (profile or {}).get("plan_url"),
        }
        for goal_id in goal_ids if goal_id in by_id
    ]


def evaluation_cache_key(agency, opportunity_id, profile, details, deployment,
                         project_description=""):
    evidence = {
        "agency": agency,
        "opportunity_id": str(opportunity_id),
        "project_description": str(project_description or ""),
        "goals": _goal_records(profile),
        "plan_url": (profile or {}).get("plan_url"),
        "details": {
            "description": str((details or {}).get("description") or ""),
            "eligibility_description": str((details or {}).get("eligibility_description") or ""),
            "applicant_types": (details or {}).get("applicant_types") or [],
        },
        "deployment": deployment,
    }
    digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"{agency_id(agency)}:{opportunity_id}:{deployment}:{digest}"


def not_evaluated(reason, model=""):
    return {
        "status": NOT_EVALUATED,
        "semantic_relevance_score": None,
        "confidence": "Low",
        "matched_goal_ids": [],
        "verified_source_references": [],
        "evidence_grounded_explanation": reason,
        "relevant_opportunity_evidence": [],
        "eligibility_concerns": [],
        "recommended_next_action": "Review official evidence manually before deciding.",
        "evaluation_model": model or "Not used",
        "evaluated_at": None,
        "usage": {},
    }


def select_ai_candidates(grants, max_candidates=5):
    """Select a diverse, deterministic pool without relying only on keywords."""
    eligible = [grant for grant in grants if grant.get("id") not in (None, "")]
    selected, selected_ids = [], set()

    def add(items):
        for grant in items:
            identifier = str(grant.get("id"))
            if identifier not in selected_ids and len(selected) < max_candidates:
                selected.append(grant)
                selected_ids.add(identifier)

    baseline = sorted(
        eligible,
        key=lambda grant: (
            grant.get("match_score") is None,
            -(grant.get("match_score") or 0),
        ),
    )
    zero_overlap = [
        grant for grant in eligible
        if not grant.get("match_reasons") and grant.get("match_score") == 0
    ]
    add(baseline[:2])
    add(zero_overlap[:2])
    add(eligible)
    return selected


def _validate_result(raw, profile, details, agency, exclusion, project_description=""):
    if not isinstance(raw, dict):
        raise ValueError("response was not an object")
    score = raw.get("semantic_relevance_score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("invalid semantic score")
    confidence = raw.get("confidence")
    if confidence not in CONFIDENCES:
        raise ValueError("invalid confidence")
    valid_ids = {_goal_id(goal, index) for index, goal in enumerate(profile.get("goals", []))}
    matched = raw.get("matched_goal_ids")
    if not isinstance(matched, list) or not all(item in valid_ids for item in matched):
        raise ValueError("invalid matched goals")
    evidence = raw.get("relevant_opportunity_evidence")
    concerns = raw.get("eligibility_concerns")
    if not isinstance(evidence, list) or not isinstance(concerns, list):
        raise ValueError("invalid evidence fields")
    strategic_score = raw.get("strategic_relevance_score")
    project_score = raw.get("project_relevance_score")
    for field, value in (
        ("strategic_relevance_score", strategic_score),
        ("project_relevance_score", project_score),
    ):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100
        ):
            raise ValueError(f"invalid {field}")
    if strategic_score is None and not project_description:
        strategic_score = score
    if project_score is None and project_description:
        project_score = score
    result = {
        "status": EVALUATED,
        "semantic_relevance_score": score,
        "strategic_relevance_score": strategic_score,
        "project_relevance_score": project_score,
        "confidence": confidence,
        "matched_goal_ids": matched,
        "verified_source_references": _source_references(profile, matched),
        "evidence_grounded_explanation": str(raw.get("evidence_grounded_explanation") or "")[:1200],
        "relevant_opportunity_evidence": [str(item)[:700] for item in evidence[:5]],
        "eligibility_concerns": [str(item)[:700] for item in concerns[:5]],
        "recommended_next_action": str(raw.get("recommended_next_action") or "")[:1200],
        "evaluation_model": str(raw.get("evaluation_model") or ""),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "usage": raw.get("usage") if isinstance(raw.get("usage"), dict) else {},
    }
    if exclusion:
        result["eligibility_concerns"] = list(dict.fromkeys(
            result["eligibility_concerns"] + [str(exclusion.get("reason") or "Official applicant exclusion requires review.")]
        ))
        result["recommended_next_action"] = (
            "Do not apply directly; verify the official notice and any alternate applicant route."
        )
    return result


def evaluate_semantic_match(
    agency,
    profile,
    grant,
    details,
    config,
    exclusion=None,
    cache=None,
    request_post: Callable = requests.post,
    project_description="",
):
    """Evaluate one opportunity, using only verified goals and official details."""
    deployment = str(config.get("AZURE_OPENAI_DEPLOYMENT", ""))
    cache_key = evaluation_cache_key(
        agency, grant.get("id"), profile, details, deployment, project_description
    )
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    if not profile or not profile.get("goals"):
        return not_evaluated("No verified strategic goals are available for this agency.", deployment)
    if not grant.get("id"):
        return not_evaluated("The opportunity has no official identifier.", deployment)
    if not details or not details.get("description"):
        return not_evaluated("Official opportunity evidence has not been loaded.", deployment)

    endpoint = str(config.get("AZURE_OPENAI_ENDPOINT", "")).rstrip("/")
    api_version = str(config.get("AZURE_OPENAI_API_VERSION", "2024-10-21"))
    api_key = str(config.get("AZURE_OPENAI_API_KEY", ""))
    if not all((endpoint, api_key, deployment)):
        raise SemanticEvaluationError("Azure semantic evaluation is not configured.")
    if not endpoint.startswith("https://") or ".openai.azure.com" not in endpoint:
        raise SemanticEvaluationError("Invalid Azure OpenAI endpoint.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", deployment):
        raise SemanticEvaluationError("Invalid Azure OpenAI deployment name.")

    goals = _goal_records(profile)
    official_evidence = {
        "title": str(grant.get("title") or "")[:300],
        "description": str(details.get("description") or "")[:6500],
        "eligibility_description": str(details.get("eligibility_description") or "")[:3500],
        "applicant_types": details.get("applicant_types") or [],
        "close_date": grant.get("closeDate"),
        "project_description": str(project_description or "")[:4000],
    }
    system = (
        "Evaluate strategic relevance using the supplied verified goals and official evidence. "
        "If a project description is supplied, also evaluate project fit against the official evidence "
        "and report that fit in the same semantic_relevance_score; state the project basis in the explanation. "
        "Never invent goals, pages, eligibility, amounts, deadlines, or citations. "
        "Return JSON with semantic_relevance_score (integer 0-100), strategic_relevance_score "
        "(integer 0-100 or null), project_relevance_score (integer 0-100 or null), "
        "confidence (High/Medium/Low), "
        "matched_goal_ids (only supplied IDs), evidence_grounded_explanation, "
        "relevant_opportunity_evidence (array), eligibility_concerns (array), "
        "recommended_next_action, evaluation_model, evaluated_at, and usage. "
        "Strategic relevance is not eligibility. If applicant restrictions exist, flag them and do not recommend direct application."
    )
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({
                "agency": agency,
                "verified_goals": goals,
                "official_opportunity_evidence": official_evidence,
            }, ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": 500,
    }
    try:
        response = request_post(
            f"{endpoint}/openai/deployments/{deployment}/chat/completions",
            params={"api-version": api_version},
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=35,
        )
        response.raise_for_status()
        data = response.json()
        raw = data["choices"][0]["message"]["content"]
        raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", str(raw).strip())
        result = json.loads(raw)
        usage = data.get("usage")
        if isinstance(usage, dict):
            result["usage"] = {
                key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if key in usage and isinstance(usage[key], int)
            }
        result["evaluation_model"] = deployment
        validated = _validate_result(
            result, profile, details, agency, exclusion, project_description
        )
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise SemanticEvaluationError(
            "Azure semantic evaluation failed or returned invalid structured data."
        ) from None
    if cache is not None:
        cache[cache_key] = validated
    return validated
