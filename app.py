import streamlit as st

from modules.dashboard import show_dashboard
from modules.profile import show_profile
from modules.search import show_search
from ui import saved_store
from ui.how_it_works import show_ai_help, show_how_it_works
from ui.nav import PAGES
from ui.saved_page import show_saved
from ui.styles import inject_css

st.set_page_config(page_title="GrantScope", page_icon="ui/assets/nc.svg", layout="wide")
inject_css()
st.logo("ui/assets/logo.svg", size="large")

PAGES.update({
    "brief": st.Page(show_dashboard, title="Brief", url_path="brief", default=True),
    "browse": st.Page(show_search, title="Browse all", url_path="browse"),
    "saved": st.Page(show_saved, title=f"Saved ({saved_store.count_all()})", url_path="saved"),
    "alerts": st.Page(show_profile, title="Alerts", url_path="alerts"),
    "how": st.Page(show_how_it_works, title="How it works", url_path="how-it-works"),
})
try:  # hidden pages need a newer Streamlit than 1.51; there, AI Help is simply not linked
    PAGES["ai_help"] = st.Page(show_ai_help, title="AI Help", url_path="ai-help", visibility="hidden")
except TypeError:
    pass
st.navigation(list(PAGES.values()), position="top").run()
