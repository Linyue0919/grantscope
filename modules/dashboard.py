"""Dashboard: decision support for NC agencies choosing which federal grants to pursue."""
import os
from datetime import date

import streamlit as st

from modules.grant_card import render_grant_card
from modules.profile import get_preferences
from services.agency_profiles import (
    find_unprofiled_plan, get_agency_profile, list_profiled_agencies,
    list_unprofiled_agencies, load_plan_data, resolve_agency_name,
)
from services.ai_eligibility import AzureEligibilityEvaluator
from services.ai_matching import AzureFitEvaluator, describe_config, load_ai_config
from services.application_effort import EffortAnalysisError, assess_effort, fetch_announcement_text
from services.grants_api import get_grants
from services.match_engine import (
    AI_WEIGHT, DESCRIPTION_CAP, ELIGIBLE_TYPE, FIT_POINTS, MatchSettings, run_matching,
)
from services.opportunity_details import fetch_opportunity_details

DAYS_OPTIONS = {"Any open grant": None, "At least 7 days left": 7, "At least 14 days left": 14,
                "At least 30 days left": 30, "At least 60 days left": 60, "At least 90 days left": 90}
SCREEN_LABELS = {
    "closed": "Deadline passed",
    "not_enough_time": "Fewer days left than you require",
    "not_eligible": "Confirmed eligibility restriction excludes state agencies",
    "below_min_award": "Award ceiling below your minimum",
    "unknown_deadline_hidden": "No closing date listed (hidden)",
}


@st.cache_resource
def _shared_details_cache():
    """Official details shared across sessions (an opportunity's details rarely change)."""
    return {}


@st.cache_resource
def _shared_ai_cache():
    return {}


def _ai_config():
    """Azure OpenAI settings from environment variables, then Streamlit secrets."""
    return load_ai_config(st.secrets)


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


def _analyze_announcement(record):
    details = _shared_details_cache().get(record["id"])
    store = st.session_state.setdefault("announcements", {})
    try:
        with st.spinner("Reading the official announcement..."):
            store[record["id"]] = fetch_announcement_text(details)
    except EffortAnalysisError as exc:
        st.session_state.setdefault("announcement_errors", {})[record["id"]] = str(exc)
    st.rerun()


def _with_announcement(record):
    """Apply an on-demand full-announcement analysis to a record's effort assessment."""
    analysis = st.session_state.get("announcements", {}).get(record["id"])
    if not analysis:
        return record
    details = _shared_details_cache().get(record["id"])
    return dict(record, effort=assess_effort(details, *analysis))


def _render_card(record, prefix):
    error = st.session_state.get("announcement_errors", {}).pop(record["id"], None)
    render_grant_card(_with_announcement(record), key_prefix=prefix, on_analyze=_analyze_announcement)
    if error:
        st.caption(f"⚠ Full announcement: {error}")


def _default_agency(prefs, agencies):
    resolved = resolve_agency_name(prefs.get("agency"))
    return resolved if resolved in agencies else agencies[0]


def _render_unprofiled_notice(prefs):
    saved = prefs.get("agency")
    if saved and not resolve_agency_name(saved):
        plan = find_unprofiled_plan(saved)
        link = f" [Official plan]({plan['plan_url']})." if plan else ""
        st.info(f"Your Profile agency ({saved}) does not have verified strategic goals yet, "
                f"so grants cannot be assessed for it.{link} Choose a profiled agency below.")


