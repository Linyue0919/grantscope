# GrantScope AI research benchmark and competition plan

Prepared November 7, 2026. **Preparation only: no new deployments, paid inference or production changes.** The three-case pilot is the next proposed experiment; the original ten-case summary arm remains available for later expansion. No model results or human reference labels have been produced.

## Production audit and runtime diagnosis

Inspected local `services/semantic_matching.py`, `services/discovery.py`, `services/eligibility.py`, `services/verified_goals.py` and `modules/search.py`, including the working tree. Existing teammate changes are outside this work.

| Component | Actual behavior | Implication |
|---|---|---|
| Azure request | Deployment Chat Completions, API `2024-10-21`, temperature 0, JSON object mode, `max_tokens=800`, timeout 35 seconds | 800 limits completion, not prompt. JSON mode does not enforce a schema. |
| Input | Agency; goal IDs/paraphrases/page/terms; title 300 characters; description 6,500; eligibility 3,500; funding activities 3,500; project 4,000; applicant types/status/date/note | Character caps can remove restrictions. No full notice, amendments or attachments. Goal source URL/PDF not supplied in model message. No dedicated complete match/readiness record. |
| Output | Scores and explanations in one response; explanation retained up to 1,200 characters; evidence and concerns capped at five each | No enforced analysis-before-decision boundary. Output field order does not establish internal reasoning order. |
| Evidence check | Schema/score validation and exact snippet matching against official detail fields | A genuine quote can still fail to support a suitability claim. Entailment and omitted requirements are not established. |
| Scheduling | Up to eight diversified searches; detail fetching and model evaluations serial; persistence batches default five | Five is a persistence batch, not five parallel Azure calls. Serial work is a plausible runtime contributor. |
| Cache/retry | Reuse current-version successes/exclusions; failed/new IDs may run on explicit Search/Analyze More; ordinary filter reruns do not invoke AI | No automatic Azure retry loop. Interruption before batch persistence can repeat unpersisted work on explicit resume. |
| Depth | Quick 10, Balanced 30, Deep 50, Custom 5–100 in increments of five | Attempt counts are evaluation invocations; early missing-detail rejection need not send HTTP. |
| Diagnostics | Accepted responses retain three aggregate usage counts; rejected responses lose raw content/usage; no per-request or per-stage elapsed log | Cannot calculate all-call cost, request latency or retrieval/generation time split retrospectively. |

### Measured versus unknown

The completed DEQ cache contains 38 accepted evaluations, 12 evidence-validation failures and two deterministic eligibility exclusions. The 12 failure IDs are 357725, 327345, 343653, 351231, 363634, 329436, 334905, 362755, 350230, 364179, 360645 and 352238. Their recorded reason is `Azure semantic evaluation failed: evidence snippets do not match official detail text.` These reached response parsing and validation; they are not evidence of transport timeouts, 429s or malformed JSON. Raw failed quotes were discarded, so the precise mismatch mechanism is unknown.

The 38 successes record 58,131 prompt and 17,716 completion tokens (75,847 total); rejected-call usage is unknown. Successful timestamps span 157.192041 seconds: this is neither whole-run duration nor measured per-call latency. No observed truncation failure was recorded for these 50 attempts. The code rejects `finish_reason=length`; that does not prove no truncation ever occurs elsewhere. An 800-token cap plausibly limits explanation completeness, but is **not a measured cause of slow runtime**. Retrieval, network, generation and cache-miss contributions require new stage telemetry, not speculation. Validation failures waste completed work and reduce coverage; absent automatic retries, they do not independently prove extra calls in that run.

## Independent evidence-first design

Preserve production discovery and deterministic exclusions. For a later approved integration:

