# GrantScope hard gates and high recall foundation

November 7, 2026. Implemented **offline prototypes**, not integrated into Search or Dashboard. No production file, credentials, deployments or recommendation caches were changed. No paid calls. This foundation does not extract verified rules automatically or prove recall/accuracy.

## Actual local pipeline findings

| Area | Observed behavior | Recall / trust implication |
|---|---|---|
| Discovery | `diversified_retrieval_queries` emits at most eight queries, with project/goal strings capped at 240 characters. Up to 25 results/query plus seeds; no exhaustive pagination in `prepare_ai_recommendations`. Special project expansion is oriented to cyber/education/workforce. | A bounded discovered set, not all relevant federal opportunities. Water/broadband synonyms are not comprehensively expanded. The new queue cannot recover undiscovered grants. |
| Selection | `select_ai_candidates` adds two lexical/baseline-priority records, two zero-baseline-overlap records, then original input order. Current preparation requests up to the full unique pool, but processes only a bounded new-evaluation count. | Existing limited diversity is real; it is not GPT-4o Top-K. Bounded batches can still leave useful records pending. There was no independent low-ranked AI recall-audit allocation. |
| Scores/display | `classify_recommendation` requires the configured relevance threshold for normal recommendations. Below-threshold successful records are retained in persistent cache and Search's “Other results,” not deleted. Additional purpose/evidence/status/date checks can demote high scores to review. | Do not describe low-score records as permanently deleted. They can be overlooked in the collapsed review section; a low successful score is reused without independent deep research. |
| Filters | Unknown dates are omitted unless explicitly included; deadline-window restriction is optional. Status/agency/amount filters apply to merged cached and seed records. | A hidden record is not proof of ineligibility or irrelevance. Visible counts differ from research-pool counts. |
| Eligibility | Narrow NSF-exclusive, tribal-only and institute-only pattern rules; fallback `Needs Review`, not confirmed eligibility. Excluded direct-applicant records are retained but skipped for AI. | Unknown is not automatically a failure. Existing rules do not implement a general exception/partnership adjudicator; direct-route exclusion must not imply all routes excluded. |
| Canonical IDs | Seed and cached records merge by string opportunity ID; retrieval deduplicates string IDs with first record winning. | Fixes outside-seed visibility, but no preservation of conflicting duplicate evidence variants. Production IDs are not normalized for leading zeros. |
| Cache/retry | Agency plus hash of stripped project, evaluation version analyst-v2. Current successful evaluations and exclusions reused; failures can retry on explicit submission/Analyze More. New records saved progressively, default batches five; serial evaluation. | Ordinary reruns do not automatically pay. An interruption before batch persistence may repeat unpersisted work. Evidence/source freshness is not established by persistent cache version alone. |
| Production model | One GPT-4o request over capped official summary fields, `max_tokens=800`, JSON-object mode, 35-second timeout. Scores and explanation generated together; exact quotes checked, not entailment. | No enforced analysis-first stage, full NOFO or material-requirement completeness guarantee. Model conclusions are not official eligibility findings. |
| Benchmark | Frozen three-case primary-notice arm, explicit gaps, same model input messages, two stages, blank human references. | No new model superiority or human performance result exists. The original ten-case summary arm must remain analytically separate. |
| Dashboard boundary | Teammate owns `app.py` and `modules/dashboard.py`; shared production services already expose cached records/classification. | Prototype modules are not imported by either UI. Project cache must not masquerade as agency-only strategic evaluation. Legacy keyword scores remain baseline labels. |

## Gate decision schema and trust boundary

`research_foundation/hard_gates.py` defines `State`, `Source`, `Citation`, `Finding`, `GateResult`, `evaluate_gates` and `screen_timing`.

States: **PASS**, **CONFIRMED_EXCLUSION**, **CONDITIONAL**, **INSUFFICIENT_EVIDENCE**. Required gates: applicant, funding purpose, geography/land, match, sponsorship, timing and official documents. A nonapplicable requirement needs an explicit reviewed finding; silence does not satisfy it.

