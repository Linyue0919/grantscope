# Final product acceptance — November 7, 2026

This report supersedes the readiness conclusions in final-system-audit.md. Scope: latest local working tree, including pre-existing uncommitted Search/engine/test changes, modified app.py and untracked Dashboard. No remote commit was used as implementation evidence. app.py and modules/dashboard.py were inspected but not edited. No Azure requests, cache clearing, commits, pushes, merges or deployment were performed.

## Acceptance decisions

**Search demo: NO-GO for an unqualified working-product claim.** The offline path and a limited real-browser smoke test pass. The complete real provider-to-browser flow remains unverified, and the cached high scores failed suitability review. A justified no-match result can satisfy research quality; a positive-result quota is not an acceptance condition. Save/readback for a recommendation remains verified only with mocked providers.

**Integrated Dashboard + Search demo: NO-GO.** Dashboard still uses its keyword shortlist path; it does not consume the shared recommendation classification contract. Public Schools lacks verified agency goals and agency-only precomputation.

## Six analysis dimensions

| Dimension | Local implementation and acceptance finding |
|---|---|
| Project-purpose relevance | Project-first scores and explanation exist, but the cached 70 for Emerging Voices is a false positive for NC teacher/staff training. A quotation check cannot establish suitability. New output explicitly assesses purpose support; conflicting/unclear/missing assessments stay in review regardless of high score. This is a model judgment, not independent semantic proof. |
| Verified strategic-goal relevance | Only DEQ and OSBM have goal records in VERIFIED_GOALS. Public Schools is unavailable, not zero. New validator forces strategic score null when no goals were supplied. Cards explicitly label unavailable assessment. Existing goal paraphrases/pages still need human source review before pitch claims. |
| Funding purpose / allowable activities | Detail adapter previously omitted the fundingActivityCategoryDesc field that establishes the Philippines/U.S. youth purpose of Emerging Voices. It now preserves that field and supplies it to Azure. Recommendation gate requires explicit Supported purpose status; otherwise review. Dollar ceilings remain program-level; SaTC EDU has a different cap than the overall $1.2m ceiling. |
| Applicant eligibility / partnership | Deterministic exclusions take precedence. Fresh SaTC official text exclusively lists specified nonprofits and IHEs: selected NC state department is excluded as direct applicant by the new narrow rule. No model inference establishes eligibility. A university lead may be worth investigating, but permitted roles, PI conditions and budgets need official verification. Unknown cases remain Needs Review. |
| Deadline / status / readiness | Removed default 30-day restriction; a checkbox makes it optional. Past dates remain excluded. Detail adapter preserves POSTED/FORECASTED, official application date, estimated forecast date and timing note. Primary recommendation gate rejects forecasts, unknown/non-posted status and missing/past dates. SaTC January 25, 2027 is a target date with proposals accepted anytime per the official note, not a verified hard close. Application readiness is explicitly unverified. |
| Evidence / uncertainty / next action | Both 70-point grants' cached snippets match freshly retrieved official fields. They still do not establish direct suitability. New cards expose separate dimensions, confidence, official evidence, timing notes and next action. Needs-review reasons are shown in Other results. Legacy verification flags are not independent human approval or amendment checks. |

## Official recheck of cached Public Schools results

Two no-cost fetchOpportunity requests succeeded on November 7. Public evidence snapshots are in acceptance-evidence/357554.json and acceptance-evidence/347707.json; API envelopes and tokens are excluded. Existing persistent caches were not rewritten.

