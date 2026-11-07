"""GrantScope matching engine — shared by Dashboard and (later) Search.

Framework-free: no Streamlit imports, so any page or test can call it.

Pipeline (see docs/MATCHING.md):
  1. Retrieve live Grants.gov records for several plan-derived keywords.
  2. Screen with hard rules: closed / outside the deadline window /
     confirmed ineligible applicant type / no plan-goal evidence -> excluded.
     Screening never "adjusts" a score; it removes the grant and records why.
  3. Score the remaining grants (0-100) from three transparent components:
     strategic alignment (60), deadline actionability (20), funding fit (20).

The Match Score measures fit with an agency's published strategic goals and
practical actionability. It is NOT a probability of receiving an award.
"""
import html
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone

ENGINE_VERSION = "1.0"
WEIGHTS = {"strategic_alignment": 60, "deadline": 20, "funding": 20}
# Points per matched plan term. Terms found in the grant title count fully;
# terms found only in the (often long) official description count half.
PHRASE_POINTS = 20  # multi-word plan phrase
WORD_POINTS = 10    # single-word plan term

# Grants.gov applicant type codes (fetchOpportunity -> applicantTypes[].id).
APPLICANT_TYPE_IDS = {
    "State governments": "00",
    "County governments": "01",
    "City or township governments": "02",
    "Special district governments": "04",
    "Independent school districts": "05",
    "Public and State controlled institutions of higher education": "06",
}
UNRESTRICTED_ID = "99"
OTHERS_ID = "25"
RESTRICTION_PATTERN = re.compile(
    r"\bonly\b[^.]{0,160}?\b(?:eligible|may apply|can apply|are eligible)\b", re.IGNORECASE
)

# Regions outside North Carolina that often signal a geographically limited
# program. Used only as a caution flag, never to exclude a grant.
OTHER_REGION_HINTS = (
    "great lakes", "great plains", "colorado river", "pacific", "alaska", "hawaii",
    "puerto rico", "guam", "chesapeake", "gulf of maine", "rocky mountain", "mississippi river",
    "california", "texas", "florida", "puget sound", "columbia river", "new england",
)

OPEN, FORECASTED, CLOSED, UNKNOWN = "open", "forecasted", "closed", "unknown"
ELIGIBLE_TYPE, NEEDS_REVIEW, NOT_ELIGIBLE, NOT_CHECKED = (
    "eligible_applicant_type", "needs_review", "not_eligible", "not_checked",
)
ELIGIBILITY_LABELS = {
    ELIGIBLE_TYPE: "Eligible applicant type listed",
    NEEDS_REVIEW: "Needs review",
    NOT_ELIGIBLE: "Not an eligible applicant type",
    NOT_CHECKED: "Eligibility not checked",
}
_ELIGIBILITY_RANK = {ELIGIBLE_TYPE: 0, NEEDS_REVIEW: 1, NOT_CHECKED: 2, NOT_ELIGIBLE: 3}


@dataclass
class MatchSettings:
    horizon_days: int = 90            # only grants closing within this many days
    min_award: int = 0                # preferred minimum award ceiling ($)
    include_forecasted: bool = True
    include_unknown_deadline: bool = False
    max_queries: int = 8
    rows_per_query: int = 100         # Grants.gov search2 maximum per request
    detail_limit: int = 40            # official detail lookups per run
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


def classify_deadline(hit, details, today, horizon_days):
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
        status, rule = OPEN, "Posted and closing date is today or later"
    elif status_raw == "posted":
        status, rule = UNKNOWN, "Posted, but no closing date is listed"
    else:
        status, rule = UNKNOWN, "Grants.gov status not recognized"

    within = None if days_left is None else 0 <= days_left <= horizon_days
    return {
        "status": status,
        "rule": rule,
        "close_date": close.isoformat() if close else None,
        "days_left": days_left,
        "within_horizon": within,
    }


# --------------------------------------------------------------------------- eligibility

