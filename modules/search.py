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
from services.search_foundation import discover_project
from modules.search_research import render_demo, render_project_review


def partition_recommendation_results(grants, classifications):
    """Keep only actionable AI recommendations in the primary result list."""
    by_id = {
        record["opportunity_id"]: record["recommendation"]
        for record in classifications["all_records"]
    }
    recommended = [
        grant for grant in grants
        if by_id.get(str(grant.get("id")), {}).get("classification")
        == "Recommended"
        and by_id.get(str(grant.get("id")), {}).get("included")
    ]
    review = [
        grant for grant in grants
        if by_id.get(str(grant.get("id")), {}).get("classification")
        != "Recommended"
        and by_id.get(str(grant.get("id")), {}).get("classification")
        != "Confirmed Ineligible"
    ]
    return recommended, review
from services.grant_store import LocalGrantStore
from services.discovery import (
    AIRecommendationCache,
    DiscoveryError,
    cached_semantic_results,
    classify_recommendations,
    merge_cached_opportunities,
    prepare_ai_recommendations,
    research_depth_limit,
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
        elif (closing - today).days >= 0 and (deadline_days is None or (closing - today).days <= deadline_days):
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


def _show_legacy_search():
    st.header("Find Federal Funding")
    st.caption("Find fewer grants. Find the right grants. Act sooner.")
    foundation = st.checkbox("Evidence-first research", value=True, key="search_foundation_enabled")
    store = LocalGrantStore()
    if st.checkbox("Show optional recorded research example",value=False,key="search_show_example"):
        render_demo(store)
    if not foundation:
        st.caption("Fallback Search: legacy relevance scores and filters. Legacy Recommended labels do not certify application viability. Paid GPT-4o evaluation is disabled unless explicitly enabled below.")
    allow_new_ai = False if foundation else st.checkbox("Enable paid GPT-4o evaluation on Search / Analyze More", value=False, key="search_allow_new_ai")
    saved_records = {
        f"{record['agency']}::{record['opportunity_id']}": record
        for record in store.list_records()
    }
    agency = st.selectbox("Agency to evaluate", AGENCIES+["Other NC agency / enter profile"], key="search_agency")
    if agency == "Other NC agency / enter profile":
        agency = st.text_input("NC agency name",key="search_custom_agency").strip()
        if not agency:
            st.info("Enter the NC agency name to begin."); return
    st.caption("Strategic goals are used only when officially verified.")
    query = st.text_input(
        "Keywords (optional)",
        key="search_query",
        placeholder="e.g. cybersecurity, clean water, transportation",
    )
    project_description = st.text_area(
        "What project are you trying to fund?",
        placeholder="Describe the activities, people served, and intended outcomes.",
        help="AI evaluates project fit against official opportunity evidence.",
    )
    # Keywords alone still define a project-specific research namespace.
    project_description = project_description.strip() or query.strip()
    with st.expander("Advanced filters", expanded=False):
        mission = st.text_area("Agency mission / profile context (optional; not verified strategy)",key="search_agency_mission")
        applicant = st.text_input("Applicant identity (optional)",key="search_applicant_identity")
        geography = st.text_input("Project geography (optional)",key="search_geography")
        constraints = st.text_input("Known constraints / match / partners (optional)",key="search_constraints")
        agency_profile = {"mission":mission,"applicant_identity":applicant or agency,
            "geography":(geography,) if geography else (),"constraints":(constraints,) if constraints else ()}
        if foundation:
            st.caption("Evidence-first review retains the full pool. Only research queue size below applies here; score, deadline and other filters apply to the fallback view.")
        limit_deadline = st.checkbox("Limit to a closing-date window", value=False)
        deadline_days = st.number_input(
            "Closing within (days)", min_value=1, max_value=365,
            step=1, value=30, key="search_deadline_days",
        )
        include_unknown = st.checkbox("Include grants with unknown deadlines")
        status_filter = st.multiselect(
            "Opportunity status", ["Posted", "Forecasted", "Unknown"],
            default=["Posted", "Forecasted", "Unknown"],
        )
        sort_by = st.selectbox(
            "Sort results by",
            ["Recommended match", "Award ceiling: high to low",
             "Award ceiling: low to high", "Closing date: soonest", "Newest"],
        )
        min_ceiling = st.number_input("Minimum award ceiling ($)", min_value=0, step=50000, value=0)
        max_ceiling = st.number_input("Maximum award ceiling ($; 0 = no maximum)", min_value=0, step=50000, value=0)
        minimum_ai_score = st.slider(
            "Minimum AI Match Score", 0, 100, 60, key="search_minimum_ai_score",
        )
        include_uncertain = st.checkbox(
            "Include uncertain eligibility", value=True,
            key="search_include_uncertain_eligibility",
        )
        research_depth = st.selectbox(
            "Research queue size" if foundation else "AI Research Depth",
            ["Quick", "Balanced", "Deep", "Custom"],
            index=1,
            key="search_research_depth",
            help="Planning budget only; not completed research." if foundation else "Maximum number of new Azure evaluations for an explicit search or Analyze More action.",
        )
        custom_depth = 30
        if research_depth == "Custom":
            custom_depth = st.selectbox(
                "Custom new evaluations",
                list(range(5, 101, 5)),
                index=5,
                key="search_custom_depth",
            )
        research_limit = research_depth_limit(research_depth, custom_depth)
        show_zero_matches = False
        min_match_score = 0
    eligibility_filter = "Any eligibility"
    exclude_confirmed_ineligible = True

    if st.button("Find Matching Grants", type="primary", key="search_submit"):
        retrieval_query = query.strip() or project_description.strip()
        if not retrieval_query:
            st.warning("Describe a project or add keywords to begin.")
            st.session_state.pop("search_last_results", None)
            return
        try:
            with st.spinner("Searching Grants.gov..."):
                grants = get_grants(retrieval_query, 100)
                if foundation:
                    discovery = discover_project(agency, project_description, grants, get_grants)
                    grants = discovery["grants"]
                    for message in discovery["retrieval_errors"]:
                        st.warning(message)
        except GrantsAPIError as exc:
            st.error(str(exc))
            return
        st.session_state["search_last_results"] = {
            "query": retrieval_query, "grants": grants,
            "agency": agency, "project": project_description.strip(),
        }
        if allow_new_ai:
            try:
                with st.spinner(f"Analyzing up to {research_limit} new opportunities with AI..."):
                    research_result = prepare_ai_recommendations(
                        agency,
                        project_description=project_description,
                        cache=AIRecommendationCache(),
                        config=st.secrets,
                        seed_grants=grants,
                        max_new_evaluations=research_limit,
                        batch_size=5,
                    )
                    st.session_state["search_research_summary"] = research_result.get("summary", {})
            except DiscoveryError as exc:
                st.warning(f"AI evaluation was not completed: {exc}")

    cached = st.session_state.get("search_last_results")
    if not cached:
        st.caption("Run a search to see live opportunity records.")
        return

    if cached.get("agency") != agency or cached.get("project") != project_description.strip():
        st.info("Agency or project changed. Submit Find Matching Grants to evaluate this request.")
        return
    retrieval_query = query.strip() or project_description.strip()
    if retrieval_query != cached["query"]:
        st.caption(f'Showing the previous search for "{cached["query"]}". Click Find Matching Grants to refresh.')
    grants = cached["grants"]
    cached_for_search = AIRecommendationCache().get(agency, project_description) or {}
    cached_records = cached_for_search.get("records", [])
    cached_record_by_id = {
        str(record.get("opportunity_id")): record
        for record in cached_records
        if record.get("opportunity_id")
    }
    grants = merge_cached_opportunities(grants, cached_records)
    if foundation:
        try:
            render_project_review(grants, agency, project_description, cached_records, research_limit, store, agency_profile=agency_profile)
            return
        except (ValueError, KeyError, OSError):
            st.warning('Evidence-first review could not be completed. Showing cached fallback results; no new AI calls were enabled.')
    if st.session_state.get("search_research_depth"):
        stored_summary = st.session_state.get("search_research_summary", {})
        if stored_summary:
            st.info(
                f"Last research batch: {stored_summary.get('attempted', 0)} evaluation attempts, "
                f"{stored_summary.get('succeeded', 0)} succeeded, "
                f"{stored_summary.get('failed', 0)} failed; "
                f"{stored_summary.get('skipped_ineligible', 0)} skipped after official eligibility screening."
            )
    if st.button("Analyze More", key="search_analyze_more", disabled=not allow_new_ai):
        try:
            with st.spinner(f"Analyzing up to {research_limit} new opportunities with AI..."):
                research_result = prepare_ai_recommendations(
                    agency,
                    project_description=project_description,
                    cache=AIRecommendationCache(),
                    config=st.secrets,
                    seed_grants=grants,
                    max_new_evaluations=research_limit,
                    batch_size=5,
                )
                st.session_state["search_research_summary"] = research_result.get("summary", {})
            st.rerun()
        except DiscoveryError as exc:
            st.warning(f"AI evaluation was not completed: {exc}")
    detail_cache = st.session_state.setdefault("grant_detail_cache", {})
    for record in cached_records:
        if record.get("official_details"):
            detail_cache.setdefault(str(record["opportunity_id"]), record["official_details"])
    for grant in grants:
        details = detail_cache.get(str(grant.get("id")), {})
        if details.get("opportunity_status"):
            grant["oppStatus"] = details["opportunity_status"]
        if details.get("close_date"):
            grant["closeDate"] = details["close_date"]
    agency_options = ["All federal agencies"] + sorted({
        federal_agency(grant) for grant in grants
    })
    agency_filter = st.selectbox("Federal agency", agency_options)
    matching, unknown_count = filter_by_deadline(
        grants, int(deadline_days) if limit_deadline else None, include_unknown,
    )
    matching = [
        grant for grant in matching
        if (not status_filter or grant_status(grant) in status_filter)
        and (agency_filter == "All federal agencies" or federal_agency(grant) == agency_filter)
    ]
    st.write(f'{len(matching)} candidate opportunities loaded from Grants.gov for "{cached["query"]}".')
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
    for record in cached_records:
        if record.get("official_details"):
            detail_cache.setdefault(str(record["opportunity_id"]), record["official_details"])
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
        cached_record = cached_record_by_id.get(str(grant.get("id")), {})
        if cached_record.get("eligibility_status") == "Ineligible":
            summary = {
                "status": "Ineligible",
                "explanation": cached_record.get("eligibility_reason")
                or "Official eligibility excludes this applicant.",
                "next_action": "Do not apply directly; review the official notice for any alternate applicant route.",
                "excluded": True,
            }
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
    if cached_recommendations:
        st.caption(
            "Search submission has already evaluated the current bounded batch. "
            "Cached results are reused on reruns and filter changes."
        )
    semantic_by_id = {
        key.split("::", 1)[1]: value
        for key, value in semantic_results.items()
        if key.startswith(f"{agency}::")
    }
    recommendation_records = [
        {
            "opportunity_id": str(grant.get("id")),
            "eligibility_status": cached_record_by_id.get(
                str(grant.get("id")), {}
            ).get("eligibility_status", grant["_eligibility_status"])
            if not grant["_excluded"] else "Ineligible",
            "eligibility_reason": grant.get("_eligibility_reason"),
            "opportunity_status": grant_status(grant),
            "close_date": grant.get("closeDate"),
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
    if not include_uncertain:
        ranked = [grant for grant in ranked if grant["_eligibility_status"] != "Needs Review"]
    recommended, review = partition_recommendation_results(ranked, classified)
    recommended_ranked = sort_results(
        recommended,
        sort_by,
        semantic_results,
    )
    review_ranked = sort_results(
        review,
        sort_by,
        semantic_results,
    )
    ranked = recommended_ranked
    if not ranked:
        counts = classified["counts"]
        if counts["not_evaluated"] or counts["needs_evidence_review"]:
            st.info("Evaluation is incomplete. Pending, failed, or evidence-review records remain; see Other results and research progress.")
        else:
            st.info("No qualifying AI match meets the current threshold and filters.")
        if st.session_state.get("search_research_summary", {}).get("failed"):
            st.warning("Technical evaluation failures occurred. Analyze More can retry failed records.")
        st.caption("Deadline and status filters also apply to cached AI results. Widen the deadline window or include unknown deadlines to review more records.")
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
    st.subheader("Recommended for Your Project")
    with st.expander("About these results"):
        research_summary = st.session_state.get("search_research_summary", {})
        st.caption(
            f"{classified['counts']['ai_evaluated']} of {classified['counts']['retrieved']} "
            "records in the filtered pool have AI evaluations. Only a bounded batch is "
            "evaluated per submission; remaining records are pending, not rejected."
        )
        if research_summary:
            st.caption(
                f"Last batch summary: {research_summary.get('retrieved', 0)} retrieved (before deduplication), "
                f"{research_summary.get('deduplicated', 0)} deduplicated, "
                f"{research_summary.get('official_details_screened', 0)} official details screened; "
                f"{research_summary.get('attempted', 0)} evaluation attempts and "
                f"{research_summary.get('succeeded', 0)} succeeded; "
                f"{research_summary.get('failed', 0)} failed; "
                f"{research_summary.get('remaining_candidates', 0)} retrieved candidates were not processed in this batch."
            )
        st.caption(f"Current filtered dataset: {len(recommended_ranked)} recommended · {classified['counts']['not_evaluated']} pending/failed · {classified['counts']['needs_evidence_review']} requiring evidence, purpose or readiness review.")
        st.caption("AI scores are relevance assessments, not probabilities of eligibility, success, or award.")
        st.caption(f"Below threshold: {classified['counts']['below_threshold']} · Pending: {classified['counts']['not_evaluated']} · Evidence review: {classified['counts']['needs_evidence_review']}.")
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
            st.write(f"**Opportunity ID:** {opportunity_id} · **Deadline:** {closing}")
            st.write(
                f"**Award ceiling:** {_format_amount(award_ceiling)} · "
                f"**Total program funding:** {_format_amount(total_funding)}"
            )
            st.write(f"**Federal agency:** {federal_agency_name}")
            if semantic and semantic.get("status") == "Evaluated":
                st.write(f"**AI project fit:** {semantic.get('project_relevance_score', 'Unavailable')}/100 · {semantic['confidence']} confidence")
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
            status_label = "Ineligible (confirmed exclusion)" if eligibility["excluded"] else eligibility["status"]
            st.write(f"**Eligibility:** {status_label}")
            strategic = semantic.get("strategic_relevance_score") if semantic and agency in VERIFIED_GOALS else None
            st.write("**Verified strategic-goal relevance:** " + (f"{strategic}/100" if strategic is not None else "Unavailable — no verified assessment."))
            st.write("**Funding purpose / allowable activities:** " + str((semantic or {}).get("funding_purpose_fit") or "Unavailable; review official notice."))
            st.write(f"**Status / readiness:** {grant_status(grant)} · Listed application date {closing}. Application readiness requires coordinator verification.")
            if (details or {}).get("deadline_note"):
                st.caption("Official timing note: " + details["deadline_note"])
            for concern in (semantic or {}).get("eligibility_concerns", []):
                st.warning(f"Applicant / partnership condition: {concern}")
            st.caption("Evidence snippets were checked against supplied official text; this is not independent proof of project suitability.")
            if eligibility["status"] == "Needs Review":
                st.caption("Eligibility needs official applicant verification.")
            st.write(
                f"**Why it matches:** "
                f"{semantic.get('evidence_grounded_explanation', 'AI explanation unavailable.') if semantic else 'AI explanation unavailable.'}"
            )
            st.write(
                f"**Next action:** "
                f"{semantic.get('recommended_next_action', eligibility['next_action']) if semantic else eligibility['next_action']}"
            )
            decision_col, notes_col = st.columns([1, 2])
            with decision_col:
                decision = st.selectbox(
                    "Decision",
                    ["", "Pursue", "Maybe", "Pass"],
                    index=["", "Pursue", "Maybe", "Pass"].index(saved.get("decision", "")),
                    key=f"decision_{workspace_key}",
                )
            with notes_col:
                notes = st.text_input(
                    "Coordinator notes (optional)",
                    value=saved.get("notes", ""),
                    key=f"notes_{workspace_key}",
                )
            if st.button("Save decision", key=f"save_decision_{workspace_key}"):
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
                key=f"bookmark_{workspace_key}",
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
                        st.rerun()
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
                                st.write(
                                    f"**Project fit:** {semantic.get('project_relevance_score', 'Unavailable')}/100 · "
                                    f"**Strategic fit:** {semantic.get('strategic_relevance_score', 'Unavailable')}/100"
                                )
                                st.write(semantic["evidence_grounded_explanation"])
                                if semantic.get("funding_purpose_fit"):
                                    st.write(f"**Funding-purpose fit:** {semantic['funding_purpose_fit']}")
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
                        if not semantic:
                            st.caption(
                                "AI matching has not been generated for this opportunity. "
                                "Submit Find Matching Grants to run one bounded AI batch; page reruns do not make paid requests."
                            )
                elif opportunity_id:
                    st.caption("Load official details to view analysis and evidence.")
                st.link_button(
                    "View Official Opportunity",
                    f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                )
    with st.expander(
        f"Other results ({len(review_ranked)})",
        expanded=False,
    ):
        st.caption(
            "Below-threshold, pending, failed, and evidence-review records are shown here. "
            "Confirmed ineligible opportunities are excluded."
        )
        for grant in review_ranked:
            recommendation = grant.get("_recommendation") or {}
            title = grant.get("title") or "Untitled Grant"
            status = recommendation.get("classification", "Not AI Evaluated")
            st.write(
                f"**{title}** · {status} · "
                f"Official deadline: {grant.get('closeDate') or 'Not reported'}"
            )
            st.caption(recommendation.get("reason") or "Not AI recommended. Confirm official details and eligibility before deciding.")
            opportunity_id = grant.get("id")
            if opportunity_id:
                st.link_button(
                    "View official opportunity",
                    f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                )


def show_search():
    """Simple production entry; legacy controls remain a developer-only recovery path."""
    import os
    if os.environ.get('GRANTSCOPE_LEGACY_SEARCH')=='1':
        return _show_legacy_search()
    from modules.integrated_search import show_search_screening
    return show_search_screening()
