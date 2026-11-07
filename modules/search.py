"""Live federal opportunity search with transparent deadline filtering."""
from datetime import date, datetime
import streamlit as st

from services.grants_api import get_grants, get_grant_details, GrantsAPIError
from services.agency_directory import AGENCIES
from services.matching import rank_grants
from services.eligibility import screen_eligibility


def parse_close_date(value):
    """Accept common Grants.gov date formats; never guess an invalid date."""
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def filter_by_deadline(grants, deadline_days, include_unknown=False, today=None):
    today = today or date.today()
    matching, unknown = [], 0
    for grant in grants:
        closing = parse_close_date(grant.get("closeDate"))
        if closing is None:
            unknown += 1
            if include_unknown:
                matching.append(grant)
        elif 0 <= (closing - today).days <= deadline_days:
            matching.append(grant)
    return sorted(
        matching,
        key=lambda grant: parse_close_date(grant.get("closeDate")) or date.max,
    ), unknown


def show_search():
    st.header("Search Federal Grants")
    st.write("Discover live federal funding opportunities for NC agencies.")
    st.caption("Search is independent of saved Profile preferences. Choose filters for this search.")
    agency = st.selectbox("Agency to evaluate", AGENCIES, key="search_agency")
    query = st.text_input(
        "Search opportunities",
        key="search_query",
        placeholder="e.g. clean water, transportation, rural health",
    )
    col1, col2 = st.columns(2)
    with col1:
        deadline_days = st.number_input(
            "Closing within (days)", min_value=1, max_value=365,
            step=1, value=30, key="search_deadline_days",
            help="Only affects this Search page.",
        )
    with col2:
        include_unknown = st.checkbox(
            "Include grants with unknown deadlines",
            help="Unknown dates cannot be confirmed to fall within the window.",
        )

    show_ineligible = st.checkbox(
        "Show ineligible grants (audit view)", value=False,
        help="By default, hide grants confirmed ineligible for direct application. Unchecked grants remain visible as Needs Review.",
    )
    show_zero_matches = st.checkbox(
        "Show zero-evidence matches (audit view)", value=False,
        help="Hide results with no matched strategic goal terms. This does not prove they are unrelated.",
    )
    min_award = st.number_input(
        "Minimum verified award ceiling ($; 0 = no filter)",
        min_value=0, step=50000, value=0,
        help="Applies only to opportunities whose official details you have loaded. Unknown amounts are not assumed to qualify.",
    )
    min_match_score = st.slider(
        "Minimum strategic match score", min_value=0, max_value=100,
        value=0, step=1,
        help="Prototype keyword-overlap score. Unscored agencies are kept visible and labeled.",
    )

    if st.button("Search Grants", type="primary"):
        if not query.strip():
            st.warning("Enter a keyword to search Grants.gov.")
            st.session_state.pop("search_last_results", None)
            return
        try:
            with st.spinner("Searching Grants.gov..."):
                grants = get_grants(query.strip(), 100)
        except GrantsAPIError as exc:
            st.error(str(exc))
            return
        st.session_state["search_last_results"] = {
            "query": query.strip(), "grants": grants,
        }

    cached = st.session_state.get("search_last_results")
    if not cached:
        st.caption("Run a search to see live opportunity records.")
        return

    if query.strip() != cached["query"]:
        st.caption(f'Showing the previous search for "{cached["query"]}". Click Search Grants to refresh.')
    grants = cached["grants"]
    matching, unknown_count = filter_by_deadline(
        grants, int(deadline_days), include_unknown,
    )
    st.write(
        f'{len(matching)} opportunities shown from {len(grants)} retrieved '
        f'Grants.gov records for "{cached["query"]}".'
    )
    if unknown_count:
        st.caption(
            f"{unknown_count} records have missing or unrecognized deadlines. "
            "Verify dates on the official listing."
        )
    if len(grants) >= 100:
        st.warning(
            "Only the first 100 search records were requested; this is NOT "
            "an exhaustive result set. Try a narrower keyword."
        )
    if not matching:
        st.warning("No results in this deadline window. Try more days or a broader keyword.")

    detail_cache = st.session_state.setdefault("grant_detail_cache", {})
    # Explicitly user-triggered bounded screening, not 100 background API calls.
    unscreened = [
        g for g in matching
        if g.get("id") and str(g["id"]) not in detail_cache
    ]
    if unscreened:
        st.caption(f"{len(unscreened)} displayed candidates have not had their official eligibility details checked.")
        if st.button("Screen next 10 grants using official eligibility details"):
            failures = 0
            with st.spinner("Checking up to 10 official Grants.gov records..."):
                for grant in unscreened[:10]:
                    key = str(grant["id"])
                    try:
                        detail_cache[key] = get_grant_details(grant["id"])
                    except GrantsAPIError:
                        failures += 1
            if failures:
                st.warning(f"{failures} detail requests failed; those opportunities remain Needs Review.")
            st.rerun()
    screened_count = sum(str(g.get("id")) in detail_cache for g in matching)
    st.caption(f"Official detail coverage: {screened_count}/{len(matching)} candidates. Unscreened results are not confirmed eligible.")
    if min_award > 0:
        matching = [
            g for g in matching
            if str(g.get("id")) in detail_cache
            and detail_cache[str(g.get("id"))].get("award_ceiling") is not None
            and detail_cache[str(g.get("id"))]["award_ceiling"] >= min_award
        ]
        st.caption("Award filter applies only to opportunities with loaded, verified detail records; other results are excluded, not treated as ineligible.")
    ineligible_ids = {
        str(g.get("id")) for g in matching
        if str(g.get("id")) in detail_cache
        and screen_eligibility(detail_cache[str(g.get("id"))], agency)["status"] == "Ineligible"
    }
    if not show_ineligible:
        matching = [g for g in matching if str(g.get("id")) not in ineligible_ids]
        if ineligible_ids:
            st.info(f"{len(ineligible_ids)} confirmed ineligible grant(s) hidden. Turn on 'Show ineligible grants (audit view)' to inspect them.")
    ranked = rank_grants(matching, agency, detail_cache=detail_cache)
    zero_evidence = sum(g["match_score"] == 0 for g in ranked)
    if not show_zero_matches:
        ranked = [g for g in ranked if g["match_score"] != 0]
        if zero_evidence:
            st.info(f"{zero_evidence} zero-evidence result(s) hidden. Turn on 'Show zero-evidence matches (audit view)' to inspect them. These are not proven irrelevant.")
    ranked = [g for g in ranked if g["match_score"] is None or g["match_score"] >= min_match_score]
    if not ranked:
        st.warning("No results with strategic match evidence under the current filters. Try a broader search or enable audit view.")
    if ranked and not ranked[0]["plan_verified"]:
        st.info("No verified strategic goals have been extracted for this agency yet. Results are shown without a match score; eligibility still needs human review.")
    else:
        st.caption("Match scores are a simple, preliminary strategic-topic overlap heuristic, NOT grant eligibility or award probability.")
    for grant in ranked:
        title = grant.get("title") or "Untitled Grant"
        agency = grant.get("agency") or "Unknown federal agency"
        closing = grant.get("closeDate") or "Not specified"
        opportunity_id = grant.get("id")
        with st.container(border=True):
            st.subheader(title)
            if grant["match_score"] is not None:
                st.write(f'**Strategic relevance (prototype): {grant["match_score"]}/100**')
                if grant["match_reasons"]:
                    for reason in grant["match_reasons"]:
                        st.caption(f'Plan goal: {reason["goal"]} (plan page {reason["page"]}); matched terms: {", ".join(reason["keywords"])}')
                else:
                    st.caption("No goal keywords matched in the available search summary.")
                st.markdown(f'[Agency strategic plan source]({grant["plan_url"]})')
            else:
                st.caption("Strategic plan goals not yet verified for this agency; no relevance score assigned.")
            st.write(f"**Federal agency:** {agency}")
            st.write(f"**Closing date (Grants.gov):** {closing}")
            st.caption("Eligibility requires official detail review. Strategic relevance does not establish application eligibility.")
            if opportunity_id:
                detail_key = str(opportunity_id)
                if st.button("Load official award & eligibility details", key=f"detail_{detail_key}"):
                    try:
                        with st.spinner("Loading official Grants.gov details..."):
                            detail_cache[detail_key] = get_grant_details(opportunity_id)
                        if (
                            not show_ineligible
                            and screen_eligibility(detail_cache[detail_key], prefs["agency"])["status"] == "Ineligible"
                        ):
                            st.rerun()
                    except GrantsAPIError as exc:
                        st.error(str(exc))
                details = detail_cache.get(detail_key)
                if details:
                    floor, ceiling = details["award_floor"], details["award_ceiling"]
                    fmt = lambda n: f"${n:,.0f}" if n is not None else "Not reported"
                    st.write(f'**Award floor:** {fmt(floor)} · **Award ceiling:** {fmt(ceiling)}')
                    screening = screen_eligibility(details, prefs["agency"])
                    if screening["status"] == "Ineligible":
                        st.error(f'**Eligibility: Ineligible for direct application** — {screening["reason"]}')
                        st.caption(f'Official evidence: {screening.get("evidence", "See eligibility notes below.")}')
                    else:
                        st.warning(f'**Eligibility: Needs Review** — {screening["reason"]}')
                    st.write("**Official applicant types:** " + (", ".join(details["applicant_types"]) or "Not reported"))
                    if details["eligibility_description"]:
                        with st.expander("Official eligibility notes"):
                            st.write(details["eligibility_description"])
                    if details["description"]:
                        with st.expander("Official opportunity description"):
                            st.write(details["description"])
                st.link_button(
                    "View Official Opportunity",
                    f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                )
