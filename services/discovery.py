"""Shared opportunity discovery and cached Dashboard shortlist generation."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from services.eligibility import screen_eligibility
from services.grants_api import GrantsAPIError, get_grant_details, get_grants
from services.matching import rank_grants
from services.semantic_matching import (
    SemanticEvaluationError,
    evaluate_semantic_match,
    select_ai_candidates,
)
from services.verified_goals import VERIFIED_GOALS


class DiscoveryError(RuntimeError):
    """A safe error while generating a cached shortlist."""


AI_EVALUATION_VERSION = "analyst-v2"


def research_depth_limit(depth, custom_limit=30):
    """Return the maximum number of new Azure evaluations for a depth choice."""
    if depth == "Quick":
        return 10
    if depth == "Deep":
        return 50
    if depth == "Custom":
        return max(5, min(100, int(custom_limit or 30) // 5 * 5))
    return 30


def recommendation_namespace(agency, project_description=""):
    digest = hashlib.sha256(
        str(project_description or "").strip().encode("utf-8")
    ).hexdigest()[:16]
    return f"{agency}::{digest}"


class AIRecommendationCache:
    """Persistent AI-ranked recommendation contract shared by Search and Dashboard."""

    def __init__(self, path=".grantscope/ai_recommendations.json"):
        self.path = Path(path)

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DiscoveryError("AI recommendation cache could not be read.") from exc
        if not isinstance(data, dict):
            raise DiscoveryError("AI recommendation cache has an invalid format.")
        return data

    def get(self, agency, project_description=""):
        value = self._read().get(recommendation_namespace(agency, project_description))
        if not isinstance(value, dict):
            return None
        # Keep legacy records reviewable, but never reuse an obsolete evaluation.
        value = {**value, "records": [dict(record) for record in value.get("records", [])]}
        for record in value["records"]:
            if record.get("evaluation_version") != AI_EVALUATION_VERSION:
                record["semantic"] = {"status": "Not AI Evaluated",
                    "evidence_grounded_explanation": "Cached evaluation version is stale; explicit analysis is required."}
        return value

    def save(self, agency, project_description, records, refreshed_at):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = self._read()
        namespace = recommendation_namespace(agency, project_description)
        data[namespace] = {
            "agency": agency,
            "project_description_hash": namespace.rsplit("::", 1)[1],
            "ai_status": "evaluated",
            "refreshed_at": refreshed_at,
            "records": records,
        }
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except OSError as exc:
            raise DiscoveryError("AI recommendation cache could not be written.") from exc
        if (
            self.path == Path(".grantscope/ai_recommendations.json")
            and not project_description.strip()
        ):
            DashboardShortlistCache().save(
                agency, records, refreshed_at, ai_status="evaluated"
            )


def cached_semantic_results(cache, agency, project_description=""):
    """Return only persisted evaluated results for Search rendering."""
    cached = cache.get(agency, project_description)
    if not cached or cached.get("ai_status") != "evaluated":
        return {"status": "unavailable", "results": {}, "refreshed_at": None}
    return {
        "status": "ready",
        "refreshed_at": cached.get("refreshed_at"),
        "results": {
            f"{agency}::{record.get('opportunity_id')}": record["semantic"]
            for record in cached.get("records", [])
            if isinstance(record, dict) and isinstance(record.get("semantic"), dict)
        },
    }


def classify_recommendation(record, semantic=None, minimum_score=60,
                            exclude_confirmed_ineligible=True,
                            include_uncertain=True, project_description=""):
    """Classify one cached recommendation consistently for Search and Dashboard."""
    eligibility = str(record.get("eligibility_status") or "Needs Review")
    if eligibility == "Ineligible":
        return {
            "classification": "Confirmed Ineligible",
            "included": not exclude_confirmed_ineligible,
            "score": None,
            "reason": record.get("eligibility_reason") or "Official eligibility excludes this applicant.",
        }
    if not isinstance(semantic, dict) or semantic.get("status") != "Evaluated":
        return {
            "classification": "Not AI Evaluated",
            "included": include_uncertain,
            "score": None,
            "reason": (semantic or {}).get(
                "evidence_grounded_explanation",
                "AI matching has not been generated for this opportunity.",
            ),
        }
    score_field = (
        "project_relevance_score" if str(project_description).strip()
        else "strategic_relevance_score"
    )
    score = semantic.get(score_field)
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        return {
            "classification": "Not AI Evaluated",
            "included": include_uncertain,
            "score": None,
            "reason": "The cached AI evaluation has no usable relevance score.",
        }
    if not semantic.get("evidence_verified"):
        return {
            "classification": "Needs Evidence Review",
            "included": include_uncertain,
            "score": score,
            "reason": "The AI result does not contain verifiable official evidence.",
        }
    # Relevance and an exact quotation do not establish funding suitability or readiness.
    if score >= minimum_score:
        reason = None
        if (semantic.get("funding_purpose_status") != "Supported"
                or not str(semantic.get("funding_purpose_fit") or "").strip()):
            reason = "Funding purpose, allowable activities, audience and geography need review. " + str(semantic.get("funding_purpose_fit") or "No explicit purpose-fit assessment is available.")
        elif semantic.get("eligibility_concerns"):
            reason = "Applicant or partnership conditions need review: " + "; ".join(str(item) for item in semantic["eligibility_concerns"])
        elif str(record.get("opportunity_status") or "").lower() != "posted":
            reason = "Current posted status is not verified; forecasted or unknown records are research leads."
        else:
            raw_date = str(record.get("close_date") or "")
            closing = None
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
                try:
                    closing = datetime.strptime(raw_date[:10], fmt).date()
                    break
                except ValueError:
                    pass
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo("America/New_York")).date()
            if closing is None or closing < today:
                reason = "Application date is missing, invalid or past; verify the official notice before acting."
        if reason:
            return {"classification": "Needs Evidence Review", "included": include_uncertain,
                    "score": score, "reason": reason}
    return {
        "classification": "Recommended" if score >= minimum_score else "Below AI threshold",
        "included": score >= minimum_score,
        "score": score,
        "reason": semantic.get("evidence_grounded_explanation") or "",
    }


def classify_recommendations(records, semantic_by_id, minimum_score=60,
                             exclude_confirmed_ineligible=True,
                             include_uncertain=True, project_description=""):
    """Return filtered records and stage counts without double counting."""
    counts = {
        "retrieved": len(records),
        "ai_evaluated": 0,
        "recommended": 0,
        "below_threshold": 0,
        "confirmed_ineligible": 0,
        "not_evaluated": 0,
        "needs_evidence_review": 0,
    }
    visible = []
    classified = []
    for record in records:
        semantic = semantic_by_id.get(str(record.get("opportunity_id")))
        if semantic and semantic.get("status") == "Evaluated":
            counts["ai_evaluated"] += 1
        classification = classify_recommendation(
            record, semantic, minimum_score, exclude_confirmed_ineligible,
            include_uncertain, project_description,
        )
        record = {**record, "recommendation": classification}
        classified.append(record)
        if classification["classification"] == "Confirmed Ineligible":
            counts["confirmed_ineligible"] += 1
        elif classification["classification"] == "Not AI Evaluated":
            counts["not_evaluated"] += 1
        elif classification["classification"] == "Needs Evidence Review":
            counts["needs_evidence_review"] += 1
        elif semantic and semantic.get("status") == "Evaluated":
            if classification["classification"] == "Below AI threshold":
                counts["below_threshold"] += 1
            else:
                counts["recommended"] += 1
        if classification["included"]:
            visible.append(record)
    return {"records": visible, "all_records": classified, "counts": counts}


def diversified_retrieval_queries(profile, project_description="", max_queries=8):
    """Build bounded, distinct queries from verified goals and project needs."""
    queries = []
    if project_description and project_description.strip():
        project = " ".join(project_description.strip().split())[:240]
        queries.append(project)
        lowered = project.lower()
        if any(term in lowered for term in ("cyber", "security", "awareness")):
            queries.extend(("cybersecurity education", "school safety"))
        if any(term in lowered for term in ("faculty", "teacher", "school", "k-12")):
            queries.extend(("teacher training", "education technology"))
        if any(term in lowered for term in ("training", "workforce", "awareness")):
            queries.append("workforce development")
    for goal in profile.get("goals", []):
        terms = [str(term).strip() for term in goal.get("terms", []) if str(term).strip()]
        if terms:
            queries.append(" ".join(dict.fromkeys(terms[:3])))
        if goal.get("text"):
            queries.append(str(goal["text"]).strip()[:240])
    return list(dict.fromkeys(query for query in queries if query))[:max_queries]


def _dedupe_grants(grants):
    unique = {}
    for grant in grants:
        if grant.get("id") not in (None, ""):
            unique.setdefault(str(grant["id"]), grant)
    return list(unique.values())


def merge_cached_opportunities(grants, records):
    """Merge cached official opportunities into the current Search pool by ID."""
    merged = {str(grant.get("id")): dict(grant) for grant in grants if grant.get("id")}
    for record in records or []:
        opportunity_id = record.get("opportunity_id")
        if not opportunity_id:
            continue
        cached_grant = {
            "id": str(opportunity_id),
            "title": record.get("title"),
            "agency": record.get("federal_agency"),
            "closeDate": record.get("close_date"),
            "oppStatus": record.get("opportunity_status") or "Unknown",
            "description": record.get("description"),
            "awardCeiling": record.get("award_ceiling"),
            "_cached_official_url": record.get("official_url"),
        }
        current = merged.get(str(opportunity_id), {})
        merged[str(opportunity_id)] = {
            **cached_grant,
            **current,
        }
    return list(merged.values())


def get_cached_ai_shortlist(agency, cache, minimum_score=60,
                             exclude_confirmed_ineligible=True,
                             include_uncertain=True, project_description=""):
    """Return an explicit state for Dashboard owners; never substitute baseline data."""
    cached = (cache.get(agency, project_description)
              if isinstance(cache, AIRecommendationCache) else cache.get(agency))
    if not cached:
        return {"status": "pending", "agency": agency, "records": []}
    if cached.get("ai_status") != "evaluated":
        return {
            "status": "unavailable",
            "agency": agency,
            "records": cached.get("records", []),
            "reason": "No cached AI-ranked shortlist is available.",
            "refreshed_at": cached.get("refreshed_at"),
        }
    semantic_by_id = {
        str(record.get("opportunity_id")): record.get("semantic", {})
        for record in cached.get("records", [])
    }
    classified = classify_recommendations(
        cached.get("records", []), semantic_by_id,
        minimum_score=minimum_score,
        exclude_confirmed_ineligible=exclude_confirmed_ineligible,
        include_uncertain=include_uncertain,
        project_description=project_description,
    )
    return {
        "status": "ready",
        "agency": agency,
        "refreshed_at": cached.get("refreshed_at"),
        "records": classified["records"],
        "all_records": classified["all_records"],
        "counts": classified["counts"],
    }


class DashboardShortlistCache:
    def __init__(self, path=".grantscope/dashboard_shortlists.json"):
        self.path = Path(path)

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DiscoveryError("Dashboard shortlist cache could not be read.") from exc
        if not isinstance(data, dict):
            raise DiscoveryError("Dashboard shortlist cache has an invalid format.")
        return data

    def get(self, agency):
        value = self._read().get(agency)
        if not isinstance(value, dict):
            return None
        return {"agency": agency, **value}

    def save(self, agency, records, refreshed_at, ai_status=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = self._read()
        data[agency] = {"refreshed_at": refreshed_at, "records": records}
        if ai_status:
            data[agency]["ai_status"] = ai_status
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except OSError as exc:
            raise DiscoveryError("Dashboard shortlist cache could not be written.") from exc


def _goal_query(profile):
    terms = []
    for goal in profile.get("goals", []):
        terms.extend(goal.get("terms", [])[:2])
    return " ".join(dict.fromkeys(terms[:6]))


def prepare_ai_recommendations(
    agency,
    project_description="",
    cache=None,
    fetch_grants=get_grants,
    fetch_details=get_grant_details,
    evaluate=evaluate_semantic_match,
    config=None,
    max_candidates=5,
    max_new_evaluations=None,
    batch_size=5,
    rows_per_query=25,
    seed_grants=None,
):
    """Explicitly precompute and persist a bounded AI-ranked recommendation set."""
    profile = VERIFIED_GOALS.get(agency)
    if not profile and not str(project_description).strip():
        raise DiscoveryError("This agency has no verified strategic goals.")
    if config is None:
        raise DiscoveryError("Azure configuration is required for preparation.")
    existing = cache.get(agency, project_description) if cache is not None else None
    existing_records = (
        existing.get("records", []) if isinstance(existing, dict) else []
    )
    existing_ids = {
        str(record.get("opportunity_id"))
        for record in existing_records
        if record.get("evaluation_version") == AI_EVALUATION_VERSION
        and (record.get("semantic", {}).get("status") == "Evaluated"
             or record.get("eligibility_status") == "Ineligible")
    }
    target = max_candidates if max_new_evaluations is None else max_new_evaluations
    target = max(0, min(100, int(target)))
    batch_size = max(1, min(10, int(batch_size)))
    grants = []
    grants.extend(seed_grants or [])
    try:
        for query in diversified_retrieval_queries(profile or {}, project_description):
            grants.extend(fetch_grants(query, rows=rows_per_query))
    except GrantsAPIError as exc:
        raise DiscoveryError(str(exc)) from exc
    except Exception as exc:
        raise DiscoveryError("AI recommendation retrieval failed.") from exc

    unique_grants = _dedupe_grants(grants)
    candidates = select_ai_candidates(
        [grant for grant in unique_grants
         if str(grant.get("id")) not in existing_ids],
        max_candidates=len(unique_grants),
        project_description=project_description,
    )
    all_records = list(existing_records)
    attempted = succeeded = failed = skipped_ineligible = 0
    processed = official_details_screened = 0
    persisted_batches = 0
    for offset in range(0, len(candidates), batch_size):
        if attempted >= target:
            break
        batch_records = []
        for grant in candidates[offset:offset + batch_size]:
            if attempted >= target:
                break
            processed += 1
            try:
                details = fetch_details(grant["id"])
            except GrantsAPIError as exc:
                failed += 1
                batch_records.append(_research_record(
                    grant, {}, screen_eligibility({}, agency),
                    {"status": "Not AI Evaluated",
                     "semantic_relevance_score": None,
                     "evidence_grounded_explanation": str(exc)},
                ))
                continue
            official_details_screened += 1
            screening = screen_eligibility(details, agency)
            if screening["status"] == "Ineligible":
                skipped_ineligible += 1
                batch_records.append(_research_record(
                    grant, details, screening,
                    {"status": "Not AI Evaluated",
                     "semantic_relevance_score": None,
                     "evidence_grounded_explanation": "Skipped after official eligibility screening."},
                ))
                continue
            attempted += 1
            try:
                semantic = evaluate(
                    agency, profile, grant, details, config,
                    exclusion=None, project_description=project_description,
                )
                if semantic.get("status") == "Evaluated":
                    succeeded += 1
                else:
                    failed += 1
            except (GrantsAPIError, SemanticEvaluationError) as exc:
                failed += 1
                semantic = {
                    "status": "Not AI Evaluated",
                    "semantic_relevance_score": None,
                    "evidence_grounded_explanation": str(exc),
                }
            batch_records.append(_research_record(grant, details, screening, semantic))
        # Replace retries by official ID rather than appending duplicate failures.
        records_by_id = {str(record["opportunity_id"]): record for record in all_records}
        records_by_id.update({str(record["opportunity_id"]): record for record in batch_records})
        all_records = list(records_by_id.values())
        if batch_records and cache is not None:
            cache.save(
                agency, project_description, all_records,
                datetime.now(timezone.utc).isoformat(),
            )
            persisted_batches += 1
    refreshed_at = datetime.now(timezone.utc).isoformat()
    if cache is not None and not persisted_batches:
        cache.save(agency, project_description, all_records, refreshed_at)
    return {
        "status": "ready",
        "agency": agency,
        "refreshed_at": refreshed_at,
        "records": all_records,
        "summary": {
            "retrieved": len(grants),
            "deduplicated": len(unique_grants),
            "official_details_screened": official_details_screened,
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": failed,
            "skipped_ineligible": skipped_ineligible,
            "remaining_candidates": max(0, len(candidates) - processed),
        },
    }


def _research_record(grant, details, screening, semantic):
    return {
        "opportunity_id": str(grant["id"]),
        "title": grant.get("title") or "Untitled grant",
        "federal_agency": grant.get("agency") or grant.get("agencyName") or "Unknown",
        "close_date": details.get("close_date") or grant.get("closeDate"),
        "opportunity_status": details.get("opportunity_status") or grant.get("oppStatus") or grant.get("status"),
        "official_details": dict(details),
        "official_url": details.get(
            "detail_source_url",
            f"https://www.grants.gov/search-results-detail/{grant['id']}",
        ),
        "award_floor": details.get("award_floor"),
        "award_ceiling": details.get("award_ceiling"),
        "description": details.get("description"),
        "eligibility_status": screening["status"],
        "eligibility_reason": screening.get("reason"),
        "eligibility_evidence": screening.get("evidence"),
        "baseline_keyword_score": grant.get("match_score"),
        "evaluation_version": AI_EVALUATION_VERSION,
        "semantic": semantic,
    }


def generate_dashboard_shortlist(agency, cache=None, fetch_grants=get_grants,
                                 fetch_details=get_grant_details, limit=5):
    dashboard_cache_path = Path(".grantscope/dashboard_shortlists.json")
    use_persisted_ai = cache is None or getattr(cache, "path", None) == dashboard_cache_path
    persisted = AIRecommendationCache().get(agency) if use_persisted_ai else None
    if persisted and persisted.get("ai_status") == "evaluated":
        result = {
            "status": "ready",
            "agency": agency,
            "refreshed_at": persisted.get("refreshed_at"),
            "records": persisted.get("records", []),
        }
        if cache is not None:
            cache.save(
                agency, result["records"], result["refreshed_at"],
                ai_status="evaluated",
            )
        return result
    profile = VERIFIED_GOALS.get(agency)
    if not profile:
        raise DiscoveryError("This agency has no verified strategic goals.")
    try:
        grants = fetch_grants(_goal_query(profile), rows=25)
    except Exception as exc:
        if isinstance(exc, GrantsAPIError):
            raise DiscoveryError(str(exc)) from exc
        raise DiscoveryError("Dashboard opportunity retrieval failed.") from exc
    details_cache = {}
    candidates = rank_grants(grants, agency)
    selected = [grant for grant in candidates if grant.get("id")][:limit]
    for grant in selected:
        try:
            details_cache[str(grant["id"])] = fetch_details(grant["id"])
        except GrantsAPIError:
            continue
    ranked = rank_grants(selected, agency, detail_cache=details_cache)
    records = []
    for grant in ranked:
        details = details_cache.get(str(grant["id"]), {})
        screening = screen_eligibility(details, agency)
        records.append({
            "opportunity_id": str(grant["id"]),
            "title": grant.get("title") or "Untitled grant",
            "federal_agency": grant.get("agency") or grant.get("agencyName") or "Unknown",
            "close_date": grant.get("closeDate"),
            "official_url": details.get(
                "detail_source_url",
                f"https://www.grants.gov/search-results-detail/{grant['id']}",
            ),
            "award_floor": details.get("award_floor"),
            "award_ceiling": details.get("award_ceiling"),
            "description": details.get("description"),
            "eligibility_status": screening["status"],
            "eligibility_reason": screening.get("reason"),
            "eligibility_evidence": screening.get("evidence"),
            "match_score": grant.get("match_score"),
            "match_reasons": grant.get("match_reasons", []),
        })
    records.sort(key=lambda record: (
        record["eligibility_status"] == "Ineligible",
        -(record["match_score"] or 0),
    ))
    refreshed_at = datetime.now(timezone.utc).isoformat()
    if cache is not None:
        cache.save(agency, records, refreshed_at)
    return {"agency": agency, "refreshed_at": refreshed_at, "records": records}
