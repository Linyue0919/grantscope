# GrantScope matching engine

`services/match_engine.py` is pure Python (no Streamlit). Dashboard uses it today, and Search can use it with a few lines of code.

## Data sources
| Source | Module | Notes |
|---|---|---|
| Grants.gov search (`search2`) | `services/grants_api.get_grants` (existing, unchanged) | Up to 100 records per keyword. |
| Grants.gov details (`fetchOpportunity`) | `services/opportunity_details.fetch_opportunity_details` | Award floor and ceiling, applicant types, eligibility text, description. |
| NC agency strategic plans | `data/agency_strategic_plans.json` via `services/agency_profiles` | 9 agencies, 30 goals. Each goal is a **verbatim quote** with its PDF page from the official plan linked in the [OSBM directory](https://www.osbm.nc.gov/operational-excellence/strategic-planning/agency-strategic-plans). The other 24 agencies are listed with their plan links but have **no goals**, so they're never scored. Re-check everything with `python scripts/verify_agency_plans.py`, which needs `pdftotext`. |

## Pipeline
1. **Retrieve.** Search Grants.gov for up to 8 keywords: the user's Profile priorities first, then multi-word plan phrases taken round-robin across goals. Results are de-duplicated by opportunity id.
2. **Load details.** Fetch official details for the 40 most promising candidates that fall inside the deadline window.
3. **Screen.** These are pass/fail rules, and they never adjust a score:
   - `closed`: the Grants.gov status is closed or archived, or the closing date has passed.
   - `outside_window`: the grant closes after the chosen window.
   - `not_eligible`: the listed applicant types exclude the agency's category (`State governments`).
   - `no_alignment_evidence`: no plan-goal term appears in the title or official description.
   - `forecasted_hidden` / `unknown_deadline_hidden`: hidden by a user filter.
4. **Score** the grants that pass, out of 100:

| Component | Max | Rule |
|---|---|---|
| Strategic alignment | 60 | Each plan phrase in the **title** earns 20 points and each single word 10. A term found only in the description earns half. |
| Deadline actionability | 20 | 30+ days → 20, 14–29 → 14, 7–13 → 8, <7 → 3. Forecasted → 12. No date → 6. |
| Funding fit | 20 | Ceiling ≥ minimum award → 20. Below the minimum → 5. Not reported or not loaded → 8. |

5. **Rank** by Match Score. Ties go to stronger eligibility, then the sooner deadline.

**The Match Score measures fit and actionability. It isn't a probability of winning an award.**

### Eligibility statuses
The engine never says "eligible". It only reports what the official listing shows.
- `eligible_applicant_type`: State governments, or Unrestricted, is listed and the notes contain no "only … eligible" restriction.
- `needs_review`: the applicant type is "Others", a restriction appears in the notes, or the listing has no type.
- `not_eligible`: the listed types exclude state agencies. These grants are screened out.
- `not_checked`: details weren't loaded.

### Open status
`open` (posted, closing date today or later) · `forecasted` (not accepting applications yet) · `closed` · `unknown` (posted with no closing date).

## API
```python
from services.agency_profiles import get_agency_profile
from services.grants_api import get_grants
from services.opportunity_details import fetch_opportunity_details
from services.match_engine import MatchSettings, run_matching

result = run_matching(
    get_agency_profile("Department of Environmental Quality"),
    MatchSettings(horizon_days=90, min_award=100_000),
    search_fn=get_grants, details_fn=fetch_opportunity_details,
    extra_keywords=("clean water",),          # optional user keywords
)
```
`result` keys: `engine_version, generated_at, today, agency, settings, weights, queries[], stats{}, results[], screened_out[], errors[]`.

Each record in `results` / `screened_out`:
```text
id, number, title, federal_agency, source_url, matched_queries[]
deadline   {status, rule, close_date, days_left, within_horizon}
eligibility{status, label, reason, evidence, applicant_types[]}
award      {floor, ceiling, estimated_total, cost_sharing, loaded}
alignment  {points, max, basis, reason, matched_terms[], matched_goals[{goal_id,label,quote,page,plan_url,terms,title_terms}]}
screening  {passed, codes[], reasons[]}
match_score (int or None if screened out), score_breakdown{strategic_alignment,deadline,funding}
explanation, data_gaps[], details_loaded
```
To score grants Search has already fetched, call `evaluate_grant(hit, profile, details_or_None, settings, today)` for each hit, then `rank_results(records)`. `modules/grant_card.render_grant_card(record)` renders a record in the Dashboard's style.

## Known limitations
- Term matching is lexical. The matcher catches whole words and plurals, but it can't tell what a grant actually means.
- Only 100 records per keyword are fetched, so coverage is shown as possibly incomplete.
- Restrictions to other regions are flagged from the title only and are never auto-excluded.
- Commerce (FY2021–2023) and WRC (2023–2025) are the most recent plans OSBM lists, but they're older than the others.
