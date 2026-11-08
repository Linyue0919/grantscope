"""Thin adapter: backend match results -> OpportunityView (spec section 13).

This is the ONLY place the UI reads backend data. It never changes scores or order,
never calls the network or an LLM, and never fabricates values: anything it cannot
fill from existing output falls back to "Not stated", None or an empty list.
Quotes come only from the backend's verified quotes (plan goal quotes, validated AI
evidence, official eligibility text).
"""
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
import re

from ui.brief_sections import SECTION_RULES, assign_section, fit_tier

CONFIRMED, LIKELY, NOT_STATED = "Confirmed", "Likely", "Not stated"
MARKS = {CONFIRMED: "●", LIKELY: "◐", NOT_STATED: "○"}
RECOMMENDATION_LABELS = {"top": "Top candidate", "check": "Needs a quick check",
                         "soon": "Opening soon", "lower": "Lower priority"}


@dataclass
class OpportunityView:
    id: str
    title: str
    short_name: str
    agency_full_name: str
    opportunity_number: str = None
    status: str = "open"                      # open | forecasted | closed
    backend_section: str = None               # priority | low_evidence | upcoming | likely_ineligible
    deadline_date: date = None
    days_left: int = None
    is_rolling: bool = False
    rolling_until: date = None
    submission_type: str = NOT_STATED
    submission_status: str = NOT_STATED
    fit_score: int = None
    fit_tier: str = "Low"                     # Strong | Moderate | Low (backend level names)
    fit_level: str = "Indirect"               # Direct | Related | Indirect
    matched_goals: list = field(default_factory=list)   # [{number, title, page, label}]
    fit_reasons: list = field(default_factory=list)
    reason_sentence: str = ""
    plan_quote: str = None
    plan_quote_goal: str = None
    grant_purpose_quote: str = None
    eligibility_status: str = NOT_STATED      # Confirmed | Likely | Not stated
    eligibility_short: str = "Eligibility not stated"
    eligibility_conclusion: str = ""
    eligibility_quote: str = None
    eligibility_source: str = None
    eligibility_source_url: str = None
    eligibility_positive: bool = False        # applicant types / notes name state governments
    eligibility_restricted: bool = False      # explicit conflicting restriction in official text
    region_flags: list = field(default_factory=list)     # title names a region outside NC
    disqualifiers: list = field(default_factory=list)
    award_text: str = NOT_STATED
    award_status: str = NOT_STATED
    award_chip: str = NOT_STATED
    expected_awards_text: str = "number of awards not stated"
    expected_awards_status: str = NOT_STATED
    cost_share_text: str = NOT_STATED
    cost_share_status: str = NOT_STATED
    effort_level: str = "Not enough info"
    effort_status: str = NOT_STATED
    effort_note: str = ""
    effort_drivers: list = field(default_factory=list)   # [{label, value, status}]
    known_blocker: str = None
    section: str = "lower"
    recommendation_label: str = ""
    recommendation_sentence: str = ""
    unclear_reason: str = None
    why_lower: str = None
    next_steps: list = field(default_factory=list)
    officer_questions: list = field(default_factory=list)
    grants_gov_url: str = None
    nofo_url: str = None
    plan_url: str = None
    plan_page: int = None
    plan_name: str = None
    retrieved_at: str = None
    ai_assisted: bool = False

    def to_dict(self):
        data = asdict(self)
        for key in ("deadline_date", "rolling_until"):
            if data[key]:
                data[key] = data[key].isoformat()
        return data


# --------------------------------------------------------------------------- helpers

def mark(status):
    return MARKS.get(status, "○")


def fmt_date(value):
    return f"{value:%b} {value.day}, {value.year}" if value else "Not stated"


def fmt_money(amount):
    if amount is None:
        return None
    if amount >= 1_000_000:
        text = f"{amount / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"${text}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.0f}K"
    return f"${amount:,.0f}"


def agency_display_name(name):
    """'Department of Environmental Quality' -> 'NC Department of Environmental Quality'."""
    name = (name or "").strip()
    return name if re.match(r"^(NC|N\.C\.|North Carolina)\b", name) else f"NC {name}"


def short_name(title):
    text = re.sub(r"^\s*(?:FY\s?\d{2,4}(?:\s?[-–/]\s?(?:FY\s?)?\d{2,4})?|[A-Z]\d{2}[A-Z]{2}\d{3,}|[A-Z]{2,}-[\w-]+)\s*[:\-–]?\s*",
                  "", title or "").strip() or (title or "")
    if len(text) <= 48:
        return text
    return text[:46].rsplit(" ", 1)[0].rstrip(",:;–-") + "…"