def screen_eligibility(details, profile):
    """Screen applicant eligibility from official details.

    Never returns a definitive "eligible": the best outcome is that the agency's
    applicant category is listed, which still requires confirming the notice.
    """
    if not details:
        return {"status": NOT_CHECKED, "label": ELIGIBILITY_LABELS[NOT_CHECKED],
                "reason": "Official eligibility details have not been loaded for this grant.",
                "evidence": None, "applicant_types": []}

    types = details.get("applicant_types") or []
    descriptions = [t.get("description", "") for t in types if t.get("description")]
    ids = {t.get("id") for t in types}
    text = details.get("eligibility_text") or ""
    categories = (profile or {}).get("applicant_categories") or ["State governments"]
    wanted_ids = {APPLICANT_TYPE_IDS[c] for c in categories if c in APPLICANT_TYPE_IDS}
    wanted_names = {c.lower() for c in categories}

    def result(status, reason, evidence=None):
        return {"status": status, "label": ELIGIBILITY_LABELS[status], "reason": reason,
                "evidence": evidence, "applicant_types": descriptions}

    listed = (ids & wanted_ids) or any(d.lower() in wanted_names for d in descriptions)
    unrestricted = UNRESTRICTED_ID in ids or any(d.lower().startswith("unrestricted") for d in descriptions)
    restriction = RESTRICTION_PATTERN.search(text)

    if not types and not text.strip():
        return result(NEEDS_REVIEW, "Grants.gov lists no applicant types or eligibility notes.")
    if listed or unrestricted:
        which = ", ".join(categories) if listed else "Unrestricted"
        if restriction:
            return result(NEEDS_REVIEW,
                          f"{which} is listed, but the eligibility notes contain a restriction.",
                          restriction.group(0).strip())
        return result(ELIGIBLE_TYPE,
                      f"Applicant type '{which}' is listed. Confirm remaining requirements in the notice.")
    if OTHERS_ID in ids or not types:
        evidence = restriction.group(0).strip() if restriction else (text[:240] or None)
        return result(NEEDS_REVIEW, "Applicant type is 'Others' or unspecified; read the eligibility notes.",
                      evidence)
    return result(NOT_ELIGIBLE,
                  f"Listed applicant types do not include {', '.join(categories)}.",
                  "; ".join(descriptions))


# --------------------------------------------------------------------------- scoring

def _term_points(term, in_title):
    base = PHRASE_POINTS if " " in term else WORD_POINTS
    return base if in_title else base // 2


def score_alignment(title, description, profile):
    """Strategic alignment: plan-goal terms found in the grant's official text."""
    basis = "title and official description" if description else "title only (details not loaded)"
    max_points = WEIGHTS["strategic_alignment"]
    if not profile:
        return {"points": 0, "max": max_points, "matched_goals": [], "matched_terms": [],
                "basis": basis, "reason": "No verified strategic goals for this agency."}

    counted, matched_goals = {}, []  # term -> found in title?
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
    raw = sum(_term_points(term, in_title) for term, in_title in counted.items())
    points = min(max_points, raw)
    if matched_goals:
        n_title = sum(1 for v in counted.values() if v)
        reason = (f"{len(counted)} plan term(s) across {len(matched_goals)} goal(s); {n_title} in the title. "
                  f"Title: {PHRASE_POINTS} pts per phrase, {WORD_POINTS} per word; description-only: half. "
                  f"Max {max_points}.")
    else:
        reason = "No plan-goal terms found in the grant text."
    return {"points": points, "max": max_points, "matched_goals": matched_goals,
            "matched_terms": sorted(counted), "basis": basis, "reason": reason}


def score_deadline(deadline):
    max_points = WEIGHTS["deadline"]
    days, status = deadline["days_left"], deadline["status"]
    if status == FORECASTED:
        return {"points": 12, "max": max_points,
                "reason": "Forecasted: time to prepare, but dates are estimates."}
    if days is None:
        return {"points": 6, "max": max_points, "reason": "Closing date not listed; verify on Grants.gov."}
    if days >= 30:
        points, why = 20, "30+ days to prepare an application."
    elif days >= 14:
        points, why = 14, "14-29 days left."
    elif days >= 7:
        points, why = 8, "7-13 days left; tight timeline."
    else:
        points, why = 3, "Fewer than 7 days left."
    return {"points": points, "max": max_points, "reason": f"Closes in {days} day(s). {why}"}


def _reported(amount):
    # Grants.gov uses 0 or 1 as placeholders when no amount is set.
    return amount is not None and amount > 1


def score_funding(details, min_award):
    max_points = WEIGHTS["funding"]
    if not details:
        return {"points": 8, "max": max_points, "reason": "Award amount not loaded."}
    ceiling, floor = details.get("award_ceiling"), details.get("award_floor")
    if _reported(ceiling):
        if ceiling >= min_award:
            why = f"Award ceiling ${ceiling:,.0f}" + (
                f" meets your ${min_award:,.0f} minimum." if min_award else " reported.")
            return {"points": 20, "max": max_points, "reason": why}
        return {"points": 5, "max": max_points,
                "reason": f"Award ceiling ${ceiling:,.0f} is below your ${min_award:,.0f} minimum."}
    if _reported(floor) and floor >= min_award:
        return {"points": 20, "max": max_points, "reason": f"Award floor ${floor:,.0f} meets your minimum."}
    return {"points": 8, "max": max_points, "reason": "Award amount not reported by Grants.gov."}


