# GrantScope pre deployment safety gate

Read-only Azure checks and offline pilot review, November 7, 2026. No inference, deployment write, credential rotation, production/cache edit, commit or push. Only this report and two blank independent reviewer worksheets were added.

**Follow-up implementation:** benchmark-only fail-stop/private output safeguards are now implemented and tested. The current contract is in `ai-research-benchmark/pilot/offline-plan.json`; earlier approval hashes are revoked. See [foundation implementation](hard-gates-foundation.md). Production, credentials and deployments remain unchanged.

## Security status and rotation plan

Key validity is **unverified**, not confirmed inactive. Testing the exposed value would transmit it; retrieving Azure's keys would transmit secret material in the opposite direction. Neither was done. Resource metadata returns `disableLocalAuth=null`, which does not establish whether a particular key is valid. Treat the exposed credential as compromised until its slot is regenerated.

The local `.streamlit/secrets.toml` has an Azure key; Search passes `st.secrets` to the evaluator, which reads `AZURE_OPENAI_API_KEY`. This file is ignored and untracked. Neither `AZURE_OPENAI_API_KEY` nor `OPENAI_API_KEY` is present in this inspection shell. No project `.env`/`.env.local` or global `~/.streamlit/secrets.toml` was found. These checks do not inspect another running process's retained secrets or hosted deployment settings. Do not paste any further secrets or screenshots containing keys.

After explicit approval, the owner should privately identify the exposed Key 1/Key 2 slot and all resource consumers. Use the two-key rotation procedure: establish an unexposed alternate slot, coordinating any consumers before regenerating that alternate; securely update approved local/hosted secret stores to the alternate; restart Streamlit so its process reloads secrets; validate service continuity under separately authorized authentication testing; then regenerate the compromised slot promptly. Never regenerate both slots together or assume a key is unused. If continuity validation is unavailable, schedule the transition with the owner rather than claim a zero-outage migration. Endpoint, deployment and API version need not change.

Non-secret verification records: target resource and slot only, successful regeneration timestamp/activity event, owner-confirmed private equality of the new local value with the intended active slot, boolean old/new distinction, restart time, and separately authorized authentication outcome. Do not record key prefixes/suffixes, hashes, clipboard contents or request headers. Cached UI success and the benchmark's Entra authentication do not prove the replacement API key authenticates. No credential test or rotation is authorized by this report.

