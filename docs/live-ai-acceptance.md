# Live AI acceptance — November 7, 2026

Local branch: `release/final-demo`, integration worktree `/tmp/grantscope-integration-20261107`.
**Both AI paths completed real inference and rendered actual outputs.** This is a bounded functional check, not a model-accuracy evaluation or production approval. No push, merge, remote deployment, credential rotation or Azure resource change occurred.

## Dashboard GPT-4o

Used the production shared `run_matching` path, live Grants.gov retrieval and official details, real `AzureFitEvaluator` and `AzureEligibilityEvaluator`, and Dashboard rendering functions. The acceptance workload was bounded to two discovery queries, 12 detail lookups, two fit calls and one eligibility call per run; it did not test the larger default batch under load. No model response was mocked.

The final inference run accepted all three outputs:

| Opportunity | Assessment | Actual outcome |
|---|---|---|
| [362978 — Health and Extreme Weather Solutions-Focused Research Hubs](https://www.grants.gov/search-results-detail/362978) | Strategic fit | 90/100; four verified source quotes; forecasted/upcoming, not currently accepting applications |
| 362978 | Applicant interpretation | `likely_eligible`; exact official State governments category verified; not legal eligibility certification |
| [362034 — 2026 Alaska Marine Education and Training Mini-Grant Program](https://www.grants.gov/search-results-detail/362034) | Strategic fit | 0/100; retained outside Priority after the classification fix |

The final eligibility/fit requests took approximately 2.39, 2.14 and 2.52 seconds respectively. The production Dashboard evaluator does not persist response token usage, so exact tokens and Dashboard cost are **not available** from this run.

A subsequent zero-inference policy recheck used fresh official details and the actual recorded Azure outputs. It confirmed 362034 in lower evidence, 362978 upcoming, and [362644 — Colorado River Basin Tribal Drought Resiliency](https://www.grants.gov/search-results-detail/362644) screened out by its explicit mandatory tribal-applicant requirement. Dashboard cards rendered actual AI evidence without errors. The 90-point strategic score does not make a forecast opportunity actionable.

## Search Sol Deep Research

Streamlit AppTest entered a realistic NC DEQ riparian/stream-restoration and water-quality-monitoring project, $300,000 funding preference and current-date closing threshold. Actual discovery retrieved 416 opportunities, inspected 80 official details and displayed 364144 and 363920 as screened Potential Matches. The real **Deep Research** button researched [363920 — Easement Restoration and Stewardship](https://www.grants.gov/search-results-detail/363920).

Official evidence was retrieved dynamically, including the Grants.gov summary and both attachments:
- [Primary notice, attachment 355082](https://apply07.grants.gov/grantsws/rest/opportunity/att/download/355082)
- [Additional official document, attachment 355083](https://apply07.grants.gov/grantsws/rest/opportunity/att/download/355083)

Final actual output: **RESEARCHED_AND_VALIDATED / CONDITIONAL**, project relevance **65/100**, strategic relevance **unavailable**, applicant route **needs_review**, medium relevance confidence. No verified DEQ goal sources were passed into this Search research packet, so an agency-strategy score was correctly withheld.

The analysis correctly treats qualifying NRCS easement services as the controlling purpose; a general watershed project is insufficient. It retains unresolved legal applicant/registration, qualifying easement scope, staffing, partner roles, activity-specific budget and readiness requirements. The listed closing date is November 19, 2026, 11:59 pm Eastern; the official award range is $250,000–$5,000,000 and match is not required. These facts do not prove the specific project can submit in time. Preparation remains **Cannot estimate reliably**. Amendment and incorporated-policy completeness remain explicitly unverified.

| Stage | HTTP | Input tokens | Output tokens | Latency | Validation |
|---|---:|---:|---:|---:|---|
| Analysis | 200 | 35,685 | 4,258 | 54.397 s | All 44 checks passed: 11 exact, 21 whitespace/NFC formatting, 12 explicit uncertainty |
| Decision | 200 | 42,497 | 1,594 | 23.291 s | All 41 checks passed: 9 exact, 20 whitespace/NFC formatting, 12 explicit uncertainty |

Decision validation also resolves the validated analysis claim registry and applies final hard gates. Counts are validation checks, not distinct factual claims independently adjudicated by humans. Matching quotations do not establish complete semantic correctness.

The result rendered **Conditional — needs verification**, applicant uncertainty, 65/100 relevance, unavailable strategy and official evidence. A fresh service invocation reused the actual validated cache with **zero new inference HTTP requests**, with repeat inference blocked as a safety assertion. A rerender showed the same score and state without errors. Browser pixels/layout were not manually inspected; interactions used Streamlit's testing framework with real inference and official data.

## Failures preserved and fixes

No authentication, quota, transport or malformed-JSON error occurred in these requests. All paid Sol HTTP responses were 200. Earlier evaluations were locally rejected:

| Sol attempt | Paid requests | Outcome / actual reason |
|---|---:|---|
| 1 | 1 | Analysis citations passed; decision was blocked before transmission by byte-count/token-budget confusion |
| 2 | 2 | Validated CONDITIONAL output, relevance 70; exposed unstable cache identity during the follow-up check |
| 3 | 1 | False rejection of `cannot determine` uncertainty wording |
| 4 | 1 | Compound funding-range/cost-allowability inference rejected; atomic-claim instructions added |
| 5 | 1 | Negative counterevidence mentioning allowable work falsely treated as affirmative permission |
| 6 | 2 | Final-code live analysis and decision both passed; CONDITIONAL 65; cache reuse passed |

Fixes:
1. Eligibility accepts a complete exact short applicant-category label, including surrounding quote punctuation, while rejecting empty labels and fragments. Cache prompt version advanced.
2. Sol decision input budgeting uses actual Azure analysis prompt tokens for the unchanged evidence packet plus a conservative byte bound for new content. No evidence is truncated; output, cost, TPM and no-automatic-retry safeguards remain. Matching resumed analyses can restore recorded token telemetry.
3. Applicant categories in official summary evidence are canonicalized as an unordered set. Changing their API order no longer triggers paid reanalysis; changed substantive evidence still invalidates reuse.
4. Material-inference checks detect affirmative permission predicates rather than rejecting every mention of `allowable`; explicit uncertainty and negative counterevidence are handled correctly. Exact source identity and quote checks are unchanged; unsupported affirmative eligibility/allowability remains rejected. Instructions require atomic claims and separate award arithmetic from permissions.
5. Search exposes explicit retry/resume after completed failures/incomplete research; no retry occurs on rerender. Ambiguous inflight requests remain blocked. Its caption correctly distinguishes free screening from paid Deep Research.
6. Dashboard honors the demonstrated explicit tribal-only applicant requirement, and a validated zero AI fit cannot become Priority from the keyword half of a blend. Such zero-fit records remain reviewable.

Ten GPT-4o requests and eight Sol requests were made across diagnosis and rechecks. These were separate authorized, bounded experiments after concrete findings, not automatic retry loops. Recorded Sol estimates total **$0.997026**, including cache-write telemetry; the final two-stage run estimates **$0.253972**. These use the engine's reference rates and are **not verified Azure billing charges**. Dashboard cost is not recorded; a complete all-model total cannot be stated.

## Tests, storage and remaining limitations

- Full offline suite after fixes: **242 passed, 25 skipped**. Skips are absent optional archived/private evidence fixtures, not claimed evaluations.
- Compilation and `git diff --check` passed. Credential-pattern scan found no matches in release source files. No keys/tokens were printed. Original checkout's app.py, Dashboard and legacy recommendation cache hashes remained unchanged.
- Actual raw model responses, private caches and detailed logs remain outside Git in private `/tmp/grantscope-live-*` directories. Only this nonsecret summary is added to docs.
- Modified implementation: `services/{ai_eligibility,eligibility_assessment,match_engine,official_evidence,research_engine,integration_search}.py`, `modules/integrated_search.py`, `research_foundation/{citations,protocol}.py`; regression coverage in `tests/test_live_ai_regressions.py` and `tests/test_integration_search.py`.
- The 80-detail/100-per-query retrieval limits, missing strategy sources in Search research, unknown amendment completeness and single-opportunity acceptance scope remain. Model scores varied between runs; no accuracy or consistency metric is claimed. No live verification of remote App Service deployment, browser layout or other grants is implied.
