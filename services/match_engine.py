"""GrantScope matching engine — shared by Dashboard and (later) Search.

Framework-free: no Streamlit imports, so any page or test can call it.

Pipeline (see docs/MATCHING.md):
  1. Retrieve live Grants.gov records with targeted, plan-derived keywords.
  2. Screen with deterministic pass/fail rules: closed, not enough days left
     to apply, applicant types that exclude the agency, below an optional
     minimum award. Screening removes a grant and records why; it never
     changes a score.
  3. Assess Strategic Fit (0-100): a heuristic for *relevance only*, from plan
     terms in the grant's official text, optionally blended with a validated
     Azure OpenAI semantic assessment. Deadline urgency, award size and
     application effort are reported separately and do not change it.
  4. Sort into sections: priority (open, evidence of fit), lower-evidence
     (open, no keyword evidence: low or unassessed, never silently dropped),
     upcoming (forecasted, not yet accepting applications), screened out.

Strategic Fit is not eligibility and not a probability of receiving an award.
"""
import html
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Optional

from services.application_effort import assess_effort
from services.eligibility_assessment import (
    INELIGIBLE, LABELS as ELIGIBILITY_STATUS_LABELS, LIKELY_ELIGIBLE, LIKELY_INELIGIBLE, NEEDS_REVIEW,
    NOT_CHECKED, RANK as ELIGIBILITY_RANK, apply_ai, assess_eligibility,
)

ENGINE_VERSION = "2.0"

# Keyword heuristic points per matched plan term (capped at 100).
FIT_POINTS = {"title_phrase": 40, "title_word": 20, "description_phrase": 20, "description_word": 10}
# Long descriptions mention many topics, so description-only evidence is capped:
# a strong keyword fit requires plan terms in the grant title.
DESCRIPTION_CAP = 40
# Experimental, unvalidated weight of the AI assessment when both are available.
AI_WEIGHT = 0.5
FIT_LEVELS = ((60, "strong", "Strong fit"), (30, "moderate", "Moderate fit"), (1, "low", "Low fit"))

OPEN, FORECASTED, CLOSED, UNKNOWN = "open", "forecasted", "closed", "unknown"
ELIGIBLE_TYPE = LIKELY_ELIGIBLE      # backwards-compatible alias
NOT_ELIGIBLE = INELIGIBLE            # backwards-compatible alias
ELIGIBILITY_LABELS = ELIGIBILITY_STATUS_LABELS
_ELIGIBILITY_RANK = ELIGIBILITY_RANK
PRIORITY, LOW_EVIDENCE, UPCOMING, SCREENED_OUT = "priority", "low_evidence", "upcoming", "screened_out"
LIKELY_INELIGIBLE_SECTION = "likely_ineligible"  # visible, flagged, never a priority recommendation
UPCOMING_LOW = "upcoming_low_evidence"  # forecasted, no plan evidence: counted, not listed


@dataclass
class MatchSettings:
    min_days_left: Optional[int] = 30      # None = any open grant
    min_award: Optional[int] = None        # optional advanced filter on reported award ceilings
    include_unknown_deadline: bool = False
    max_queries: int = 8
    rows_per_query: int = 100              # Grants.gov search2 maximum per request
    detail_limit: int = 60                 # official detail lookups per run
    ai_limit: int = 12                     # AI fit assessments per run (when configured)
    ai_eligibility_limit: int = 15         # AI eligibility interpretations per run (when configured)
    max_workers: int = 6


# --------------------------------------------------------------------------- text

def normalize_text(value):
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def _term_regex(term):
    return re.compile(r"(?<![a-z0-9])" + re.escape(normalize_text(term)) + r"(?:s|es)?(?![a-z0-9])")


def find_terms(text, terms):
    """Return the terms that occur in text as whole words (plural allowed)."""
    normalized = normalize_text(text)
    return [term for term in terms if _term_regex(term).search(normalized)]


# --------------------------------------------------------------------------- dates

_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y")


