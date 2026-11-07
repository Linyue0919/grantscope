
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
        st.write("Search query:", query)
        st.write("Deadline:", deadline)
        st.write("Eligibility:", eligibility)
        st.write("Minimum award:", reward)
        st.write("Minimum match score:", match_score)