Reference: [Microsoft two-key rotation](https://learn.microsoft.com/azure/ai-services/rotate-keys).

## Verified deployment metadata versus proposals

Fresh authenticated CLI catalogue confirms:

| Model/version | Resource support | GlobalStandard rate metadata | Fresh East US quota |
|---|---|---|---|
| gpt-5.5 / 2026-04-24 | Chat Completions, Responses, GlobalStandard | 1 request/minute and 1,000 tokens/minute per capacity unit | 0 used / 10,000 units |
| gpt-6.1-sol / 2026-09-29 | Chat Completions, Responses, GlobalStandard | 1 request/minute and 1,000 tokens/minute per capacity unit | 0 used / 10,000 units |

Catalogue capacity maximum is 10,000,000 for both SKUs; no restrictive allowed-values/minimum/step was returned. Proposed 200 is within returned metadata and quota. Previously recorded same-day regional capacity was positive, but capacity is not reserved. Creation may still fail. 200 units maps to **200,000 TPM and 200 RPM proposed per deployment**, not an existing allocation.

Fresh deployment listing shows only `grantscope-gpt4o`, gpt-4o/2024-11-20, GlobalStandard capacity 1688, Succeeded, 1,688,000 TPM, upgrade `OnceNewDefaultVersionAvailable`. Preserve it unchanged. New proposals:

- `grantscope-bench-gpt55-v1`: OpenAI gpt-5.5 version 2026-04-24, GlobalStandard capacity 200.
- `grantscope-bench-gpt61sol-v1`: OpenAI gpt-6.1-sol version 2026-09-29, GlobalStandard capacity 200.
- Both propose `versionUpgradeOption=NoAutoUpgrade`. Microsoft documents the enum, but catalogue metadata does not prove model-specific acceptance; verify the resulting property after an approved creation. Do not silently substitute a version or upgrade policy. NoAutoUpgrade stops at retirement; it does not extend model support. GlobalStandard is not East-US-only processing.

[Upgrade policy](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/working-with-models), [retirement semantics](https://learn.microsoft.com/azure/foundry/openai/concepts/model-retirements).

Use `/openai/v1/chat/completions` with strict `response_format=json_schema`. Reasoning models omit temperature and use `max_completion_tokens` with medium reasoning effort; internal reasoning counts against output caps and billing. GPT-4o uses temperature 0 and `max_tokens`. Two stages are two independent requests, not an API feature. No tools are required. Documentation supports these API features; new deployments and this exact request/schema combination have **not** passed live data-plane testing. An Azure CLI login is not proof of inference RBAC access. First actual pilot calls must count toward 18; no extra smoke calls.

[Azure reasoning/API support](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning), [strict structured output](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs).

## Pricing and spending

Public Microsoft sources publish Global Standard short-context GPT-5.5 input/output 5/30 USD per million tokens and GPT-6.1 Sol 2/10. They corroborate the pilot reference rates, not the subscription's effective invoice rate. The interactive Azure pricing page could not be retrieved. GPT-4o 2.5/10 remains the unverified Azure reference assumption. Account model metadata returns `cost=null`; billing access was previously 403, and remaining credit balance is unverified. Do not set `azure_prices_verified=true` based solely on these announcements.

Sources: [GPT-5.5 Microsoft price table](https://azure.microsoft.com/en-us/blog/openais-gpt-5-5-in-microsoft-foundry-frontier-intelligence-on-an-enterprise-ready-platform/), [GPT-6.1 Sol Microsoft price table](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-gpt-6-1-sol-in-microsoft-foundry-advanced-intelligence-optimized-for/4560811).

At those rates the 18-call conservative token reservation is $11.13; proposed operator ceiling $15. This is a bounded **pilot estimate**, not a resource-wide spending ceiling or guarantee against unauthorized key use. Azure budgets are alerts, not a hard stop for OpenAI; 200k TPM is a throughput cap, not a dollar cap. Subscription credit spending-limit status was not established. No spending control was created/changed. [Azure cost controls](https://learn.microsoft.com/azure/ai-services/openai/how-to/manage-costs).

## Frozen quality criteria and reviewer separation

Rechecked all raw/text document hashes via offline harness. Three cases have full primary-notice text with explicit gaps; amendments were not certified reviewed. Forest Service land, agency route, match and sponsorship requirements; NSF exclusive applicant list versus broad boilerplate; Emerging Voices' expired 2023 window and bilateral youth purpose are independently reviewable source facts, not preassigned model labels. No entire application package or agency strategy coverage claim is made.

Packet construction whitelists official fields, source documents, scenario and verified goal excerpts. Historical scores, selection/history notes, reference actions and reviewer worksheets do not enter messages. All models receive the same phase-one messages; phase two receives the same packet plus only that model's validated analysis. Six dimensions, claim kinds, counterevidence and missing requirements remain separate. Exact quotation checks do not prove claim entailment; humans must assess support and omissions.

Two separate blank worksheets now exist: `pilot/independent-reviewer-1.json` and `pilot/independent-reviewer-2.json`. Each records A–F facts, inferences, unknowns, contradictions, source locations and support findings, plus independent answers to the three staff questions. Reviewers work independently before model outputs; retain both originals, adjudicate in the existing human-review template, then seal its hash. No reference labels have been filled. Frozen rubric and pilot contract remain unchanged:

`a721d5ceac0263d6369e2bea573e39997a698d42b4ffa66021e999d973329f24`

The executable gate checks completed fields, not real reviewer independence or semantic correctness. It also does not automatically force every disclosed packet gap into the model's missing-requirement list. Human material-omission review is essential.

## Exact proposed pilot execution

Concurrency one. Seed 20261107 fixes these pairs; execute requirement analysis then decision only if analysis validates:

1. 357554 / GPT-5.5 — potential calls 1–2.
2. 357554 / GPT-4o — 3–4.
3. 357554 / GPT-6.1 Sol — 5–6.
4. 364144 / GPT-6.1 Sol — 7–8.
5. 364144 / GPT-5.5 — 9–10.
6. 364144 / GPT-4o — 11–12.
7. 347707 / GPT-6.1 Sol — 13–14.
8. 347707 / GPT-5.5 — 15–16.
9. 347707 / GPT-4o — 17–18.

Numbers compress when a decision is skipped; no replacement requests. Maximum nine analyses/nine decisions. First full-notice request per model is its compatibility test, not an additional call.

Budgets: GPT-4o 8,000 analysis/3,000 decision; each reasoning model 25,000/8,000 combined reasoning+visible output. Per-request conservative input limit 120,000 (UTF-8 payload bytes +4096 allowance), no truncation. Maximum aggregate input 2,160,000 and output 231,000 tokens. Sequential new-model starts at least 61 seconds apart per model. Timeouts 10 seconds connect/180 seconds read inactivity, not a hard total deadline. Latency is unmeasured; reserve tonight's time conservatively and stop before interfering with the demo rehearsal.

Before each request reserve worst-case token cost; started events make crashes spent/unknown. Preserve usage including reasoning details, raw provider body/content, request ID, HTTP status, finish reason, elapsed time, pacing wait and validation reason, including rejected responses. Unknown timeout usage remains unknown. No retry, JSON repair call, budget escalation or automatic resume. Use a fresh private output directory under `umask 077`, outside Git/production caches; restrict directory to owner, never store authorization headers/tokens, CLI stdout or secrets. Input fixtures contain only official documents and hypothetical project text. The hardened harness now enforces 0700 output directories and 0600 artifact files; verify them before sharing artifacts. Inspect/redact outputs before sharing.

Current global preflight aborts: missing/mismatched approval/contract, incomplete sealed references, evidence hash failure, wrong model/version/state, budget/call cap. Oversized stage-two payload makes its pair incomplete without another request. A JSON/schema/quote/finish/refusal/transport/HTTP failure is recorded and skips the remainder of that pair, **the original harness continued other pairs; the follow-up implementation now halts the entire run for provider/configuration and ambiguous transport failures**.

**Execution safety update:** the benchmark-only fail-stop change has now been implemented; require independent review before paid approval so an authentication, unsupported API/schema configuration, deployment-not-found, quota/rate-limit, server/network/timeout or unknown-billing failure halts the entire run after logging. Do not silently retry. Keep model-content/schema/quote/consistency failures as benchmark outcomes with no phase-two call; continue other pairs only under the approved policy. The follow-up implementation includes offline tests and a new contract; renewed approval remains required. Thus the current contract is a reviewed preparation baseline, not authorization to execute unchanged.

## Approval actions and competition decision

**GO for offline preparation tonight; NO-GO for inference now.** A supervised isolated pilot is reasonable tonight only after the gates below close. Production model rollout remains NO-GO before the final.

1. Security owner approves and performs a coordinated two-key rotation and approved secret-store update/restart, with non-secret verification. No rotation/configuration permission is implied for this assistant.
2. Two humans complete independent reference worksheets and adjudication. Confirm evidence extraction limitations and missing amendments explicitly.
3. Billing owner verifies effective model rates and accepts the $15 pilot envelope; do not assume the $500 credit is available.
4. Review the completed benchmark-only fail-stop/output-permission hardening, offline validation and replacement contract; no production edits.
5. Separately approve creation of exactly the two named/versioned GlobalStandard/200-unit/NoAutoUpgrade deployments. Verify resulting allocation/policy and permissions without inference. Reject silent substitutions.
6. Explicitly approve at most 18 total calls/$15 against the new sealed contract/references; no extra smoke calls, retries, resume or production routing changes.

Evaluate/GenAI Field Notes may honestly use the frozen official evidence, prior observed validator failures, documented false-positive risks, preregistered six-axis rubric, packet hashes, offline tests and preparation limitations. They cannot yet claim model superiority, measured accuracy/latency/cost, human agreement, time savings or application impact. This task reran all 71 offline tests successfully, including eight harness tests; diff and new-document whitespace checks passed. No new browser/live UI validation was performed.

Search demo risks remain purpose/eligibility overstatement, incomplete official packages, timing/status uncertainty and credential transition. Do not demonstrate 364144 as unconditional, 357554 as a confirmed direct state-department route, or 347707 as open. Dashboard has not passed joint browser acceptance; project-scoped evaluations are not agency-only strategic matches. Teammate files remain untouched. Rehearse Search → card → Save and the teammate's integrated route using existing permitted data before claiming integrated readiness. Keep new deployments, schema adapters, cache migrations and model routing outside production until separately approved and tested.
