# Dashboard handoff — November 7, 2026

Owner: Dashboard teammate. This review did not edit app.py or modules/dashboard.py.

## Required wiring

Read AIRecommendationCache through get_cached_ai_shortlist; do not render raw DashboardShortlistCache records as AI recommendations.

```python
from services.discovery import AIRecommendationCache, get_cached_ai_shortlist
state = get_cached_ai_shortlist(
    agency, AIRecommendationCache(), project_description="",
    minimum_score=60, exclude_confirmed_ineligible=True,
    include_uncertain=True,
)
recommendations = [r for r in state.get("records", [])
                   if r["recommendation"]["classification"] == "Recommended"]
```

`pending` means no agency-only cache; `unavailable` means no AI contract. `ready` means cache loaded, not that any grant is eligible or recommended. `records` can include review records; explicitly select Recommended for primary cards. Display `counts` and `all_records` separately for coverage/review. Preserve official opportunity IDs and links when saving through LocalGrantStore.save(agency, opportunity_id, ...).

## Two distinct contexts, one engine

- Agency-first: `project_description=""`; evaluate against VERIFIED_GOALS[agency]; primary relevance is `strategic_relevance_score`. Missing verified goals means unavailable, never zero. Do not use project scores as strategic scores.
- Project-first: exact submitted project namespace; primary relevance is `project_relevance_score`; agency strategic fit is an independent optional dimension.
- Public Schools has no verified goal profile and no agency-only AI cache. Its project evaluations cannot populate an agency-first Dashboard. Separate agency-only preparation is necessary AFTER source-grounded goals exist and paid usage is authorized.
- DEQ's agency-only cache contains three legacy records with no current evaluation version. Current AIRecommendationCache marks them pending; it is not a demo-ready AI shortlist. The mirrored Dashboard cache bypasses that version guard if read directly.

## Preparation contract (not executed by this review)

`prepare_ai_recommendations(agency, project_description="", cache=AIRecommendationCache(), config=..., max_new_evaluations=..., batch_size=5)` uses the same official evidence, deterministic screening and Azure validator as Search. Do not run automatically on page reruns. Research depth bounds evaluation attempts, not all Grants.gov requests. Successful current-version IDs are reused; failed IDs retry; failures must remain explicit.

## Card fields / acceptance checks

Keep project/strategic relevance, funding-purpose explanation, official eligibility, current status/application date, evidence/confidence, and next action distinct. Only primary cards classified Recommended may use recommendation language. Never label baseline_keyword_score or match_score as AI. Unknown eligibility is not confirmed eligible. Forecasts and unknown/past dates are research leads; confirmed direct-applicant exclusions stay out of normal results. Partnership suggestions are not proof that subawards or collaboration are allowed.

Test: agency switch cannot mix caches; absent goals show unavailable; a high-score official exclusion stays hidden; legacy records stay pending; cached successful IDs incur no new evaluation; save and My Grants retain the same agency/ID. Show a reviewed agency-only positive before calling the combined product demo-ready.
