"""Calendar exports (spec section 10): .ics file and Google Calendar template links.

Hand-written RFC 5545 (no extra dependency). Only official deadlines are exported:
open opportunities with a stated closing date. Grants.gov gives dates without times,
so events are all-day. Forecasts and undated items are skipped and counted.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from ui.view_model import NOT_STATED

SMALL_WORDS = {"of", "and", "the", "for", "on", "in", "to", "a", "an", "&"}


def agency_abbreviation(name):
    """'National Institutes of Health' -> 'NIH'; keeps an existing '(EPA)' style suffix."""
    name = (name or "").strip()
    if name.endswith(")") and "(" in name:
        return name[name.rindex("(") + 1:-1]
    letters = "".join(w[0] for w in name.replace("-", " ").split() if w.lower() not in SMALL_WORDS and w[0].isalpha())
    return letters.upper()[:8] or "Federal"


def exportable(view):
    return view.status == "open" and view.deadline_date is not None and (view.days_left is None or view.days_left >= 0)


def _escape(text):
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line):
    """Fold lines longer than 75 octets (RFC 5545 §3.1), never splitting a UTF-8 character."""
    out, current = [], ""
    for ch in line:
        limit = 75 if not out else 74  # continuation lines start with a space
        if len((current + ch).encode("utf-8")) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return "\r\n ".join(out)


def _description(view):
    parts = []
    if view.award_status != NOT_STATED:
        parts.append(f"Award: {view.award_text}")
    else:
        parts.append("Award: not stated in the listing")
    if view.reason_sentence:
        parts.append(view.reason_sentence)
    if view.grants_gov_url:
        parts.append(f"Grants.gov listing: {view.grants_gov_url}")
    if view.nofo_url:
        parts.append(f"Funding notice (NOFO): {view.nofo_url}")
    parts.append("Deadline date from Grants.gov; confirm the exact time in the official announcement.")
    return "\n".join(parts)


def _summary(view):
    return f"Deadline: {view.short_name} ({agency_abbreviation(view.agency_full_name)})"


def build_ics(views, calendar_name="GrantScope deadlines"):
    """Return (ics_bytes, exported_count, skipped_count)."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//GrantScope//Funding Brief//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape(calendar_name)}"]
    exported = skipped = 0
    for view in views:
        if not exportable(view):
            skipped += 1
            continue
        exported += 1
        start = view.deadline_date
        lines += [
            "BEGIN:VEVENT",
            f"UID:{view.id}@grantscope",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{start + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(_summary(view))}",
            f"DESCRIPTION:{_escape(_description(view))}",
        ]
        if view.grants_gov_url:
            lines.append(f"URL:{view.grants_gov_url}")
        lines.append("TRANSP:TRANSPARENT")
        for days in (14, 3):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:-P{days}D",
                      f"DESCRIPTION:{_escape(f'{days} days until deadline: {view.short_name}')}", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return ("\r\n".join(_fold(line) for line in lines) + "\r\n").encode("utf-8"), exported, skipped


def google_calendar_url(view):
    """All-day Google Calendar template link, or None if the deadline isn't an official date."""
    if not exportable(view):
        return None
    start = view.deadline_date
    params = {
        "action": "TEMPLATE",
        "text": _summary(view),
        "dates": f"{start:%Y%m%d}/{start + timedelta(days=1):%Y%m%d}",
        "details": _description(view),
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def ics_filename(agency_short):
    safe = "".join(c for c in (agency_short or "Agency") if c.isalnum()) or "Agency"
    return f"GrantScope_{safe}_deadlines_{datetime.now():%Y-%m-%d}.ics"
