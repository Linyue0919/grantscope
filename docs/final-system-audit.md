# GrantScope release audit — November 7, 2026

Historical first-pass audit. Superseded by [product-acceptance.md](product-acceptance.md), including fresh official rechecks and stricter recommendation gates. The two cached 70s are no longer accepted as primary recommendations.

## Verdict
NO-GO for a claim that both journeys share an evidence-grounded AI engine. Search passes offline integration; real provider and browser validation remain incomplete. No Azure calls, cache clearing, commits, pushes, merges, or deployment were performed. app.py and modules/dashboard.py were inspected but not edited by this audit.

## Request trace and canonical records
Search submission captures agency, project (keywords are the fallback project), and seed grants. prepare_ai_recommendations combines seeds with up to eight diversified Grants.gov queries, deduplicates by string opportunity ID, fetches official details, screens deterministic exclusions, validates Azure JSON and exact evidence snippets, and persists progressive batches. Successful current-version evaluations and confirmed exclusions are reused. Failed records can retry and replace the prior record by ID. Analyze More resumes this path and reruns rendering immediately.

Search merges agency/project cache records with seeds before deadline/status filtering. String opportunity IDs join cached eligibility, semantic results, classification, partitioning, sorting, and recommendation cards. Detail evidence is ID-scoped and reusable across agencies; agency eligibility is recomputed. Evaluation namespaces use exact agency plus a hash of the stripped project; thresholds and display filters do not invalidate evaluations. Changing the agency/project suppresses prior session results until submission. Session seeds and research summaries are not used across those changes.

## Demonstrated defects repaired
- Cached diversified opportunities lost their status on merge and were removed by default status filtering. Persist status; retain Unknown status explicitly and include it in default filters.
- Any cached record blocked retries, including detail/Azure failures. Reuse only current-version successful evaluations or deterministic exclusions; replace retries rather than append duplicate IDs.
- Old versions were implicitly assumed current. Mark missing/obsolete versions pending on cache read; add evaluation version to semantic memoization key.
- Agency/project changes combined previous session seeds with a different evaluation namespace. Bind submitted results to agency/project; keywords-only requests receive project isolation too.
- Analyze More loaded its result after the visible dataset was constructed. Rerun after persistence.
- Official detail payloads were discarded by persistence, preventing full evidence display without refetch. Persist and hydrate details for newly evaluated records.
- Blank evidence snippets passed a vacuous all() check. Require nonempty string snippets matching official text.
- Fresh confirmed exclusions could be overridden by cached unknown eligibility. Fresh exclusions now take precedence.
- Uncertain-eligibility toggle did not control primary cards. It now suppresses unknown-eligibility results when disabled.
- Zero-result text conflated incomplete evaluation and no qualifying results. Distinguish those states and report technical failures from research progress.

## Test evidence
60 tests passed. New test_search_integration.py executes actual Grants.gov search/detail adapters with mocked HTTP, actual Azure JSON/evidence validation, disk persistence, retry/resume, agency/project isolation, and Streamlit AppTest interactions. Diversified ID 2 is absent from seed ID 1 and renders a primary card at 85. Astronomy is scored 5 and never renders a primary card; an official tribal-only exclusion skips Azure; missing evidence and malformed Azure output remain pending. Retry replaces the failed ID; successful IDs reuse cache. Raising threshold to 90 removes the card without Azure calls. Changing the project suppresses old cards. Blank snippets are rejected. Existing tests cover depth limits, batching, screening, scoring, and cache behavior.

python -m compileall -q app.py modules services tests scripts and git diff --check passed. Native browser testing was attempted: in-app browser unavailable; Chrome tab creation failed with an automation timeoutMs error. Local server startup was also blocked initially by sandbox binding restrictions; the approved retry found port 8501 already occupied. AppTest is not a substitute for a successful native browser/live-provider check.

## Cached Public Schools evaluations
Namespace suffix 6960a6614cfb056e: 30 records; 13 successful analyst-v2 evaluations. At threshold 60, two stored evidence-verified evaluations classify Recommended before display filters. With default 30-day deadline filter neither is visible: SaTC closes January 25, 2027, and Emerging Voices has no deadline. Widening to at least 79 days exposes SaTC; unknown deadlines require explicit inclusion. Default status handling now retains legacy Unknown statuses without inventing Posted status.

| ID | Title | Project score | Stored evidence verified | Eligibility |
|---|---|---:|---|---|
| 344608 | Training-based Workforce Development for Advanced Cyberinfrastructure | 40 | True | Needs Review |
| 351231 | U.S. Mission Italy PDS Annual Program Statement | 20 | True | Needs Review |
| 362086 | Annual Program Statement (APS) For Fiscal Year 2026 | 40 | True | Needs Review |
| 327185 | Public Diplomacy Small Grants Program | 30 | True | Needs Review |
| 357554 | Security, Privacy, and Trust in Cyberspace (NSF SaTC) | 70 | True | Needs Review |
| 364048 | NIJ FY 2026 Research and Evaluation on School Safety | 40 | True | Needs Review |
| 329806 | STARBASE Wright Patt | 20 | True | Needs Review |
| 334092 | Culture of Research and University Exchanges Prep program (CRUX) in One Health and Agricultural STEM | 20 | True | Needs Review |
| 331311 | Request for Information (RFI) No.  95332421K0004 - Community Engagement Services for the Solomon Islands Threshold Program | 0 | True | Needs Review |
| 361604 | National Science Foundation Fostering Interdisciplinary Networks to Develop Emergent and Responsive Solutions Foundry (NSF FINDERS FOUNDRY) | 40 | True | Needs Review |
| 358783 | U.S. Embassy Luanda Public Diplomacy Section Request for a Full Proposal Application | 40 | True | Needs Review |
| 332894 | LPS Qubit Collaboratory (LQC) | 10 | True | Needs Review |
| 347707 | 2023 Emerging Voices Small Grants Program | 70 | True | Needs Review |

SaTC suggests a partnership route because its evaluation flags higher-education/nonprofit applicant restrictions. Emerging Voices is a 2023 Philippines youth-oriented program with no cached deadline and questionable NC project applicability. Neither is a confirmed direct-application recommendation. Stored verification occurred against the original detail response; legacy records omit full official eligibility payloads, so not all quotes can be independently reverified offline. New records preserve those payloads.

## Remaining blockers and limits
- Teammate-owned Dashboard uses generate_dashboard_shortlist without Azure and renders keyword baseline relevance, rather than the shared AI classification contract. It cannot substantiate the two-journey product claim; repair requires teammate integration.
- No successful native browser test or live Grants.gov/Azure end-to-end run was completed.
- No time-based cache expiration or official amendment detection exists. Current-version successes remain reused until a deliberate invalidation/version change. Closed dates are filtered, but missing dates and stale official content require review. No cache was altered during validation.
- Legacy caches cannot independently establish every evidence snippet; model verification does not establish geographic fit, applicant eligibility, or whether an old program remains open.
- Batches persist only after each completed batch, so interruption inside a batch can repeat calls from that batch on resume. Concurrent cache writes are not locked. Retrieval/detail requests are bounded by candidates and per-query rows, but the research depth limit bounds Azure attempts rather than all HTTP requests.

One optional bounded live test, only after approval for cost: a single Azure evaluation for one current official opportunity with a clearly relevant project, through Search with max_new_evaluations=1, followed by a cache-only rerun and a higher-threshold rerun. First verify official status/eligibility with Grants.gov, without paid Azure usage. Do not use broad Quick/Balanced submission for that validation.
