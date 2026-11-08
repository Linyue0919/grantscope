"""Opportunity cards (spec section 5). Reads only OpportunityView fields."""
from html import escape

import streamlit as st

from ui.view_model import CONFIRMED, LIKELY, NOT_STATED, fmt_date, mark

STATUS_WORD = {CONFIRMED: "Confirmed", LIKELY: "Likely", NOT_STATED: "Not stated"}
HIDE_REASONS = ["Not our mission", "Award too small", "Cost share", "No capacity"]


def evidence(status):
    """Shape mark plus a screen-reader label (never color alone)."""
    return f'{mark(status)}<span class="sr-only"> {STATUS_WORD.get(status, "Not stated")}</span>'


def due_html(view):
    if view.status == "forecasted":
        return '<div class="gs-due"><b>Forecast</b><span>not yet open</span></div>'
    if view.rolling_until:
        return f'<div class="gs-due"><b>Open through {fmt_date(view.rolling_until)}</b><span>long-running</span></div>'
    if view.deadline_date:
        days = f"{view.days_left} day{'s' if view.days_left != 1 else ''} left" if view.days_left is not None else ""
        return f'<div class="gs-due"><b>Due {fmt_date(view.deadline_date)}</b><span>{days}</span></div>'
    return '<div class="gs-due"><b>Deadline not stated</b><span>check the listing</span></div>'


def score_html(view):
    if view.fit_score is None:
        return ""
    return (f'<div class="gs-score gs-tier-{view.fit_tier}" role="img" '
            f'aria-label="Fit score {view.fit_score} out of 100, {view.fit_tier} fit">'
            f'<span class="n">{view.fit_score}</span><span class="d">/100</span>'
            f'<span class="t">{view.fit_tier} fit</span></div>')


def chips_html(view):
    chips = [
        ("Award", view.award_chip, view.award_status),
        ("Cost share", view.cost_share_text.replace(" (ratio not stated)", ""), view.cost_share_status),
        ("Effort", view.effort_level, view.effort_status),
    ]
    return '<div class="gs-chips">' + "".join(
        f'<span class="gs-chip">{label}: <b>{escape(value)}</b> {evidence(status)}</span>'
        for label, value, status in chips) + "</div>"


def card_header_html(view):
    return (f'<div class="gs-card-row"><div><p class="gs-title">{escape(view.title)}</p>'
            f'<p class="gs-agency">{escape(view.agency_full_name)}</p></div>'
            f'<div class="gs-right-col">{due_html(view)}{score_html(view)}</div></div>')


def render_card(view, *, selected, on_view, on_hide, saved=None, on_toggle_save=None):
    """Card for Top candidates / Needs a quick check."""
    key = f"{'selcard' if selected else 'card'}_{view.id}"
    with st.container(border=True, key=key):
        html = card_header_html(view) + f'<p class="gs-reason">{escape(view.reason_sentence)}</p>' + chips_html(view)
        if view.section == "check" and view.unclear_reason:
            html += f'<div class="gs-unclear"><b>Unclear ○:</b> {escape(view.unclear_reason)}</div>'
        st.markdown(html, unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.button("Showing details" if selected else "View details", key=f"view_{view.id}", type="primary",
                      on_click=on_view, args=(view.id,))
            if on_toggle_save is not None:
                st.button("★ Saved" if saved else "☆ Save", key=f"save_{view.id}",
                          on_click=on_toggle_save, args=(view,))
            if view.grants_gov_url:
                st.link_button("Grants.gov listing ↗", view.grants_gov_url)
            if view.nofo_url:
                st.link_button("Funding notice (NOFO) ↗", view.nofo_url)
            st.button("Not relevant", key=f"hide_{view.id}", type="tertiary", on_click=on_hide, args=(view.id,))


def render_hidden(view, *, on_undo, reason_key):
    with st.container(key=f"hidden_{view.id}"):
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.markdown(f'<div class="gs-hidden"><b>{escape(view.short_name)}</b> is hidden from this brief.</div>',
                    unsafe_allow_html=True)
        c2.button("Undo", key=f"undo_{view.id}", on_click=on_undo, args=(view.id,), type="tertiary")
        st.pills("Why? (optional)", HIDE_REASONS, key=reason_key, label_visibility="collapsed")


def render_soon(view):
    est = (f" Estimated close date {fmt_date(view.deadline_date)} (may change)." if view.deadline_date else "")
    st.markdown(
        f'<div class="gs-row"><div class="gs-row-title">{escape(view.title)}</div>'
        f'<div class="gs-row-sub">{escape(view.agency_full_name)} · Forecast only, not yet open</div>'
        f'<div class="gs-row-sub">{escape(view.reason_sentence)}{escape(est)}</div></div>',
        unsafe_allow_html=True)
    if view.grants_gov_url:
        st.markdown(f'<a href="{escape(view.grants_gov_url)}" target="_blank" rel="noopener">'
                    'View forecast on Grants.gov ↗</a>', unsafe_allow_html=True)


def render_lower(view):
    fit = f" · Fit {view.fit_score}/100" if view.fit_score is not None else ""
    link = (f'<a href="{escape(view.grants_gov_url)}" target="_blank" rel="noopener">Grants.gov listing ↗</a>'
            if view.grants_gov_url else "")
    st.markdown(
        f'<div class="gs-row gs-card-row"><div><span class="gs-row-title">{escape(view.title)}</span>'
        f'<span class="gs-muted">{fit}</span>'
        f'<div class="gs-row-sub"><b>Why lower:</b> {escape(view.why_lower or "")}</div></div>'
        f'<div style="white-space:nowrap">{link}</div></div>',
        unsafe_allow_html=True)
