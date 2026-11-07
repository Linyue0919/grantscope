"""Live federal opportunity search with transparent, results-first triage."""
import csv
from io import StringIO
from datetime import date, datetime
import streamlit as st

from services.grants_api import get_grants, get_grant_details, GrantsAPIError
from services.agency_directory import AGENCIES
from services.matching import project_relevance, rank_grants
from services.eligibility import screen_eligibility
from services.verified_goals import VERIFIED_GOALS
from services.grant_store import LocalGrantStore
from services.discovery import (
    AIRecommendationCache,
    DiscoveryError,
    cached_semantic_results,
    classify_recommendations,
    prepare_ai_recommendations,
)


def parse_close_date(value):
    """Accept common Grants.gov date formats; never guess an invalid date."""
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def filter_by_deadline(grants, deadline_days, include_unknown=False, today=None):
    today = today or date.today()
    matching, unknown = [], 0
    for grant in grants:
        closing = parse_close_date(grant.get("closeDate"))
        if closing is None:
            unknown += 1
            if include_unknown:
                matching.append(grant)
        elif 0 <= (closing - today).days <= deadline_days:
            matching.append(grant)
    return sorted(
        matching,
        key=lambda grant: parse_close_date(grant.get("closeDate")) or date.max,
    ), unknown


def eligibility_summary(details, agency_name):
    """Return a cautious display summary without inferring eligibility."""
    if not details:
        return {
            "status": "Needs Review",
            "explanation": "Official eligibility details have not been loaded.",
            "next_action": "Load official details before deciding whether to apply.",
            "excluded": False,
        }
    screening = screen_eligibility(details, agency_name)
    if screening["status"] == "Ineligible":
        return {
            "status": "Ineligible",
            "explanation": screening["reason"],
            "next_action": "Do not apply directly; review the official notice for any alternate applicant route.",
            "excluded": True,
        }
    return {
        "status": "Needs Review",
        "explanation": screening["reason"],
        "next_action": "Verify the complete official notice and agency-specific requirements.",
        "excluded": False,
    }


def relevance_summary(grant):
    """Return a concise strategic-topic summary distinct from eligibility."""
    score = grant.get("match_score")
    if score is None:
        return "Unscored: this agency has no verified strategic plan goals."
    if grant.get("match_reasons"):
        goals = ", ".join(reason["goal"] for reason in grant["match_reasons"][:2])
        return f"{score}/100 topic overlap: {goals}"
    return f"{score}/100 topic overlap: no verified goal terms matched."


def _sort_excluded_last(grants):
    return sorted(grants, key=lambda grant: grant.get("_excluded", False))


