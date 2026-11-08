
import streamlit as st
from modules.search import show_search
from modules.profile import show_profile
from modules.my_grants import show_my_grants
from modules.dashboard import show_dashboard

st.set_page_config(
    page_title="GrantScope",
    page_icon="🔎",
    layout="wide"
)

st.title("GrantScope")
st.caption("AI-powered Federal Grant Discovery for North Carolina")

st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Go to",
    ["Dashboard", "Search", "My Grants", "Profile", "AI Help"]
)

if page == "Dashboard":
    show_dashboard()

elif page == "Search":
    show_search()

elif page == "My Grants":
    show_my_grants()

elif page == "Profile":
    show_profile()

elif page == "AI Help":
    st.header("AI Help")
    st.markdown("Enter an agency and specific project in Search. Potential Matches are screened leads, not verified recommendations. Use Deep Research on a candidate to request official-document analysis with citation checks.")
    st.markdown("Check applicant eligibility, funding purpose, deadlines, match and unresolved conditions before acting. Save useful opportunities to My Grants. Dashboard uses agency strategic goals; Search uses your project activities.")
    st.info("Deep Research uses real Azure AI and may incur charges. A failed or incomplete analysis is not a verified match. AI analysis does not replace the official funding notice or agency confirmation.")