# --------------------------------------------------------------------------- evaluation

def _short_goal(label):
    return label.split(" – ")[0] if " – " in label else label


def build_explanation(profile, alignment, deadline, funding, eligibility):
    parts = []
    if alignment["matched_goals"]:
        goals = "; ".join(
            f"{_short_goal(g['label'])} ({', '.join(g['terms'])})" for g in alignment["matched_goals"][:3]
        )
        parts.append(f"Supports {profile['short_name']} {goals}.")
    parts.append(deadline_phrase(deadline) + ".")
    parts.append(funding["reason"])
    parts.append(eligibility["label"] + ".")
    return " ".join(parts)


def deadline_phrase(deadline):
    if deadline["status"] == FORECASTED:
        return "Forecasted opportunity" + (
            f", estimated close {deadline['close_date']}" if deadline["close_date"] else "")
    if deadline["days_left"] is None:
        return "Closing date not listed"
    return f"Closes {deadline['close_date']} ({deadline['days_left']} days)"


def evaluate_grant(hit, profile, details, settings, today):
    """Screen and score one Grants.gov search hit. Returns a result record."""
    gid = str(hit.get("id") or "").strip()
    deadline = classify_deadline(hit, details, today, settings.horizon_days)
    eligibility = screen_eligibility(details, profile)
    alignment = score_alignment(html.unescape(str(hit.get("title") or "")),
                                (details or {}).get("description"), profile)

    reasons = []  # (code, human-readable text)
    if deadline["status"] == CLOSED:
        reasons.append(("closed", f"Closed: {deadline['rule']}"))
    elif deadline["within_horizon"] is False:
        reasons.append(("outside_window",
                        f"Closes in {deadline['days_left']} days, outside the {settings.horizon_days}-day window"))
    if deadline["status"] == FORECASTED and not settings.include_forecasted:
        reasons.append(("forecasted_hidden", "Forecasted grants are hidden by your settings"))
    if deadline["status"] == UNKNOWN and not settings.include_unknown_deadline:
        reasons.append(("unknown_deadline_hidden", "Closing date unknown and hidden by your settings"))
    if eligibility["status"] == NOT_ELIGIBLE:
        reasons.append(("not_eligible", f"Not eligible: {eligibility['reason']}"))
    if alignment["points"] == 0:
        reasons.append(("no_alignment_evidence", "No strategic-goal terms found in the title and official description"
                        if details else "No strategic-goal terms in the title (official description not loaded)"))

    data_gaps = []
    if not details:
        data_gaps.append("Official details not loaded: award amount and eligibility unverified")
    else:
        if not _reported(details.get("award_ceiling")) and not _reported(details.get("award_floor")):
            data_gaps.append("Award amount not reported")
        if not details.get("description"):
            data_gaps.append("No official description available")
    if deadline["days_left"] is None:
        data_gaps.append("Closing date not listed")
    region_flags = find_terms(hit.get("title"), OTHER_REGION_HINTS)
    if region_flags:
        data_gaps.append(f"Title mentions {', '.join(region_flags)}: check whether NC applicants qualify")

    record = {
        "id": gid,
        "number": hit.get("number"),
        "title": html.unescape(str(hit.get("title") or "")).strip() or "Untitled opportunity",
        "federal_agency": hit.get("agency") or hit.get("agencyCode") or "Unknown federal agency",
        "source_url": f"https://www.grants.gov/search-results-detail/{gid}" if gid else None,
        "matched_queries": list(hit.get("_matched_queries", [])),
        "deadline": deadline,
        "eligibility": eligibility,
        "award": {
            "floor": (details or {}).get("award_floor"),
            "ceiling": (details or {}).get("award_ceiling"),
            "estimated_total": (details or {}).get("estimated_funding"),
            "cost_sharing": (details or {}).get("cost_sharing"),
            "loaded": bool(details),
        },
        "alignment": alignment,
        "details_loaded": bool(details),
        "data_gaps": data_gaps,
        "screening": {"passed": not reasons, "codes": [c for c, _ in reasons],
                      "reasons": [text for _, text in reasons]},
        "match_score": None,
        "score_breakdown": None,
        "explanation": None,
    }
    if reasons:
        return record

    funding = score_funding(details, settings.min_award)
    timing = score_deadline(deadline)
    record["score_breakdown"] = {
        "strategic_alignment": {k: alignment[k] for k in ("points", "max", "reason")},
        "deadline": timing,
        "funding": funding,
    }
    record["match_score"] = alignment["points"] + timing["points"] + funding["points"]
    record["explanation"] = build_explanation(profile, alignment, deadline, funding, eligibility)
    return record