def parse_date(value):
    """Parse Grants.gov date strings; return None rather than guessing."""
    if not value:
        return None
    raw = str(value).strip()
    match = re.match(r"([A-Za-z]{3,9} \d{1,2}, \d{4})", raw)
    candidates = [match.group(1)] if match else []
    candidates += [raw[:10], raw]
    for candidate in candidates:
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def classify_deadline(hit, details, today):
    """Deterministic open-status classification."""
    status_raw = str(hit.get("oppStatus") or "").strip().lower()
    close = parse_date(hit.get("closeDate"))
    if close is None and details:
        close = parse_date(details.get("close_date_text"))
    days_left = (close - today).days if close else None

    if status_raw in {"closed", "archived"}:
        status, rule = CLOSED, f"Grants.gov status is '{status_raw}'"
    elif close is not None and days_left < 0:
        status, rule = CLOSED, "Closing date has passed"
    elif status_raw == "forecasted":
        status, rule = FORECASTED, "Forecasted: not yet accepting applications; dates are estimates"
    elif status_raw == "posted" and close is not None:
        status, rule = OPEN, "Posted and accepting applications"
    elif status_raw == "posted":
        status, rule = UNKNOWN, "Posted, but no closing date is listed"
    else:
        status, rule = UNKNOWN, "Grants.gov status not recognized"
    return {"status": status, "rule": rule, "close_date": close.isoformat() if close else None,
            "days_left": days_left}


def urgency(deadline):
    """Time pressure, reported separately from relevance."""
    days, status = deadline["days_left"], deadline["status"]
    if status == FORECASTED:
        return {"level": "upcoming", "label": "Not yet open"}
    if days is None:
        return {"level": "unknown", "label": "No closing date listed"}
    if days <= 14:
        return {"level": "urgent", "label": f"{days} days left — urgent"}
    if days <= 30:
        return {"level": "soon", "label": f"{days} days left"}
    return {"level": "comfortable", "label": f"{days} days left"}


# --------------------------------------------------------------------------- eligibility

def screen_eligibility(details, profile, title="", source_url=None, ai=None):
    """Eligibility from structured applicant types AND official notes (see eligibility_assessment).

    A validated AI interpretation may resolve unclear cases but never overrides a
    confirmed restriction. Never returns guaranteed eligibility.
    """
    return apply_ai(assess_eligibility(details, profile, title, source_url), ai)


# --------------------------------------------------------------------------- relevance

def _fit_level(score):
    for threshold, level, label in FIT_LEVELS:
        if score >= threshold:
            return level, label
    return "low", "Low fit"


def keyword_relevance(title, description, profile):
    """Deterministic heuristic: plan terms found in the grant's official text."""
    basis = "title and official description" if description else "title only (description not loaded)"
    if not profile:
        return {"score": None, "matched_goals": [], "matched_terms": [], "basis": basis,
                "reason": "No verified strategic goals for this agency."}
    counted, matched_goals = {}, []
    for goal in profile["goals"]:
        in_title = set(find_terms(title, goal["terms"]))
        in_desc = set(find_terms(description, goal["terms"])) if description else set()
        found = [t for t in goal["terms"] if t in in_title or t in in_desc]
        if found:
            matched_goals.append({
                "goal_id": goal["goal_id"], "label": goal["label"], "quote": goal["quote"],
                "page": goal["page"], "plan_url": profile["plan_url"], "terms": found,
                "title_terms": [t for t in found if t in in_title],
            })
            for term in found:
                counted[term] = counted.get(term, False) or term in in_title
    title_raw = desc_raw = 0
    for term, in_title in counted.items():
        kind = "phrase" if " " in term else "word"
        if in_title:
            title_raw += FIT_POINTS[f"title_{kind}"]
        else:
            desc_raw += FIT_POINTS[f"description_{kind}"]
    score = min(100, title_raw + min(DESCRIPTION_CAP, desc_raw))
    if matched_goals:
        n_title = sum(1 for v in counted.values() if v)
        reason = (f"{len(counted)} plan term(s) across {len(matched_goals)} goal(s), {n_title} in the title. "
                  f"Title phrase {FIT_POINTS['title_phrase']}, title word {FIT_POINTS['title_word']}, "
                  f"description phrase {FIT_POINTS['description_phrase']}, description word "
                  f"{FIT_POINTS['description_word']} (description total capped at {DESCRIPTION_CAP}); "
                  "overall cap 100.")
    elif description:
        reason = "No plan terms in the title or official description (may still be relevant in other words)."
    else:
        reason = "No plan terms in the title; the official description was not loaded."
    return {"score": score, "matched_goals": matched_goals, "matched_terms": sorted(counted),
            "basis": basis, "reason": reason}


