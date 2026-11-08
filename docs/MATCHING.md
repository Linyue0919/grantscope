# GrantScope matching engine (v2)

`services/match_engine.py` is pure Python (no Streamlit). Dashboard uses it today. Search can use it with a few lines of code (see [API](#api)).

## Data sources
| Source | Module | Notes |
|---|---|---|
| Grants.gov search (`search2`) | `services/grants_api.get_grants` (unchanged) | Up to 100 records per keyword. |
| Grants.gov details (`fetchOpportunity`) | `services/opportunity_details` | Award floor and ceiling, applicant types, eligibility notes, synopsis, cost-sharing field, attachments. |
| Full announcement (NOFO) PDF | `services/application_effort.fetch_announcement_text` | Read only when the user asks, through the "Analyze full announcement" button. |
| NC agency strategic plans | `data/agency_strategic_plans.json` via `services/agency_profiles` | 9 agencies, 30 goals, each a **verbatim quote** with its PDF page. The other 24 OSBM-listed agencies have no goals and are never assessed. Re-verify with `python scripts/verify_agency_plans.py`. |
| Azure OpenAI (optional) | `services/ai_matching` | Semantic relevance only, and only with validated citations. |

## Pipeline
1. **Retrieve.** Search Grants.gov for up to 8 targeted keywords: Profile priorities first, then multi-word plan phrases round-robin across goals. Each agency therefore gets its **own candidate set**.
2. **Load details** for a deterministic shortlist of the 60 best candidates that aren't closed. Candidates with title evidence come first, then those found by more queries. The shortlist doesn't depend on the days-left filter, and only shortlisted details are used. So results never depend on what was cached earlier, and a stricter filter always returns a subset of a looser one.
3. **Screen** with pass/fail rules. A screened-out grant is excluded and the reason recorded; screening never changes a score.

| Code | Rule |
|---|---|
| `closed` | Grants.gov status is closed or archived, or the closing date has passed |
| `not_enough_time` | Open, but fewer days left than "At least X days left" (default 30; "Any" turns it off) |
| `not_eligible` | The official applicant types don't include the agency's category (`State governments`) |
| `below_min_award` | Optional advanced filter. Only applies when a ceiling is **reported**; grants with no reported amount are kept and the gap is noted. |
| `unknown_deadline_hidden` | No closing date listed (shown if the user opts in) |

4. **Strategic Fit Score (0–100, heuristic): relevance only.**
   - **Keyword heuristic:** plan terms in the grant **title** score 40 per phrase and 20 per word. Terms in the official **description** score 20 per phrase and 10 per word, with the description's total **capped at 40**, because long descriptions mention many topics. The overall cap is 100.
   - **AI (optional):** GPT-4o rates 0–100 relevance against the verified goals. The answer must cite source ids and **verbatim quotes**, and those quotes must be found in the grant text and goal quotes. Answers that fail this check are rejected and the keyword heuristic is used.
   - When both are available, the score is an **experimental, unvalidated 50/50 blend** (`AI_WEIGHT`). Both component scores are kept in `relevance.keyword` and `relevance.ai`.
   - Deadline, funding, eligibility and effort **do not** change the score.
5. **Sections:**
   - `priority`: open, passed screening, Strategic Fit > 0. This is the main list, ranked by fit, with clearer eligibility breaking ties. The deadline is not a ranking factor.
   - `low_evidence`: open and passed screening, but no plan evidence. Its level is `low` when official text was checked and `unassessed` when only the title was available. **Listed, not excluded.**
   - `upcoming`: forecasted grants (not accepting applications yet) that have plan evidence. Forecasted grants without evidence are only counted (`upcoming_low_evidence`).
   - `screened_out`: grants removed by the rules above, each with its reason.

Strategic Fit is **not** eligibility and **not** a probability of receiving an award.

### Eligibility (structured types + official notes, never guaranteed)
`services/eligibility_assessment.py` reads **both** the structured applicant types and the full "Additional Information on Eligibility" notes. Each assessment returns:
- `status` and `label`
- `certainty`: `confirmed`, `interpretation` or `uncertain`
- `basis`: `structured_field`, `eligibility_notes`, `ai_interpretation` or `conflict`
- `reasoning`
- `quote`: a short **exact** substring of the official text
- `quote_source` and `source_url`, which is the Grants.gov listing
- `to_verify`
- `checks`, `listed_categories`, and `ai`

| Status | When | Where it appears |
|---|---|---|
| `ineligible` (confirmed) | The structured types exclude State governments, or the notes explicitly say state governments/agencies are not eligible | Screened out (`not_eligible`) |
| `likely_ineligible` (interpretation) | The notes list eligible applicants without state governments (e.g., NOAA CPO: higher education, nonprofits, commercial, tribal, federal), or an "only …" restriction | The **Likely not eligible** section: visible and flagged, never Priority |
| `needs_review` | "Others" with unclear notes, or the field and notes conflict, or the AI disagrees with the rules | Priority, flagged |
| `likely_eligible` (interpretation) | State governments (or Unrestricted) is listed with no conflicting notes, or the notes list states | Priority, with "verify" |
| `not_checked` | Details weren't loaded | Priority or lower-evidence, flagged |

Lists introduced as "Other/Additional eligible applicants include…" (the usual NIH wording) add to the structured types and are **not** treated as exclusive. "United States" is never read as "state government".

**GPT-4o eligibility interpretation** (`services/ai_eligibility.py`, optional):
- Runs for up to 15 open candidates whose rule-based status isn't conclusive.
- Must return a verdict, its reasoning, and an exact quote from the official text. Answers with a fabricated quote, or language claiming guaranteed eligibility, are rejected.
- Merging rules:
  - It resolves `needs_review` into a likely status.
  - It **never** changes `ineligible`. Confirmed exclusions aren't even sent to the model.
  - When it disagrees with a rule-based interpretation, the result becomes `needs_review`.

### Funding (informational)
The display is "$floor – $ceiling per award", "Up to $ceiling per award", or "Not reported". Grants.gov placeholder values of 0 or 1 count as not reported. The note always says ceilings are maximums, not guaranteed amounts.

### Application effort (evidence only)
`assess_effort` scans official text: the synopsis, eligibility notes, supporting-document names, the cost-sharing field, and the full announcement when the user analyzes it. It looks for:
- cost sharing
- partnerships
- letters of support
- budget narrative
- project narrative
- letter of intent
- data management plan
- biosketches
- environmental review
- evaluation plan
- page limits
- SAM/UEI registration

Each requirement it finds has a quote and its source. Mentions stated as absent or optional (for example "does not have any cost sharing") are ignored. The structured Grants.gov cost-sharing field takes precedence over text. The resulting levels:
- `higher`: 4 or more requirements, or cost sharing plus a partnership.
- `moderate`: 2–3 requirements.
- `fewer_found`: the full announcement was analyzed and fewer than 2 were found.
- `unclear`: only the summary was checked and few requirements appeared in it.
- `insufficient`: there's too little text to judge.
- `unknown`: details weren't loaded.

**No hour estimates.**

## Azure OpenAI configuration
Set these in App Service settings, or locally in your shell or a gitignored `.streamlit/secrets.toml`:
`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` (default `grantscope-gpt4o`), `AZURE_OPENAI_API_VERSION` (default `2024-10-21`).

If these aren't set, the toggle is disabled and the rules and keyword heuristic are used. Check the setup without revealing secrets with `python scripts/check_ai_config.py --sample`. A template is in `.streamlit/secrets.toml.example`. At most 12 grants are assessed per run: the top priority and upcoming grants, plus up to 4 zero-keyword grants with official text, which checks for false negatives. Results are cached by agency, goals, grant content, deployment, API version and prompt version.

## API
```python
from services.agency_profiles import get_agency_profile
from services.grants_api import get_grants
from services.opportunity_details import fetch_opportunity_details
from services.match_engine import MatchSettings, run_matching

result = run_matching(
    get_agency_profile("Department of Environmental Quality"),
    MatchSettings(min_days_left=30, min_award=None),
    search_fn=get_grants, details_fn=fetch_opportunity_details,
    extra_keywords=("clean water",),      # optional user keywords
    ai_evaluator=None,                    # or services.ai_matching.AzureFitEvaluator(config)
)
```
`result` keys: `engine_version, generated_at, today, agency, settings, fit_points, ai_weight, queries[], ai{}, stats{}, results[] (priority), low_evidence[], upcoming[], screened_out[], errors[]`.

Record fields:
```text
id, number, title, federal_agency, source_url, matched_queries[], section
deadline {status, rule, close_date, days_left}      urgency {level, label}
eligibility {status, label, summary, checks[], to_verify[], evidence, applicant_types[], region_flags[]}
funding {display, floor, ceiling, estimated_total, number_of_awards, reported, note, cost_sharing}
relevance {fit_score, method, level, label, keyword{score, reason, basis, matched_goals, ...}, ai{...}|None, matched_goals[]}
fit_score, why, effort {level, label, summary, requirements[{key,label,evidence,source}], not_required[], page_limit, ...}
details_loaded, data_gaps[], screening {passed, codes[], reasons[]}
```
To assess grants Search has already fetched, call `evaluate_grant(hit, profile, details_or_None, settings, today)` for each one, then `rank_results(records)`. `modules/grant_card.render_grant_card(record)` renders a record in the Dashboard's style.

## Known limitations
- The keyword heuristic is lexical. AI assessment helps, but its 50/50 blend weight isn't validated.
- Only 100 records per keyword and 60 detail lookups per run are fetched, so coverage is disclosed in the UI.
- Effort detection uses regular expressions over official text. Requirements worded unusually can be missed; the full announcement is analyzed only on request and only up to 120 pages.
- Restrictions to other regions are flagged from the title only.
