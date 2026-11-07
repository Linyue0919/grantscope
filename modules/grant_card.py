"""Reusable Streamlit rendering for match_engine result records.

Search can call render_grant_card(result) to show records produced by
services.match_engine with the same layout as the Dashboard.
"""
import streamlit as st

from services.match_engine import CLOSED, FORECASTED, NEEDS_REVIEW, NOT_CHECKED, ELIGIBLE_TYPE, UNKNOWN

ELIGIBILITY_STYLE = {
    ELIGIBLE_TYPE: (":green", "✔"),
    NEEDS_REVIEW: (":orange", "⚠"),
    NOT_CHECKED: (":gray", "?"),
}
COMPONENT_LABELS = {
    "strategic_alignment": "Strategic alignment",
    "deadline": "Deadline actionability",
    "funding": "Funding fit",
}


def money(value):
    return f"${value:,.0f}" if value is not None and value > 1 else None


def format_funding(award):
    if not award["loaded"]:
        return "Not loaded"
    floor, ceiling = money(award["floor"]), money(award["ceiling"])
    if ceiling and floor:
        return f"{floor} – {ceiling}"
    if ceiling:
        return f"Up to {ceiling}"
    if floor:
        return f"From {floor}"
    total = money(award["estimated_total"])
    return f"Not reported (program total {total})" if total else "Not reported"


def format_deadline(deadline):
    status, days, close = deadline["status"], deadline["days_left"], deadline["close_date"]
    if status == FORECASTED:
        return f":blue[Forecasted] · est. {close}" if close else ":blue[Forecasted] · date TBD"
    if status == UNKNOWN or days is None:
        return ":gray[Not listed: verify]"
    if status == CLOSED:
        return ":gray[Closed]"
    color = ":red" if days <= 14 else ":orange" if days <= 30 else ":green"
    return f"{close} · {color}[{days} days left]"


def format_eligibility(eligibility):
    color, icon = ELIGIBILITY_STYLE.get(eligibility["status"], (":gray", "?"))
    return f"{color}[{icon} {eligibility['label']}]"


def render_score(score):
    st.markdown(
        f"<div style='text-align:right;line-height:1.1'>"
        f"<span style='font-size:2rem;font-weight:700'>{score}</span>"
        f"<span style='opacity:.6'> / 100</span><br>"
        f"<span style='font-size:.75rem;opacity:.7'>Match Score</span></div>",
        unsafe_allow_html=True,
    )


def render_grant_card(result, key_prefix="grant"):
    """Render one passed-screening result record."""
    with st.container(border=True):
        head, score_col = st.columns([5, 1])
        with head:
            st.markdown(f"#### {result['title']}")
            meta = [result["federal_agency"]]
            if result.get("number"):
                meta.append(result["number"])
            st.caption(" · ".join(meta))
        with score_col:
            render_score(result["match_score"])

        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Deadline**  \n{format_deadline(result['deadline'])}")
        c2.markdown(f"**Funding**  \n{format_funding(result['award'])}")
        c3.markdown(f"**Eligibility**  \n{format_eligibility(result['eligibility'])}")

        st.markdown(f"**Why it matches:** {result['explanation']}")
        for goal in result["alignment"]["matched_goals"][:2]:
            st.caption(f"“{goal['quote']}”  ({goal['label']}, strategic plan PDF p. {goal['page']})")

        with st.expander("Score details, sources & data gaps"):
            rows = [
                {"Component": COMPONENT_LABELS[name], "Points": f"{part['points']} / {part['max']}",
                 "How it was scored": part["reason"]}
                for name, part in result["score_breakdown"].items()
            ]
            st.table(rows)
            st.caption(f"Alignment basis: {result['alignment']['basis']}. "
                       f"Eligibility: {result['eligibility']['reason']}")
            if result["eligibility"].get("applicant_types"):
                st.caption("Official applicant types: " + "; ".join(result["eligibility"]["applicant_types"]))
            if result["eligibility"].get("evidence"):
                st.caption(f"Eligibility evidence: “{result['eligibility']['evidence']}”")
            st.caption(f"Deadline rule: {result['deadline']['rule']}.")
            if result["data_gaps"]:
                st.warning("Missing or uncertain: " + "; ".join(result["data_gaps"]))
            if result["matched_queries"]:
                st.caption("Found by searching: " + ", ".join(result["matched_queries"]))

        b1, b2, _ = st.columns([1, 1, 2])
        if result["source_url"]:
            b1.link_button("Grants.gov listing ↗", result["source_url"])
        goals = result["alignment"]["matched_goals"]
        if goals:
            b2.link_button(f"Strategic plan (p. {goals[0]['page']}) ↗", goals[0]["plan_url"])
