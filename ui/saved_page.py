"""Saved page (full version in Phase b)."""
import streamlit as st

from ui import saved_store


def show_saved():
    agency = st.session_state.get("brief_agency", "")
    items = saved_store.list_saved(agency)
    st.markdown('<p class="gs-h1">Saved opportunities</p>', unsafe_allow_html=True)
    st.caption(f"{agency} · {len(items)} saved · Saved for this session only")
    if not items:
        st.info("Nothing saved yet. Use ☆ Save on any opportunity in your brief.")
