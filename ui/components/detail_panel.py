"""Detail panel (spec section 6, in that exact order). Reads only OpportunityView fields."""
from html import escape

import streamlit as st

from ui.components.card import evidence
from ui.view_model import CONFIRMED, LIKELY, NOT_STATED, fmt_date, mark, to_eastern

SECTION_CLASS = {"top": "top", "check": "check", "soon": "soon", "lower": "lower"}


def _link(url, text):
    return f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(text)}</a>' if url else ""


def _plan_link(view, text=None):
    if not view.plan_url:
        return ""
    url = f"{view.plan_url}#page={view.plan_page}" if view.plan_page else view.plan_url
    return _link(url, text or (f"Strategic plan p. {view.plan_page} ↗" if view.plan_page else "Strategic plan ↗"))


def _tile(label, value, sub):
    return (f'<div class="gs-tile"><div class="l">{label}</div><div class="v">{escape(value)}</div>'
            f'<div class="s">{sub}</div></div>')


def _status_line(status):
    return f"{evidence(status)} {escape({CONFIRMED: 'Confirmed', LIKELY: 'Likely', NOT_STATED: 'Not stated'}[status])}"


def render_panel(view, *, on_close, saved=None, on_toggle_save=None, extra_actions=None, how_it_works_page=None):
    with st.container(border=True, key="panel"):
        # 1. Header
        head, close = st.columns([6, 1], vertical_alignment="top")
        links = " &nbsp; ".join(x for x in (_link(view.grants_gov_url, "Grants.gov listing ↗"),
                                             _link(view.nofo_url, "Funding notice (NOFO) ↗")) if x)
        head.markdown(f'<p class="gs-panel-title">{escape(view.title)}</p>'
                      f'<p class="gs-agency">{escape(view.agency_full_name)}</p>'
                      f'<p class="gs-small">{links}</p>', unsafe_allow_html=True)
        close.button("✕", key="panel_close", on_click=on_close, help="Close details")
        if on_toggle_save is not None or extra_actions:
            with st.container(horizontal=True, gap="small", vertical_alignment="center"):
                if on_toggle_save is not None:
                    st.button("★ Saved" if saved else "☆ Save", key=f"panel_save_{view.id}",
                              on_click=on_toggle_save, args=(view,))
                if extra_actions:
                    extra_actions(view)

        # 2. Recommendation box
        tag = "AI-assisted" if view.ai_assisted else "Rule-based"
        score = (f'<div class="gs-reco-score"><span class="n">{view.fit_score}</span><span class="gs-muted">/100</span>'
                 f'<div class="gs-small">{view.fit_tier} fit</div></div>') if view.fit_score is not None else ""
        st.markdown(
            f'<div class="gs-reco gs-reco-{SECTION_CLASS[view.section]}"><div>'
            f'<div class="gs-reco-label">Recommendation · {escape(view.recommendation_label)}'
            f'<a class="gs-ai-tag" href="#gs-sources" title="How this was assessed">{tag}</a></div>'
            f'<div class="gs-reco-text">{escape(view.recommendation_sentence)}</div></div>{score}</div>',
            unsafe_allow_html=True)

        # 3. Application readiness
        if view.deadline_date and view.days_left is not None:
            deadline_v, deadline_s = fmt_date(view.deadline_date), f"{view.days_left} days left"
        elif view.status == "forecasted":
            deadline_v, deadline_s = "Not open yet", "forecast only"
        else:
            deadline_v, deadline_s = "Not stated", "check the listing"
        award_sub = (f"{_status_line(view.award_status)} · {escape(view.expected_awards_text)}"
                     if view.award_status != NOT_STATED else f"{_status_line(NOT_STATED)} · see the funding notice")
        st.markdown(
            '<div class="gs-h3">Application readiness</div><div class="gs-grid">'
            + _tile("Deadline", deadline_v, escape(deadline_s))
            + _tile("Eligibility", view.eligibility_short, _status_line(view.eligibility_status))
            + _tile("Effort", view.effort_level, _status_line(view.effort_status))
            + _tile("Award", view.award_text if view.award_status != NOT_STATED else "Not stated", award_sub)
            + "</div>", unsafe_allow_html=True)

        # 4. Why it matches your strategic plan
        st.markdown(f'<div class="gs-h3">Why it matches your strategic plan · '
                    f'<span class="gs-muted">{view.fit_level} fit</span></div>', unsafe_allow_html=True)
        if view.fit_reasons:
            st.markdown("\n".join(f"- {r}" for r in view.fit_reasons))
        else:
            st.markdown('<p class="gs-small">No plan goal was matched in the listing text.</p>', unsafe_allow_html=True)
        if view.plan_quote or view.grant_purpose_quote:
            with st.expander("See the evidence from both documents"):
                boxes = []
                if view.plan_quote:
                    boxes.append(f'<div class="gs-evbox"><div class="l">Your plan</div>'
                                 f'<b>{escape(view.plan_quote_goal or "")}</b>'
                                 f'<div class="gs-quote">“{escape(view.plan_quote)}”</div>{_plan_link(view)}</div>')
                if view.grant_purpose_quote:
                    boxes.append(f'<div class="gs-evbox"><div class="l">This opportunity</div><b>Program purpose</b>'
                                 f'<div class="gs-quote">“{escape(view.grant_purpose_quote)}”</div>'
                                 f'{_link(view.grants_gov_url, "Grants.gov listing ↗")}</div>')
                st.markdown(f'<div class="gs-evidence">{"".join(boxes)}</div>', unsafe_allow_html=True)

        # 5. Details behind this assessment
        st.markdown('<div class="gs-h3">Details behind this assessment</div>', unsafe_allow_html=True)
        with st.expander(f"Eligibility · {mark(view.eligibility_status)} {view.eligibility_status}"):
            st.markdown(escape(view.eligibility_conclusion) or "The listing does not state eligibility clearly.")
            if view.eligibility_quote:
                st.markdown(f'<div class="gs-quote">“{escape(view.eligibility_quote)}”</div>', unsafe_allow_html=True)
                st.markdown(f'<p class="gs-small">Source: {escape(view.eligibility_source or "Grants.gov")} · '
                            f'{_link(view.eligibility_source_url, "view")}</p>', unsafe_allow_html=True)
            st.markdown("**What could disqualify you**")
            items = view.disqualifiers or ["Nothing specific found in the listing. Read the eligibility section of the funding notice."]
            st.markdown("\n".join(f"- {escape(i)}" for i in items))
        with st.expander(f"Application effort · {view.effort_level}"):
            st.markdown(escape(view.effort_note))
            rows = "".join(f'<tr><td>{escape(d["label"])}</td><td class="v">{escape(d["value"])} '
                           f'{evidence(d["status"])}</td></tr>' for d in view.effort_drivers)
            st.markdown(f'<table class="gs-drivers">{rows}</table>', unsafe_allow_html=True)
        st.markdown('<div id="gs-sources"></div>', unsafe_allow_html=True)
        with st.expander("Sources & method"):
            retrieved = to_eastern(view.retrieved_at) if view.retrieved_at else None
            retrieved_text = f"{retrieved:%b %-d, %Y, %-I:%M %p} ET" if retrieved else "Not stated"
            st.markdown(
                "An AI model helped draft parts of this summary where available. Every quoted fact is checked "
                "against the official text; anything we couldn't verify is marked “Not stated.” Placement in the "
                "brief follows fixed rules: missing information can lower a recommendation but never raise it.")
            fit_line = (f"**Fit score:** {view.fit_score}/100 ({view.fit_tier}), based on how closely the listing "
                        "matches your strategic plan goals." if view.fit_score is not None else "**Fit score:** Not scored.")
            st.markdown(
                f"{fit_line}  \n**Opportunity number:** {escape(view.opportunity_number or 'Not stated')}  \n"
                f"**Listing retrieved:** {retrieved_text}  \n"
                f"**Strategic plan:** {escape(view.plan_name or 'Agency')} strategic plan"
                + (f", p. {view.plan_page}" if view.plan_page else ""))
            if how_it_works_page is not None:
                st.page_link(how_it_works_page, label="How GrantScope assesses opportunities")

        # 6. If you decide to pursue
        if view.section in ("top", "check") and view.next_steps:
            with st.container(key=f"pursue_{view.id}"):
                st.markdown('<div class="gs-h3">If you decide to pursue</div>'
                            '<p class="gs-small">Suggested next steps, in order.</p>', unsafe_allow_html=True)
                for i, step in enumerate(view.next_steps):
                    st.checkbox(step, key=f"step_{view.id}_{i}")
                if view.officer_questions:
                    with st.expander("Questions for the program officer"):
                        st.markdown("\n".join(f"- {escape(q)}" for q in view.officer_questions))
                text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(view.next_steps))
                if view.officer_questions:
                    text += "\n\nQuestions for the program officer:\n" + "\n".join(f"- {q}" for q in view.officer_questions)
                with st.popover("Copy next steps", type="primary"):
                    st.caption("Use the copy icon in the box.")
                    st.code(f"{view.title}\n\n{text}", language=None)
