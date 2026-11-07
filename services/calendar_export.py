"""Calendar export for saved grants with validated official deadlines."""
from datetime import date, datetime


def _ics_text(value):
    return str(value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_date(value):
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    raw = str(value or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:10], fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y%m%d")
    except ValueError:
        return ""


def grants_to_ics(records):
    events = []
    for record in records:
        event_date = _ics_date(record.get("close_date"))
        if len(event_date) != 8 or not event_date.isdigit():
            continue
        description = "Agency: " + str(record.get("agency") or "Unknown")
        if record.get("notes"):
            description += "\nNotes: " + str(record["notes"])
        events.extend([
            "BEGIN:VEVENT",
            f"UID:grantscope-{_ics_text(record.get('agency'))}-{_ics_text(record.get('opportunity_id'))}",
            f"DTSTART;VALUE=DATE:{event_date}",
            f"SUMMARY:{_ics_text(record.get('title') or 'Grant deadline')}",
            f"DESCRIPTION:{_ics_text(description)}",
            f"URL:{_ics_text(record.get('official_url'))}",
            "END:VEVENT",
        ])
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//GrantScope//My Grants//EN", *events, "END:VCALENDAR", ""])