def _first_value(record, *keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def grant_status(grant):
    value = _first_value(grant, "oppStatus", "opportunityStatus", "status")
    normalized = str(value or "").strip().lower()
    if "forecast" in normalized:
        return "Forecasted"
    if "post" in normalized:
        return "Posted"
    return "Unknown"


def federal_agency(grant):
    return str(_first_value(
        grant, "agency", "agencyName", "federalAgency", "agencyCode"
    ) or "Unknown federal agency").strip()


def official_award_ceiling(grant, details):
    if details:
        return parse_amount(details.get("award_ceiling"))
    return parse_amount(_first_value(grant, "awardCeiling", "award_ceiling"))


def official_total_funding(grant, details):
    if details:
        return parse_amount(details.get("total_funding"))
    return parse_amount(_first_value(grant, "estimatedFunding", "totalFunding", "total_funding"))


def parse_amount(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def sort_results(grants, sort_by, semantic_results=None):
    semantic_results = semantic_results or {}

    def close_key(grant):
        return parse_close_date(grant.get("closeDate")) or date.max

    def award_key(grant):
        return parse_amount(grant.get("_award_ceiling"))

    def newest_key(grant):
        raw = _first_value(grant, "openDate", "postedDate", "createdDate")
        return parse_close_date(raw) or date.min

    def semantic_score(grant):
        semantic = semantic_results.get(
            f"{grant.get('_agency_namespace', '')}::{grant.get('id')}", {}
        )
        field = (
            "project_relevance_score"
            if grant.get("_project_relevance_score") is not None
            else "strategic_relevance_score"
        )
        return semantic.get(field)

    if sort_by == "Award ceiling: high to low":
        key, reverse = lambda g: award_key(g) is not None, True
        ordered = sorted(grants, key=lambda g: (award_key(g) is not None, award_key(g) or 0), reverse=reverse)
    elif sort_by == "Award ceiling: low to high":
        ordered = sorted(grants, key=lambda g: (award_key(g) is None, award_key(g) or 0))
    elif sort_by == "Closing date: soonest":
        ordered = sorted(grants, key=close_key)
    elif sort_by == "Newest":
        ordered = sorted(grants, key=newest_key, reverse=True)
    else:
        ordered = sorted(
            grants,
            key=lambda g: (
                g.get("_excluded", False),
                semantic_results.get(
                    f"{g.get('_agency_namespace', '')}::{g.get('id')}", {}
                ).get("status") != "Evaluated",
                -(semantic_score(g) if semantic_score(g) is not None else -1),
                g.get("match_score") is None,
                -(g.get("match_score") or 0),
                close_key(g),
            ),
        )
    return sorted(ordered, key=lambda grant: grant.get("_excluded", False))


def apply_search_filters(grants, agency_filter="All federal agencies",
                         statuses=None, eligibility_filter="Any eligibility",
                         goal_filter="Any verified goal", min_ceiling=None,
                         max_ceiling=None):
    statuses = set(statuses or [])
    filtered = []
    for grant in grants:
        if agency_filter != "All federal agencies" and federal_agency(grant) != agency_filter:
            continue
        if statuses and grant_status(grant) not in statuses:
            continue
        if eligibility_filter != "Any eligibility" and grant["_eligibility_status"] != eligibility_filter:
            continue
        if goal_filter != "Any verified goal" and not any(
            reason["goal"] == goal_filter for reason in grant.get("match_reasons", [])
        ):
            continue
        ceiling = parse_amount(grant.get("_award_ceiling"))
        if grant["_eligibility_status"] != "Ineligible":
            if min_ceiling is not None and (ceiling is None or ceiling < min_ceiling):
                continue
            if max_ceiling is not None and (ceiling is None or ceiling > max_ceiling):
                continue
        filtered.append(grant)
    return filtered


def decision_csv(grants, decisions):
    output = StringIO()
    fields = [
        "opportunity_id", "title", "federal_agency", "status", "closing_date",
        "award_ceiling", "total_program_funding", "strategic_relevance",
        "eligibility", "decision", "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for grant in grants:
        decision = decisions.get(
            f"{grant.get('_agency_namespace', '')}::{grant.get('id')}",
            decisions.get(str(grant.get("id")), {}),
        )
        writer.writerow({
            "opportunity_id": grant.get("id") or "",
            "title": grant.get("title") or "Untitled Grant",
            "federal_agency": federal_agency(grant),
            "status": grant_status(grant),
            "closing_date": grant.get("closeDate") or "Missing",
            "award_ceiling": grant.get("_award_ceiling") or "Missing",
            "total_program_funding": grant.get("_total_funding") or "Missing",
            "strategic_relevance": relevance_summary(grant),
            "eligibility": grant.get("_eligibility_status", "Needs Review"),
            "decision": decision.get("decision", ""),
            "notes": decision.get("notes", ""),
        })
    return output.getvalue()


def _format_amount(value):
    return f"${value:,.0f}" if value is not None else "Not reported"


def show_search():
    st.header("Search Federal Grants")
    st.write("Discover live federal funding opportunities for NC agencies.")
    st.caption("Search is independent of saved Profile preferences. Choose filters for this search.")
    store = LocalGrantStore()
    saved_records = {
        f"{record['agency']}::{record['opportunity_id']}": record
        for record in store.list_records()
    }
    agency = st.selectbox("Agency to evaluate", AGENCIES, key="search_agency")
    st.caption("All 33 North Carolina agency directory options are preserved. Strategic goals are shown only where verified.")
    query = st.text_input(
        "Search opportunities",
        key="search_query",
        placeholder="e.g. clean water, transportation, rural health",
    )
    project_description = st.text_area(
        "Project description (optional)",
        placeholder="Describe the concrete project, population, location, or outcomes.",
        help="Project relevance is a transparent term-overlap signal from official opportunity text. It is separate from strategic relevance and AI evaluation.",
    )
    col1, col2 = st.columns(2)
    with col1:
        deadline_days = st.number_input(
            "Closing within (days)", min_value=1, max_value=365,
            step=1, value=30, key="search_deadline_days",
            help="Only affects this Search page.",
        )
    with col2:
        include_unknown = st.checkbox(
            "Include grants with unknown deadlines",
            help="Unknown dates cannot be confirmed to fall within the window.",
        )

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        status_filter = st.multiselect(
            "Opportunity status",
            ["Posted", "Forecasted"],
            default=["Posted", "Forecasted"],
            help="Status comes from the official Grants.gov search record.",
        )
        eligibility_filter = st.selectbox(
            "Eligibility",
            ["Any eligibility", "Needs Review", "Ineligible"],
            help="Needs Review includes opportunities without confirmed eligibility.",
        )
        sort_by = st.selectbox(
            "Sort results by",
            [
                "Recommended match",
                "Award ceiling: high to low",
                "Award ceiling: low to high",
                "Closing date: soonest",
                "Newest",
            ],
        )
    with filter_col2:
        min_ceiling = st.number_input(
            "Minimum award ceiling ($)",
            min_value=0, step=50000, value=0,
            help="Filters the official award ceiling, not total program funding.",
        )
        max_ceiling = st.number_input(
            "Maximum award ceiling ($; 0 = no maximum)",
            min_value=0, step=50000, value=0,
            help="Filters the official award ceiling, not total program funding.",
        )

    show_zero_matches = st.checkbox(
        "Show zero-evidence matches (audit view)", value=False,
        key="search_show_zero_matches",
        help="Hide results with no matched strategic goal terms. This does not prove they are unrelated.",
    )
    min_match_score = st.slider(
        "Baseline keyword score (audit only)", min_value=0, max_value=100,
        value=0, step=1,
        key="search_baseline_keyword_score",
        help="Displayed for comparison only. AI recommendations use the Minimum AI Match Score below.",
    )
    minimum_ai_score = st.slider(
        "Minimum AI Match Score", min_value=0, max_value=100,
        value=60, step=1,
        key="search_minimum_ai_score",
        help="Applies only to successfully AI-evaluated opportunities; changing it makes no Azure calls.",
    )
    exclude_confirmed_ineligible = st.checkbox(
        "Exclude confirmed ineligible grants", value=True,
        key="search_exclude_confirmed_ineligible",
        help="Uses only official applicant eligibility evidence. AI guesses never confirm ineligibility.",
    )
    include_uncertain = st.checkbox(
        "Include uncertain eligibility", value=True,
        key="search_include_uncertain_eligibility",
        help="Keeps Needs Review and Not AI Evaluated opportunities visible with clear labels.",
    )

    if st.button("Search Grants", type="primary"):
        if not query.strip():
            st.warning("Enter a keyword to search Grants.gov.")
            st.session_state.pop("search_last_results", None)
            return
        try:
            with st.spinner("Searching Grants.gov..."):
                grants = get_grants(query.strip(), 100)
        except GrantsAPIError as exc:
            st.error(str(exc))
            return
        st.session_state["search_last_results"] = {
            "query": query.strip(), "grants": grants,
        }

    cached = st.session_state.get("search_last_results")
    if not cached:
        st.caption("Run a search to see live opportunity records.")
        return

    if query.strip() != cached["query"]:
        st.caption(f'Showing the previous search for "{cached["query"]}". Click Search Grants to refresh.')
    grants = cached["grants"]
    agency_options = ["All federal agencies"] + sorted({
        federal_agency(grant) for grant in grants
    })
    agency_filter = st.selectbox("Federal agency", agency_options)
    matching, unknown_count = filter_by_deadline(
        grants, int(deadline_days), include_unknown,
    )
    matching = [
        grant for grant in matching
        if (not status_filter or grant_status(grant) in status_filter)
        and (agency_filter == "All federal agencies" or federal_agency(grant) == agency_filter)
    ]
    st.write(
        f'{len(matching)} opportunities shown from {len(grants)} retrieved '
        f'Grants.gov records for "{cached["query"]}".'
    )
    if unknown_count:
        st.caption(
            f"{unknown_count} records have missing or unrecognized deadlines. "
            "Verify dates on the official listing."
        )
    if len(grants) >= 100:
        st.warning(
            "Only the first 100 search records were requested; this is NOT "
            "an exhaustive result set. Try a narrower keyword."
        )
    if not matching:
        st.warning("No results in this deadline window. Try more days or a broader keyword.")

    detail_cache = st.session_state.setdefault("grant_detail_cache", {})
    # Explicitly user-triggered bounded screening, not 100 background API calls.
    unscreened = [
        g for g in matching
        if g.get("id") and str(g["id"]) not in detail_cache
    ]
    if unscreened:
        st.caption(f"{len(unscreened)} displayed candidates have not had their official eligibility details checked.")
        if st.button("Screen next 10 grants using official eligibility details"):
            failures = 0
            with st.spinner("Checking up to 10 official Grants.gov records..."):
                for grant in unscreened[:10]:
                    key = str(grant["id"])
                    try:
                        detail_cache[key] = get_grant_details(grant["id"])
                    except GrantsAPIError:
                        failures += 1
            if failures:
                st.warning(f"{failures} detail requests failed; those opportunities remain Needs Review.")
            st.rerun()
    screened_count = sum(str(g.get("id")) in detail_cache for g in matching)
    st.caption(f"Official detail coverage: {screened_count}/{len(matching)} candidates. Unscreened results are not confirmed eligible.")
    ranked = rank_grants(matching, agency, detail_cache=detail_cache)
    for grant in ranked:
        grant["_agency_namespace"] = agency
        summary = eligibility_summary(
            detail_cache.get(str(grant.get("id"))), agency
        )
        grant["_excluded"] = summary["excluded"]
        grant["_eligibility_status"] = "Ineligible" if summary["excluded"] else "Needs Review"
        grant["_eligibility_reason"] = summary["explanation"]
        grant["_award_ceiling"] = official_award_ceiling(
            grant, detail_cache.get(str(grant.get("id")))
        )
        grant["_total_funding"] = official_total_funding(
            grant, detail_cache.get(str(grant.get("id")))
        )
        project_score, project_terms = project_relevance(
            project_description, grant, detail_cache.get(str(grant.get("id")))
        )
        grant["_project_relevance_score"] = project_score
        grant["_project_relevance_terms"] = project_terms
    goal_options = ["Any verified goal"] + sorted({
        reason["goal"] for grant in ranked for reason in grant.get("match_reasons", [])
    })
    goal_filter = st.selectbox(
        "Verified strategic goal",
        goal_options,
        help="Only verified strategic-plan goals appear here; unverified agencies remain unscored.",
    )
    ranked = apply_search_filters(
        ranked,
        eligibility_filter=eligibility_filter,
        goal_filter=goal_filter,
        min_ceiling=float(min_ceiling) if min_ceiling else None,
        max_ceiling=float(max_ceiling) if max_ceiling else None,
    )
    ai_candidate_pool = list(ranked)
    excluded_count = sum(grant["_excluded"] for grant in ranked)
    if excluded_count:
        st.info(f"{excluded_count} explicitly excluded opportunity(ies) remain visible below the other results.")
    semantic_results = {}
    recommendation_cache = AIRecommendationCache()
    cached_state = cached_semantic_results(
        recommendation_cache, agency, project_description
    )
    cached_recommendations = recommendation_cache.get(agency, project_description)
    if cached_state["status"] == "ready":
        semantic_results.update(cached_state["results"])
        st.success(
            "AI matching loaded from the persistent recommendation cache. "
            f"Last refreshed: {cached_recommendations.get('refreshed_at', 'unknown')}."
        )
    else:
        st.info(
            "AI matching not generated yet for this agency and project description. "
            "The visible baseline remains labeled as keyword relevance."
        )
    for grant in ai_candidate_pool:
        grant["_agency_namespace"] = agency
    if not cached_recommendations and st.button(
        "Generate AI recommendations (up to 5 bounded evaluations)",
        key="generate_ai_recommendations",
    ):
        try:
            with st.spinner("Preparing bounded AI recommendations..."):
                prepare_ai_recommendations(
                    agency,
                    project_description=project_description,
                    cache=recommendation_cache,
                    config=st.secrets,
                )
            st.success("AI recommendations saved. Rerun the page to load them.")
            st.rerun()
        except DiscoveryError as exc:
            st.error(str(exc))
    zero_evidence = sum(g["match_score"] == 0 and not g["_excluded"] for g in ranked)
    if not show_zero_matches:
        ranked = [
            g for g in ranked
            if g["match_score"] != 0
            or g["_excluded"]
            or semantic_results.get(f"{agency}::{g.get('id')}", {}).get("status") == "Evaluated"
        ]
        if zero_evidence:
            st.info(f"{zero_evidence} zero-evidence result(s) remain available for AI evaluation; unevaluated ones are hidden unless audit view is enabled.")
    semantic_by_id = {
        key.split("::", 1)[1]: value
        for key, value in semantic_results.items()
        if key.startswith(f"{agency}::")
    }
    recommendation_records = [
        {
            "opportunity_id": str(grant.get("id")),
            "eligibility_status": grant["_eligibility_status"],
            "eligibility_reason": grant.get("_eligibility_reason"),
        }
        for grant in ranked
    ]
    classified = classify_recommendations(
        recommendation_records,
        semantic_by_id,
        minimum_score=minimum_ai_score,
        exclude_confirmed_ineligible=exclude_confirmed_ineligible,
        include_uncertain=include_uncertain,
        project_description=project_description,
    )
    classification_by_id = {
        record["opportunity_id"]: record["recommendation"]
        for record in classified["all_records"]
    }
    for grant in ranked:
        grant["_recommendation"] = classification_by_id.get(str(grant.get("id")))
    ranked = [
        grant for grant in ranked
        if classification_by_id.get(str(grant.get("id")), {}).get("included", True)
    ]
    ranked = sort_results(ranked, sort_by, semantic_results)
    if not ranked:
        st.warning("No results with strategic match evidence under the current filters. Try a broader search or enable audit view.")
    decisions = st.session_state.setdefault("grant_decisions", {})
    for key, record in saved_records.items():
        if record.get("decision") or record.get("notes"):
            decisions[key] = {
                "decision": record.get("decision", ""),
                "notes": record.get("notes", ""),
            }
    missing_deadline = sum(parse_close_date(grant.get("closeDate")) is None for grant in ranked)
    missing_ceiling = sum(grant.get("_award_ceiling") is None for grant in ranked)
    unknown_status = sum(grant_status(grant) == "Unknown" for grant in ranked)
    unverified_goals = sum(not grant["plan_verified"] for grant in ranked)
    st.subheader("Results Overview")
    st.write(
        f"{len(ranked)} opportunities shown · "
        f"{classified['counts']['recommended']} recommended · "
        f"{classified['counts']['confirmed_ineligible']} confirmed ineligible · "
        f"{classified['counts']['not_evaluated']} not AI evaluated · "
        f"{sum((agency + '::' + str(grant.get('id'))) in decisions for grant in ranked)} decisions saved"
    )
    with st.expander("Data quality details"):
        st.caption(
            f"Retrieved search records: {len(grants)} · Classified result pool: {classified['counts']['retrieved']} · "
            f"AI evaluated: {classified['counts']['ai_evaluated']} · "
            f"Below AI threshold: {classified['counts']['below_threshold']} · "
            f"Missing deadlines: {missing_deadline} · Missing award ceilings: {missing_ceiling} · "
            f"Unknown statuses: {unknown_status} · Agencies without verified goals: {unverified_goals}"
        )
        st.caption("Award ceiling is the maximum award per opportunity. It is not total program funding.")
        st.caption("Strategic relevance is a deterministic topic-overlap heuristic, not an AI score, eligibility decision, or award probability.")
    if ranked and not ranked[0]["plan_verified"]:
        st.info("No verified strategic goals have been extracted for this agency yet. Results are shown without a match score; eligibility still needs human review.")
    else:
        st.caption("Match scores are a simple, preliminary strategic-topic overlap heuristic, NOT grant eligibility or award probability.")
    st.download_button(
        "Export visible results (CSV)",
        decision_csv(ranked, decisions),
        file_name="grantscope-results.csv",
        mime="text/csv",
        disabled=not ranked,
    )
    for grant in ranked:
        title = grant.get("title") or "Untitled Grant"
        federal_agency_name = federal_agency(grant)
        closing = grant.get("closeDate") or "Not specified"
        opportunity_id = grant.get("id")
        details = detail_cache.get(str(opportunity_id)) if opportunity_id else None
        eligibility = eligibility_summary(details, agency)
        award_ceiling = grant.get("_award_ceiling")
        total_funding = official_total_funding(grant, details)
        decision_key = str(opportunity_id)
        workspace_key = f"{agency}::{decision_key}"
        saved = decisions.get(workspace_key, {})
        saved_record = saved_records.get(workspace_key)
        bookmarked = saved_record is not None
        semantic = semantic_results.get(workspace_key)
        with st.container(border=True):
            st.subheader(title)
            st.write(f"**Federal agency:** {federal_agency_name}")
            st.write(f"**Deadline:** {closing} · **Status:** {grant_status(grant)}")
            st.write(
                f"**Award ceiling:** {_format_amount(award_ceiling)} · "
                f"**Total program funding:** {_format_amount(total_funding)}"
            )
            st.write(f"**Baseline Keyword Score:** {relevance_summary(grant)}")
            if project_description.strip():
                project_score = grant.get("_project_relevance_score")
                project_label = (
                    f"{project_score}/100 term overlap"
                    if project_score is not None else "Not evaluated: official text unavailable"
                )
                st.write(f"**Project relevance (baseline):** {project_label}")
            if semantic and semantic.get("status") == "Evaluated":
                st.write(
                    f"**AI Strategic Relevance:** "
                    f"{semantic.get('strategic_relevance_score') if semantic.get('strategic_relevance_score') is not None else 'Not evaluated'}/100"
                )
                if project_description.strip():
                    st.write(
                        f"**AI Project Relevance:** "
                        f"{semantic.get('project_relevance_score') if semantic.get('project_relevance_score') is not None else 'Not evaluated'}/100 "
                        f"({semantic['confidence']} confidence)"
                    )
            recommendation = grant.get("_recommendation")
            if recommendation:
                st.write(
                    f"**Recommendation status:** {recommendation['classification']}"
                    + (
                        f" ({recommendation['score']}/100)"
                        if recommendation["score"] is not None else ""
                    )
                )
            else:
                st.write(
                    "**AI Semantic Relevance:** Not AI Evaluated"
                    + (f" — {semantic['evidence_grounded_explanation']}" if semantic else "")
                )
            st.caption("Baseline Keyword Score is separate from AI Semantic Relevance.")
            status_label = "Ineligible (confirmed exclusion)" if eligibility["excluded"] else eligibility["status"]
            st.write(f"**Eligibility:** {status_label}")
            st.caption(eligibility["explanation"])
            st.write(f"**Recommended next action:** {eligibility['next_action']}")
            decision_col, notes_col = st.columns([1, 2])
            with decision_col:
                decision = st.selectbox(
                    "Decision",
                    ["", "Pursue", "Maybe", "Pass"],
                    index=["", "Pursue", "Maybe", "Pass"].index(saved.get("decision", "")),
                    key=f"decision_{decision_key}",
                )
            with notes_col:
                notes = st.text_input(
                    "Coordinator notes (optional)",
                    value=saved.get("notes", ""),
                    key=f"notes_{decision_key}",
                )
            if st.button("Save decision", key=f"save_decision_{decision_key}"):
                if not decision:
                    st.warning("Choose Pursue, Maybe, or Pass before saving.")
                else:
                    decision_data = {"decision": decision, "notes": notes.strip()}
                    decisions[workspace_key] = decision_data
                    store.save(
                        agency, decision_key,
                        {
                            **decision_data,
                            "title": title,
                            "federal_agency": federal_agency_name,
                            "close_date": grant.get("closeDate"),
                            "official_url": f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                        },
                    )
                    st.success("Decision saved for this session.")
            if st.button(
                "Remove from My Grants" if bookmarked else "Save to My Grants",
                key=f"bookmark_{decision_key}",
            ):
                if bookmarked:
                    store.remove(agency, decision_key)
                    saved_records.pop(workspace_key, None)
                else:
                    store.save(
                        agency, decision_key,
                        {
                            "title": title,
                            "federal_agency": federal_agency_name,
                            "close_date": grant.get("closeDate"),
                            "official_url": f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                        },
                    )
                st.rerun()
            if opportunity_id:
                detail_key = str(opportunity_id)
                if st.button("Load official award & eligibility details", key=f"detail_{detail_key}"):
                    try:
                        with st.spinner("Loading official Grants.gov details..."):
                            detail_cache[detail_key] = get_grant_details(opportunity_id)
                        details = detail_cache[detail_key]
                        eligibility = eligibility_summary(details, agency)
                    except GrantsAPIError as exc:
                        st.error(str(exc))
                if details:
                    with st.expander("View analysis & evidence"):
                        floor, ceiling = details["award_floor"], details["award_ceiling"]
                        st.write(f'**Award floor:** {_format_amount(floor)} · **Award ceiling:** {_format_amount(ceiling)}')
                        st.write(f'**Total program funding:** {_format_amount(details.get("total_funding"))}')
                        st.write("**Official applicant types:** " + (", ".join(details["applicant_types"]) or "Not reported"))
                        if details["description"]:
                            st.write("**Official opportunity description:**")
                            st.write(details["description"])
                        if details["eligibility_description"]:
                            st.write("**Official eligibility evidence:**")
                            st.write(details["eligibility_description"])
                        if eligibility["excluded"]:
                            st.write(f'**Exclusion evidence:** {details.get("eligibility_description") or details.get("description")}')
                        if grant["match_score"] is not None:
                            st.write("**Scoring explanation:**")
                            if grant["match_reasons"]:
                                for reason in grant["match_reasons"]:
                                    st.caption(f'Plan goal: {reason["goal"]} (plan page {reason["page"]}); matched terms: {", ".join(reason["keywords"])}')
                            else:
                                st.caption("No goal keywords matched in the available search summary.")
                            st.markdown(f'[Agency strategic plan source]({grant["plan_url"]})')
                        else:
                            st.caption("Strategic plan goals are not verified; no relevance score is assigned.")
                        if semantic:
                            st.write("**Semantic evaluation evidence:**")
                            if semantic["status"] == "Evaluated":
                                st.write(semantic["evidence_grounded_explanation"])
                                if semantic["relevant_opportunity_evidence"]:
                                    st.caption("Official opportunity evidence:")
                                    for item in semantic["relevant_opportunity_evidence"]:
                                        st.caption(f"• {item}")
                                if semantic["verified_source_references"]:
                                    st.caption("Verified strategic-plan references:")
                                    for reference in semantic["verified_source_references"]:
                                        st.caption(
                                            f"• {reference['goal_id']} · page {reference['page']} · "
                                            f"{reference['url']}"
                                        )
                                for concern in semantic["eligibility_concerns"]:
                                    st.warning(f"Eligibility concern: {concern}")
                                st.write(f"**AI recommended next action:** {semantic['recommended_next_action']}")
                                st.caption(
                                    f"Model: {semantic['evaluation_model']} · "
                                    f"Evaluated: {semantic['evaluated_at']} · "
                                    f"Usage: {semantic.get('usage') or 'not reported'}"
                                )
                            else:
                                st.caption(semantic["evidence_grounded_explanation"])
                        if agency in VERIFIED_GOALS and not semantic:
                            st.caption(
                                "AI matching has not been generated for this opportunity. "
                                "Use the bounded preparation action above; page reruns do not make paid requests."
                            )
                elif opportunity_id:
                    st.caption("Load official details to view analysis and evidence.")
                st.link_button(
                    "View Official Opportunity",
                    f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                )
