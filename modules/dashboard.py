"""Dashboard: highest-priority federal grants for an NC agency, ranked by Match Score."""
from datetime import date

import streamlit as st

from modules.grant_card import render_grant_card
from modules.profile import get_preferences
from services.agency_profiles import (
    find_unprofiled_plan, get_agency_profile, list_profiled_agencies,
    list_unprofiled_agencies, load_plan_data, resolve_agency_name,
)
from services.grants_api import get_grants
from services.match_engine import ELIGIBLE_TYPE, WEIGHTS, MatchSettings, run_matching
from services.opportunity_details import fetch_opportunity_details

WINDOW_OPTIONS = [30, 60, 90, 180, 365]
SCREEN_LABELS = {
    "closed": "Deadline passed",
    "outside_window": "Closes after your window",
    "not_eligible": "State agencies not an eligible applicant type",
    "no_alignment_evidence": "No link to the agency's strategic goals",
    "forecasted_hidden": "Forecasted (hidden by filter)",
    "unknown_deadline_hidden": "No closing date listed (hidden by filter)",
}


@st.cache_resource
def _shared_details_cache():
    """Official details shared across sessions (an opportunity's details rarely change)."""
    return {}


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_match(agency, horizon_days, min_award, include_forecasted, include_unknown,
                  keywords, today_iso):
    settings = MatchSettings(
        horizon_days=horizon_days, min_award=min_award,
        include_forecasted=include_forecasted, include_unknown_deadline=include_unknown,
    )
    return run_matching(
        get_agency_profile(agency), settings,
        search_fn=get_grants, details_fn=fetch_opportunity_details,
        today=date.fromisoformat(today_iso), extra_keywords=keywords,
        details_cache=_shared_details_cache(),
    )


def _default_agency(prefs, agencies):
    resolved = resolve_agency_name(prefs.get("agency"))
    return resolved if resolved in agencies else agencies[0]


def _render_unprofiled_notice(prefs):
    saved = prefs.get("agency")
    if saved and not resolve_agency_name(saved):
        plan = find_unprofiled_plan(saved)
        link = f" [Official plan]({plan['plan_url']})." if plan else ""
        st.info(f"Your Profile agency ({saved}) does not have extracted strategic goals yet, "
                f"so it cannot be scored.{link} Choose a profiled agency below to preview matching.")


def _render_summary(result):
    results, stats = result["results"], result["stats"]
    soon = sum(1 for r in results if r["deadline"]["days_left"] is not None and r["deadline"]["days_left"] <= 30)
    eligible = sum(1 for r in results if r["eligibility"]["status"] == ELIGIBLE_TYPE)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Matched grants", len(results))
    m2.metric("Closing within 30 days", soon)
    m3.metric("Eligible applicant type listed", eligible)
    m4.metric("Opportunities scanned", stats["unique_candidates"])


def _render_coverage(result):
    stats = result["stats"]
    with st.expander("Search coverage & screening"):
        st.write(f"**{stats['unique_candidates']}** unique Grants.gov opportunities retrieved from "
                 f"**{len(result['queries'])}** searches; official details loaded for "
                 f"**{stats['details_loaded']}**. **{stats['passed_screening']}** passed screening.")
        if stats["possibly_incomplete"]:
            st.caption("Some searches returned the 100-record maximum or failed, so coverage is not exhaustive.")
        st.table([
            {"Search keyword": q["query"],
             "Derived from": "Your Profile" if q["source"] == "user" else f"Plan goal {q['source']}",
             "Records": q["retrieved"],
             "Note": "Error" if q["error"] else ("100-record cap reached" if q["cap_reached"] else "")}
            for q in result["queries"]
        ])
        if stats["screened_out_by_reason"]:
            st.markdown("**Screened out (excluded, not down-ranked):**")
            st.table([{"Reason": SCREEN_LABELS.get(code, code), "Grants": count}
                      for code, count in sorted(stats["screened_out_by_reason"].items(), key=lambda kv: -kv[1])])
        for error in result["errors"]:
            st.caption(f"⚠ {error}")