def _parse_goal(goal):
    label = goal.get("label") or ""
    m = re.match(r"Goal\s*(\d+)?\s*[–-]\s*(.+)", label)
    number = int(m.group(1)) if m and m.group(1) else None
    title = (m.group(2) if m else label).strip()
    named = f"Goal {number}: {title}" if number else title
    return {"number": number, "title": title, "page": goal.get("page"), "label": named,
            "terms": goal.get("terms") or [], "title_terms": goal.get("title_terms") or [],
            "quote": goal.get("quote"), "plan_url": goal.get("plan_url"), "via_ai": bool(goal.get("via_ai"))}


def _parse_iso(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


# --------------------------------------------------------------------------- eligibility

def _eligibility(record):
    e = record.get("eligibility") or {}
    status = e.get("status")
    types = [t.lower() for t in e.get("applicant_types") or []]
    listed = [c.lower() for c in e.get("listed_categories") or []]
    state_in_types = any(t.startswith("state governments") for t in types)
    unrestricted = any(t.startswith("unrestricted") for t in types)
    notes_name_states = "state governments" in listed and e.get("basis") == "eligibility_notes"
    restricted = (status in ("needs_review",) and e.get("basis") in ("conflict",)) or any(
        c.get("item") in ("'Only' restriction", "Explicit exclusion") for c in e.get("checks") or [])
    if status == "needs_review" and "restriction" in (e.get("reasoning") or "").lower():
        restricted = True
    positive = status == "likely_eligible" and (state_in_types or unrestricted or notes_name_states) and not restricted

    if positive and (state_in_types or notes_name_states):
        ev_status, short = CONFIRMED, "State governments listed as eligible applicants"
    elif positive:
        ev_status, short = CONFIRMED, "Open to all applicant types (Unrestricted)"
    elif status == "likely_eligible":
        ev_status, short = LIKELY, "Likely eligible; state agencies not named"
    elif restricted:
        ev_status, short = NOT_STATED, "Lead role unclear"
    elif status in ("likely_ineligible", "ineligible"):
        ev_status, short = CONFIRMED if status == "ineligible" else LIKELY, "State agencies likely not eligible"
    else:
        ev_status, short = NOT_STATED, "Eligibility not stated"

    quote = e.get("quote") if e.get("quote_source") else None
    if quote and e.get("quote_truncated"):
        quote = quote + " …"
    disqualifiers = [v for v in e.get("to_verify") or []
                     if not v.startswith("Read the eligibility section")]
    return {
        "eligibility_status": ev_status, "eligibility_short": short,
        "eligibility_conclusion": _plain(e.get("reasoning") or ""),
        "eligibility_quote": quote, "eligibility_source": e.get("quote_source"),
        "eligibility_source_url": e.get("source_url"),
        "eligibility_positive": positive, "eligibility_restricted": restricted,
        "disqualifiers": disqualifiers[:4],
        "restriction_quote": quote if restricted else None,
        "region_flags": e.get("region_flags") or [],
    }


def _plain(text):
    """Remove machinery words from backend sentences shown to users."""
    text = re.sub(r"\s*This is not a guarantee\.?", " The listing does not guarantee eligibility.", text)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------- funding & effort

def _funding(record):
    f = record.get("funding") or {}
    floor, ceiling, total, awards = f.get("floor"), f.get("ceiling"), f.get("estimated_total"), f.get("number_of_awards")
    if ceiling and floor:
        chip = f"{fmt_money(floor)}–{fmt_money(ceiling)}"
        text = f"{fmt_money(floor)} – {fmt_money(ceiling)} per award"
    elif ceiling:
        chip = f"Up to {fmt_money(ceiling)}"
        text = f"Up to {fmt_money(ceiling)} per award"
    elif floor:
        chip = f"From {fmt_money(floor)}"
        text = f"From {fmt_money(floor)} per award"
    elif total:
        chip = f"{fmt_money(total)} total"
        text = f"{fmt_money(total)} total program funding"
    else:
        chip = text = NOT_STATED
    status = CONFIRMED if text != NOT_STATED else NOT_STATED
    if awards:
        expected = f"about {awards:,.0f} award{'s' if awards != 1 else ''} expected"
        expected_status = CONFIRMED
    else:
        expected, expected_status = "number of awards not stated", NOT_STATED
    cost = f.get("cost_sharing")
    if cost is True:
        cost_text, cost_status = "Required (ratio not stated)", CONFIRMED
    elif cost is False:
        cost_text, cost_status = "None", CONFIRMED
    else:
        cost_text, cost_status = NOT_STATED, NOT_STATED
    return {"award_text": text, "award_chip": chip, "award_status": status,
            "expected_awards_text": expected, "expected_awards_status": expected_status,
            "cost_share_text": cost_text, "cost_share_status": cost_status}


EFFORT_LEVELS = {"higher": "Heavy", "moderate": "Moderate", "fewer_found": "Light"}


def _effort(record, cost_text, cost_status):
    ef = record.get("effort") or {}
    reqs = {r["key"]: r for r in ef.get("requirements") or []}
    level = EFFORT_LEVELS.get(ef.get("level"), "Not enough info")
    if level == "Not enough info":
        status = NOT_STATED
    else:
        status = CONFIRMED if ef.get("announcement_analyzed") else LIKELY

    def row(label, key, value_found, look):
        if key in reqs:
            return {"label": label, "value": value_found, "status": CONFIRMED, "evidence": reqs[key]["evidence"]}
        return {"label": label, "value": f"Not stated (check {look})", "status": NOT_STATED, "evidence": None}

    drivers = [{"label": "Cost share / match", "value": cost_text if cost_status != NOT_STATED
                else "Not stated (check the funding notice)", "status": cost_status, "evidence": None}]
    if "pre_application" in reqs:
        drivers.append({"label": "Submission process", "value": "Letter of intent first", "status": CONFIRMED,
                        "evidence": reqs["pre_application"]["evidence"]})
    else:
        drivers.append({"label": "Submission process", "value": "Not stated (check the funding notice)",
                        "status": NOT_STATED, "evidence": None})
    page_limit = ef.get("page_limit")
    if page_limit:
        drivers.append({"label": "Project narrative", "value": f"Up to {page_limit['pages']} pages",
                        "status": CONFIRMED, "evidence": page_limit.get("evidence")})
    else:
        drivers.append(row("Project narrative", "narrative", "Required", "the funding notice"))
    if "registration" in reqs:
        drivers.append({"label": "Registrations", "value": "SAM.gov / UEI, Grants.gov", "status": CONFIRMED,
                        "evidence": reqs["registration"]["evidence"]})
    else:
        drivers.append({"label": "Registrations", "value": "SAM.gov / UEI, Grants.gov (standard for federal grants)",
                        "status": LIKELY, "evidence": None})
    drivers.append(row("Partners", "partnership", "Required", "the eligibility section"))
    for key, label in (("letters", "Letters of support"), ("budget", "Budget narrative"),
                       ("data_plan", "Data management plan"), ("personnel", "Key personnel documents"),
                       ("evaluation", "Evaluation plan"), ("environmental", "Environmental review")):
        if key in reqs:
            drivers.append({"label": label, "value": "Required", "status": CONFIRMED, "evidence": reqs[key]["evidence"]})

    found = [r["label"] for r in ef.get("requirements") or [] if r.get("substantive")]
    if level == "Not enough info":
        note = ("The listing summary does not say enough about application requirements. "
                "The funding notice usually lists them.")
    elif found:
        note = f"Effort is driven by: {', '.join(found[:4]).lower()}."
    else:
        note = "Few application requirements were found in the official text."
    submission = drivers[1]
    return {"effort_level": level, "effort_status": status, "effort_note": note, "effort_drivers": drivers,
            "submission_type": submission["value"] if submission["status"] != NOT_STATED else NOT_STATED,
            "submission_status": submission["status"]}


# --------------------------------------------------------------------------- relevance

def _relevance(record, profile):
    rel = record.get("relevance") or {}
    goals = [_parse_goal(g) for g in rel.get("matched_goals") or []]
    ai = rel.get("ai") or {}
    ai_ok = ai.get("status") == "ok"
    if any(g["title_terms"] for g in goals):
        level = "Direct"
    elif goals:
        level = "Related"
    else:
        level = "Indirect"

    reasons = []
    for g in goals[:2]:
        page = f" (Strategic plan p. {g['page']})" if g["page"] else ""
        terms = g["title_terms"] or g["terms"]
        if terms:
            reasons.append(f"The listing mentions {', '.join(terms[:3])}, which relates to {g['label']}{page}.")
        else:
            reasons.append(f"Relates to {g['label']}{page}.")
    first = goals[0] if goals else None
    if ai_ok and ai.get("explanation") and (ai.get("score") or 0) > 20 and first:
        page = f" (Strategic plan p. {first['page']})" if first["page"] else ""
        sentence = f"{ai['explanation'].rstrip('.')}, supporting {first['label']}{page}."
    elif first:
        page = f" (Strategic plan p. {first['page']})" if first["page"] else ""
        terms = first["title_terms"] or first["terms"]
        verb = "Directly matches" if level == "Direct" else "Relates to"
        detail = f": the listing mentions {', '.join(terms[:3])}" if terms else ""
        sentence = f"{verb} {first['label']}{page}{detail}."
    else:
        sentence = "No clear link to the agency's strategic plan was found in the listing text."

    purpose = None
    if ai_ok:
        purpose = next((ev["quote"] for ev in ai.get("evidence") or [] if ev.get("source_id") == "D"), None)
    return {"matched_goals": [{k: g[k] for k in ("number", "title", "page", "label")} for g in goals],
            "fit_reasons": reasons, "reason_sentence": sentence, "fit_level": level,
            "plan_quote": first["quote"] if first else None, "plan_quote_goal": first["label"] if first else None,
            "plan_page": first["page"] if first else None, "grant_purpose_quote": purpose, "ai_fit_ok": ai_ok,
            "goal_terms": (first["title_terms"] or first["terms"]) if first else []}


# --------------------------------------------------------------------------- templates

def _unclear_reason(v, extra):
    if v.eligibility_restricted:
        quote = extra.get("restriction_quote")
        return ("whether a state agency meets the eligibility restriction"
                + (f": “{quote[:120]}”" if quote else "."))
    if not v.eligibility_positive:
        return "whether state agencies are eligible applicants."
    if v.region_flags:
        return f"whether North Carolina applicants are in scope (the title mentions {', '.join(v.region_flags)})."
    if v.deadline_date is None:
        return "the application deadline. The listing doesn't give a closing date."
    if v.award_status == NOT_STATED:
        return "the award amount. The listing doesn't state award sizes."
    return "how directly the program fits your plan."


def _why_lower(v, record):
    if v.backend_section == "likely_ineligible" or v.known_blocker:
        return v.known_blocker or "The eligibility notes list other applicant types; state agencies aren't included."
    if v.fit_score is not None and v.fit_score < SECTION_RULES["moderate_min"] and v.matched_goals:
        terms = (record.get("relevance") or {}).get("matched_goals", [{}])[0].get("terms") or []
        return (f"Indirect fit: only a passing mention of {', '.join(terms[:2])}." if terms
                else "Indirect fit with the strategic plan.")
    if record.get("details_loaded"):
        return "No strategic-plan goals were found in the listing text."
    return "The listing wasn't reviewed in detail; no plan goals were found in its title."


def _recommendation(v):
    goal = v.matched_goals[0]["label"] if v.matched_goals else "your strategic plan"
    if v.section == "top":
        timing = (f"Worth starting now: the deadline is {v.days_left} days away and registration checks take time."
                  if v.days_left is not None and v.days_left <= 60 else
                  f"There is time to plan: the deadline is {v.days_left} days away." if v.days_left is not None
                  else "")
        return f"{v.fit_tier} fit with {goal} and no blockers found in the listing. {timing}".strip()
    if v.section == "check":
        return f"{v.fit_tier} fit with {goal}, but one thing isn't confirmed yet: {v.unclear_reason} Check that first."
    if v.section == "soon":
        return f"Forecast only, not yet accepting applications. Relates to {goal}; watch for the posting."
    return f"Lower priority. {v.why_lower}"


def _next_steps(v):
    steps = []
    if v.section == "check" and v.unclear_reason:
        steps.append(f"Confirm {v.unclear_reason.rstrip('.')} with the program officer.")
    if v.eligibility_positive or v.section == "top":
        steps.append("Confirm your SAM.gov and Grants.gov registrations are active (renewals can take about 2 weeks).")
    if v.cost_share_text.startswith("Required"):
        steps.append("Identify the source of the non-federal match with your budget office.")
    if v.submission_type == "Letter of intent first":
        steps.append("Note the letter-of-intent step; it comes before the full application.")
    steps.append("Read the eligibility and scoring criteria in the funding notice before drafting."
                 if v.nofo_url else "Open the Grants.gov listing and read the full announcement before drafting.")
    if v.deadline_date and v.days_left and v.days_left > 21:
        go = v.deadline_date - timedelta(days=21)
        steps.append(f"Make a go/no-go decision by {fmt_date(go)} (3 weeks before the deadline).")
    return steps[:3]


def _questions(v, extra):
    qs = []
    if v.eligibility_restricted and extra.get("restriction_quote"):
        qs.append(f"Does a North Carolina state agency meet this requirement: “{extra['restriction_quote'][:140]}”?")
    elif not v.eligibility_positive:
        qs.append("Can a state agency apply as the lead applicant, or only as a partner?")
    for flag in extra.get("region_flags") or []:
        qs.append(f"The program mentions {flag}. Are North Carolina applicants eligible?")
    if v.award_status == NOT_STATED:
        qs.append("What is the expected award range and how many awards are planned?")
    if v.cost_share_status == NOT_STATED:
        qs.append("Is a non-federal cost share or match required?")
    if v.submission_status == NOT_STATED:
        qs.append("Is a letter of intent or pre-application required?")
    if v.deadline_date is None:
        qs.append("What is the application deadline?")
    return qs[:5]


# --------------------------------------------------------------------------- builder

def build_view(record, profile, details=None, retrieved_at=None, find_nofo=None):
    deadline = record.get("deadline") or {}
    status = {"forecasted": "forecasted", "closed": "closed"}.get(deadline.get("status"), "open")
    d = _parse_iso(deadline.get("close_date"))
    days = deadline.get("days_left")
    fit = record.get("fit_score")
    elig = _eligibility(record)
    fund = _funding(record)
    effort = _effort(record, fund["cost_share_text"], fund["cost_share_status"])
    rel = _relevance(record, profile)
    ai_elig_ok = ((record.get("eligibility") or {}).get("ai") or {}).get("status") == "ok"

    nofo = None
    if find_nofo and details:
        try:
            attachment = find_nofo(details)
            nofo = attachment.get("url") if attachment else None
        except Exception:  # noqa: BLE001 - a missing NOFO only hides a button
            nofo = None

    blocker = None
    if record.get("section") == "likely_ineligible":
        blocker = "The eligibility notes list other applicant types; state agencies aren't included."

    v = OpportunityView(
        id=str(record.get("id")), title=record.get("title") or "Untitled opportunity",
        short_name=short_name(record.get("title")), agency_full_name=record.get("federal_agency") or "Federal agency not stated",
        opportunity_number=record.get("number"), status=status, backend_section=record.get("section"),
        deadline_date=d, days_left=days if d else None,
        is_rolling=False, rolling_until=d if (d and days is not None and days > 365) else None,
        fit_score=fit, fit_tier=fit_tier(fit), grants_gov_url=record.get("source_url"), nofo_url=nofo,
        plan_url=(profile or {}).get("plan_url"), plan_name=(profile or {}).get("short_name"),
        retrieved_at=retrieved_at, known_blocker=blocker,
        ai_assisted=rel["ai_fit_ok"] or ai_elig_ok,
        **{k: elig[k] for k in ("eligibility_status", "eligibility_short", "eligibility_conclusion",
                                "eligibility_quote", "eligibility_source", "eligibility_source_url",
                                "eligibility_positive", "eligibility_restricted", "disqualifiers",
                                "region_flags")},
        **fund, **effort,
        **{k: rel[k] for k in ("matched_goals", "fit_reasons", "reason_sentence", "fit_level", "plan_quote",
                               "plan_quote_goal", "plan_page", "grant_purpose_quote")},
    )
    v.section = assign_section(v)
    v.recommendation_label = RECOMMENDATION_LABELS[v.section]
    if v.section == "check":
        v.unclear_reason = _unclear_reason(v, elig)
    if v.section == "lower":
        v.why_lower = _why_lower(v, record)
    v.recommendation_sentence = _recommendation(v)
    v.next_steps = _next_steps(v)
    v.officer_questions = _questions(v, elig)
    return v


def build_views(result, profile, details_cache=None, find_nofo=None):
    """All views in backend order: priority, likely-ineligible, lower-evidence, upcoming."""
    details_cache = details_cache or {}
    views = []
    for key in ("results", "likely_ineligible", "low_evidence", "upcoming"):
        for record in result.get(key) or []:
            views.append(build_view(record, profile, details_cache.get(str(record.get("id"))),
                                    result.get("generated_at"), find_nofo))
    return views


def header_stats(result, min_days):
    stats = result.get("stats") or {}
    hidden = (stats.get("screened_out_by_reason") or {}).get("not_enough_time", 0)
    return {"reviewed": stats.get("actionable_candidates", 0),
            "not_shown": hidden if min_days else 0,
            "generated_at": result.get("generated_at")}


def to_eastern(iso):
    """'2026-11-08T07:25:00+00:00' -> datetime in America/New_York (None if unparseable)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromisoformat(iso).astimezone(ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001
        return None