Each finding retains reason, source ID/quote/location, support reviewer or deterministic rule/version, exception review, application-route review, verified alternate-route flag and unresolved requirements. Each source retains official URL, exact text, version, retrieval time and a current/authoritative attestation. PASS/exclusion require reviewed claim support and an exact quotation from a current authoritative HTTPS `.gov`/`.mil` source. This domain rule is deliberately conservative; other official hosts need a reviewed future extension, not automatic trust.

**The engine does not infer entailment from a matched quote.** `support_reviewed_by` and source-currentness are explicit caller attestations, to be supplied by human review or independently tested deterministic rules. A model must not self-certify these. They are not a cryptographic trust system. Missing support downgrades to insufficient evidence. A reviewed exclusion without exception/route review becomes conditional. A claimed exclusion conflicting with a verified alternate route requires adjudication. A fully verified route can satisfy the applicant gate, but does not satisfy other gates automatically.

Duplicate gate findings require adjudication, not first/last-wins. Missing gates are insufficient evidence. Any confirmed exclusion dominates overall viability, with every unknown/condition still retained. Otherwise insufficient evidence precedes conditional; PASS requires all seven resolved. Preliminary PASS is not actionable; only final PASS sets `actionable=true`. This means **viability verified for the evaluated route**, not “should apply” or award likelihood. Relevance is not an input to gate aggregation.

`screen_timing` consumes source-reviewed structured status/date facts. It distinguishes hard deadlines from target, rolling and forecast/unknown dates. A past target date alone cannot exclude. Hard deadline remains open through its calendar date; closed/archived or expired hard dates nominate exclusion, which still requires reviewed current notice/extension/alternate routes and source support in aggregation. It uses ISO calendar dates, not timestamp/timezone cutoffs. Exact-time deadlines require an additional verified check; do not claim readiness from this helper alone.

`GateResult` returns phase, overall state, per-gate effective state/reason, actionable boolean, unresolved conditions and an audit trail containing all original findings and their cited sources. No excluded record is deleted. Final application decisions still need the independent relevance analysis and next action.

## High recall queue

`research_foundation/research_queue.py`: `build_queue(candidates, QueueConfig(...))` returns full deduplicated pool, selected sequence, nonselected records, reasons, unfilled lane slots, seed and budget.

Candidate fields: stable opportunity `id`/`opportunity_id`, source namespace (default grants.gov), optional `priority_score`, agency/program type, `uncertain`, `user_selected` and gate state. Low score cannot remove a candidate. Confirmed exclusions remain in the pool for audit; user research selection does not override their viability. No candidate is described as deeply researched merely because it is selected.

Deduplication normalizes numeric identities (e.g. 009 and 9) within a source namespace. It preserves **every original duplicate variant**, uses maximum duplicate priority only for scheduling, unions research flags and marks contradictory category/gate metadata uncertain. It does not adjudicate source precedence or merge facts into a fabricated official record.

Default budget ten; lane quotas user 2, uncertainty 2, diversity 2, low-ranked recall audit 1, high priority 3. Round-robin lane order is user → uncertainty → diversity → recall audit → priority. Diversity favors less-represented agency/program groups among selections; missing metadata stays unknown. Recall audit samples reproducibly from the bottom quarter of scored candidates, seed 20261107, after stable identity sorting. Unknown scores use the uncertainty path, not a fabricated zero. Candidate rows record all qualifying paths and the lane actually selecting them.

Lane quotas are limits, not percentages; explicit quotas can leave budget unused. Budget smaller than five cannot guarantee all paths; even larger budgets cannot guarantee a path when its pool is empty/already selected or its quota is zero. Explicit user requests consume budget; overflow stays pending with an explanation. Input order does not change selected identities. This protects selection avenues, **not a measured recall rate**. The queue never selects only GPT-4o Top-K by default.

## Shared engine contract

`research_foundation/contract.py` provides typed `ResearchInput`, `SharedResult`, an input builder and result consistency validation. This is a proposed common interface, not a new production service.

