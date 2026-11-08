"""Reusable Streamlit rendering for match_engine result records.

Search can call render_grant_card(record) to show records produced by
services.match_engine with the same layout as the Dashboard.
"""
import streamlit as st

from services.eligibility_assessment import (
    INELIGIBLE, LIKELY_ELIGIBLE, LIKELY_INELIGIBLE, NEEDS_REVIEW, NOT_CHECKED,
)

ELIGIBILITY_SHORT = {
    LIKELY_ELIGIBLE: ":green[✔ Appears eligible — verify]",
    NEEDS_REVIEW: ":orange[⚠ Needs review]",
    NOT_CHECKED: ":gray[? Not yet checked]",
    LIKELY_INELIGIBLE: ":red[✖ Likely not eligible]",
    INELIGIBLE: ":red[✖ Not eligible]",
}
CERTAINTY_STYLE = {"confirmed": ":red", "interpretation": ":blue", "uncertain": ":orange"}
URGENCY_STYLE = {"urgent": ":red", "soon": ":orange", "comfortable": ":green", "unknown": ":gray", "upcoming": ":blue"}
EFFORT_STYLE = {"higher": ":red", "moderate": ":orange", "fewer_found": ":green", "insufficient": ":gray",
                "unclear": ":gray", "unknown": ":gray"}
CHECK_ICON = {"ok": "✅", "verify": "⚠️", "fail": "❌", "unknown": "❔"}


def plan_link(goal):
    """Official plan URL opened at the cited page (the PDFs are served inline)."""
    return f"{goal['plan_url']}#page={goal['page']}"


def render_fit(record):
    score = record["fit_score"]
    value = "—" if score is None else str(score)
    st.markdown(
        "<div style='text-align:right;line-height:1.15'>"
        f"<span style='font-size:1.9rem;font-weight:700'>{value}</span>"
        "<span style='opacity:.6'> /100</span><br>"
        f"<span style='font-size:.72rem;opacity:.75'>Strategic fit · heuristic</span></div>",
        unsafe_allow_html=True,
    )


def _eligibility_tab(record):
    elig = record["eligibility"]
    certainty = CERTAINTY_STYLE.get(elig["certainty"], ":gray")
    st.markdown(f"**{elig['label']}** · {certainty}[{elig['certainty_label']}]")
    st.markdown(elig["reasoning"])
    if elig.get("quote"):
        ellipsis = " …" if elig.get("quote_truncated") else ""
        st.markdown(f"> “{elig['quote']}{ellipsis}”")
        link = f" — [view on Grants.gov]({elig['source_url']})" if elig.get("source_url") else ""
        st.caption(f"Source: {elig.get('quote_source') or 'Grants.gov'}{link}")
    if elig.get("listed_categories"):
        st.caption("Eligible applicant categories found in the notes: " + ", ".join(elig["listed_categories"]))
    if elig["applicant_types"]:
        st.caption("Structured applicant types: " + "; ".join(elig["applicant_types"]))
    for check in elig["checks"]:
        st.caption(f"{CHECK_ICON.get(check['status'], '•')} {check['item']}: {check['detail']}")
    ai = elig.get("ai")
    if ai:
        if ai.get("status") == "ok":
            st.caption(f"AI interpretation ({ai.get('model')}): {ai['verdict'].replace('_', ' ')} — {ai['reasoning']}")
        else:
            st.caption(f"AI interpretation {ai.get('status')}: {'; '.join(ai.get('errors') or [])[:200]}. "
                       "Rule-based assessment shown.")
    if elig["to_verify"]:
        st.markdown("**What to verify**")
        st.markdown("\n".join(f"- {item}" for item in elig["to_verify"]))
    st.caption("GrantScope never guarantees eligibility. Confirm with the official announcement or program contact.")


def _effort_tab(record, key, on_analyze):
    effort = record["effort"]
    st.markdown(f"**{effort['label']}.** {effort['summary']}")
    if effort["requirements"]:
        for req in effort["requirements"]:
            st.markdown(f"- **{req['label']}** — _{req['source']}_  \n  “{req['evidence']}”")
    for item in effort.get("not_required") or []:
        st.markdown(f"- Not required: {item}")
    if effort.get("page_limit"):
        pl = effort["page_limit"]
        st.markdown(f"- **Page limit:** {pl['pages']} pages — _{pl['source']}_  \n  “{pl['evidence']}”")
    if effort["sources_checked"]:
        st.caption("Checked: " + ", ".join(effort["sources_checked"]) + ". No time estimates are made.")
    if on_analyze and record["details_loaded"] and not effort["announcement_analyzed"]:
        if st.button("Analyze full announcement (PDF)", key=f"{key}_nofo",
                     help="Downloads the official announcement from Grants.gov and scans it for requirements."):
            on_analyze(record)
    if effort.get("announcement_url"):
        st.link_button("Full announcement (PDF) ↗", effort["announcement_url"])