def combine_relevance(keyword, ai, description_loaded, profile):
    """Strategic Fit Score: keyword heuristic, blended with a validated AI score if present."""
    ai_ok = bool(ai) and ai.get("status") == "ok"
    if keyword["score"] is None:
        fit, method = None, "none"
    elif ai_ok:
        fit = round((1 - AI_WEIGHT) * keyword["score"] + AI_WEIGHT * ai["score"])
        method = "keyword + AI (experimental 50/50 blend)"
    else:
        fit, method = keyword["score"], "keyword heuristic"
    # Zero keyword overlap is "low" (official text checked) or "unassessed" (only the title
    # was available) — never a definitive exclusion.
    if fit is None:
        level, label = "unassessed", "Fit not assessed"
    elif fit > 0:
        level, label = _fit_level(fit)
    elif description_loaded or ai_ok:
        level, label = "low", "Low fit — no plan evidence found"
    else:
        level, label = "unassessed", "Fit not assessed — description not loaded"
    goals = list(keyword["matched_goals"])
    if ai_ok and profile:
        known = {g["goal_id"] for g in goals}
        for goal in profile["goals"]:
            if goal["goal_id"] in ai["goal_ids"] and goal["goal_id"] not in known:
                goals.append({"goal_id": goal["goal_id"], "label": goal["label"], "quote": goal["quote"],
                              "page": goal["page"], "plan_url": profile["plan_url"], "terms": [],
                              "title_terms": [], "via_ai": True})
    return {"fit_score": fit, "method": method, "level": level, "label": label,
            "keyword": keyword, "ai": ai, "matched_goals": goals}


# --------------------------------------------------------------------------- funding

def _reported(amount):
    # Grants.gov uses 0 or 1 as placeholders when no amount is set.
    return amount is not None and amount > 1


def funding_summary(details):
    """Accurate, informational funding description. Not used for scoring."""
    if not details:
        return {"display": "Not loaded", "floor": None, "ceiling": None, "estimated_total": None,
                "number_of_awards": None, "reported": False, "note": "Official details not loaded."}
    floor, ceiling = details.get("award_floor"), details.get("award_ceiling")
    total, awards = details.get("estimated_funding"), details.get("number_of_awards")
    if _reported(floor) and _reported(ceiling):
        display = f"${floor:,.0f} – ${ceiling:,.0f} per award"
    elif _reported(ceiling):
        display = f"Up to ${ceiling:,.0f} per award"
    elif _reported(floor):
        display = f"From ${floor:,.0f} per award"
    elif _reported(total):
        display = f"${total:,.0f} total program funding"
    else:
        display = "Not reported"
    extras = []
    if _reported(total) and display != f"${total:,.0f} total program funding":
        extras.append(f"estimated total program funding ${total:,.0f}")
    if _reported(awards):
        extras.append(f"about {awards:,.0f} award(s) expected")
    note = "Award ceilings are maximums, not guaranteed amounts."
    if extras:
        note = "Grants.gov lists " + " and ".join(extras) + ". " + note
    return {"display": display, "floor": floor if _reported(floor) else None,
            "ceiling": ceiling if _reported(ceiling) else None,
            "estimated_total": total if _reported(total) else None,
            "number_of_awards": awards if _reported(awards) else None,
            "reported": display != "Not reported", "note": note,
            "cost_sharing": details.get("cost_sharing")}


# --------------------------------------------------------------------------- evaluation

def _short_goal(label):
    return label.replace(" – ", ": ", 1)


def why_this_matters(profile, relevance):
    """One concise sentence for the card."""
    goals = relevance["matched_goals"]
    if not profile:
        return "No verified strategic goals for this agency."
    ai = relevance.get("ai") or {}
    if ai.get("status") == "ok" and ai.get("explanation") and ai.get("score", 0) > 20:
        return ai["explanation"]
    if not goals:
        return relevance["keyword"]["reason"]
    first = goals[0]
    terms = first["title_terms"] or first["terms"]
    more = f" (+{len(goals) - 1} more goal{'s' if len(goals) > 2 else ''})" if len(goals) > 1 else ""
    terms_text = f" — mentions {', '.join(terms[:3])}" if terms else ""
    return f"Supports {profile['short_name']} {_short_goal(first['label'])}{terms_text}{more}."


