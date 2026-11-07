
import streamlit as st

AGENCIES = [
    "NC Department of Environmental Quality",
    "NC Department of Transportation",
    "NC Department of Health and Human Services",
]

PRIORITIES = [
    "Clean Water",
    "Climate Resilience",
    "Transportation",
    "Rural Health",
    "Workforce Development",
    "Education",
]


def show_profile():
    st.header("Agency Profile")
    st.write("Personalize federal grant discovery for your agency.")

    # Initialize preferences for this browser session.
    if "agency_preferences" not in st.session_state:
        st.session_state.agency_preferences = {
            "agency": AGENCIES[0],
            "priorities": ["Clean Water", "Climate Resilience"],
            "deadline_days": 15,
            "minimum_award": 100000,
            "minimum_match_score": 75,
            "notification": "Weekly digest",
        }

    prefs = st.session_state.agency_preferences

    with st.form("agency_profile_form"):
        agency = st.selectbox(
            "Government Agency",
            AGENCIES,
            index=AGENCIES.index(prefs["agency"]),
        )

        priorities = st.multiselect(
            "Strategic Priorities",
            PRIORITIES,
            default=prefs["priorities"],
        )

        deadline_days = st.slider(
            "Default Deadline Window (days)",
            min_value=1,
            max_value=90,
            value=prefs["deadline_days"],
        )

        col1, col2 = st.columns(2)

        with col1:
            minimum_award = st.number_input(
                "Minimum Award ($)",
                min_value=0,
                step=50000,
                value=prefs["minimum_award"],
            )

        with col2:
            minimum_match_score = st.slider(
                "Minimum Match Score",
                min_value=0,
                max_value=100,
                value=prefs["minimum_match_score"],
            )

        notification = st.radio(
            "Notification Preference",
            [
                "Weekly digest",
                "High-priority alerts",
                "None",
            ],
        )

        submitted = st.form_submit_button(
            "Save Preferences",
            type="primary",
        )

    if submitted:
        st.session_state.agency_preferences = {
            "agency": agency,
            "priorities": priorities,
            "deadline_days": deadline_days,
            "minimum_award": minimum_award,
            "minimum_match_score": minimum_match_score,
            "notification": notification,
        }

        st.success("Agency preferences saved for this session!")

    st.caption(
        "Preferences are currently stored for this session. "
        "Email notifications are not active yet."
    )