def _render_method(profile):
    data = load_plan_data()
    with st.expander("How the Match Score works"):
        st.markdown(
            f"""
**Screening rules (pass/fail, applied first):** grants that are closed, close after your window,
list applicant types that exclude state agencies, or show no link to the agency's strategic goals
are **excluded**. They are not just down-ranked.

**Match Score (0–100), for grants that pass:**
- **Strategic alignment (up to {WEIGHTS['strategic_alignment']}):** phrases from the agency's official goals found in
  the grant title (full points) or official description (half points).
- **Deadline actionability (up to {WEIGHTS['deadline']}):** more time to apply scores higher; forecasted and
  undated grants get partial credit.
- **Funding fit (up to {WEIGHTS['funding']}):** award ceiling compared with your minimum award; unreported
  amounts get partial credit.

The Match Score measures **fit and actionability**. It is **not** the probability of winning an award.
"Eligible applicant type listed" means Grants.gov lists *State governments*; always confirm the full
eligibility rules in the official notice.

**Sources:** live data from the Grants.gov API. Agency goals are verbatim quotes from the
{profile['short_name']} strategic plan ({profile['plan_period']}), [official PDF]({profile['plan_url']}),
listed in the [NC OSBM directory]({data['source_directory']}).
            """
        )


def show_dashboard():
    st.header("Dashboard")
    st.caption("The most relevant open federal grants for your agency, matched to its official strategic plan.")

    prefs = get_preferences()
    agencies = list_profiled_agencies()
    _render_unprofiled_notice(prefs)

    c1, c2, c3 = st.columns([2, 1, 1])
    agency = c1.selectbox("Agency", agencies, index=agencies.index(_default_agency(prefs, agencies)),
                          key="dash_agency")
    horizon = c2.selectbox("Closing within", WINDOW_OPTIONS, index=WINDOW_OPTIONS.index(90),
                           format_func=lambda d: f"{d} days", key="dash_horizon")
    min_award = c3.number_input("Minimum award ($)", min_value=0, step=50000,
                                value=int(prefs.get("minimum_award", 0)), key="dash_min_award")
    with st.expander("More filters"):
        f1, f2 = st.columns(2)
        include_forecasted = f1.checkbox("Include forecasted grants", value=True, key="dash_forecasted",
                                         help="Forecasted grants are not yet accepting applications.")
        include_unknown = f2.checkbox("Include grants with no closing date", value=False, key="dash_unknown")
        use_profile_keywords = st.checkbox(
            "Also search my Profile priorities", value=True, key="dash_profile_kw",
            help="Adds your Profile priorities as extra search keywords. They do not change the score.",
        )

    profile = get_agency_profile(agency)
    same_agency = resolve_agency_name(prefs.get("agency")) == agency
    keywords = tuple(prefs.get("priorities", [])) if (use_profile_keywords and same_agency) else ()

    refresh = st.button("↻ Refresh live data", help="Fetch the latest opportunities from Grants.gov")
    if refresh:
        _cached_match.clear()

    with st.spinner("Scanning live Grants.gov opportunities against the agency's strategic plan..."):
        try:
            result = _cached_match(agency, int(horizon), int(min_award), include_forecasted,
                                   include_unknown, keywords, date.today().isoformat())
        except Exception as exc:  # noqa: BLE001 - show a friendly error instead of a stack trace
            st.error(f"Could not build the dashboard: {exc}")
            return

    if result["errors"] and not result["stats"]["unique_candidates"]:
        st.error("Grants.gov could not be reached. Please try Refresh in a moment.")
        for error in result["errors"][:3]:
            st.caption(error)
        return

    _render_summary(result)
    st.caption(f"Updated {result['generated_at'].replace('T', ' ').replace('+00:00', ' UTC')} · "
               "Match Score measures fit with the agency's strategic goals, not the chance of winning.")

    results = result["results"]
    if not results:
        st.warning("No grants passed screening for these filters. Try a longer window or include forecasted grants.")
    else:
        show_n = st.radio("Show", ["Top 10", "All"], horizontal=True, key="dash_show",
                          label_visibility="collapsed") if len(results) > 10 else "All"
        for i, item in enumerate(results if show_n == "All" else results[:10]):
            render_grant_card(item, key_prefix=f"dash_{i}")

    _render_coverage(result)
    _render_method(profile)
    with st.expander(f"Other NC agencies ({len(list_unprofiled_agencies())} plans not yet profiled)"):
        st.caption("These agencies have official strategic plans, but their goals have not been extracted "
                   "and verified yet, so GrantScope does not score grants for them.")
        st.markdown("\n".join(f"- [{a['name']}]({a['plan_url']})" for a in list_unprofiled_agencies()))
