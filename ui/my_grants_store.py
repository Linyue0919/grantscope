"""Brief → My Grants: save opportunities into the same persistent store Search uses.

Uses Search's own save path unchanged: modules.search_research.save_research_record()
writing to services.grant_store.LocalGrantStore ($GRANTSCOPE_DATA_DIR/grants.json).
Fields the Brief doesn't have are filled from the view model; project text stays empty.
"""
from datetime import date, datetime

from modules.search_research import save_research_record
from services.grant_store import LocalGrantStore
from ui.view_model import OpportunityView, short_name

RESEARCH_DEPTH = "Funding Brief strategic-plan screening only"
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d")


def _store():
    return LocalGrantStore()


def record_fields(view):
    """The fields Search's save passes, filled from an OpportunityView."""
    reason = view.reason_sentence or view.recommendation_sentence or ""
    fields = {
        "title": view.title,
        "official_url": view.grants_gov_url,
        "federal_agency": view.agency_full_name,
        "close_date": view.deadline_date.isoformat() if view.deadline_date else None,
        "project_description": "",
        "research_depth": RESEARCH_DEPTH,
        "notes": f"Saved from Funding Brief: {reason}".strip(),
    }
    # The store keeps the first value it sees for title/URL/agency/date, so don't write blanks.
    return {k: v for k, v in fields.items() if v is not None}


def save(agency, view):
    return save_research_record(_store(), agency, str(view.id), record_fields(view))


def records(agency):
    """My Grants records for one agency; [] if the store can't be read."""
    try:
        return _store().list_records(agency)
    except RuntimeError:
        return []


def saved_ids(agency):
    return {str(r.get("opportunity_id")) for r in records(agency)}


def _parse_date(value):
    raw = str(value or "").strip()[:10]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def view_from_record(record, today=None):
    """Minimal OpportunityView for a My Grants record that isn't in the current brief."""
    today = today or date.today()
    title = record.get("title") or "Untitled grant"
    deadline = _parse_date(record.get("close_date"))
    return OpportunityView(
        id=str(record.get("opportunity_id")), title=title, short_name=short_name(title),
        agency_full_name=record.get("federal_agency") or "Federal agency not stated", status="open",
        deadline_date=deadline, days_left=(deadline - today).days if deadline else None,
        grants_gov_url=record.get("official_url"))


def reminder_views(agency, fresh_views=(), today=None):
    """Views for this agency's My Grants records, preferring fresh brief data when listed."""
    fresh = {v.id: v for v in fresh_views or ()}
    return [fresh.get(str(r.get("opportunity_id"))) or view_from_record(r, today) for r in records(agency)]