def _render_summary(result):
    results = result["results"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Priority grants", len(results), help="Open, enough time to apply, evidence of strategic fit.")
    m2.metric("Appear eligible", sum(1 for r in results if r["eligibility"]["status"] == ELIGIBLE_TYPE),
              help="Official applicant types or eligibility notes include state governments. Still verify.")
    m3.metric("Strong fit (60+)", sum(1 for r in results if (r["fit_score"] or 0) >= 60))
    m4.metric("Upcoming (not yet open)", len(result["upcoming"]),
              help="Forecasted grants with strategic-plan evidence. Not yet accepting applications.")


def _render_low_evidence(records):
    if not records:
        return
    with st.expander(f"Lower-evidence candidates ({len(records)}) — open grants with low or unassessed fit"):
        st.caption("These grants are open and passed screening, but no strategic-plan terms were found "
                   "(Low fit) or their official description was not loaded (Not assessed). They are listed, "
                   "not excluded, because relevant grants can use different wording.")
        st.dataframe(
            [{"Grant": r["title"], "Fit": r["relevance"]["label"], "Time to apply": r["urgency"]["label"],
              "Eligibility": r["eligibility"]["label"], "Funding": r["funding"]["display"],
              "Listing": r["source_url"]} for r in records],
            column_config={"Listing": st.column_config.LinkColumn("Listing", display_text="Open ↗")},
            hide_index=True, width="stretch",
        )


def _render_likely_ineligible(records):
    if not records:
        return
    with st.expander(f"Likely not eligible to apply directly ({len(records)}) — verify before dismissing"):
        st.caption("The official eligibility notes appear to limit applicants to categories that do not include "
                   "state governments. These are interpretations, not confirmed exclusions, so they stay visible. "
                   "Partnering with an eligible applicant may still be possible.")
        st.dataframe(
            [{"Grant": r["title"], "Strategic fit": r["fit_score"], "Why": r["eligibility"]["reasoning"],
              "Official text": (r["eligibility"]["quote"] or "") + (" …" if r["eligibility"]["quote_truncated"] else ""),
              "Basis": r["eligibility"]["certainty_label"], "Listing": r["source_url"]} for r in records],
            column_config={"Listing": st.column_config.LinkColumn("Listing", display_text="Open ↗"),
                           "Strategic fit": st.column_config.NumberColumn(format="%d")},
            hide_index=True, width="stretch",
        )


def _render_coverage(result, profile, keywords):
    stats, queries = result["stats"], result["queries"]
    with st.expander("About these results: coverage and limits"):
        sources = f"{profile['short_name']}'s strategic goals" + (" and your Profile priorities" if keywords else "")
        st.markdown(
            f"GrantScope searched Grants.gov with **{len(queries)} targeted keywords** drawn from {sources}. "
            "Each agency is searched with its own keywords, so **different agencies see different candidate "
            "sets**.\n\n"
            f"- Grants.gov returns at most **100 records per keyword**; **{stats['capped_queries']} of "
            f"{len(queries)}** searches reached that cap, so some matching opportunities may not have been "
            f"retrieved.\n"
            f"- **{stats['unique_candidates']}** unique opportunities were retrieved; "
            f"**{stats['actionable_candidates']}** were still open (or upcoming) with enough time left.\n"
            f"- Official details (eligibility, funding, requirements) were loaded for "
            f"**{stats['details_loaded']}** of them. Grants without details show \"Not yet checked\" and "
            "\"Fit not assessed\".\n"
            "- Upcoming (forecasted) grants are listed separately and are never priority recommendations."
        )
        st.dataframe(
            [{"Keyword": q["query"],
              "Source": "Your Profile" if q["source"] == "user" else f"Plan goal {q['source']}",
              "Records": q["retrieved"],
              "Note": "Search failed" if q["error"] else ("100-record cap reached" if q["cap_reached"] else "")}
             for q in queries],
            hide_index=True, width="stretch",
        )
        if stats["screened_out_by_reason"]:
            st.markdown("**Screened out by deterministic rules (excluded, not down-ranked):**")
            st.markdown("\n".join(f"- {SCREEN_LABELS.get(code, code)}: {count}"
                                  for code, count in sorted(stats["screened_out_by_reason"].items(),
                                                            key=lambda kv: -kv[1])))
        for error in result["errors"][:5]:
            st.caption(f"⚠ {error}")


def _render_method(profile, result):
    data = load_plan_data()
    ai = result["ai"]
    ai_line = {
        "disabled": "AI semantic assessment is **off**; the score is the keyword heuristic.",
        "ok": f"AI semantic assessment (**{ai['model']}**) was used for {ai['accepted']} grant(s).",
        "partial": f"AI semantic assessment (**{ai['model']}**): {ai['accepted']} accepted, "
                   f"{ai['rejected']} rejected for unverifiable citations, {ai['errors']} failed. "
                   "Others use the keyword heuristic.",
        "error": "AI semantic assessment failed; the keyword heuristic is used.",
    }[ai["status"]]
    elig_ai = result.get("ai_eligibility", {})
    if elig_ai.get("status", "disabled") != "disabled":
        ai_line += (f" AI eligibility interpretation: {elig_ai['accepted']} accepted, {elig_ai['rejected']} rejected, "
                    f"{elig_ai['errors']} failed.")
    cfg = describe_config(_ai_config())
    if cfg["configured"]:
        ai_line += f" Configured deployment: `{cfg['deployment']}` (API {cfg['api_version']}, endpoint {cfg['endpoint']})."
    with st.expander("How GrantScope decides"):
        st.markdown(
            f"""
**1. Screening (deterministic, pass/fail).** Excluded: closed grants, grants with fewer days left than you
require, grants with a **confirmed** eligibility restriction (the structured applicant types exclude state
governments, or the notes explicitly say state governments are not eligible), and (if set) grants whose
reported award ceiling is below your minimum. Forecasted grants go to *Upcoming*.

**Eligibility** reads both the structured applicant types and the full eligibility notes. When the notes list
eligible applicants without state governments, the grant is shown as *Likely not eligible* (an interpretation,
kept visible but out of the priority list). Unclear cases stay in the list, flagged *Needs review*. A GPT-4o
interpretation (when configured) can resolve unclear cases only with an exact quote from the official text; it
can never override a confirmed restriction, and disagreements become *Needs review*.

**2. Strategic fit (0–100, heuristic).** Measures relevance to {profile['short_name']}'s published goals only.
Keyword heuristic: plan terms in the grant title (phrase {FIT_POINTS['title_phrase']}, word
{FIT_POINTS['title_word']}) or official description (phrase {FIT_POINTS['description_phrase']}, word
{FIT_POINTS['description_word']}; description-only evidence capped at {DESCRIPTION_CAP}), capped at 100. When AI is used, the score is an **experimental,
unvalidated** blend ({int((1 - AI_WEIGHT) * 100)}% keyword, {int(AI_WEIGHT * 100)}% AI); AI answers are
accepted only if their quotes are found verbatim in the grant text and goals. {ai_line}

**3. Reported separately, never in the score:** eligibility, days left, funding (award ceilings are
maximums, not guaranteed amounts) and application effort (requirements found in official text; no hour
estimates).

Strategic fit is **not** eligibility and **not** the probability of receiving an award.

**Sources:** live Grants.gov API; {profile['short_name']} strategic plan ({profile['plan_period']}),
[official PDF]({profile['plan_url']}), from the [NC OSBM directory]({data['source_directory']}).
            """
        )


def show_dashboard():
    st.header("Dashboard")
    st.caption("Open federal grants that fit your agency's strategic plan, with time to apply.")

    prefs = get_preferences()
    agencies = list_profiled_agencies()
    _render_unprofiled_notice(prefs)
    ai_config = _ai_config()

    c1, c2 = st.columns([2, 1])
    agency = c1.selectbox("Agency", agencies, index=agencies.index(_default_agency(prefs, agencies)),
                          key="dash_agency")
    days_label = c2.selectbox("Time to apply", list(DAYS_OPTIONS), index=list(DAYS_OPTIONS).index("At least 30 days left"),
                              key="dash_min_days", help="Hide grants that close too soon to prepare an application.")
    min_days = DAYS_OPTIONS[days_label]

    with st.expander("Advanced filters"):
        a1, a2 = st.columns(2)
        min_award = a1.number_input("Minimum award ceiling ($, optional)", min_value=0, step=50000, value=0,
                                    key="dash_min_award",
                                    help="Hides grants whose reported award ceiling is lower. "
                                         "Grants that do not report an amount are kept.")
        include_unknown = a2.checkbox("Include grants with no closing date", value=False, key="dash_unknown")
        use_profile_keywords = a2.checkbox(
            "Also search my Profile priorities", value=True, key="dash_profile_kw",
            help="Adds your Profile priorities as extra search keywords. They do not change the score.")
        use_ai = a1.toggle("AI semantic assessment (GPT-4o)", value=bool(ai_config), key="dash_ai",
                           disabled=not ai_config,
                           help="Requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY." if not ai_config
                           else "Adds a validated semantic assessment to the keyword heuristic.")
        if not ai_config:
            st.caption("AI is not configured, so Strategic Fit uses the deterministic keyword heuristic.")

    profile = get_agency_profile(agency)
    same_agency = resolve_agency_name(prefs.get("agency")) == agency
    keywords = tuple(prefs.get("priorities", [])) if (use_profile_keywords and same_agency) else ()

    if st.button("↻ Refresh live data", help="Fetch the latest opportunities from Grants.gov"):
        _cached_match.clear()

    with st.spinner(f"Checking live Grants.gov opportunities against the {profile['short_name']} strategic plan..."):
        try:
            result = _cached_match(agency, min_days, int(min_award), include_unknown, keywords,
                                   bool(use_ai and ai_config), date.today().isoformat())
        except Exception as exc:  # noqa: BLE001 - friendly error instead of a stack trace
            st.error(f"Could not build the dashboard: {exc}")
            return

    if result["errors"] and not result["stats"]["unique_candidates"]:
        st.error("Grants.gov could not be reached. Please try Refresh in a moment.")
        return

    _render_summary(result)
    st.caption(f"Live data as of {result['generated_at'].replace('T', ' ').replace('+00:00', ' UTC')}. "
               "Strategic fit is a heuristic for relevance, separate from eligibility and award likelihood.")

    results = result["results"]
    st.subheader("Priority grants")
    if not results:
        st.warning("No open grants with strategic-plan evidence meet these filters. Try 'Any open grant' "
                   "or review the lower-evidence candidates below.")
    else:
        show_all = len(results) > 10 and st.toggle(f"Show all {len(results)}", key="dash_show_all")
        for record in results if show_all else results[:10]:
            _render_card(record, "dash")

    if result["upcoming"]:
        with st.expander(f"Upcoming — forecasted, not yet accepting applications ({len(result['upcoming'])})"):
            hidden = result["stats"]["upcoming_low_evidence"]
            st.caption("Forecasted opportunities are announced but not open. Dates and amounts are estimates. "
                       "Useful for planning; not priority recommendations."
                       + (f" {hidden} other forecasted grant(s) without plan evidence are not listed." if hidden else ""))
            for record in result["upcoming"][:15]:
                _render_card(record, "up")

    _render_likely_ineligible(result["likely_ineligible"])
    _render_low_evidence(result["low_evidence"])
    _render_coverage(result, profile, keywords)
    _render_method(profile, result)
    with st.expander(f"Other NC agencies ({len(list_unprofiled_agencies())} plans not yet profiled)"):
        st.caption("These agencies have official strategic plans, but their goals have not been extracted "
                   "and verified yet, so GrantScope does not assess grants for them.")
        st.markdown("\n".join(f"- [{a['name']}]({a['plan_url']})" for a in list_unprofiled_agencies()))