1. Freeze an official opportunity snapshot, full notice, amendments and material attachments; retain URLs, retrieval times, raw/text SHA-256, extraction method and missing-document status. Treat documents as untrusted evidence, not instructions. Never silently truncate or claim an attachment was read from its name.
2. Produce a requirement inventory across activities/prohibitions, applicant/partner route, geography/land/beneficiaries, sponsorship, match, intermediate/final deadlines, status and readiness. Separate confirmed source facts, inferences, unknown requirements and contradictions. Verified strategy uses source passages; unavailable strategy stays null.
3. Validate stage-one structure and citations before requesting stage two. Stage one has no score fields. Stage two independently answers Can We Apply / Should We Apply / Can We Act in Time, then gives relevance scores. High relevance cannot override material contradictions or unknowns.
4. Validate exact quotations and internal decision consistency automatically; independently review **claim entailment and material omissions** against the complete packet. Current harness does not solve semantic entailment automatically. A schema-valid/quote-valid result is not an accepted human recommendation.
5. Present a short decision brief with restrictions, uncertainty and the next responsible role/action; keep detailed evidence available. Distinguish actionable candidate, conditional lead, not suitable/eligible and insufficient evidence. Preserve rejection diagnostics; no silent paid retries.

### Suggested separate budgets, not production changes

| Stage | Proposed initial policy |
|---|---|
| Discovery/triage | Deterministic retrieval/eligibility; zero model calls in this pilot. Optional future model triage: 1,000 completion tokens, separate evaluation required. |
| Official extraction | Local PDF/HTML/OOXML extraction, zero inference. Retain all text and explicit gaps. Future OCR/extraction-model budget must be approved separately; no hidden chunk calls. |
| Requirement analysis | GPT-4o 8,000 output tokens; reasoning arms 25,000 **combined reasoning and visible output** tokens, medium effort. Ask for concise auditable findings, not private chain-of-thought. |
| Decision brief | GPT-4o 3,000; reasoning arms 8,000 combined tokens. No automatic expansion after truncation. |

Budgets are configurable in the independent harness `MODELS` registry and bound into its contract hash. Different reasoning/visible budgets reflect API accounting, not different evidence or questions. This is an operational comparison under explicit caps, not equal-compute inference. Hidden reasoning usage counts toward billed completion tokens. Record `length`, refusal, schema, quote and consistency failures separately from human decision errors.

## Three-case pilot evidence

`docs/ai-research-benchmark/pilot/manifest.json` registers exactly B01/364144, B03/357554 and B04/347707. It reuses the same hypothetical scenarios as the ten-case arm. Historical model conclusions and human inventory notes are excluded by the packet whitelist. No cached AI score serves as a label.

| ID | Frozen official documents | Completeness and material findings for human review only |
|---|---|---|
| 364144 | All 23 PDF pages of the October 2026 NOFO, attachment 355360; fact sheet 355402 | Full primary notice text included; budget workbook/equipment form, linked land tool, State Forest Action Plan and full strategy plan not ingested. PDF p5 narrows applicants to a state forestry or appropriate/equivalent agency, not automatic eligibility for every state department. P4 requires nontribal State Forester sponsorship, draft narrative/budget by December 17, 2026 and final application January 26, 2027. P6 requires 1:1 nonfederal match for NC. P7 restricts land to qualifying rural forest land. P8–9 describes implementation outcomes and excludes basic research and certain construction. These do not establish that a standalone sensor deployment qualifies. Land, allowable costs, DEQ agency route, sponsor and match need confirmation. |
| 357554 | Full official NSF 25-515 HTML solicitation, posted December 5, 2024 | Exact solicitation from Grants.gov's linked publication, not a newer similarly titled program. Specific applicant list is IHEs and qualifying nonprofit/nonacademic organizations; broad NSF boilerplate about K–12 support is not this solicitation's eligibility rule. EDU allows innovative evidence-based cybersecurity education at K–12 and other levels, but ordinary staff training is not automatically sufficient. No verified NC Public Schools strategic plan, PI/institution/partner commitments or referenced PAPPG/policy notices. Target dates are not hard closing dates; notice says proposals accepted anytime. |
| 347707 | Complete body text of official `2023 EV Small Grants NOFO.docx`, attachment 327608 | Notice explicitly closes May 22, 2023 and requires Philippines–US youth/bilateral purpose. A FORECASTED database label does not establish a live 2026 opening. NC cyber staff training alone does not establish this purpose or youth-led applicant route. Generic SF424 forms and current reopening/amendment confirmation absent. No verified agency strategy. |