def rank_results(records):
    """Highest Match Score first; ties favor stronger eligibility, then sooner deadline."""
    return sorted(records, key=lambda r: (
        -(r["match_score"] or 0),
        _ELIGIBILITY_RANK[r["eligibility"]["status"]],
        r["deadline"]["days_left"] if r["deadline"]["days_left"] is not None else 10 ** 6,
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
    except Exception as exc:  # noqa: BLE001 - one failing query must not break the run
        return None, f"{type(exc).__name__}: {exc}"


def run_matching(profile, settings=None, *, search_fn, details_fn, today=None,
                 extra_keywords=(), details_cache=None):
    """Retrieve, screen, score and rank grants for one agency profile.

    search_fn(keyword, rows) -> list of Grants.gov search hits
    details_fn(opportunity_id) -> normalized details (services.opportunity_details)
    Returns a JSON-serializable dict (schema in docs/MATCHING.md).
    """
    settings = settings or MatchSettings()
    today = today or date.today()
    details_cache = {} if details_cache is None else details_cache
    queries = build_queries(profile, extra_keywords, settings.max_queries)
    errors = []

    with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
        outcomes = list(pool.map(lambda q: _safe_call(search_fn, q["text"], settings.rows_per_query), queries))

    candidates = {}
    coverage = []
    for query, (hits, error) in zip(queries, outcomes):
        hits = hits or []
        coverage.append({"query": query["text"], "source": query["source"], "retrieved": len(hits),
                         "cap_reached": len(hits) >= settings.rows_per_query, "error": error})
        if error:
            errors.append(f"Search '{query['text']}' failed: {error}")
        for hit in hits:
            gid = str(hit.get("id") or "").strip()
            if not gid:
                continue
            entry = candidates.setdefault(gid, dict(hit, _matched_queries=[]))
            entry["_matched_queries"].append(query["text"])

    # Load official details only for the most promising date-eligible candidates.
    def prelim(hit):
        deadline = classify_deadline(hit, None, today, settings.horizon_days)
        alignment = score_alignment(hit.get("title"), "", profile)
        return deadline, alignment

    shortlist = []
    for hit in candidates.values():
        deadline, alignment = prelim(hit)
        if deadline["status"] == CLOSED or deadline["within_horizon"] is False:
            continue
        shortlist.append((-alignment["points"], -len(hit["_matched_queries"]),
                          deadline["days_left"] if deadline["days_left"] is not None else 10 ** 6,
                          str(hit["id"])))
    shortlist.sort()
    to_fetch = [gid for *_, gid in shortlist if gid not in details_cache][:settings.detail_limit]
    if to_fetch:
        with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
            fetched = list(pool.map(lambda gid: _safe_call(details_fn, gid), to_fetch))
        for gid, (details, error) in zip(to_fetch, fetched):
            if error:
                errors.append(f"Details for {gid} failed: {error}")
            else:
                details_cache[gid] = details

    records = [evaluate_grant(hit, profile, details_cache.get(gid), settings, today)
               for gid, hit in candidates.items()]
    passed = rank_results([r for r in records if r["screening"]["passed"]])
    screened_out = [r for r in records if not r["screening"]["passed"]]

    reason_counts = {}
    for record in screened_out:
        code = record["screening"]["codes"][0]
        reason_counts[code] = reason_counts.get(code, 0) + 1

    return {
        "engine_version": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "agency": profile["name"] if profile else None,
        "settings": asdict(settings),
        "weights": dict(WEIGHTS),
        "queries": coverage,
        "stats": {
            "unique_candidates": len(candidates),
            "details_loaded": sum(1 for r in records if r["details_loaded"]),
            "passed_screening": len(passed),
            "screened_out": len(screened_out),
            "screened_out_by_reason": reason_counts,
            "possibly_incomplete": any(q["cap_reached"] or q["error"] for q in coverage),
        },
        "results": passed,
        "screened_out": screened_out,
        "errors": errors,
    }
