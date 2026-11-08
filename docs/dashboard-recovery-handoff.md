# Dashboard handoff — shared research contract

November 7, 2026. `app.py` and `modules/dashboard.py` were inspected and not edited. The current Dashboard still calls `generate_dashboard_shortlist`, displays a clearly labelled keyword baseline, and does not invoke deep research. Do not call that baseline an AI strategic match.

## Exact agency-first entry

```python
from services.search_foundation import build_project_review
from services.research_engine import (
    request_for_candidate, run_research, configured_provider,
    ResearchBudget, ResearchStore, context_key,
)

profile = {
    "mission": agency_mission_context,
    "applicant_identity": legal_applicant_name,
    "applicant_category": applicant_category,  # user-declared vs verified explicitly
    "geography": ["North Carolina"],
    "constraints": known_constraints,
    "verified_goals": reviewed_goals,  # tuple of VerifiedGoal, not unreviewed strings
    "goal_sources": reviewed_goal_sources,  # tuple of Source
}
factory = lambda grant: request_for_candidate(
    agency_name, None, grant, mode="agency_first", profile=profile,
)
review = build_project_review(
    discovered_grants, agency_name, None, cached_records=(), budget=2,
    agency_profile=profile, mode="agency_first",
)
scope = context_key(factory({"id": "scope", "title": "scope"}))
cache = ResearchStore()
previous = cache.load(scope)
# ONLY in the handler for an explicit user research/refresh action:
result = run_research(
    review, factory, configured_provider(server_config),
    budget=ResearchBudget(2, 4, 2.42), previous=previous,
    on_update=lambda records: cache.save(scope, records),
)
```

`VerifiedGoal` requires goal_id, text, source_id, exact quote, location and verified_by. The corresponding authoritative `Source` must contain that quotation. Unverified mission context is not a verified goal; supply empty goal/source tuples and show strategy as **Unavailable**. Do not fabricate an agency project to make this work. Agency-first project scores are null; the mode is part of the cache namespace. Never reuse Search project scores as Dashboard strategy.

## Display and billing contract

Use `records[opportunity_id]`. `RESEARCHED_AND_VALIDATED` means structural/source checks passed, not legally certified eligibility. Display `shared_result.can_apply`, `should_apply`, `can_act_in_time`, separate relevance, unresolved conditions, next actions, official sources and counterevidence. `should_apply == reject` must not be promoted just because the final gate classification remains conditional pending human attestation. Keep confirmed exclusions out of actionable cards. Forecasted is not open; retain Posted/Forecasted/Closed/Archived distinctly and check refreshed status/deadline.

Cache is isolated by mode, agency, legal applicant, goals, project, geography, constraints and date; evidence/protocol hashes gate reuse. Persist before requests. Ordinary rendering, Save and widget reruns must never trigger `run_research`; only an explicit action may authorize a bounded run. Failed paths do not automatically retry; ambiguous transport/authentication/quota/cost failures stop the action. The production Search main button authorizes its normal bounded shortlist. Do not call optional GPT-4o prioritization or Sol from the Dashboard's unconditional rendering path.

Current Dashboard integration is **not accepted**: the teammate still needs to wire this API, preserve its action boundary, and test its own UI. Shared agency-first invocation has offline integration coverage; no live agency-only evaluation or Dashboard browser acceptance was performed.