Raw files and uncapped extracted text are under `pilot/sources/`; `provenance.json` records hashes, final URLs and methods. PDF extraction is text-only without OCR; DOCX body paragraphs include table text but omit images/headers/footers; HTML uses the main element. **Visual layout fidelity has not been verified.** All three have primary notice text, not a certified complete application package or verified amendment chain. Human reviewers must check the originals, source precedence and extraction fidelity. Missing attachments and project facts are part of the packet's disclosed coverage, not invented model facts.

Only DEQ has two source-checked strategic-objective excerpts (OSBM DEQ plan, PDF pp4/6); the full plan is not ingested. Other strategic scores must remain null. Final model results may correctly differ in uncertainty but must not fabricate strategic alignment.

### Fairness and independent review

The original ten cases cover water, broadband, flood resilience, public health and adverse/conditional leads; they remain summary-only in `manifest.json`. Do not pool their results with the new full-primary-notice pilot. This three-case sample is a diagnostic stress test; it contains no established positive control and cannot estimate population precision, recall or false-negative rate.

Use the fixed six-axis rubric in `docs/ai-research-human-rubric.md`. Blank pilot sheets are in `pilot/human-review-template.json`. Two reviewers must independently review the packet before inference, document source passages/material requirements, then adjudicate reference action and A–F findings. Keep original separate reviews and adjudication; the executable gate checks a sealed completed reference file, not the independence of real reviewers. Actions, source locations and all six dimensions are required. Labels remain blank today.

Each model sees identical source documents and stage-one messages. Stage two receives only the same packet plus its own validated stage-one analysis. Model order is seeded/shuffled; no tools/browsing/historical scores/reviewer labels are available to the models. Contract binds script, prompts, schemas, models, manifest, evidence hashes and rubric. Verify raw and extracted document hashes offline before calls. Citation matching and consistency gates are not human ground truth.

Compare critical applicant/purpose errors, false-positive actionable recommendations, omitted material conditions, unsupported assertions, quote validity versus entailment, appropriate abstention, human agreement, completion rate, billed/reasoning tokens, provider elapsed time and cost per **human-accepted** brief. Count failed attempts and unknown timeout usage; do not report only accepted outputs. No Precision@K without a common candidate ranking and adjudicated relevance labels. No accuracy/model-win/time-saving claim exists yet.

## Deployment proposal requiring approval

Resource `grantscope-ai-team07`, East US; existing authenticated read-only inspection verified subscription catalogue, quota and regional capacity, not inference on new deployments. No deployments created by this work.

| Arm | Exact deployment | Model/version | Type and allocation |
|---|---|---|---|
| Existing | `grantscope-gpt4o` | `gpt-4o` / `2024-11-20` | Existing GlobalStandard, 1,688 units; unchanged |
| Proposed isolated | `grantscope-bench-gpt55-v1` | `gpt-5.5` / `2026-04-24` | GlobalStandard, **200 units / 200,000 TPM** |
| Proposed isolated | `grantscope-bench-gpt61sol-v1` | `gpt-6.1-sol` / `2026-09-29` | GlobalStandard, **200 units / 200,000 TPM** |

For new deployments propose `NoAutoUpgrade` if supported; reject a substituted version. No PTU purchase or production routing changes. GlobalStandard does not promise East-US-only processing. 200k TPM accommodates the conservative 120k input + 25k output reservation; earlier 100-unit proposal is superseded. Available quota/capacity is not a deployment guarantee or verified billing credit.

Use Azure `/openai/v1/chat/completions`, strict `response_format=json_schema`, no tools. GPT-4o uses `max_tokens` and temperature 0. Reasoning arms omit temperature and use `max_completion_tokens` plus medium reasoning effort. Responses API would require `text.format`/different usage fields and is not silently interchangeable. Microsoft documents Chat Completions and structured outputs for these reasoning models; a real new-deployment data-plane request remains untested. CLI preflight reads exact model/version/state and captures Entra authentication only in memory; no project secrets or token logging. Never downgrade strict outputs silently if unsupported.

