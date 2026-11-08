# Product recovery and acceptance — November 7, 2026

Baseline: `2f54c20f120a86c60fb20d82d1ae925153654d3c`, branch `feature/search-reliability`. No commit/push, deployment change, credential rotation, or legacy recommendation-cache update was made. App/Dashboard hashes match the baseline protected snapshots. No product-completion claim.

## Delivered behavior and actual root causes

1. **Stage Two regenerated quotations.** In the preceding private live artifacts, WaterSMART 362755 failed 5 of 17 decision citation checks; NOAA 363758 failed 8 of 18. Quotations joined discontinuous passages with ellipses, changed text, or placed quoted metadata in uncited uncertainty. Their Stage One analyses passed 34 and 35 source checks. The validator correctly rejected Stage Two; this was not an Azure HTTP failure.
2. **Repaired evidence references.** Stage Two now receives a deterministic `A-1`…`F-N`/`COUNTER-N` registry from its already-validated analysis. Its `evidence_claim_ids` must exist, be unique and resolve against the same source packet. Reused claims are revalidated. Genuinely new `decision_claims` still require independent, contiguous source-specific quotations. No fuzzy matching, cross-source rescue, deleted qualifiers, or relaxed normalization was added. Claim IDs and original source links are visible in the evidence expander. This is structural/source validation, not independent human entailment adjudication.
3. **Separate paid actions made normal Search incomplete.** The default entry now takes agency/project/optional applicant/geography and one Find Matching Grants action. It performs diversified discovery, bounded official-summary inspection, shortlist selection, official document intake, Sol analysis/decision, validation, gates and presentation. It preserves the full discovered pool. Internal default is two opportunities/four Sol call slots/$2.42 conservative reservation. Server configuration may set one to three initial opportunities, capped at $4. Cached GPT-4o priorities may influence selection but cannot exclude candidates; fresh GPT-4o triage is not automatically invoked. Sol supplies researched relevance, separately from deterministic discovery aids.
4. **Queue order was the display order.** Main ranking now uses researched disposition and relevance, with preliminary deterministic fit used only to order unresearched leads. The queue's selected flag is absent from the ranking key. Rejected/closed/forecasted opportunities cannot become promising recommendations through a high relevance score. All other candidates remain in a paginated All Opportunities section and audit download. Preliminary candidates have no invented AI score.
5. **Long-sentence retrieval and generic overlap harmed shortlist quality.** Query generation now starts with concise topic terms, bounded to eight diversified queries; IDs remain deduplicated in the canonical pool. Shortlist selection reads up to twelve topic-led official summaries and requires meaningful fit for a diversity override. Later preflight showed that this remains a heuristic, not a verified suitability filter. Final term-selection refinements were checked with real public summaries but were not followed by another paid run; do not claim selection accuracy.
6. **Fixed 61-second waits were unconditional.** Provider pacing now accounts for the configured deployment TPM, observed token usage and request-limit reset information. Five live HTTP requests incurred zero artificial pacing seconds. Requests remain serial; 429/auth/configuration/ambiguous transport/unexpected billing stop the action without retry. This is a local limiter, not a subscription-wide distributed limiter.
7. **Research fields were discarded on Save.** LocalGrantStore's whitelist accepted notes but discarded project/status/depth fields. It now preserves those explicit fields, while retaining coordinator decisions and merged notes. The actual NOAA record was rendered, saved, loaded through a fresh My Grants AppTest, marked Maybe, and reloaded from a new store instance. No model was called for these checks.
8. **Agency-first queue construction required a project.** `build_project_review(..., mode='agency_first')` now builds the same contract without a fake project, ignores cached project scores and uses only supplied verified goals for agency-only topic aids. Shared agency-first orchestration has offline coverage. Dashboard itself is unchanged and still needs teammate integration.

## Live evidence — not mocked model outputs

The actual one-click Streamlit Search was exercised with fresh Grants.gov retrieval and the existing Entra-authenticated Sol deployment. Raw response ledgers, snapshots and evidence remain in private `/tmp/grantscope-recovery-acceptance-20261107` (not repository contents). No historical GPT-4o judgment was sent to Sol; no frozen 364144 case was loaded.