def _evidence_tab(record):
    goals = record["relevance"]["matched_goals"]
    if not goals:
        st.caption("No strategic-plan evidence was found for this grant.")
    for goal in goals:
        via = " (cited by AI)" if goal.get("via_ai") else ""
        terms = f" — matched: {', '.join(goal['terms'])}" if goal["terms"] else ""
        st.markdown(f"**{goal['label']}**{via}{terms}")
        st.caption(f"“{goal['quote']}” — [strategic plan, PDF p. {goal['page']}]({plan_link(goal)})")
    ai = record["relevance"].get("ai") or {}
    if ai.get("status") == "ok" and ai.get("evidence"):
        st.markdown("**AI-cited evidence (quotes verified against sources)**")
        for item in ai["evidence"]:
            st.caption(f"{item['source_label']}: “{item['quote']}”")


def _scoring_tab(record):
    rel = record["relevance"]
    kw = rel["keyword"]
    st.markdown(f"**Strategic fit: {record['fit_score'] if record['fit_score'] is not None else '—'}/100** "
                f"({rel['label']}; method: {rel['method']})")
    st.caption(f"Keyword heuristic: {kw['score'] if kw['score'] is not None else '—'}/100 — {kw['reason']} "
               f"Basis: {kw['basis']}.")
    ai = rel.get("ai")
    if ai:
        if ai.get("status") == "ok":
            st.caption(f"AI semantic assessment ({ai.get('model')}): {ai['score']}/100. {ai.get('explanation', '')}")
        else:
            st.caption(f"AI assessment {ai.get('status')}: {'; '.join(ai.get('errors') or [])[:300]} "
                       "Keyword heuristic used.")
    st.caption("Strategic fit measures alignment with the agency's published goals. It is not eligibility, "
               "and not the probability of receiving an award. Deadline, funding and effort do not change it.")
    st.caption(f"Deadline: {record['deadline']['rule']}. {record['funding']['note']}")
    if record["data_gaps"]:
        st.warning("Missing or uncertain: " + "; ".join(record["data_gaps"]))
    if record["matched_queries"]:
        st.caption("Found by searching Grants.gov for: " + ", ".join(record["matched_queries"]))


def render_grant_card(record, key_prefix="grant", on_analyze=None):
    """Concise card; evidence and technical detail live in the expander."""
    key = f"{key_prefix}_{record['id']}"
    with st.container(border=True):
        head, score_col = st.columns([5, 1.3])
        with head:
            st.markdown(f"**{record['title']}**")
            st.caption(" · ".join(x for x in (record["federal_agency"], record.get("number")) if x))
        with score_col:
            render_fit(record)

        urg = record["urgency"]
        effort = record["effort"]
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"**Eligibility**  \n{ELIGIBILITY_SHORT.get(record['eligibility']['status'])}")
        c2.markdown(f"**Time to apply**  \n{URGENCY_STYLE.get(urg['level'], ':gray')}[{urg['label']}]")
        c3.markdown(f"**Funding**  \n{record['funding']['display']}")
        c4.markdown(f"**Effort**  \n{EFFORT_STYLE.get(effort['level'], ':gray')}[{effort['label']}]")

        st.markdown(f"**Why this matters:** {record['why']}")

        b1, b2, _ = st.columns([1, 1, 1.2])
        if record["source_url"]:
            b1.link_button("Grants.gov listing ↗", record["source_url"])
        goals = record["relevance"]["matched_goals"]
        if goals:
            b2.link_button(f"Strategic plan p. {goals[0]['page']} ↗", plan_link(goals[0]))

        with st.expander("Details: eligibility, requirements, evidence, scoring"):
            t1, t2, t3, t4 = st.tabs(["Eligibility", "Application effort", "Strategic evidence", "Scoring & data"])
            with t1:
                _eligibility_tab(record)
            with t2:
                _effort_tab(record, key, on_analyze)
            with t3:
                _evidence_tab(record)
            with t4:
                _scoring_tab(record)
