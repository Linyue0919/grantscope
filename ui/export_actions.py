"""Streamlit download buttons for exports. Files are built locally from view snapshots
(cached per snapshot), so rendering never calls the backend or an LLM."""
import json

import streamlit as st

from services.agency_profiles import get_agency_profile
from ui.export_ics import build_ics, google_calendar_url, ics_filename
from ui.export_pdf import build_grant_pdf, build_summary_pdf, pdf_filename
from ui.view_model import view_from_dict


def agency_short(agency):
    profile = get_agency_profile(agency) or {}
    return profile.get("short_name") or "Agency"


@st.cache_data(show_spinner=False, max_entries=200)
def _grant_pdf_bytes(snapshot_json, agency):
    return build_grant_pdf(view_from_dict(json.loads(snapshot_json)), agency)


@st.cache_data(show_spinner=False, max_entries=50)
def _summary_pdf_bytes(snapshots_json, agency):
    return build_summary_pdf([view_from_dict(d) for d in json.loads(snapshots_json)], agency)


def _snap(view):
    return json.dumps(view.to_dict(), sort_keys=True, default=str)


def grant_pdf_button(view, agency, key):
    st.download_button("Download PDF", data=_grant_pdf_bytes(_snap(view), agency),
                       file_name=pdf_filename(agency_short(agency), "opportunity"), mime="application/pdf",
                       key=key, on_click="ignore")


def summary_pdf_button(views, agency, key, label="Download summary (PDF)", primary=False):
    if not views:
        return
    data = _summary_pdf_bytes(json.dumps([v.to_dict() for v in views], sort_keys=True, default=str), agency)
    st.download_button(label, data=data, file_name=pdf_filename(agency_short(agency), "saved"),
                       mime="application/pdf", key=key, on_click="ignore", type="primary" if primary else "secondary")


def ics_button(views, agency, key):
    """Download all exportable deadlines as one .ics file; returns how many were skipped."""
    data, exported, skipped = build_ics(views, calendar_name=f"GrantScope deadlines · {agency_short(agency)}")
    st.download_button("Export to calendar (.ics)", data=data, file_name=ics_filename(agency_short(agency)),
                       mime="text/calendar", key=key, on_click="ignore", disabled=exported == 0)
    return skipped


def google_calendar_button(view):
    url = google_calendar_url(view)
    if url:
        st.link_button("Add to Google Calendar ↗", url)
