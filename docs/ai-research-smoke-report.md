# GrantScope first live AI research smoke report

November 7, 2026. **Experiment stopped. Two paid analysis calls, zero decision calls, zero retries.** This is one opportunity, not a completed comparative accuracy benchmark. No model winner is declared.

## Authorized deployments and unchanged production

Created exactly these child deployments on `grantscope-ai-team07` (East US):

| Deployment | Verified model/version | SKU / capacity | Actual rate limits | Upgrade / state |
|---|---|---|---|---|
| grantscope-bench-gpt55-v1 | gpt-5.5 / 2026-04-24 | GlobalStandard / 200 | 200,000 TPM; 200 RPM | NoAutoUpgrade / Succeeded |
| grantscope-bench-gpt61sol-v1 | gpt-6.1-sol / 2026-09-29 | GlobalStandard / 200 | 200,000 TPM; 200 RPM | NoAutoUpgrade / Succeeded |

Only those two deployment URLs received PUT requests, using ARM API 2024-10-01. Existing `grantscope-gpt4o` model/version, SKU, capacity, upgrade, state, capability and rate-limit metadata matched the before snapshot after creation and again after inference. Production files/cache hashes also matched their pre-work snapshots. No credential/configuration edit, role change, production integration, commit or push occurred. The new deployments remain provisioned; no unauthorized cleanup/deletion was attempted.

A local verification error initially stopped creation after GPT-5.5 succeeded: Azure omitted `jsonSchemaResponse` from its capability dictionary. I corrected the assumption that omission meant unsupported, added a regression test, and created only the remaining Sol deployment. No deployment PUT was retried or overwritten, and no inference had occurred at that point. Both models subsequently accepted the strict JSON-schema request and returned HTTP 200, demonstrating actual compatibility for this stage.

## Scope, provenance and inputs

Executed with `/openai/v1/chat/completions`, Entra authentication captured in memory, medium reasoning effort, `max_completion_tokens=25000` for analysis and an unused 8000 decision cap. No temperature, tools, redirects or automatic retries. Concurrency one. The exposed API key was neither read for inference, tested nor rotated.

Frozen opportunity: **364144**, Landscape Scale Restoration Grant Program for Non-Federal Lands. Full primary notice/fact-sheet text, original hypothetical DEQ water-sensor project and two source-checked strategic excerpts were supplied. Missing amendments, referenced plan/tool/form contents and extraction verification were disclosed. Historical GPT-4o ratings, reviewer labels and known-mistake notes were excluded. Saved stage-one `messages` are identical across both models; both report 16,440 prompt tokens.

The smoke driver reuses the existing harness's packet loader, payload builder, validation, cost reservations and private logging. A narrowly registered one-case/two-model authorization branch accepts the user's explicit public-rate/no-reference-label smoke permission; the full benchmark's human-label/pricing gates remain in place. The smoke schema adds the requested viability classification and explicitly maps the existing A–F dimensions, identically for both models. This is a separate contract, not silent execution of the 18-call benchmark.

Executed contract SHA-256:
`9de5d3a9cc56375c5fcaf1a424c8a19c34ca1b438052540ac97eabb45c2b21bf`

## Side-by-side execution and telemetry

| Measure | GPT-5.5 | GPT-6.1 Sol |
|---|---|---|
| Returned model | gpt-5.5-2026-04-24 | gpt-6.1-sol-2026-09-29 |
| Analysis started UTC | 23:27:40.762037 | 23:28:11.570812 |
| Analysis ended UTC | 23:28:11.103483 | 23:28:58.439258 |
| HTTP / finish reason | 200 / stop | 200 / stop |
| Measured request elapsed | 30.340 s | 46.867 s |
| Prompt tokens | 16,440 | 16,440 |
| Billed completion tokens | 3,734 | 3,500 |
| Reasoning tokens, already included in completion | 512 | 70 |
| Cache-read tokens | 0 | 0 |
| Cache-write tokens | Not reported (older-model accounting) | 16,437 |
| Schema / A–F structure | Passed before citation check | Passed before citation check |
| Citation validation | Failed | Failed |
| Decision brief | Skipped; no request | Skipped; no request |
| Can Apply / Should Apply / Act in Time final answers | **Not produced** | **Not produced** |
| Final viability classification or scores | **Not produced** | **Not produced** |
| Corrected public-rate cost estimate | $0.194220 | $0.0760985 |

