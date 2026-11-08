"""Saved opportunities, session-only (st.session_state), keyed by agency.

Stores a snapshot of the view-model fields needed for display and export, plus
saved_at, so the Saved page still works if the listing changes during the session.
Saved items are cleared when the browser session ends ("Saved for this session only").
"""
from datetime import datetime, timezone

import streamlit as st

_KEY = "saved_grants"


def _store():
    return st.session_state.setdefault(_KEY, {})


def list_saved(agency):
    return list(_store().get(agency, {}).values())


def is_saved(agency, opp_id):
    return str(opp_id) in _store().get(agency, {})


def save(agency, view):
    snapshot = view.to_dict()
    snapshot["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _store().setdefault(agency, {})[str(view.id)] = snapshot


def unsave(agency, opp_id):
    _store().get(agency, {}).pop(str(opp_id), None)


def toggle(agency, view):
    if is_saved(agency, view.id):
        unsave(agency, view.id)
    else:
        save(agency, view)


def count_all():
    return sum(len(items) for items in _store().values())
