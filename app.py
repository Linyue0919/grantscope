
import streamlit as st
from modules.search import show_search
from modules.profile import show_profile
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
    ["Dashboard", "Search", "Profile", "AI Help"]
)

if page == "Dashboard":
    show_dashboard()

elif page == "Search":
    show_search()

elif page == "Profile":
    show_profile()

elif page == "AI Help":
    st.header("AI Assistant")
    st.info("AI assistant is under development.")