Aggregate: 32,880 prompt + 7,234 completion = **40,114 tokens**, including 582 reasoning tokens. Request latencies exclude separate CLI preflight/authentication time. Both responses completed; neither timed out, hit quota or truncated. The experiment stopped at two calls because both failed the stage-one validation gate; the two unused decision-call slots are not permission to retry.

### Cost correction and limitation

Initial four-call conservative ceiling was $3.00 using ordinary input/output prices. Sol's response exposed an estimator omission: `prompt_tokens_details.cache_write_tokens` was retained but not incorporated by the old simple cost calculation. Raw logs are unchanged and contain its original $0.06788 estimate. A separate derived summary corrects it.

At public GlobalStandard short-context rates, with the documented default 30-minute cache lifetime:

- GPT-5.5: `(16,440 × $5 + 3,734 × $30) / 1,000,000 = $0.194220`.
- Sol: `((16,440 − 16,437) × $2 + 16,437 × $2.50 + 3,500 × $10) / 1,000,000 = $0.0760985`.
- **Total estimated $0.2703185, approximately $0.27**. This is an estimate, not an invoice or verified credit deduction.

Microsoft publishes the [Sol cache-write rate](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-gpt-6-1-sol-in-microsoft-foundry-advanced-intelligence-optimized-for/4560811), documents [default 30-minute caching and usage accounting](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching), and documents API parity for cache controls. OpenAI explains [cache-write rates replace ordinary input rates for those tokens](https://developers.openai.com/api/docs/guides/prompt-caching). Actual subscription tariffs, taxes and credit balance remain unverified.

The cache-aware ceiling for the same four maximum-budget calls would be **$3.12**, still below the authorized $15. The initial $3.00 ceiling was incomplete; do not reuse that calculation for another experiment. There is no completed brief, so cost per completed research brief is undefined. Stop remains in effect; no additional calls were used to diagnose pricing.

## Citation failures versus substantive analysis

Both recorded error: `Evidence validation: unknown source or nonmatching exact quote`. Offline inspection of **all** claims, without altering validation or rerunning models, gives:

| Diagnostic | GPT-5.5 | GPT-6.1 Sol |
|---|---|---|
| Total claims including counterevidence | 36 | 33 |
| Exact cited-source matches | 12 | 11 |
| Nonmatches that match after whitespace-only normalization | 19 | 17 |
| Other cited-source mismatch | 1 | 0 |
| Unknown source IDs | 0 | 0 |
| Allowed uncited unresolved requirements | 3 | 5 |
| Additional schema-policy violation | 1 uncited reasoned inference | 0 |

Whitespace diagnostics are **not validation passes**. The frozen extracted PDF retains line wrapping; both models generally returned single-line quotations. The original strict substring validator rejects them. The run did not normalize, repair or accept these quotations post hoc.

GPT-5.5's additional purpose quote is present in the supplied **Grants.gov synopsis**, but attributed to `official-364144-notice`. This is a wrong-source citation, not proof the underlying program-purpose statement is invented. It also supplied an uncited reasoned inference about the project; the current claim policy only permits null source IDs for unresolved requirements. That requires a project-context citation design review, not automatic rewriting as a valid official claim.

No HTTP-200 output was promoted to a validated recommendation. This is useful failure accounting, not a 0% research-accuracy claim or a meaningful quotation-quality ranking between models.

## Independently identified requirements and human-review concerns

The following describes **unvalidated model drafts**, checked informally against the frozen source for this report. It is not blinded adjudication or completed reference labeling.

| Dimension | GPT-5.5 draft | GPT-6.1 Sol draft | Official evidence / review concern |
|---|---|---|---|
| A project activity | Conditional: sensors/monitoring are not automatically restoration accomplishments | Conditional: distinguishes informing restoration from delivering it | NOFO p8 requires measurable on-the-ground quantitative accomplishments; project work plan is missing. |
| B verified strategy | Conditional; cites both supplied DEQ objectives and mixes in State Forest Action Plan requirements | Supported for water-quality excerpt; explicitly does not claim flood-strategy implementation | DEQ p4/p6 excerpts only. Grant-specific forestry-strategy compliance must remain separate from agency strategy. |
| C purpose/activities | Marks conflicting; describes landscape restoration, equipment approval and unallowable costs | Marks conditional; identifies equipment restoration nexus and unproven installation/research exclusions | NOFO pp7–10. GPT-5.5's “conflicting” could overstate uncertainty as a contradiction; actual project land/treatments/costs are unspecified. |
| D applicant/route | Conditional; distinguishes broad state-government category from appropriate/equivalent agency; sponsorship unconfirmed | Conditional; same distinction, plus partner commitments and approved subawards/contracts | NOFO p5 applicant list and pp11–12 sponsorship/partner requirements. Neither establishes DEQ qualification or a ready alternate lead. |
| E timing/match/readiness | Conditional; identifies December 17 draft, January 26 final, 1:1 nonfederal match and three-year completion | Conditional; same, plus $100k minimum/$300k single-state ceiling and sponsorship cap | NOFO pp4,6,14. Future deadlines alone do not prove registration, sponsor, budget or match readiness. GPT-5.5 omits the explicit award range. |
| F evidence/counterevidence | Lists many missing conditions, but labels some hypothetical land/construction issues as disqualifying contradictions | Explicitly states no confirmed project-specific disqualifying contradiction; identifies synopsis/full-notice sponsorship-exemption discrepancy | Unknown sites or contemplated construction do not prove this project violates a rule. Synopsis exempts Tribal organizations more broadly than NOFO; DEQ has no such exemption. Amendment chain remains unverified. |

Primary official sources: [NOFO, all 23 pages](https://apply07.grants.gov/grantsws/rest/opportunity/att/download/355360), [fact sheet](https://apply07.grants.gov/grantsws/rest/opportunity/att/download/355402), [opportunity 364144](https://www.grants.gov/search-results-detail/364144). Local originals, extraction provenance/hashes and disclosed gaps remain in `docs/ai-research-benchmark/pilot/sources/`.

Both drafts independently identify the central distinction: water-quality thematic alignment does not establish an actionable forest-restoration application. Neither produced a validated final eligibility/suitability decision. Sol's apparent caution and additional conditions are observations from one unadjudicated case, not evidence it is the superior model.

## Artifacts, safety and offline validation

Private raw artifacts remain outside Git:

- `/tmp/grantscope-smoke-20261107-results/`: original four ledger events (two started/two failed), both requests, raw responses/full usage, contract and separate derived-cost summary.
- `/tmp/grantscope-smoke-20261107-state/`: creation payloads/responses, quota/model preflight, authorization and deployment snapshots before/after inference.

Directories are 0700; experiment files 0600. No authorization headers/tokens are persisted. Known authentication token redaction is applied to diagnostics; no request used the exposed API key. Review original responses before sharing. Temporary paths may eventually be cleaned by the operating system; preserve them securely if needed, without committing raw artifacts.

Final offline suite: **101 passed**. Compilation and diff checks passed. New/updated experiment code: `scripts/smoke_ai_research.py`, `tests/test_smoke_ai_research.py`, and narrow smoke-scope/telemetry additions in `scripts/benchmark_ai_research.py`. Existing complete-benchmark approval hashes are invalidated by those code changes; no full-benchmark approval was enabled. Frozen evidence and human reference labels were not rewritten.

## Decision and next work

**Suitable for independent human review: yes, as rejected raw analysis drafts with the failure reasons attached. Suitable for actionable cards or production deployment: no.** No decision brief exists. No browser/UI acceptance result or accuracy/recall/time-saving/impact claim follows from this run.

Do not run the larger three-case pilot yet. First, offline and prospectively: preserve this failed run; version a canonical whitespace representation with source-offset/page mapping; retain exact source identity checks and reject paraphrases/wrong-source attribution; make project context citable; review the fact/inference/conditional-contradiction taxonomy; fix cache-write-aware cost reservation/logging. Independently review both raw drafts against the frozen originals. These are recommendations, not fixes applied after seeing outputs.

A larger experiment can then be warranted under a **new contract and explicit authorization**, with human reference labels for comparative evaluation and an updated budget. Unused smoke calls do not carry forward. Keep the working Search/GPT-4o/Dashboard paths and recommendation caches unchanged. Credential rotation remains an owner-coordinated blocker; the exposed key's validity was not tested. No further Azure writes or inference are being performed.