def evaluate_grant(hit, profile, details, settings, today, ai_result=None, announcement=None,
                   ai_eligibility=None):
    """Screen, assess and classify one Grants.gov search hit."""
    gid = str(hit.get("id") or "").strip()
    title = html.unescape(str(hit.get("title") or "")).strip() or "Untitled opportunity"
    deadline = classify_deadline(hit, details, today)
    source_url = f"https://www.grants.gov/search-results-detail/{gid}" if gid else None
    eligibility = screen_eligibility(details, profile, title, source_url, ai_eligibility)
    description = (details or {}).get("description") or ""
    keyword = keyword_relevance(title, description, profile)
    relevance = combine_relevance(keyword, ai_result, bool(description), profile)
    funding = funding_summary(details)
    effort = assess_effort(details, *(announcement or (None, None)))

    reasons = []  # (code, human-readable text)
    if deadline["status"] == CLOSED:
        reasons.append(("closed", f"Closed: {deadline['rule']}"))
    elif (deadline["status"] == OPEN and settings.min_days_left is not None
          and deadline["days_left"] < settings.min_days_left):
        reasons.append(("not_enough_time",
                        f"Only {deadline['days_left']} days left (you asked for at least {settings.min_days_left})"))
    if deadline["status"] == UNKNOWN and not settings.include_unknown_deadline:
        reasons.append(("unknown_deadline_hidden", "No closing date listed (hidden by your settings)"))
    if eligibility["status"] == INELIGIBLE:  # confirmed official restriction only
        reasons.append(("not_eligible", eligibility["summary"]))
    if settings.min_award and funding["ceiling"] is not None and funding["ceiling"] < settings.min_award:
        reasons.append(("below_min_award",
                        f"Award ceiling ${funding['ceiling']:,.0f} is below your ${settings.min_award:,.0f} minimum"))

    if reasons:
        section = SCREENED_OUT
    elif eligibility["status"] == LIKELY_INELIGIBLE:
        section = LIKELY_INELIGIBLE_SECTION
    elif deadline["status"] == FORECASTED:
        section = UPCOMING if relevance["fit_score"] else UPCOMING_LOW
    elif relevance["fit_score"]:
        section = PRIORITY
    else:
        section = LOW_EVIDENCE

    data_gaps = []
    if not details:
        data_gaps.append("Official details not loaded: funding, eligibility and effort are unverified")
    else:
        if not funding["reported"]:
            data_gaps.append("Award amount not reported on Grants.gov")
        if not description:
            data_gaps.append("No official description available")
    if deadline["days_left"] is None:
        data_gaps.append("Closing date not listed")
    if settings.min_award and details and funding["ceiling"] is None:
        data_gaps.append("Award ceiling not reported, so your minimum-award filter could not be applied")

    return {
        "id": gid,
        "number": hit.get("number"),
        "title": title,
        "federal_agency": hit.get("agency") or hit.get("agencyCode") or "Unknown federal agency",
        "source_url": source_url,
        "matched_queries": list(hit.get("_matched_queries", [])),
        "section": section,
        "deadline": deadline,
        "urgency": urgency(deadline),
        "eligibility": eligibility,
        "funding": funding,
        "relevance": relevance,
        "fit_score": relevance["fit_score"],
        "effort": effort,
        "why": why_this_matters(profile, relevance),
        "details_loaded": bool(details),
        "data_gaps": data_gaps,
        "screening": {"passed": not reasons, "codes": [c for c, _ in reasons],
                      "reasons": [text for _, text in reasons]},
    }


def rank_results(records):
    """Highest Strategic Fit first; ties favor clearer eligibility. Deadline is not a ranking factor."""
    return sorted(records, key=lambda r: (
        -(r["fit_score"] or 0),
        _ELIGIBILITY_RANK[r["eligibility"]["status"]],
        r["title"].lower(),
        r["id"],
    ))


# --------------------------------------------------------------------------- retrieval

