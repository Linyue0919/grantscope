"""Brief: the Funding Brief page (spec docs/DASHBOARD_REDESIGN.md).

The data-loading functions below (_shared_details_cache, _shared_ai_cache, _ai_config,
_cached_match) are unchanged from the previous Dashboard: the brief calls the backend
exactly as before and only changes how results are presented (via ui/view_model.py).
"""
import os
from datetime import date

import streamlit as st

from modules.profile import get_preferences
from services.agency_profiles import get_agency_profile, list_profiled_agencies, resolve_agency_name
from services.ai_eligibility import AzureEligibilityEvaluator
from services.ai_matching import AzureFitEvaluator, load_ai_config
from services.application_effort import find_announcement
from services.grants_api import get_grants
from services.match_engine import MatchSettings, run_matching
from services.opportunity_details import fetch_opportunity_details
from ui import saved_store
from ui.brief_sections import SECTION_DESCRIPTIONS, SECTION_RULES, SECTION_TITLES, group_views
from ui.components.card import render_card, render_hidden, render_lower, render_soon
from ui.components.detail_panel import render_panel
from ui.nav import PAGES
from ui.view_model import agency_display_name, build_views, header_stats, to_eastern

DEFAULT_AGENCY = "Department of Health and Human Services"
CLOSED = "__closed__"


@st.cache_resource
def _shared_details_cache():
    """Official details shared across sessions (an opportunity's details rarely change)."""
    return {}


@st.cache_resource
def _shared_ai_cache():
    return {}


def _ai_config():
    """Azure OpenAI settings from environment variables, then Streamlit secrets."""
    merged = dict(os.environ)
    try:
        for key in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT",
                    "AZURE_OPENAI_API_VERSION"):
            if key in st.secrets and not merged.get(key):
                merged[key] = st.secrets[key]
    except Exception:  # noqa: BLE001 - no secrets file is normal
        pass
    return load_ai_config(merged)


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_match(agency, min_days_left, min_award, include_unknown, keywords, use_ai, today_iso):
    settings = MatchSettings(min_days_left=min_days_left, min_award=min_award or None,
                             include_unknown_deadline=include_unknown)
    config = _ai_config() if use_ai else None
    fit_ai = AzureFitEvaluator(config, cache=_shared_ai_cache()) if config else None
    elig_ai = AzureEligibilityEvaluator(config, cache=_shared_ai_cache()) if config else None
    return run_matching(
        get_agency_profile(agency), settings,
        search_fn=get_grants, details_fn=fetch_opportunity_details,
        today=date.fromisoformat(today_iso), extra_keywords=keywords,
        details_cache=_shared_details_cache(), ai_evaluator=fit_ai, eligibility_evaluator=elig_ai,
    )


# --------------------------------------------------------------------------- state helpers

def _agency():
    agencies = list_profiled_agencies()
    if st.session_state.get("brief_agency") not in agencies:
        st.session_state["brief_agency"] = DEFAULT_AGENCY if DEFAULT_AGENCY in agencies else agencies[0]
    return st.session_state["brief_agency"]


def _set_agency(name):
    st.session_state["brief_agency"] = name
    st.session_state["brief_selected"] = None
    st.session_state["brief_hidden"] = {}


def _select(opp_id):
    st.session_state["brief_selected"] = opp_id


def _close_panel():
    st.session_state["brief_selected"] = CLOSED


def _hide(opp_id):
    st.session_state.setdefault("brief_hidden", {})[opp_id] = True
    if st.session_state.get("brief_selected") == opp_id:
        st.session_state["brief_selected"] = None


def _undo(opp_id):
    st.session_state.setdefault("brief_hidden", {}).pop(opp_id, None)


def _toggle_save(view):
    saved_store.toggle(_agency(), view)


def _refresh():
    _cached_match.clear()
    st.session_state["brief_refreshing"] = True


def load_brief(agency, min_days):
    """Run the existing backend pipeline (cached) and build view models. No extra calls."""
    prefs = get_preferences()
    keywords = tuple(prefs.get("priorities", [])) if resolve_agency_name(prefs.get("agency")) == agency else ()
    use_ai = bool(_ai_config())  # backend default: AI on when configured
    result = _cached_match(agency, min_days, 0, False, keywords, use_ai, date.today().isoformat())
    profile = get_agency_profile(agency)
    views = build_views(result, profile, _shared_details_cache(), find_announcement)
    return result, profile, views


