"""Saved opportunities page (spec section 8). Session-only storage via ui/saved_store.py."""
from datetime import date
from html import escape

import streamlit as st

from ui import saved_store
from ui.components.card import card_header_html, chips_html
from ui.components.detail_panel import render_panel
from ui.export_actions import grant_pdf_button
from ui.nav import PAGES
from ui.view_model import RECOMMENDATION_LABELS, agency_display_name, view_from_dict

SORTS = ["Deadline (soonest first)", "Date saved"]


def _fresh_views(agency):
    """Fresh views from the Brief's cached pipeline (no new backend calls on a cache hit)."""
    try:
        from modules.dashboard import load_brief
        _, _, views = load_brief(agency, int(st.session_state.get("brief_days", 30)))
        return {v.id: v for v in views}
    except Exception:  # noqa: BLE001 - the Saved page still works from snapshots
        return None


def saved_items(agency):
    """[(view, note, saved_at)] using fresh values when the item is still listed."""
    fresh = _fresh_views(agency)
    items = []
    for snap in saved_store.list_saved(agency):
        saved_view = view_from_dict(snap)
        note = None
        if fresh is not None and saved_view.id in fresh:
            view = fresh[saved_view.id]
            if view.deadline_date != saved_view.deadline_date:
                note = "Deadline changed since you saved it"
        else:
            view = saved_view
            if fresh is not None:
                note = "No longer listed as open with your current filter"
        items.append((view, note, snap.get("saved_at", "")))
    return items


def sort_items(items, how):
    if how == SORTS[1]:
        return sorted(items, key=lambda it: it[2], reverse=True)
    return sorted(items, key=lambda it: (it[0].deadline_date is None, it[0].deadline_date or date.max))


def _select_saved(opp_id):
    st.session_state["saved_selected"] = opp_id


def _close_saved():
    st.session_state["saved_selected"] = None


def _remove(agency, opp_id):
    saved_store.unsave(agency, opp_id)
    if st.session_state.get("saved_selected") == opp_id:
        st.session_state["saved_selected"] = None


def _toggle(view):
    saved_store.toggle(st.session_state.get("brief_agency", ""), view)


def _render_saved_card(view, note, agency, selected, extra_links):
    with st.container(border=True, key=f"{'selcard' if selected else 'card'}_saved_{view.id}"):
        label = RECOMMENDATION_LABELS.get(view.section, "")
        html = card_header_html(view)
        if view.deadline_date and view.days_left is not None and view.days_left < 0:
            html += '<p class="gs-small">Closed</p>'
        html += f'<p class="gs-small"><b>{escape(label)}</b></p>'
        html += f'<p class="gs-reason">{escape(view.reason_sentence)}</p>' + chips_html(view)
        if note:
            html += f'<div class="gs-unclear">{escape(note)}</div>'
        st.markdown(html, unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.checkbox("Select", key=f"pick_{view.id}", value=True)
            st.button("Showing details" if selected else "View details", key=f"sview_{view.id}", type="primary",
                      on_click=_select_saved, args=(view.id,))
            if view.grants_gov_url:
                st.link_button("Grants.gov ↗", view.grants_gov_url)
            if view.nofo_url:
                st.link_button("NOFO ↗", view.nofo_url)
            if extra_links:
                extra_links(view)
            st.button("Remove", key=f"remove_{view.id}", type="tertiary", on_click=_remove, args=(agency, view.id))


def show_saved(toolbar=None, card_links=None, panel_actions=None):
    agency = st.session_state.get("brief_agency")
    if not agency:
        from modules.dashboard import DEFAULT_AGENCY
        agency = DEFAULT_AGENCY
    items = saved_items(agency)
    st.markdown('<p class="gs-eyebrow">Saved</p><p class="gs-h1">Saved opportunities</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="gs-small">{escape(agency_display_name(agency))} · {len(items)} saved · '
                'Saved for this session only</p>', unsafe_allow_html=True)
    if not items:
        st.info("Nothing saved yet. Use ☆ Save on any opportunity in your brief.")
        if "brief" in PAGES:
            with st.container(key="inlinelink_saved_brief"):
                st.page_link(PAGES["brief"], label="Go to your brief", width="content")
        return

    with st.container(horizontal=True, gap="small", vertical_alignment="center", key="saved_toolbar"):
        how = st.segmented_control("Sort by", SORTS, default=SORTS[0], key="saved_sort")
        if toolbar:
            selected_views = [v for v, _, _ in items if st.session_state.get(f"pick_{v.id}", True)]
            toolbar(agency, selected_views)
    items = sort_items(items, how or SORTS[0])

    selected = st.session_state.get("saved_selected")
    by_id = {v.id: v for v, _, _ in items}
    panel_view = by_id.get(selected)
    if panel_view:
        main, side = st.columns([5, 3], gap="large")
    else:
        main, side = st.container(), None
    with main:
        for view, note, _ in items:
            _render_saved_card(view, note, agency, view.id == selected, card_links)
    if side is not None:
        with side:
            render_panel(panel_view, on_close=_close_saved, saved=True, on_toggle_save=_toggle,
                         extra_actions=lambda v: grant_pdf_button(v, agency, key=f"spdf_{v.id}"),
                         how_it_works_page=PAGES.get("how"))