def build_queries(profile, extra_keywords=(), max_queries=8):
    """Search keywords: user keywords first, then multi-word plan terms by goal."""
    queries, seen = [], set()

    def add(text, source):
        key = normalize_text(text)
        if key and key not in seen and len(queries) < max_queries:
            seen.add(key)
            queries.append({"text": text.strip(), "source": source})

    for keyword in extra_keywords:
        add(keyword, "user")
    if profile:
        per_goal = [[t for t in g["terms"] if " " in t] or g["terms"][:1] for g in profile["goals"]]
        depth = max((len(terms) for terms in per_goal), default=0)
        for i in range(depth):  # round-robin so every goal is represented
            for goal, terms in zip(profile["goals"], per_goal):
                if i < len(terms):
                    add(terms[i], goal["goal_id"])
    return queries


def _safe_call(fn, *args):
    try:
        return fn(*args), None
    except Exception as exc:  # noqa: BLE001 - one failing call must not break the run
        return None, f"{type(exc).__name__}: {exc}"


def run_matching(profile, settings=None, *, search_fn, details_fn, today=None, extra_keywords=(),
                 details_cache=None, ai_evaluator=None, announcements=None, eligibility_evaluator=None):
    """Retrieve, screen, assess and rank grants for one agency profile.

    search_fn(keyword, rows) -> list of Grants.gov search hits
    details_fn(opportunity_id) -> normalized details (services.opportunity_details)
    ai_evaluator(record, profile, details) -> AI fit result (optional; services.ai_matching)
    eligibility_evaluator(record, profile, details) -> AI eligibility result (optional; services.ai_eligibility)
    announcements: {grant_id: (announcement_text, url)} from on-demand NOFO analysis
    Returns a JSON-serializable dict (schema in docs/MATCHING.md).
    """
    settings = settings or MatchSettings()
    today = today or date.today()
    details_cache = {} if details_cache is None else details_cache
    announcements = announcements or {}
    queries = build_queries(profile, extra_keywords, settings.max_queries)
    errors = []

    with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
        outcomes = list(pool.map(lambda q: _safe_call(search_fn, q["text"], settings.rows_per_query), queries))

    candidates, coverage = {}, []
    for query, (hits, error) in zip(queries, outcomes):
        hits = hits or []
        coverage.append({"query": query["text"], "source": query["source"], "retrieved": len(hits),
                         "cap_reached": len(hits) >= settings.rows_per_query, "error": error})
        if error:
            errors.append(f"Search '{query['text']}' failed: {error}")
        for hit in hits:
            gid = str(hit.get("id") or "").strip()
            if gid:
                entry = candidates.setdefault(gid, dict(hit, _matched_queries=[]))
                entry["_matched_queries"].append(query["text"])

    # Load official details for a deterministic shortlist: not closed, title evidence first, then
    # grants found by several queries. The shortlist does not depend on the days-left filter, and
    # only shortlisted details are used, so results never depend on what an earlier run cached
    # (a stricter filter always returns a subset of a looser one).
    shortlist, actionable = [], 0
    for gid, hit in candidates.items():
        deadline = classify_deadline(hit, None, today)
        if deadline["status"] == CLOSED:
            continue
        if not (deadline["status"] == OPEN and settings.min_days_left is not None
                and deadline["days_left"] < settings.min_days_left):
            actionable += 1
        title_score = keyword_relevance(html.unescape(str(hit.get("title") or "")), "", profile)["score"] or 0
        shortlist.append((-title_score, -len(hit["_matched_queries"]), deadline["status"] != OPEN, gid))
    shortlist.sort()
    selected = {gid for *_, gid in shortlist[:settings.detail_limit]}
    to_fetch = sorted(gid for gid in selected if gid not in details_cache)
    if to_fetch:
        with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
            fetched = list(pool.map(lambda gid: _safe_call(details_fn, gid), to_fetch))
        for gid, (details, error) in zip(to_fetch, fetched):
            if error:
                errors.append(f"Details for {gid} failed: {error}")
            else:
                details_cache[gid] = details

    ai_fit, ai_elig = {}, {}

    def details_for(gid):
        return details_cache.get(gid) if gid in selected else None

    def evaluate(gid):
        return evaluate_grant(candidates[gid], profile, details_for(gid), settings, today,
                              ai_result=ai_fit.get(gid), announcement=announcements.get(gid),
                              ai_eligibility=ai_elig.get(gid))

    records = {gid: evaluate(gid) for gid in candidates}

    def run_ai(evaluator, chosen, store):
        summary = {"status": "ok", "evaluated": 0, "accepted": 0, "rejected": 0, "errors": 0,
                   "model": getattr(evaluator, "model_label", None)}
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(lambda r: _safe_call(evaluator, r, profile, details_for(r["id"])), chosen))
        for record, (result, error) in zip(chosen, outcomes):
            result = result or {"status": "error", "errors": [error]}
            store[record["id"]] = result
            summary["evaluated"] += 1
            status = result.get("status")
            key = "accepted" if status == "ok" else "rejected" if status == "rejected" else "errors"
            summary[key] += 1
        if summary["evaluated"] and summary["errors"] == summary["evaluated"]:
            summary["status"] = "error"
        elif summary["errors"] or summary["rejected"]:
            summary["status"] = "partial"
        return summary

    disabled = {"status": "disabled", "evaluated": 0, "accepted": 0, "rejected": 0, "errors": 0, "model": None}
    ai_summary, elig_summary = dict(disabled), dict(disabled)
    if profile and eligibility_evaluator is not None:
        # Interpret eligibility where rules are not conclusive. Confirmed restrictions and
        # grants screened out for other reasons are never sent to the model.
        open_sections = (PRIORITY, UPCOMING, LIKELY_INELIGIBLE_SECTION)
        candidates_for_elig = [r for r in records.values()
                               if r["section"] in open_sections and r["details_loaded"]
                               and r["eligibility"]["status"] in (NEEDS_REVIEW, LIKELY_ELIGIBLE, LIKELY_INELIGIBLE)]
        chosen = rank_results(candidates_for_elig)[:settings.ai_eligibility_limit]
        elig_summary = run_ai(eligibility_evaluator, chosen, ai_elig)
    if profile and ai_evaluator is not None:
        # Top keyword matches plus a few zero-keyword candidates with official text (false-negative check).
        open_records = [r for r in records.values() if r["section"] in (PRIORITY, UPCOMING)]
        rescue = [r for r in records.values() if r["section"] == LOW_EVIDENCE and r["details_loaded"]]
        rescue_n = min(4, settings.ai_limit // 3)
        chosen = rank_results(open_records)[:settings.ai_limit - rescue_n] + rescue[:rescue_n]
        ai_summary = run_ai(ai_evaluator, chosen, ai_fit)
    if ai_fit or ai_elig:
        records = {gid: evaluate(gid) for gid in candidates}

    by_section = {s: [] for s in (PRIORITY, LOW_EVIDENCE, UPCOMING, UPCOMING_LOW, LIKELY_INELIGIBLE_SECTION,
                                  SCREENED_OUT)}
    for record in records.values():
        by_section[record["section"]].append(record)

    reason_counts = {}
    for record in by_section[SCREENED_OUT]:
        code = record["screening"]["codes"][0]
        reason_counts[code] = reason_counts.get(code, 0) + 1

    return {
        "engine_version": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "agency": profile["name"] if profile else None,
        "settings": asdict(settings),
        "fit_points": dict(FIT_POINTS),
        "ai_weight": AI_WEIGHT,
        "queries": coverage,
        "ai": ai_summary,
        "ai_eligibility": elig_summary,
        "stats": {
            "unique_candidates": len(candidates),
            "actionable_candidates": actionable,
            "details_loaded": sum(1 for r in records.values() if r["details_loaded"]),
            "details_considered": len(selected),
            "priority": len(by_section[PRIORITY]),
            "low_evidence": len(by_section[LOW_EVIDENCE]),
            "upcoming": len(by_section[UPCOMING]),
            "upcoming_low_evidence": len(by_section[UPCOMING_LOW]),
            "likely_ineligible": len(by_section[LIKELY_INELIGIBLE_SECTION]),
            "screened_out": len(by_section[SCREENED_OUT]),
            "screened_out_by_reason": reason_counts,
            "capped_queries": sum(1 for q in coverage if q["cap_reached"]),
            "possibly_incomplete": any(q["cap_reached"] or q["error"] for q in coverage),
        },
        "results": rank_results(by_section[PRIORITY]),
        "low_evidence": rank_results(by_section[LOW_EVIDENCE]),
        "upcoming": rank_results(by_section[UPCOMING]),
        "likely_ineligible": rank_results(by_section[LIKELY_INELIGIBLE_SECTION]),
        "screened_out": by_section[SCREENED_OUT],
        "errors": errors,
    }