# --------------------------------------------------------------------------- header

def _render_header(agency, profile, result, min_days, compact):
    """Stacked header, one idea per row (eyebrow, agency, scope, filter, note, custom search, meta)."""
    stats = header_stats(result, min_days)
    with st.container(key="brief_header", gap="small"):
        st.markdown('<p class="gs-eyebrow">Funding brief</p>', unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small", vertical_alignment="center", key="brief_agency_row"):
            st.markdown(f'<p class="gs-h1{" gs-h1-compact" if compact else ""}">{agency_display_name(agency)}</p>',
                        unsafe_allow_html=True, width="content")
            with st.popover("Change agency", width="content"):
                st.markdown('<p class="gs-eyebrow">Switch to</p>', unsafe_allow_html=True)
                for name in list_profiled_agencies():
                    label = agency_display_name(name) + ("  ·  Current" if name == agency else "")
                    st.button(label, key=f"agency_{name}", on_click=_set_agency, args=(name,), type="tertiary",
                              disabled=name == agency, width="stretch")
        plan = (f'<a href="{profile["plan_url"]}" target="_blank" rel="noopener">public strategic plan ↗</a>'
                if profile and profile.get("plan_url") else "public strategic plan")
        st.markdown(f'<p class="gs-scope">Open federal opportunities matched to your agency\'s {plan}.</p>',
                    unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small", vertical_alignment="center", key="brief_filter_row"):
            st.markdown('<p class="gs-scope">Show opportunities with at least</p>', unsafe_allow_html=True,
                        width="content")
            st.number_input("Minimum days left to apply", min_value=0, max_value=365, step=1, key="brief_days",
                            label_visibility="collapsed", width=110)
            st.markdown('<p class="gs-scope">days left to apply</p>', unsafe_allow_html=True, width="content")
        if stats["not_shown"]:
            n = stats["not_shown"]
            st.markdown(f'<p class="gs-small">{n} opportunit{"ies have" if n != 1 else "y has"} fewer than '
                        f'{min_days} days left and {"are" if n != 1 else "is"} not shown.</p>', unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small", vertical_alignment="center", key="inlinelink_browse"):
            st.markdown('<p class="gs-scope">Looking for a specific program or requirement?</p>',
                        unsafe_allow_html=True, width="content")
            if "browse" in PAGES:
                st.page_link(PAGES["browse"], label="Try a custom search in Browse all", width="content")
        when = to_eastern(stats["generated_at"]) if stats["generated_at"] else None
        when_text = f"Updated today, {when:%-I:%M %p} ET" if when else "Updated recently"
        with st.container(horizontal=True, gap="small", vertical_alignment="center", key="brief_meta_row"):
            st.markdown(f'<p class="gs-small">{when_text} · {stats["reviewed"]} open opportunities from '
                        f'<a href="https://www.grants.gov/" target="_blank" rel="noopener">Grants.gov</a> reviewed</p>',
                        unsafe_allow_html=True, width="content")
            st.button("⟳ Refresh data", key="brief_refresh", on_click=_refresh, type="tertiary")


# --------------------------------------------------------------------------- sections

def _section_heading(name, count=None, extra=""):
    title = SECTION_TITLES[name] + (f" ({count})" if count is not None else "")
    st.markdown(f'<div class="gs-section-title">{title}</div>'
                f'<p class="gs-section-desc">{SECTION_DESCRIPTIONS[name]}{extra}</p>', unsafe_allow_html=True)


def _render_cards(views, selected_id, hidden, agency):
    for view in views:
        if hidden.get(view.id):
            render_hidden(view, on_undo=_undo, reason_key=f"reason_{view.id}")
            continue
        render_card(view, selected=view.id == selected_id, on_view=_select, on_hide=_hide,
                    saved=saved_store.is_saved(agency, view.id), on_toggle_save=_toggle_save)


def _render_sections(groups, selected_id, hidden, agency):
    top, check, soon, lower = groups["top"], groups["check"], groups["soon"], groups["lower"]
    if not any(groups.values()):
        st.info("No opportunities match these settings. Try fewer days to apply.")
        return
    _section_heading("top")
    if top:
        cap = SECTION_RULES["top_cap"]
        show_all = len(top) > cap and st.session_state.get("brief_top_all", False)
        _render_cards(top if show_all else top[:cap], selected_id, hidden, agency)
        if len(top) > cap:
            st.toggle(f"Show {len(top) - cap} more top candidates", key="brief_top_all")
    else:
        st.markdown(f'<p class="gs-small">No top candidates right now. {len(check)} '
                    f'opportunit{"ies need" if len(check) != 1 else "y needs"} a quick check.</p>',
                    unsafe_allow_html=True)
    if check:
        _section_heading("check")
        _render_cards(check, selected_id, hidden, agency)
    with st.expander(f"**Opening soon ({len(soon)})**"):
        if soon:
            for view in soon:
                render_soon(view)
        else:
            st.caption("No forecasted opportunities for this agency right now.")
    with st.expander(f"**Lower priority ({len(lower)})** · mostly indirect fit or a known blocker"):
        cap = SECTION_RULES["lower_cap"]
        for view in lower[:cap]:
            render_lower(view)
        if len(lower) > cap:
            st.markdown(f'<p class="gs-small">and {len(lower) - cap} more.</p>', unsafe_allow_html=True)
            if "browse" in PAGES:
                with st.container(key="inlinelink_lower_browse"):
                    st.page_link(PAGES["browse"], label="Try Browse all for a custom search", width="content")


def _render_saved_bar(agency, extra=None):
    """Slim dark bar at the end of the brief when something is saved (sticky footers are fragile)."""
    items = saved_store.list_saved(agency)
    if not items:
        return
    names = ", ".join(i.get("short_name", "") for i in items[:3]) + (f" and {len(items) - 3} more" if len(items) > 3 else "")
    with st.container(key="savedbar"):
        st.markdown(f'<div class="gs-savedbar"><b>{len(items)} saved:</b> {names}'
                    '<span class="gs-savedbar-note"> · Saved for this session only</span></div>',
                    unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small"):
            if st.button("View saved", key="savedbar_view", type="primary"):
                st.switch_page(PAGES["saved"])
            if extra:
                extra(agency, items)


def _render_footer(profile):
    st.markdown('<div class="gs-footer">', unsafe_allow_html=True)
    if "how" in PAGES:
        with st.container(key="inlinelink_footer_how"):
            st.page_link(PAGES["how"], label="How GrantScope assesses opportunities", width="content")
    st.markdown(f'<p class="gs-small">Sources: Grants.gov listings and announcements, '
                f'{profile["short_name"] if profile else "agency"} Strategic Plan · '
                'GrantScope never guarantees eligibility or awards.</p></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- page

def show_dashboard():
    agency = _agency()
    st.session_state.setdefault("brief_days", 30)
    st.session_state.setdefault("brief_hidden", {})
    min_days = int(st.session_state["brief_days"])
    refreshing = st.session_state.pop("brief_refreshing", False)
    with st.spinner("Refreshing…" if refreshing else "Loading your funding brief…"):
        try:
            result, profile, views = load_brief(agency, min_days)
        except Exception:  # noqa: BLE001 - friendly message; details stay in server logs
            st.error("Couldn't load opportunities from Grants.gov right now. Try Refresh data in a moment.")
            return

    groups = group_views(views)
    selected = st.session_state.get("brief_selected")
    hidden = st.session_state["brief_hidden"]
    visible = {v.id: v for v in views}
    if selected is None or (selected != CLOSED and selected not in visible):
        first = next((v for v in groups["top"] + groups["check"] if not hidden.get(v.id)), None)
        selected = first.id if first else CLOSED
        st.session_state["brief_selected"] = selected
    panel_view = visible.get(selected) if selected != CLOSED else None

    if panel_view:
        main, side = st.columns([5, 3], gap="large")
    else:
        main, side = st.container(), None
    with main:
        _render_header(agency, profile, result, min_days, compact=panel_view is not None)
        _render_sections(groups, panel_view.id if panel_view else None, hidden, agency)
        _render_saved_bar(agency)
        _render_footer(profile)
    if side is not None:
        with side:
            render_panel(panel_view, on_close=_close_panel, saved=saved_store.is_saved(agency, panel_view.id),
                         on_toggle_save=_toggle_save, how_it_works_page=PAGES.get("how"))
