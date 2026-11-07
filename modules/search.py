"""Live federal opportunity search with transparent deadline filtering."""
from datetime import date, datetime
import streamlit as st

from services.grants_api import get_grants, GrantsAPIError
from modules.profile import get_preferences
from services.matching import rank_grants


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
    prefs = get_preferences()
    st.info(f'Current agency: {prefs["agency"]}. Search defaults come from Agency Profile.')

    signature = (prefs["agency"], tuple(prefs["priorities"]), prefs["deadline_days"])
    if st.session_state.get("search_profile_signature") != signature:
        st.session_state["search_profile_signature"] = signature
        st.session_state["search_deadline_days"] = int(prefs["deadline_days"])
        st.session_state["search_query"] = " ".join(prefs["priorities"][:1]).lower()
        st.session_state.pop("search_last_results", None)

    query = st.text_input(
        "Search opportunities",
        key="search_query",
        placeholder="e.g. clean water, transportation, rural health",
    )
    col1, col2 = st.columns(2)
    with col1:
        deadline_days = st.number_input(
            "Closing within (days)", min_value=1, max_value=365,
            step=1, key="search_deadline_days",
            help="Override your saved Profile deadline for this search.",
        )
    with col2:
        include_unknown = st.checkbox(
            "Include grants with unknown deadlines",
            help="Unknown dates cannot be confirmed to fall within the window.",
        )

    st.caption(
        f'Profile preferences: minimum award ${prefs["minimum_award"]:,}; '
        f'minimum match score {prefs["minimum_match_score"]}/100. '
        "These are NOT active filters: award amounts and agency eligibility "
        "need official detail verification; match scoring needs a separate model."
    )

    if st.button("Search Grants", type="primary"):
        if not query.strip():
            st.warning("Enter a keyword or choose a strategic priority in Profile.")
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

    ranked = rank_grants(matching, prefs["agency"])
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
            st.caption("Eligibility: Needs Review. Award amount: not verified. Relevance is based on available summary text only; verify full official opportunity details.")
            if opportunity_id:
                st.link_button(
                    "View Official Opportunity",
                    f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                )
