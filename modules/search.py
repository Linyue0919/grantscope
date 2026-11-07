from datetime import date, datetime
import streamlit as st
from services.grants_api import get_grants
from modules.profile import get_preferences


def parse_close_date(value):
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def show_search():
    st.header("Search Federal Grants")
    st.write("Discover federal funding opportunities for NC agencies.")
    prefs = get_preferences()
    st.info(f'Current agency: {prefs["agency"]}. Search defaults come from Agency Profile.')

    signature = (prefs["agency"], tuple(prefs["priorities"]), prefs["deadline_days"])
    if st.session_state.get("search_profile_signature") != signature:
        st.session_state["search_profile_signature"] = signature
        st.session_state["search_deadline_days"] = int(prefs["deadline_days"])
        st.session_state["search_query"] = " ".join(prefs["priorities"][:1]).lower()

    query = st.text_input(
        "Search opportunities", key="search_query",
        placeholder="e.g. clean water, transportation, rural health",
    )
    col1, col2 = st.columns(2)
    with col1:
        deadline_days = st.number_input(
            "Closing within (days)", min_value=1, max_value=365,
            step=1, key="search_deadline_days",
            help="Change this for one search without changing your saved Profile.",
        )
    with col2:
        include_unknown = st.checkbox(
            "Include grants with unknown deadlines", value=False,
            help="Unknown deadlines cannot be confirmed to fall within your window.",
        )

    st.caption(
        f'Profile preferences: minimum award ${prefs["minimum_award"]:,}; '
        f'minimum match score {prefs["minimum_match_score"]}/100. '
        "These are not active filters yet: award amounts and agency eligibility "
        "require additional official details; match scoring requires an evaluation model."
    )

    if st.button("Search Grants", type="primary"):
        if not query.strip():
            st.warning("Enter a keyword or select a strategic priority in Profile.")
            return
        try:
            with st.spinner("Searching live Grants.gov opportunities..."):
                grants = get_grants(query.strip(), 100)
        except Exception as error:
            st.error(f"Unable to retrieve Grants.gov records: {error}")
            return

        today = date.today()
        matching = []
        unknown_count = 0
        for grant in grants:
            closing = parse_close_date(grant.get("closeDate"))
            if closing is None:
                unknown_count += 1
                if include_unknown:
                    matching.append(grant)
                continue
            days_left = (closing - today).days
            if 0 <= days_left <= deadline_days:
                matching.append(grant)

        st.write(
            f"Retrieved {len(grants)} Grants.gov records for this keyword; "
            f"{len(matching)} meet the deadline display criteria."
        )
        if unknown_count:
            st.caption(
                f"{unknown_count} records have missing or unrecognized deadlines; "
                "check the official listing before relying on dates."
            )
        if len(grants) == 100:
            st.caption("Showing results from the first 100 API records, not an exhaustive search.")
        if not matching:
            st.warning("No results in this deadline window. Try a broader keyword or more days.")

        for grant in matching:
            title = grant.get("title") or "Untitled Grant"
            agency = grant.get("agency") or "Unknown federal agency"
            closing = grant.get("closeDate") or "Not specified"
            opportunity_id = grant.get("id")
            with st.container(border=True):
                st.subheader(title)
                st.write(f"**Federal agency:** {agency}")
                st.write(f"**Closing date (Grants.gov):** {closing}")
                st.caption("Agency eligibility, award amount, and match score: not yet verified.")
                if opportunity_id:
                    st.link_button(
                        "View Official Opportunity",
                        f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                    )
