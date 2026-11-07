
import streamlit as st
from modules.search import show_search
from modules.profile import show_profile
from modules.my_grants import show_my_grants
from services.grant_store import LocalGrantStore

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
    st.header("Dashboard")
    st.caption(f"Saved grants: {len(LocalGrantStore().list_records())}")
    st.info("Dashboard is under development.")

elif page == "Search":
    show_search()

elif page == "My Grants":
    show_my_grants()

elif page == "Profile":
    show_profile()

elif page == "AI Help":
    st.header("AI Assistant")
    st.info("AI assistant is under development.")