| Input | Meaning |
|---|---|
| mode | agency_first or project_first |
| agency/profile | Stable ID, name, jurisdiction, mission |
| verified goals | Source-linked text, exact quote/location, reviewer; empty means unavailable |
| original project/activities | Required project context for Search; absent for agency-only Dashboard |
| applicant/geography/constraints | Actual entity/category, locations and known or unresolved implementation constraints |
| opportunity/evidence | Stable ID, original title/funder/program, versioned official source text/provenance, missing documents, as-of |

The builder accepts no prioritizer/model-result fields. It supplies original context and source documents independently to deep models, with computed text hashes and a fingerprint covering mode, agency, applicant/project, evidence, constraints and as-of. It rejects agency-only mode carrying project-specific context. Empty strategy remains unavailable. Source quote verification is not automatic semantic entailment.

| Output | Required distinction |
|---|---|
| relevance | Project activity, verified strategy and purpose assessments separately; unavailable strategy score null |
| application viability | Seven hard gates, phase, state, reasons and audit |
| evidence/counterevidence | Source-linked facts, inferences and contradictions |
| unresolved requirements | Missing documents, unknown facts, route/readiness conditions |
| Can Apply | Verified direct/alternate route versus direct exclusion versus needs review; do not conflate closed timing with applicant category |
| Should Apply | Independent pursue / conditional_lead / reject / insufficient_evidence, not a score threshold |
| Act in Time | Official opening/date/intermediate milestones and actual readiness, or explicit uncertainty |
| next actions | Concrete verification/application action and responsible role, without invented contacts |
| research/evidence provenance | Depth, coverage/amendment status, source hashes, analysis/decision versions and model/review status |

Result consistency validation rejects pursuit while viability is excluded, incomplete or preliminary. It does not establish substantive correctness. The contract is typed Python, not yet a production wire protocol or exhaustive runtime validation layer.

Both UIs should later call one orchestration service: discovery → retained pool → reviewed preliminary gates → bounded diverse queue → original-evidence analysis → final reviewed gates → decision brief → common result. UI adapters render fields; they must not recompute eligibility or score-based decisions. “Save” must retain the same opportunity/request/result identity. Search supplies a project; Dashboard requests agency-only goals/mandate relevance. Agency-only research needs its own scope/cache fingerprint and cannot certify unspecified project feasibility. Neither UI should use the other's project-specific judgment as interchangeable data.

## Benchmark-only safety changes

`scripts/benchmark_ai_research.py` now fails the **entire run**, after logging, on any non-200 HTTP response, missing/malformed provider envelope, or ambiguous transport/runtime failure. Requests cannot follow redirects automatically. Authentication, configuration/schema-request errors, quota/rate limits and server errors therefore stop after the first request. No automatic retries, repair calls or resume. HTTP-200 model-content JSON/schema/quote/consistency/refusal/length failures remain recorded comparison outcomes, skip the remainder of that pair and do not get a repair call.

Output directory must be newly created with mode 0700; contract/request/log files use 0600. Contract/request files use exclusive creation; ledger refuses symlinks and unsafe modes/types. Provider failures retain raw body, usage if returned, HTTP/request ID, elapsed time, category, abort flag and whether billed completion usage was supplied. Missing usage is unknown, never zero. The known Entra token is redacted from provider diagnostics; authorization headers/CLI token stdout are never persisted. Public source documents/hypothetical scenarios are the only model inputs. Review raw artifacts before sharing; these controls are not a general secret-discovery scanner for arbitrary future private inputs.

Every request reserves its maximum possible token cost before submission; started events survive ambiguous crashes. Existing 18-call/$15 proposal and 120k conservative input bound remain unchanged. All old approval hashes are invalidated; regenerated templates remain `approved=false` with no human labels. Private permissions do not grant inference authorization.

## AI configuration and approval boundary

Production `grantscope-gpt4o` remains unchanged. Optional future GPT-4o prioritization may order a queue but may not become an exclusion rule. GPT-5.5 is a candidate analyst, GPT-6.1 Sol an independent challenger/audit arm, not a mandatory second scorer or proven winner.

