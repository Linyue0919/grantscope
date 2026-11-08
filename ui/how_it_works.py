"""How it works: a short static explanation of how GrantScope assesses opportunities."""
import streamlit as st

from ui.nav import PAGES


def show_how_it_works():
    st.markdown('<p class="gs-eyebrow">How it works</p><p class="gs-h1">How GrantScope assesses opportunities</p>',
                unsafe_allow_html=True)
    st.markdown("""
**Where the data comes from.** Opportunities come live from the federal **Grants.gov** listings and their official
details. Each agency's priorities come from its **public strategic plan**, listed by the NC Office of State Budget
and Management. Plan goals are quoted word for word, with page numbers.

**What the fit score means.** The fit score (0–100) shows how closely a listing matches your agency's strategic
plan goals. **Strong** is 60 or more, **Moderate** is 30–59, **Low** is under 30. It is not a measure of
eligibility, and not the chance of winning an award.

**How the brief is organized.**
- **Top candidates:** a good fit, state governments listed as eligible applicants, and the deadline and award stated.
- **Needs a quick check:** a good fit, but one important fact isn't confirmed. Each card names exactly what to check.
- **Opening soon:** forecasts that aren't accepting applications yet.
- **Lower priority:** an indirect fit or a known blocker. Shown so you can see what was considered.

Missing information can lower a recommendation, but never raise it.

**What the marks mean.**
- **● Confirmed:** found in the official text (for example, the listing's applicant types). Confirmed means the
  fact is in the official source, not that eligibility is guaranteed.
- **◐ Likely:** inferred from listing fields or a checked reading of the text.
- **○ Not stated:** we couldn't find it. The card tells you where to look.

**The AI's role.** Where it is turned on, an AI model helps read long eligibility notes and judge how well a
program fits your plan. Its answers are used only when every quote it cites is found word for word in the official
text. It never overrides an explicit eligibility restriction.

**GrantScope never guarantees eligibility or awards.** Always confirm with the official announcement or the
program officer.
""")
    if "ai_help" in PAGES:
        with st.container(key="inlinelink_ai_help"):
            st.page_link(PAGES["ai_help"], label="AI Help (assistant, in development)", width="content")


def show_ai_help():
    st.markdown('<p class="gs-h1">AI Assistant</p>', unsafe_allow_html=True)
    st.info("AI assistant is under development.")
