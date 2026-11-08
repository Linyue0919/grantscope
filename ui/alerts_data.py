"""Pure helpers for the Alerts page: which grants an alert or digest would include.

Everything here reads OpportunityView objects built by ui/view_model.py from the
backend result the Brief already loaded. No network, LLM or backend calls.
"""
from datetime import date, timedelta

from ui.brief_sections import SECTION_RULES
from ui.export_ics import exportable
from ui.view_model import build_view

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DEFAULT_SETTINGS = {
    "digest_on": True,
    "digest_day": "Monday",
    "instant_on": True,
    "threshold": 80,
    "positive_only": True,
    "remind_14": True,
    "remind_3": True,
    "email": "",
}
THRESHOLD_RANGE = (50, 100)
CLOSING_WITHIN = 14
REMINDER_DAYS = (14, 3)
EXCLUDED_BACKEND = ("likely_ineligible", "screened_out")


def is_open(view):
    """Accepting applications now: not a forecast, and not past a stated deadline."""
    if view.status != "open":
        return False
    return view.days_left is None or view.days_left >= 0


def instant_matches(views, threshold, positive_only=True):
    """Open opportunities at or above the fit threshold, highest score first (stable for ties)."""
    out = [v for v in views
           if is_open(v) and v.backend_section not in EXCLUDED_BACKEND
           and v.fit_score is not None and v.fit_score >= threshold
           and (not positive_only or (v.eligibility_positive and not v.eligibility_restricted))]
    return sorted(out, key=lambda v: -v.fit_score)


def closing_soon_views(result, profile, details_cache=None, find_nofo=None, brief_views=(), within=CLOSING_WITHIN):
    """Relevant open grants closing within `within` days.

    Combines Brief views (when the Brief's own day filter is under `within`) with records the
    backend screened out only for "not enough time". Those are already scored in the same
    result, so this adds no backend call. Weak fits (below the Moderate threshold) are left out.
    """
    seen, out = set(), []
    for v in brief_views:
        if is_open(v) and v.days_left is not None and v.days_left <= within and v.id not in seen:
            seen.add(v.id)
            out.append(v)
    for record in (result or {}).get("screened_out") or []:
        codes = (record.get("screening") or {}).get("codes") or []
        if codes != ["not_enough_time"]:
            continue
        v = build_view(record, profile, (details_cache or {}).get(str(record.get("id"))),
                       (result or {}).get("generated_at"), find_nofo)
        if v.id in seen or not is_open(v) or v.days_left is None or v.days_left > within:
            continue
        seen.add(v.id)
        out.append(v)
    min_fit = SECTION_RULES["moderate_min"]
    out = [v for v in out if v.fit_score is not None and v.fit_score >= min_fit]
    return sorted(out, key=lambda v: (v.days_left, -(v.fit_score or 0)))


def digest_groups(views, closing):
    """Digest contents grouped like the Brief (backend order kept within each group)."""
    return {
        "top": [v for v in views if v.section == "top" and is_open(v)],
        "check": [v for v in views if v.section == "check" and is_open(v)],
        "closing": list(closing),
    }


def next_weekday(day_name, today=None):
    """Next date (after today) that falls on day_name."""
    today = today or date.today()
    target = DAYS.index(day_name) if day_name in DAYS else 0
    ahead = (target - today.weekday()) % 7 or 7
    return today + timedelta(days=ahead)


def digest_subject(agency_short, groups):
    parts = []
    if groups["top"]:
        parts.append(f"{len(groups['top'])} top candidate{'s' if len(groups['top']) != 1 else ''}")
    if groups["check"]:
        parts.append(f"{len(groups['check'])} to check")
    if groups["closing"]:
        parts.append(f"{len(groups['closing'])} closing within {CLOSING_WITHIN} days")
    body = ", ".join(parts) if parts else "no new opportunities this week"
    return f"GrantScope weekly digest for {agency_short}: {body}"


def instant_subject(view):
    return f"High-fit grant for you: {view.short_name} ({view.fit_score}/100)"


def reminder_schedule(views, days_before=REMINDER_DAYS, today=None):
    """[(reminder_date, days_before, view)] for upcoming reminders, soonest first, plus the
    count of saved items that can't get reminders (forecast, no stated deadline, or closed)."""
    today = today or date.today()
    rows, skipped = [], 0
    for v in views:
        if not exportable(v):
            skipped += 1
            continue
        for n in days_before:
            when = v.deadline_date - timedelta(days=n)
            if when >= today:
                rows.append((when, n, v))
    rows.sort(key=lambda r: (r[0], r[2].short_name))
    return rows, skipped


def valid_email(text):
    text = (text or "").strip()
    if not text or " " in text or text.count("@") != 1:
        return False
    local, domain = text.split("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")
