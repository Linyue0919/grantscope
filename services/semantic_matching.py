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


def _failure(reason):
    return SemanticEvaluationError(f"Azure semantic evaluation failed: {reason}.")


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
    profile = profile or {}
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
        "strategic_relevance_score": None,
        "project_relevance_score": None,
        "confidence": "Low",
        "matched_goal_ids": [],
        "verified_source_references": [],
        "evidence_grounded_explanation": reason,
        "relevant_opportunity_evidence": [],
        "eligibility_concerns": [],
        "recommended_next_action": "Review official evidence manually before deciding.",
        "funding_purpose_fit": "",
        "evaluation_model": model or "Not used",
        "evaluated_at": None,
        "usage": {},
    }


def select_ai_candidates(grants, max_candidates=5, project_description=""):
    """Select a diverse, deterministic pool without relying only on keywords."""
    eligible = [grant for grant in grants if grant.get("id") not in (None, "")]
    selected, selected_ids = [], set()

    def add(items):
        for grant in items:
            identifier = str(grant.get("id"))
            if identifier not in selected_ids and len(selected) < max_candidates:
                selected.append(grant)
                selected_ids.add(identifier)

    project_terms = {
        term for term in re.findall(r"[a-z0-9]+", str(project_description).lower())
        if len(term) > 3
    }

    def project_aid(grant):
        text = " ".join(
            str(grant.get(field) or "")
            for field in ("title", "description", "synopsis")
        ).lower()
        return sum(term in text for term in project_terms)

    baseline = sorted(
        eligible,
        key=lambda grant: (
            -project_aid(grant) if project_description else 0,
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


def _source_text(details):
    return " ".join(
        str(details.get(field) or "")
        for field in ("description", "eligibility_description", "applicant_types")
    ).lower()


def _validate_result(raw, profile, details, agency, exclusion, project_description=""):
    if not isinstance(raw, dict):
        raise ValueError("schema mismatch: response was not an object")
    score = raw.get("semantic_relevance_score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("invalid semantic_relevance_score")
    confidence = raw.get("confidence")
    if confidence not in CONFIDENCES:
        raise ValueError("invalid confidence")
    valid_ids = {
        _goal_id(goal, index)
        for index, goal in enumerate((profile or {}).get("goals", []))
    }
    matched = raw.get("matched_goal_ids")
    if not isinstance(matched, list) or not all(item in valid_ids for item in matched):
        raise ValueError("invalid matched_goal_ids")
    evidence = raw.get("relevant_opportunity_evidence")
    concerns = raw.get("eligibility_concerns")
    if not isinstance(evidence, list) or not isinstance(concerns, list):
        raise ValueError("missing evidence fields")
    explanation = str(raw.get("evidence_grounded_explanation") or "").strip()
    next_action = str(raw.get("recommended_next_action") or "").strip()
    if not explanation:
        raise ValueError("missing evidence_grounded_explanation")
    if not next_action:
        raise ValueError("missing recommended_next_action")
    source_text = _source_text(details)
    if evidence and not any(
        str(item).strip().lower() in source_text
        for item in evidence if str(item).strip()
    ):
        raise ValueError("evidence snippets do not match official detail text")
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
        "evidence_grounded_explanation": explanation[:1200],
        "relevant_opportunity_evidence": [str(item)[:700] for item in evidence[:5]],
        "eligibility_concerns": [str(item)[:700] for item in concerns[:5]],
        "recommended_next_action": next_action[:1200],
        "funding_purpose_fit": str(raw.get("funding_purpose_fit") or "")[:1200],
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
    if (not profile or not profile.get("goals")) and not str(project_description).strip():
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
        "Act as a Federal Grant Analyst. Evaluate actual funding suitability, not keyword similarity. "
        "Consider the applicant agency identity, project activities, verified goals, official purpose, "
        "allowable activities, applicant eligibility, funding constraints, and deadline. "
        "If a project description is supplied, also evaluate project fit against the official evidence "
        "and use project_relevance_score as the primary relevance score. If no project is supplied, "
        "use verified strategic goals. If neither exists, do not evaluate. "
        "A K-12 astronomy or science grant is not suitable for cybersecurity training unless the official "
        "purpose and activities support cybersecurity. "
        "Never invent goals, pages, eligibility, amounts, deadlines, or citations. "
        "Use exact short snippets from supplied official description or eligibility fields in "
        "relevant_opportunity_evidence. "
        "Return JSON with semantic_relevance_score (integer 0-100), strategic_relevance_score "
        "(integer 0-100 or null), project_relevance_score (integer 0-100 or null), "
        "confidence (High/Medium/Low), "
        "matched_goal_ids (only supplied IDs), evidence_grounded_explanation, "
        "relevant_opportunity_evidence (array), eligibility_concerns (array), funding_purpose_fit, "
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
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
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
        if not isinstance(data, dict):
            raise ValueError("malformed response envelope")
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ValueError("response truncated")
        message = choice["message"]
        if message.get("refusal"):
            raise ValueError("model refusal")
        raw = message["content"]
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("missing response content")
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
    except requests.RequestException:
        raise _failure("request failed") from None
    except json.JSONDecodeError:
        raise _failure("malformed JSON response") from None
    except ValueError as exc:
        raise _failure(str(exc)) from None
    except (KeyError, IndexError, TypeError):
        raise _failure("schema mismatch") from None
    if cache is not None:
        cache[cache_key] = validated
    return validated
