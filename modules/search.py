from services.grants_api import get_grants
import streamlit as st

def show_search():
    st.header("Search Federal Grants")
    st.write("Discover federal funding opportunities for NC agencies.")

    query = st.text_input(
        "Search opportunities",
        placeholder="e.g. clean water, transportation, rural health"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        deadline = st.selectbox(
            "Deadline",
            ["Any", "Within 30 days", "Within 60 days", "Within 90 days"]
        )

    with col2:
        eligibility = st.selectbox(
            "Eligibility",
            ["All", "Eligible", "Needs Review", "Ineligible"]
        )

    with col3:
        reward = st.selectbox(
            "Minimum Award",
            ["Any", "$100K+", "$1M+", "$5M+"]
        )

    match_score = st.slider(
        "Minimum Match Score",
        min_value=0,
        max_value=100,
        value=70
    )

  

    if st.button("Search Grants", type="primary"):
        try:
            with st.spinner("Searching Grants.gov..."):
                grants = get_grants(query or "water", 20)

            st.success(f"Retrieved {len(grants)} grant records")

            for grant in grants:
                title = grant.get("title", "Untitled Grant")
                agency = grant.get("agency", "Unknown Agency")
                deadline = grant.get("closeDate", "Not specified")
                opportunity_id = grant.get("id")

                with st.container(border=True):
                    st.subheader(title)
                    st.write(f"**Agency:** {agency}")
                    st.write(f"**Deadline:** {deadline}")

                    if opportunity_id:
                        st.link_button(
                            "View Official Opportunity",
                            f"https://www.grants.gov/search-results-detail/{opportunity_id}"
                        )

        except Exception as error:
            st.error(f"Unable to retrieve grants: {error}")