Sources checked November 7: [Azure reasoning parameters and model support](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning), [structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs), [GPT-6.1 Sol API/pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [reasoning token accounting/guidance](https://developers.openai.com/api/docs/guides/reasoning).

## Exact call and spending plan

**At most 18 requests: 3 cases × 3 models × 2 stages, one replicate, no retries.** Failed analysis skips its decision. A malformed/truncated response consumes its reserved call/budget; no repair call. A rerun or model/version/input change needs a new contract and approval. A new output directory is required; no overwrite or automatic resume.

Each request must fit 120,000 conservative input tokens, estimated as UTF-8 payload bytes + 4,096 framing allowance, not a measured tokenizer count. No silent truncation. GPT-4o analysis input+output is bounded to 128,000; stage-two analysis growth is checked again before submission and can refuse an oversized payload. That refusal makes the pair incomplete rather than shortening evidence. Per-model total output ceilings across three cases: GPT-4o 33,000; each reasoning arm 99,000. Aggregate 231,000 billed completion tokens maximum; aggregate conservative input ceiling 2,160,000.

| Model | Reference USD / million uncached input / billed output | Three-case conservative ceiling |
|---|---|---|
| GPT-4o | 2.50 / 10 | $2.13 |
| GPT-5.5 | 5 / 30 | $6.57 |
| GPT-6.1 Sol | 2 / 10 | $2.43 |
| Total | No cache discounts assumed | **$11.13** |

[Azure's GPT-5.5 announcement](https://azure.microsoft.com/en-us/blog/openais-gpt-5-5-in-microsoft-foundry-frontier-intelligence-on-an-enterprise-ready-platform/) publishes 5/30. [OpenAI GPT-4o](https://developers.openai.com/api/docs/models/gpt-4o) and GPT-6.1 Sol pages provide comparison list rates. **These are not verified subscription-specific Azure tariffs for every arm.** Credits, taxes, actual discounts and $500 balance are unverified; earlier billing access returned 403. Approval is blocked until Azure rates are checked and the contract updated if needed.

Illustrative usage scenarios, not forecasts: 5k input/request and 2k total billed output/model/case yields about $0.585; 20k input/request with every output cap consumed yields $5.43. Proposed pilot approval ceiling **$15**, bounded to 18 calls, with $11.13 worst-case reference-rate token reservation. The original ten-case arm now computes 60 calls/$37.10 at revised budgets and would need a separate approval up to $40; do not run it by accident.

Latency is unknown. Allow roughly 10–70 minutes for planning a serial pilot, not a measured SLA. New models start at most once per 61 seconds per deployment; record pacing separately. Timeout is 10 seconds connect / 180 seconds read inactivity, **not a hard wall-clock deadline**. Timeout providers may still bill; missing usage stays unknown. Log started/completed events with fsync, payload/contract hash, raw content, HTTP status, request ID, finish reason, validation reason, full usage including reasoning-token details, elapsed time and undiscounted cost estimate before rejecting output. Never log authorization headers. No automatic paid retry.

## Offline commands and approval gates

```sh
python scripts/benchmark_ai_research.py --manifest docs/ai-research-benchmark/pilot/manifest.json --write-plan docs/ai-research-benchmark/pilot/offline-plan.json
python -m pytest -q
python -m compileall -q services modules scripts tests app.py
git diff --check
```

Default mode has no network/authentication. `pilot/approval-template.json` remains `approved=false`; its current hash binds the pilot. Before a future paid run, explicitly approve the two new deployment configurations, verify account rates/data-plane permissions, complete/seal human reference labels, and approve this exact 18-call/$15 contract. The harness cannot create deployments. Merely approving a JSON file is not a substitute for the user's authorization. This work stops before any such actions.

## Safe integration and November 8 competition checklist

**Search:** preserve the working demo, but NO-GO for claiming its current scores establish application suitability. Do not use 364144 as an unconditional recommendation. Require land/agency route, implementation purpose, sponsorship and match confirmation. Do not present 347707 as actionable; its original notice is expired. Do not imply a general state department can directly apply to 357554. No fresh browser/live Search test was performed in this benchmark preparation.

**Dashboard boundary:** teammate owns `app.py`/`modules/dashboard.py`. Existing [handoff](dashboard-integration-handoff.md) documents shared IDs/evaluation contract. Project-specific cache records are not agency-only evidence. An agency-first Dashboard needs separately scoped agency-only evaluations with verified goals; never relabel a project score or keyword baseline as an agency AI recommendation. No integration GO claim without teammate contract/browser validation.

Minimal later integration: approve an isolated adapter for the new requirement/decision schema; keep old Search untouched until an adversarial regression fixture verifies restrictions and cards. Introduce a new evaluation/cache version including document hashes and agency/project scope; do not reuse legacy judgments as new evidence. Gate actionable cards on verified purpose, applicant route and timing; conditional leads remain explicit. Rollback must select the old deployment/path without clearing caches. Do not attempt this last-minute production migration before human-reviewed pilot evidence.

Before final:

- Freeze production and manually rehearse one Search → recommendation → Save to My Grants flow; record IDs, evidence, restrictions, deadline and saved record. Verify Analyze More/cache reuse with existing telemetry; do not authorize new paid work implicitly.
- Confirm Dashboard ownership and shared API contract with the teammate. Demonstrate agency-first versus project-first honestly; flag any unverified integration.
- For Understand, show staff's three decisions and the actual workflow problem; collect attributable stakeholder feedback if available, not invented user research.
- For Frame, explain why topic similarity and a matched quote are insufficient; use the documented adverse cases and six-axis rubric.
- For Solve, show official intake, exclusions, ID merge/cache behavior and conditional actions, distinguishing implemented production from prepared benchmark architecture.
- For Evaluate/GenAI Field Notes, show frozen packet hashes, preregistered rubric, blind review protocol, failure accounting and actual offline tests. Label the pilot “prepared, not executed.” Report model results only after approval, execution and adjudication.
- For Drive Impact, describe intended decision quality and avoided wasted applications as hypotheses. Actual time savings, staff acceptance, application outcomes and award impact require observed baselines/user studies; none are measured here.

Defer new model rollout, automatic semantic judges, broad PDF crawling, parallel inference, cache migrations and UI restructuring until after the final unless separately approved and validated.

## Validation evidence for this preparation

Full offline suite: **71 passed**, including eight independent-harness tests. A mocked three-case run completed all **18 stage calls and nine decision briefs**, with identical frozen evidence across models, conditional synthetic decisions, usage/reasoning-token details and timing retained, and no authentication token in logs. A separate mocked provider run preserved HTTP-200 rejected schema output/usage and skipped all decision calls after failed analysis. Tests also reject tampered notice/text hashes, early scoring, fabricated quotations, invented strategy and high-score pursuit despite unresolved requirements. These are synthetic provider fixtures, not model or human benchmark results.

Compilation of services/modules/scripts/tests/app, tracked diff checks, and whitespace checks on 26 authored/derived text files passed. The original downloaded NSF HTML retains publisher whitespace and is excluded from style normalization so its raw hash remains faithful. SHA-256 of `app.py`, `modules/dashboard.py`, `services/semantic_matching.py` and the persistent AI recommendation cache exactly match the pre-work snapshots. No browser validation, new Azure deployment, inference call, cache rewrite, commit or push occurred. Public official document downloads were the only new evidence-network activity.


## Hard gates foundation implementation update

See [hard gates and shared contract](hard-gates-foundation.md) for the isolated gate engine, retained-pool mixed research queue, unanchored deep packet builder and competition integration boundary. They are not connected to production. Benchmark-only provider/configuration/ambiguous transport failures now halt the entire run after private diagnostic logging; HTTP-200 model-output validation failures remain no-retry paired outcomes. Output directories/files enforce 0700/0600 and authorization-token redaction. Redirect following is disabled. The new script hash revokes all earlier experiment approvals; current false approval templates/offline plan are regenerated. Human references remain blank and paid calls remain prohibited without subsequent explicit approval.