| Grant | Cached project score / strategic score | Fresh official evidence | Decision |
|---|---|---|---|
| [357554 — Security, Privacy, and Trust in Cyberspace (NSF SaTC)](https://www.grants.gov/search-results-detail/357554) | 70 / unavailable; stored evidence_verified true; every cached quote matched fresh description/eligibility text | POSTED. EDU designation funds cybersecurity education/workforce development, generally up to $500,000 over three years; education-research collaboration can allow another $100,000. Exclusive direct applicants are specified non-academic nonprofits and IHEs. PI must meet appointment requirements at an eligible organization. Listed target January 25, 2027; official timing note says proposals accepted anytime, with panel timing consequences. | Relevant educational research/training lead, but NOT a direct-application recommendation for the NC state department. Official exclusion rule now applies when details are loaded. Investigate an eligible lead and project design only if the agency wants a research partnership. No partnership allowance or application readiness is certified. |
| [347707 — 2023 Emerging Voices Small Grants Program](https://www.grants.gov/search-results-detail/347707) | 70 / unavailable; stored evidence_verified true; every cached quote matched fresh fields | FORECASTED, fiscal year 2023, estimated application date May 22, 2023. Funding activity field focuses on youth-led programs strengthening Philippines/U.S. connections. Cybersecurity is one theme; geography/audience/purpose are substantive conditions. No current application deadline was established. | False positive for an NC K-12 staff-training project. Do not recommend. Do not misstate the forecast's estimated 2023 date as a proven hard close; current availability is unverified. |

Largest Public Schools namespace: 30 cached records, 13 successful evaluations. Eleven are below 60; the two 70s now fail primary-recommendation acceptance gates. **Zero primary recommendations supported by this review.** This does not establish that no suitable federal grant exists: retrieval is bounded and the other records have not been human adjudicated. Complete cached title/score inventory remains in final-system-audit.md; frozen labeling template is evaluation-review-template.json.

## Minimal P0 repairs made in this review

1. Deadline window defaults off; past dates remain suppressed.
2. Preserve official status, dates, forecast estimate, timing note and funding activity description in official detail records; pass relevant fields into Azure; hydrate details before display filters.
3. Add explicit Supported/Conflicting/Unclear funding-purpose assessment to the existing evaluation contract. Missing legacy assessment means review, not automatic paid reevaluation. Existing caches remain intact.
4. High score cannot override conflicting/unknown purpose, applicant/partnership concerns, non-posted status or unknown/past application dates.
5. Narrow exclusive NSF nonprofit/IHE applicant rule excludes NC state departments as direct applicants; guard against rules that also explicitly list government applicants.
6. Force unavailable strategic-goal score to null and show distinct analysis dimensions on primary cards. Display official timing qualification.
7. Summary labels distinguish last-batch activity from current filtered recommendation/pending/review counts; widget decision state uses agency and ID. Official detail reload reruns classification.

## Actual end-to-end evidence

`tests/test_search_integration.py::test_full_search_pipeline_and_rendering` now runs **app.py**, using mocked HTTP at Grants.gov and Azure boundaries and a temporary real disk cache/store. It traverses Dashboard navigation to Search, submits the agency/project, diversified retrieval, detail adapter, deterministic screening, real Azure response validator, cache, merged IDs, recommendation card, Save to My Grants, then actual My Grants navigation/readback.

Diversified ID 2 is absent from seed ID 1, renders at 85, saves with the same agency/ID/title, and appears in My Grants. Astronomy scores 5 and never renders as a primary card; tribal-only ID 4 never invokes Azure. Missing evidence and malformed Azure output remain failed/pending. A retry replaces its failed ID without duplicates; successful IDs are reused. Analyze More makes no additional mocked Azure requests when only the missing-evidence record remains. Raising threshold to 90 removes recommendations without calls. Changing project suppresses previous records. Tests also cover high score versus purpose/status/date/applicant gates, public official evidence snapshots, no invented strategic score, unrestricted deadlines, progressive batch persistence and depth bounds.

This is an integration test with mocked providers, not a live Azure/browser success claim. **63 tests passed**, compilation passed and git diff --check passed; no accuracy metric follows from those checks.

## Real browser observations and limits

Chrome extension tab control failed with timeoutMs errors. Native Chrome controls worked. The existing localhost:8505 app visibly retained old defaults and the historical 0-of-7 symptom, so it was not used as proof of the current code. Its project input did allow recovery of the exact cached project text, confirmed by namespace hash. A separate server was started from this workspace at http://127.0.0.1:8517.

Observed in the fresh actual app: Dashboard-to-Search navigation; empty Find Matching Grants submission produces the expected validation warning; Advanced filters shows closing-window checkbox unchecked, default score 60, and Posted/Forecasted/Unknown statuses; depth dropdown contains Quick, Balanced, Deep and Custom; selecting Custom exposes the bounded new-evaluation selector. No nonempty search or Analyze More action was submitted in the real browser because either can retry cached failures with paid Azure requests. Thus live result-card/save acceptance remains **incomplete**, although the actual app's save/readback is verified in AppTest.

### Exact manual acceptance steps and evidence to collect

1. Run `python -m streamlit run app.py --server.port 8517` from this workspace (or use the review server already running). Open that port, not an older instance. Capture URL plus Search controls. Confirm deadline-window checkbox is off and unknown strategic goals are unavailable.
2. Without authorization for paid usage, do not submit a nonempty Find Matching Grants or Analyze More: current cache contains retryable failures. Run `python -m pytest -q tests/test_search_integration.py` for the no-cost complete replay, including Save/My Grants.
3. After explicit authorization for a bounded live evaluation, select the exact reviewed agency/project and record the project text, research depth and maximum attempts before submitting. Custom's smallest UI batch is 5; it cannot guarantee a one-request test. To retain a one-request cap, use an approved test harness invoking prepare_ai_recommendations(max_new_evaluations=1) rather than pretending Quick is one call.
4. Capture: submitted input; research summary (retrieved/deduped/screened/attempted/succeeded/failed); primary card ID, purpose explanation, official eligibility, status/date/timing note, evidence, confidence and next action. Compare ID to the exact agency/project cache record. Manually review full official NOFO. No appropriate match is a valid outcome if clearly explained.
5. Change only threshold: capture updated recommendations and unchanged evaluated timestamps/request count. Analyze More may spend on failed or new IDs and is not a cache-only verification action.
6. For an approved visible primary card, click Save to My Grants, navigate to My Grants and capture matching agency, ID, title and URL. Reload the application and confirm persistence. Do not use a fabricated positive or relabel a partner-only lead as direct eligibility to force this step.

## Blockers ranked

**P0 — Search acceptance**
- No independently reviewed real case has completed the live provider/browser acceptance checklist; save/readback remains tested with mocked providers. No additional Azure usage was authorized. A justified no-match case is acceptable and must not be replaced by a fabricated positive.
- Full-purpose support is a model assessment plus quotes, not a proven semantic entailment check. New gates reduce known false positives; accuracy is not validated on human labels.
- Legacy successes lack the purpose-status assessment and current official status/detail payload, so they remain review leads; current successes are not automatically refreshed. Stale official amendments require deliberate review.

**P1 — Integration and evaluation**
- Dashboard must adopt shared AI classification and separate agency-only preparation; Public Schools goals are absent and DEQ agency-only records are stale.
- Need human-reviewed labels and a same-candidate comparison; no Precision@K is available.
- Only processed diversified candidates are persisted; unevaluated candidates outside the seed pool can be absent from visible results until a subsequent retrieval. Last-batch remaining count is not exhaustive search coverage.
- Successful ordinary resume avoids duplicate evaluations, but interruption inside a batch can repeat its unpersisted attempts. Cache writes have no cross-process lock.

**P2 — Prototype limits**
- Up to eight queries, per-query truncation, no pagination, narrow eligibility patterns, no time-based cache expiration, and no verified readiness checklist. Search may miss suitable grants; unknown eligibility never means eligible.
- Strategic-plan records cover two agencies and still require comprehensive human source checking. No measured government staff time saved, application completion rate or funding impact.

## Reproducible competition evaluation plan

The frozen review template contains the SAME 30 IDs from Public Schools namespace 6960a6614cfb056e, original AI scores/statuses, and empty human-label slots. It is not a gold dataset. The two official rechecks above are analyst findings, not independent human-reviewed labels.

1. Agency user and a second reviewer independently label all six dimensions using dated full official evidence, blinded to rankings. Labels: project support yes/no/unclear, strategic support yes/no/unavailable, activities allowed yes/no/unclear, direct eligibility excluded/needs-review/verified-by-reviewer, partner-route verified/unverified, status/date readiness, overall pursue/review/reject. Record reviewer/date/reason/source and adjudicate disagreements.
2. The exact original project text was recovered from the existing localhost:8505 Search input and its hash matched namespace 6960a6614cfb056e. It is preserved in the review template. Freeze that project and the same 30 candidate IDs/detail snapshots; if new AI evaluation is needed, obtain authorization first. Do not retrieve a different pool for either arm.
3. For project-first comparison use services.matching.project_relevance on the exact same title/description/detail text as a clearly labeled lexical baseline; compare against AI project score. For agency-first use rank_grants only where goals are verified, with separate agency-only AI evaluation. Public Schools strategic baseline is unavailable, not zero.
4. Fix K (e.g. 5), deterministic ID tie-break, threshold and shared safety filters in advance. Report both raw ranking precision and safe displayed precision, coverage/abstention and denominators. Precision@K is relevant labeled items in top K divided by K when K labeled results exist; report actual displayed n separately when fewer than K. Keep unreviewed labels unknown; never call them negatives to inflate precision.
5. Audit false positives (Emerging Voices purpose/audience mismatch; SaTC direct-applicant mistake), false negatives (human-relevant low-scored/unprocessed candidates), retrieval misses and model disagreement. Current data demonstrate a false positive but cannot estimate false-negative rate or precision. The reproduced lexical top five (same 30 IDs; cached title/description) are 351231 (60), 327185 (54), 334326 (54), 362086 (51), 357133 (49). AI top five among the 13 evaluated IDs are 347707 (70), 357554 (70), 344608 (40), 358783 (40), 361604 (40). This is a descriptive ranking comparison, not a fair completed precision benchmark: 17 AI candidates lack successful evaluations and the legacy cache omits some original eligibility text.
6. Measure research time on the same task, official-detail coverage, unresolved eligibility, latency, observed token usage/cost and successful save/readback. No extrapolated funding or time-savings claims.

## Evidence for the five pitch dimensions

- Understand: NC coordinators need three separate answers—can we apply, should we apply, can we prepare in time. User task and applicant identity govern suitability.
- Frame: retrieval/relevance is separate from direct eligibility, purpose, timing and evidence. Unknown is a first-class outcome; breadth and source coverage are bounded.
- Solve: actual adapters -> official screening -> Azure validation -> persistent IDs -> cards -> My Grants works in an offline integration replay; browser smoke checks passed only the stated controls.
- Evaluate: disclose the Emerging Voices false positive and correction; show official snapshots and reproducible labeling plan. No Precision@K or improvement percentage is claimed.
- Drive Impact: demonstrate a traceable coordinator handoff and saved official record. Staff-time savings, applications and awards are intended outcomes, not measured results.

## Next actions by owner

User/Search owner: review these two official snapshots; do not demo either as direct eligibility. Complete the manual browser evidence checklist with an approved opportunity and agreed cost bound; capture exact project text. Obtain independent labels before using accuracy claims. The exact cached project text is now preserved in the review template with a verified namespace hash. Keep scope frozen.

Dashboard teammate: follow dashboard-integration-handoff.md; use AIRecommendationCache + get_cached_ai_shortlist, explicitly select Recommended, preserve agency/ID, distinguish unavailable goals, and prepare a separate agency-only cache only with verified goals and usage authorization. Do not reuse Public Schools project scores as strategic matches. Demo acceptance requires both journeys checked against the same safety contract.

Integrity check: SHA-256 digests of app.py, modules/dashboard.py and both persistent recommendation caches were unchanged from this review's first digest check through final validation.