| Scenario / real opportunity | Current listed status / deadline | Real outcome | Citations | Model latency / estimated cost |
|---|---|---|---|---|
| DEQ rural watershed restoration — **361418**, Great Lakes Restoration Initiative: Community Forest and Open Space Conservation Program | Posted / Dec 8, 2026 | Two stages validated; project 15/100; **reject this project**. Engine viability remains conditional pending independent gate attestation; it is displayed as unsuitable, not actionable. | 28 analysis + 24 referenced decision claims passed | 43.625 + 18.205 sec; $0.101132 |
| Wildlife Resources Commission coastal habitat restoration — **363758**, DARRP Restoration Implementation Grants (2026) | Posted / Nov 18, 2026 | Two stages validated; project 85/100; **conditional route-verification lead**, not a direct state application recommendation. Eligibility and timing need review; strategy unavailable. | 29 analysis + 27 referenced decision claims passed | 38.953 + 21.065 sec; $0.168362 |

Official sources dynamically retrieved:

- [361418 official listing](https://www.grants.gov/search-results-detail/361418) and [GLRI notice DOCX, attachment 353864](https://apply07.grants.gov/grantsws/rest/opportunity/att/download/353864). The notice funds fee-simple forestland acquisition and requires at least 75% of a tract in the specified Wisconsin/Michigan pilot area. This conflicts with the supplied NC project. Applicant categories and match/acquisition readiness are separate concerns.
- [363758 official listing](https://www.grants.gov/search-results-detail/363758) and [NOAA notice PDF, attachment 354907](https://apply07.grants.gov/grantsws/rest/opportunity/att/download/354907). Purpose concerns marine/coastal restoration linked to oil spills, hazardous releases or other natural-resource damage. It explicitly excludes federal/state/tribal government applications; local-government and other eligible-lead conditions require review. Collaboration language does **not** establish an authorized funded Commission role. Registration readiness and the November 18 deadline remain material. The practical next action is to verify an eligible lead and permissible participation with program/grants staff; do not prepare a direct state application.

Both notices were ingested with hashes and source IDs. Neither amendment chain nor incorporated-policy completeness was independently certified. Strategic scores are null because no verified goals were supplied. No accuracy, recall, Precision@K, legal eligibility certification, or staff-time savings were measured.

### Other observed paths and remaining failures

- The DEQ run retained **157** distinct opportunities; the Wildlife run retained **109**. Discovery does not imply suitability.
- A first DEQ shortlist included 357524, a youth mental-health program, with no readable primary notice: **zero Azure calls**. This and other irrelevant title-led selections motivated bounded official-summary review.
- A subsequent DEQ shortlist selected **337086** (Public Health Crisis Response): several historical notice versions made the packet exceed the conservative 175,000-byte input bound. The provider rejected it **before HTTP**; no evidence was silently truncated. This remains an input-coverage/performance limitation, and was also a poor project selection.
- **359155** (Mind and Body Interventions): official linked HTML yielded no identified full notice; **zero Azure calls**. It remains incomplete, not rejected for eligibility.
- **364144** was automatically discovered and selected in the Wildlife run, dynamically researched from fresh sources, not the frozen demo. Its new Stage One failed one quotation check: the cited PDF has `science-` followed by a line break before `based`; the model wrote `science-based` and attributed text resembling the summary to the PDF. No punctuation/source repair was performed; **Stage Two was not called**. This record is not counted toward the two successful nonfixture cases. The failure proves source guards still operate; it does not establish reliable completion for every grant.
- Final topic-term/diversity refinements still selected WaterSMART 362394 and 364144 in a public-summary preflight. Those are research candidates, not verified NC matches. Fresh-candidate selection quality remains a release risk. No further paid retry was made.

### Reconciled telemetry

Six provider attempts/reservations, **five actual Azure HTTP calls**, all HTTP 200; one pre-HTTP input-bound rejection. Total prompt tokens **90,230**, completion tokens **12,700**, total **102,930**; recorded reasoning tokens **459**, cache-write tokens **90,215**, cached-read tokens **0**. Total model HTTP latency **172.092 seconds**, artificial pacing **0 seconds**. End-to-end discovery/extraction wall time was not separately recorded.

Conservative reservation **$3.785**, actual reference-rate estimate **$0.3525675** including reported cache writes. Reference rates: $2/M uncached input, $0.10/M cache reads, $2.50/M cache writes, $10/M output; cache writes replace ordinary input for their reported subset. This is an estimate, not verified subscription billing. No additional paid requests were made after the ledger completed. A local acceptance-harness serializer failed after the first successful case; continuation repaired only artifact serialization and restored the existing call ledger and cache. It did not reset the cap or repeat that successful research.

## User-experience acceptance and blockers

- Actual Streamlit AppTest: arbitrary agency/project, one click, multiple discovered records, real Sol outcomes, readable states, evidence, Save and widget reruns. Both scenario checks reported no repeated calls after Save/rerun. The real NOAA card and My Grants reload were subsequently checked against persisted live output, without a model provider.
- Offline regression: **152 tests pass**; compilation and diff whitespace checks pass. These totals include existing local official-evidence fixture packets excluded from the checkpoint; full clean-checkout reproducibility remains unresolved.
- Local Streamlit review server launched on **8523**, using the unchanged app with isolated test storage and a provider that prohibits additional inference. App entry/imports are also exercised in offline AppTest. This is not browser acceptance.
- **Browser acceptance NOT PASSED.** CUA could inventory Chrome, but both creating a review tab and selecting the existing localhost tab failed with `Cannot read properties of undefined (reading 'timeoutMs')`. No visual/click browser success is claimed.
- Final shortlist and display refinements after the live calls passed offline/public-summary checks; the exact final selection path has not completed a fresh paid acceptance run. Source-specific model failures and incomplete evidence still occur.

**Disposition:** repaired shared contract and known-case source-backed rendering are demonstrated. **NO-GO for claiming full final product/browser acceptance or reliable arbitrary-project recommendations.** A qualified demonstration of the validated negative case and NOAA conditional lead is supportable if its research time, source gaps and direct-applicant restriction are clearly disclosed. Dashboard + Search integration is not accepted until the teammate wires and tests agency-first behavior.

## Launch and manual browser gate

Normal launch (existing CLI login; no key handling):

```sh
GRANTSCOPE_AZURE_CLI=/tmp/grantscope-azure-cli/bin/az python -m streamlit run app.py --server.port 8524 --server.headless true
```

Clicking Find Matching Grants authorizes the bounded normal workflow and may bill. Rendering, Save and widget reruns do not. The legacy fallback remains recoverable through server-only `GRANTSCOPE_LEGACY_SEARCH=1` on a separate port; it is not a default staff control. Do not replace a teammate's running server.

Manual browser gate: open `http://localhost:8523` for the isolated, no-additional-inference review server; select Search; inspect the simplified fields; use the exact agency/project strings in the private scenario artifacts to review matching-context cached output. This server may show explicit blocked/incomplete states for newly selected, uncached grants. Inspect NOAA's source-backed conditional result, open its evidence, confirm the state-government exclusion and date, Save, navigate to My Grants, change to Maybe, reload and confirm persistence. Record screenshots of input, results, evidence, and My Grants plus the private request ledger before/after. Do not treat this cache replay as fresh inference. To accept a fresh end-to-end browser run, use the normal server with a newly agreed bounded test ledger and inspect the resulting real provider telemetry. Do not make uncontrolled repeat searches.

Dashboard teammate: see `dashboard-recovery-handoff.md`. Remaining priorities: P0 browser validation and final shortlist suitability; P0 honest handling of source/input failures; P1 independent human claim/route review, amendment coverage, clean-checkout fixtures and Dashboard wiring; P2 distributed rate control and richer retrieval/evidence coverage. No extra paid trial is proposed before the current evidence is reviewed.

## Exact files changed for this recovery

- `modules/search.py`, new `modules/search_workflow.py`
- `research_foundation/protocol.py`
- `services/discovery.py`, `services/official_evidence.py`, `services/research_engine.py`, `services/search_foundation.py`, new `services/search_workflow.py`, `services/grant_store.py`
- `tests/test_dynamic_research.py`, `tests/test_search_foundation.py`, `tests/test_search_integration.py`, new `tests/test_search_recovery.py`
- new `scripts/recover_search_acceptance.py`
- new `docs/product-recovery-acceptance.md`, `docs/dashboard-recovery-handoff.md`

Pre-existing local `app.py` modifications, untracked `modules/dashboard.py`, recorded-case data, benchmark packets and generated integration evidence were left intact. No files were staged or committed in this recovery.
