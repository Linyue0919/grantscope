import streamlit as st

AGENCIES = [
    "NC Department of Environmental Quality",
    "NC Department of Transportation",
    "NC Department of Health and Human Services",
]
PRIORITIES = [
    "Clean Water", "Climate Resilience", "Transportation",
    "Rural Health", "Workforce Development", "Education",
]
DEFAULT_PREFERENCES = {
    "agency": AGENCIES[0],
    "priorities": ["Clean Water", "Climate Resilience"],
    "deadline_days": 15,
    "minimum_award": 100000,
    "minimum_match_score": 75,
    "notification": "Weekly digest",
}
NOTIFICATIONS = ["Weekly digest", "High-priority alerts", "None"]


def get_preferences():
    if "agency_preferences" not in st.session_state:
        st.session_state.agency_preferences = {
            **DEFAULT_PREFERENCES,
            "priorities": list(DEFAULT_PREFERENCES["priorities"]),
        }
    return st.session_state.agency_preferences


def show_profile():
    st.header("Agency Profile")
    st.write("Personalize federal grant discovery for your agency.")
    prefs = get_preferences()

    with st.form("agency_profile_form"):
        agency = st.selectbox(
            "Government Agency", AGENCIES,
            index=AGENCIES.index(prefs["agency"]) if prefs["agency"] in AGENCIES else 0,
        )
        priorities = st.multiselect(
            "Strategic Priorities", PRIORITIES,
            default=[p for p in prefs["priorities"] if p in PRIORITIES],
        )
        deadline_days = st.slider(
            "Default Deadline Window (days)", 1, 90,
            value=int(prefs["deadline_days"]),
        )
        col1, col2 = st.columns(2)
        with col1:
            minimum_award = st.number_input(
                "Preferred Minimum Award ($)", min_value=0,
                step=50000, value=int(prefs["minimum_award"]),
            )
        with col2:
            minimum_match_score = st.slider(
                "Preferred Minimum Match Score", 0, 100,
                value=int(prefs["minimum_match_score"]),
            )
        notification = st.radio(
            "Notification Preference", NOTIFICATIONS,
            index=NOTIFICATIONS.index(prefs["notification"]) if prefs["notification"] in NOTIFICATIONS else 0,
        )
        submitted = st.form_submit_button("Save Preferences", type="primary")

    if submitted:
        st.session_state.agency_preferences = {
            "agency": agency,
            "priorities": priorities,
            "deadline_days": int(deadline_days),
            "minimum_award": int(minimum_award),
            "minimum_match_score": int(minimum_match_score),
            "notification": notification,
        }
        # Refresh Search defaults the next time the user opens Search.
        st.session_state.pop("search_profile_signature", None)
        st.success("Preferences saved! Open Search to use your updated defaults.")

    st.caption(
        "Preferences last for this Streamlit session, not across devices. "
        "Award and match-score preferences are saved but are not applied until "
        "verified award data and a matching engine are available. "
        "Email notifications are not active."
    )