Independent pilot proposes gpt-4o/2024-11-20, gpt-5.5/2026-04-24 and gpt-6.1-sol/2026-09-29. Two new benchmark-only GlobalStandard deployments, 200 units each, NoAutoUpgrade subject to creation acceptance. Use v1 Chat Completions strict JSON Schema; GPT-4o output caps 8k analysis/3k brief with temperature 0; reasoning arms medium effort with 25k/8k combined reasoning+visible tokens, no temperature, `max_completion_tokens`. These unequal accounting budgets do not change the evidence/task. They are hypotheses to test, not proof newer models are better. Current Microsoft API review is recorded in the [safety gate](pre-deployment-safety-gate.md); no new network verification/inference occurred in this implementation.

The two-stage benchmark already prevents scores in analysis and supplies only each model's own analysis to its decision stage. It is not production integration of these prototypes. Pilot maximum remains 18 calls, reference-rate ceiling $11.13, proposed owner envelope $15; effective Azure tariffs/credits and data-plane access remain unverified.

## Final demo and competition checklist

- Freeze production tonight; rehearse permitted existing Search → visible card → Save and ID consistency. No fresh browser validation was performed here. Keep application purpose, eligibility and timing qualifications visible.
- Teammate reviews shared contract and implements Dashboard adapter only after separate approval. Verify agency-only scope, null unavailable strategy and baseline labels. Integrated Dashboard/Search demo remains unverified.
- Understand: show the actual staff decisions and evidence gaps; no invented stakeholder feedback.
- Frame: distinguish discovery recall, research coverage, relevance, viability and readiness. Unknown is not disqualification.
- Solve: show tested prototype gates/queue and benchmark logging; label them offline, not shipped UI behavior.
- Evaluate: use adversarial synthetic tests, frozen official packets and blank independent rubric. No accuracy/recall/model superiority claim before approved real runs and human adjudication. Future ranking comparison needs keyword and AI on the same labeled candidates.
- Drive Impact: explain intended avoided wasted applications and earlier action as hypotheses; collect user outcomes/time baselines later.

Remaining approvals: (1) security owner coordinates exposed-key rotation/config transition; validity remains unverified and no key was printed/tested; (2) independent humans complete/seal references; (3) owner verifies rates/permissions and reviews the new safety contract; (4) separately authorize two exact deployments and bounded inference; (5) separately authorize production adapter/cache-version/UI integration only after pilot review. No approval is implied by offline code preparation. Do not commit/push without a later explicit request.

## Offline validation and exact changed files

Full suite: **99 passed**. Compilation of prototype, benchmark, tests and existing app/services/modules passed. Tracked diff checks and whitespace checks on all newly authored/changed text passed. Credential-assignment scan passed. SHA-256 of teammate app/Dashboard, production semantic service and persistent AI cache match the pre-work snapshots; Git reports no production service/Search modifications. The preexisting tracked app change remains untouched.

New: `research_foundation/__init__.py`, `research_foundation/hard_gates.py`, `research_foundation/research_queue.py`, `research_foundation/contract.py`, `tests/test_matching_foundation.py`, this document.

Updated: `scripts/benchmark_ai_research.py`, `tests/test_benchmark_ai_research.py`, `docs/ai-research-benchmark-plan.md`, `docs/pre-deployment-safety-gate.md`, `docs/ai-research-benchmark/approval-template.json`, `docs/ai-research-benchmark/pilot/approval-template.json`, `docs/ai-research-benchmark/pilot/offline-plan.json`. Existing source packets, rubric and blank reference labels were not rewritten. Generated Python/pytest caches are local ignored test artifacts.

The mocked three-case two-stage test still completes 18 requests/nine briefs. Provider-error tests stop after exactly one request for 400/401/403/404/429/500/503; timeout, connection and malformed-envelope tests likewise stop without retry, preserving unknown billing status. Private permissions, overwrite refusal and token redaction are verified. These are synthetic mocks, not live model or grant-decision performance results. No browser test, paid inference, Azure operation, deployment, rotation, commit or push occurred in this implementation task.
