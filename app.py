
import streamlit as st

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
    st.header("Search Federal Grants")
    query = st.text_input("Search grants", placeholder="Enter keywords...")
    if query:
        st.write("You searched for:", query)

elif page == "Profile":
    st.header("Agency Profile")
    st.info("Profile is under development.")

elif page == "AI Help":
    st.header("AI Assistant")
    st.info("AI assistant is under development.")
