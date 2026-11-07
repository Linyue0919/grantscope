import streamlit as st
from services.agency_directory import AGENCIES, SOURCE_URL

# Initial agency directory, not a claim of complete or verified coverage.
# Custom entry makes the prototype usable by agencies not listed here.
CUSTOM_AGENCY = "Other agency / enter manually"
PRIORITIES = [
    "Clean Water", "Climate Resilience", "Transportation",
    "Rural Health", "Workforce Development", "Education",
]
DEFAULT_PREFERENCES = {
    "agency": "Department of Environmental Quality",
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
    st.caption(f"{len(AGENCIES)} official OSBM strategic-plan directory entries. [View OSBM directory]({SOURCE_URL})")
    prefs = get_preferences()

    saved_agency = prefs.get("agency", AGENCIES[0])
    initial_choice = saved_agency if saved_agency in AGENCIES else CUSTOM_AGENCY

    with st.form("agency_profile_form"):
        agency_choice = st.selectbox(
            "Government Agency",
            AGENCIES + [CUSTOM_AGENCY],
            index=(AGENCIES + [CUSTOM_AGENCY]).index(initial_choice),
        )
        custom_agency = st.text_input(
            "Agency name (for Other)",
            value=saved_agency if initial_choice == CUSTOM_AGENCY else "",
            help="If your agency is not listed, choose Other above and enter its name.",
        )
        priorities = st.multiselect(
            "Strategic Priorities", PRIORITIES,
            default=[p for p in prefs["priorities"] if p in PRIORITIES],
        )
        custom_priorities = st.text_input(
            "Additional strategic priorities (comma-separated)",
            value=", ".join(p for p in prefs["priorities"] if p not in PRIORITIES),
            help="For example: coastal resilience, public libraries, broadband.",
        )
        deadline_days = st.slider(
            "Default Deadline Window (days)", 1, 365,
            value=max(1, min(365, int(prefs["deadline_days"]))),
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
        agency = custom_agency.strip() if agency_choice == CUSTOM_AGENCY else agency_choice
        if not agency:
            st.error("Please enter an agency name when choosing Other.")
            return
        extra = [item.strip() for item in custom_priorities.split(",") if item.strip()]
        combined = list(dict.fromkeys(priorities + extra))
        st.session_state.agency_preferences = {
            "agency": agency,
            "priorities": combined,
            "deadline_days": int(deadline_days),
            "minimum_award": int(minimum_award),
            "minimum_match_score": int(minimum_match_score),
            "notification": notification,
        }
        st.session_state.pop("search_profile_signature", None)
        st.success("Preferences saved! Open Search to use your updated defaults.")

    st.caption(
         "This list covers the entries on the OSBM strategic-plan directory, not every possible NC public body. "
        "Adding an agency does not mean its strategic plan has been ingested or that "
        "its grant eligibility has been verified. Preferences last for this Streamlit "
        "session only. Award and match-score filters are not yet active; email "
        "notifications are not active."
    )
