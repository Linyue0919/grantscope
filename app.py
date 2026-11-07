
import streamlit as st
from modules.search import show_search

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
    st.header("Dashboard")
    st.info("Dashboard is under development.")

elif page == "Search":
    show_search()

elif page == "Profile":
    st.header("Agency Profile")
    st.info("Profile is under development.")

elif page == "AI Help":
    st.header("AI Assistant")
    st.info("AI assistant is under development.")

