# General GrantScope research integration and Dashboard handoff

November 7, 2026. **The earlier sprint connected generic discovery/planning but left dynamic deep research disconnected.** The recorded case was too prominent. This correction connects a generic per-opportunity research service; the recorded example is now off by default and has no role in that service.

## Current stage status

| Stage | Actual implementation | Validation in this task |
|---|---|---|
| Discovery | Existing Grants.gov search plus bounded diversified retrieval; full candidate/duplicate retention | Existing live Search evidence, offline integration tests and real recorded government summaries |
| Preliminary screening | Shared hard-gate engine; only trusted, source-supported reviewed findings can confirm exclusion; missing eligibility remains unknown | High-score exclusion skips model calls, partnership/exception and unknown cases tested |
| GPT-4o prioritization | Optional explicit paid triage action; version-checked existing deployment; score/uncertainty/reason only, never an exclusion or eligibility decision | Mocked provider/service tests; **no new live inference** |
| Queue | User, uncertainty, agency/program diversity, low-ranked audit and priority paths; bounded planning budget; all records retained | Multi-grant, low-priority override, budget and retention tests |
| Per-grant evidence | Dynamic Grants.gov details, published attachments and official linked documents; bounded PDF/DOCX/HTML/text extraction, versions/hashes, missing-document inventory | Actual live intake of 362755 primary NOFO and FAQ; mocked multiple grants/amendments; actual PDF extractor test |
| Requirement analysis | Generic A–F schema, original agency/project/applicant/geography/constraints and official evidence; no GPT-4o judgments | Multiple grants/agencies tested with synthetic Azure responses |
| Decision | Separate second request, source-specific decision claims, scope/consistency checks, final hard gates and independent relevance/viability/timing | Multi-grant service and actual Streamlit interaction tests with injected providers |
| Telemetry/cache | Per-stage usage/raw response/latency/errors; independent private versioned research cache; evidence/context/protocol isolation, partial-stage resume, persisted in-flight markers and prior-version audit | Temporary cache and mocked transport/billing/error tests; production cache untouched |
| Search UI | Explicit consent and per-action opportunity/call/reference-cost budgets, visible research states, conditional/rejected briefs, source links and Save | Actual Streamlit AppTest researches three arbitrary fixture opportunities and saves a result without duplicate calls |
| Dashboard | Same context factory, protocol, queue, gates and research service support agency-first inputs | Agency-first service test passes; **teammate UI not edited or connected** |

**No Azure deployment or inference request was made in this task.** Real model behavior for the new generic schema remains unverified. The prior one-case pilot does not validate arbitrary-case accuracy. Mock responses are explicitly synthetic and are not human labels or performance evidence.

## Normal dynamic Search workflow

Select any listed agency or **Other NC agency / enter profile**, provide the original project and optionally mission/profile, actual applicant, geography and constraints in Advanced filters. Mission/preferences are user context, **not verified strategy**. Search does not fabricate goals; strategic relevance stays unavailable/null unless source-reviewed goal records are supplied through the common API.

Find Matching Grants retains the broad discovery pool and reads existing project-scoped priorities. All candidates remain in the table/export/paginated cards, including low scores, exclusions and unresolved identities. Missing official IDs receive stable internal audit identities; they are not given fabricated Grants.gov detail links or paid research calls. Queue size is a planning limit, not completed coverage.

Optional **GPT-4o research prioritization (paid)** requires its own consent and call/dollar limits. It researches no full application viability: scores only organize the retained queue. Existing successful priorities are reused within the current context/session. The legacy fallback is still available, with separate paid opt-in; its recommendation labels are explicitly not official viability certification.

Optional **Experimental deep research — selected opportunities** requires a separate consent and budget. It uses existing `grantscope-bench-gpt61sol-v1` only. Each selected grant gets its own official intake and independent analysis/decision sequence. It does not use another grant's facts, historical model explanations, priority scores or the recorded example. No provider is instantiated for a default Search.

Current states, with milestone history retained:

- DISCOVERED
- PRELIMINARY_SCREENED
- QUEUED_FOR_RESEARCH
- RESEARCHED_AND_VALIDATED
- RESEARCH_FAILED
- NOT_YET_RESEARCHED

A missing notice, failed quote or unsupported material assertion cannot produce a full research-based recommendation. Partial analysis with no decision budget remains NOT_YET_RESEARCHED. Exclusions remain in the audit pool. Confirmed preliminary exclusions skip models; low priorities do not veto research. Failures do not retry unless a new explicit action selects the retry option. Authentication/configuration/quota, ambiguous transport, unknown billing or unexpected-cost failures stop the entire action.

## Evidence and final decisions

`services/official_evidence.py` accepts a numeric Grants.gov ID, not a fixture filename. It reads current detail fields and attachment inventories, prefers notice/amendment-related names, downloads bounded official HTTPS government documents, extracts text and records source IDs, URLs, retrieval times, raw/text hashes and extraction methods. Redirects must remain on official `.gov`/`.mil` hosts. Default maximum five document attempts, 8 MB each; PDF extraction maximum 250 pages; no silent truncation.

PDF/DOCX/HTML extraction is not certification of document completeness. Scanned PDFs requiring OCR, unsupported spreadsheets, failed downloads, external policy references and document limits remain explicit gaps. Primary-notice identification uses filename/header signals and is not a legal completeness review. Missing primary notice blocks model research. Amendment completeness is **not** inferred from successful downloads. The live check on 362755 extracted 71,729 NOFO characters and 11,207 FAQ characters, with other attachments honestly left unread under a three-attempt test limit; see `integration-evidence/dynamic-official-intake.json`.

The generic protocol enforces A–F structure, source-specific NFC/whitespace quotation checks, evidence for purpose/applicant/timing, agency-goal source attribution, null unavailable strategic scores, explicit uncertainty and cited decision facts. Original project text is separately citable as **user context**, not official funding permission. It cannot satisfy official eligibility/purpose/timing evidence requirements. No fuzzy matching, source rescue, changed dates/amounts/negations/qualifiers or automatic citation repair.

RESEARCHED_AND_VALIDATED means the two stages passed source/structure/consistency checks; it does **not** mean independent human claim entailment or legal eligibility is certified. A model-proposed exclusion is not a confirmed gate by itself. Final viability comes from the shared hard-gate engine:

- ACTIONABLE needs all material gates independently supported and a consistent fully supported decision.
- CONDITIONAL preserves potentially useful opportunities with unresolved route, activity or readiness conditions.
- CONFIRMED_EXCLUSION requires the trusted source/exception/route contract, not a score.
- INSUFFICIENT_EVIDENCE remains distinct from exclusion.

A reasoned “should not apply for this project” judgment remains `reject`; it is not silently converted to a positive research lead, nor automatically labeled confirmed applicant ineligibility. Model proposal and final engine classification are shown separately. The default automated path does not self-attest official requirements as verified; it commonly returns conditional drafts pending review. Trusted programmatic reviewed-gate inputs may supply verification; this sprint does not add a human adjudication UI.

## Budgets, security and caching

Sol uses medium reasoning and strict JSON Schema, analysis cap 25,000 and brief cap 8,000 including internal reasoning, 175,000 conservative input-token bound (UTF-8 payload bytes plus allowance), no tools/temperature, sequential calls and conservative pacing. Oversized evidence is refused, not truncated; long notices may therefore remain incomplete. Maximum budget reservation is $0.6875 analysis + $0.5175 decision = **$1.205 per maximum-budget brief**, using public short-context/cache-write reference rates. Default three-opportunity/$5 action fits those bounds. Subscription-specific tariff/credit balance remains unverified and Azure budgets are not hard account spending stops.

GPT-4o triage is separate: at most 64k conservative input/1k output, $0.17 reserved per call at reference rates; default five calls/$1. Both controls are disabled without explicit consent and a button action. These defaults authorize nothing during automated tests. The exposed credential was not printed, tested or changed; its owner must coordinate rotation before trusted live use.

Provider adapters make no deployment writes, validate expected returned model versions and do not retry/redirect. Raw diagnostics redact the configured key; authorization headers are not stored. Inputs contain original user context and official sources, never prior model judgments. The new cache is `.grantscope/research_v1`, not the production recommendation cache. It uses private directory/file modes, context/mode/applicant/profile/as-of isolation, protocol hashes, re-fetched evidence hashes before paid-call reuse and partial-stage resume. Previously researched nonselected records are labeled historical; refresh before acting. Prior candidate identities and changed-evidence/protocol versions are retained for audit. Save uses the existing grant workspace notes contract without deleting coordinator notes.

## Multi-grant end-to-end evidence

Final suite: **143 tests passed**, plus compilation and diff/whitespace checks. Key tests in `tests/test_dynamic_research.py`:

- Four distinct funding-purpose candidates; a 99-priority source-supported exclusion never invokes a model; three remaining candidates complete independent two-stage mocked research, including a priority-1 candidate.
- Changed agency/project and agency-first mode cannot reuse project-specific judgments. Agency-first has no project score. Source-reviewed strategy cannot be substituted with a grant-topic quote.
- Missing notices and bad citations fail per opportunity, retain candidates, and never manufacture eligibility.
- One-call budget saves analysis without inventing a complete brief; a later explicit action reuses that analysis instead of repeating its paid stage.
- Evidence changes invalidate successful research cache; unchanged evidence/context/protocol reuses it. Cache retains earlier identities and version audit.
- Transport failure stops all remaining paths; provider adapter errors never retry or log the synthetic secret.
- Real recorded Grants.gov summaries for 362755 and 362843 remain accessible when attachments are deliberately unavailable. No fictional successful document review is claimed.
- The actual Streamlit Search function accepts a custom NC agency/profile and broadband project, discovers multiple mocked opportunities, enforces consent, completes three two-stage mocked research paths, renders RESEARCHED_AND_VALIDATED cards and saves one. Save/rerun does not repeat provider calls.
- Real PDF extraction, official-domain/redirect limits, keyword-vs-AI labeling, wrong-source/qualifier/negation/date checks and the existing fallback integration all pass.

No general live-model accuracy, recall, savings, human-review agreement or outcome metric is available. A symmetric labeled live evaluation is still required for those claims. Interrupted requests retain an in-flight marker; a new action stops rather than silently repeating a possibly paid request. An explicit retry requires acknowledging possible charges. The previous actual-browser tool failure remains unresolved; these are Streamlit interaction tests, not a new browser-click validation claim.

## Exact Dashboard integration interface

Dashboard must use the same service, not project-specific caches or a copied scoring engine:

```python
from services.research_engine import (
    request_for_candidate, run_research, ResearchBudget, AzureSolProvider
)

# grants and queue are the same stable-ID candidate/queue contract used by Search.
# profile may carry original mission/applicant/geography/constraints and actual
# source-reviewed VerifiedGoal/Source objects; preferences are not verified goals.
factory = lambda candidate: request_for_candidate(
    agency_name, None, candidate, mode="agency_first", profile=profile
)
# Only in an explicitly authorized paid-action handler:
result = run_research(
    queued_review, factory, AzureSolProvider(config),
    budget=ResearchBudget(max_opportunities=3, max_calls=6, max_usd=5),
    previous=prior_records,
)
```

`queued_review` is the shared queue/pool format: `queue.pool`, `queue.selected`, identity, original records, selection reason and preliminary gate result. Reuse `build_queue`/`evaluate_gates`; do not call a project-first adapter with a blank fake project. Records expose research state/history, coverage/sources, analysis/decision, model-vs-final classification, typed SharedResult serialization, unresolved requirements, next actions and stage telemetry. Store scope is `context_key(factory(candidate))`. Trusted reviewed gates may be passed separately; a model may not manufacture those attestations.

The teammate must wire an agency-first adapter/explicit action, render the same states and evidence, and keep agency-only cache namespaces separate. `app.py` and `modules/dashboard.py` were not edited. No claim of integrated Dashboard UI acceptance is made.

## What is safe before the final and what remains

Generic Search wiring is now present and has passed the required **multi-grant integration test with mocked inference**. This is stronger than the previous discovery-plus-recorded-case path, but it is not live verification of arbitrary grants. Before live use, verify the configured credential/permissions and explicitly approve a small generic paid run; this task intentionally made none. Keep paid controls experimental and off during an unreviewed competition rehearsal. The optional recorded case remains only a regression/example.

Remaining limitations: document availability/format/OCR, extraction fidelity and amendment completeness; strict citation failures; input/timeout bounds; human semantic entailment and application-readiness confirmation; live behavior/cost for the new general schema; Dashboard UI hookup/browser rehearsal. No new resources or deploys are needed for a future bounded run. Preserve the legacy fallback and do not claim every retained or queued grant was deeply researched.

Changed this correction: `modules/search.py`, `modules/search_research.py`, `services/search_foundation.py`, new `services/official_evidence.py`, new `services/research_engine.py`, new `services/research_priority.py`, new `research_foundation/protocol.py`, `research_foundation/contract.py` (integration docstring), `requirements.txt` (pypdf dependency), new `tests/test_dynamic_research.py`, `tests/test_search_foundation.py` (example opt-in), this document and `docs/integration-evidence/dynamic-official-intake.json`. pypdf was installed in the existing Python environment for actual extraction testing. Existing teammate edits and earlier uncommitted benchmark work remain untouched. No commit or push.

Launch: `python -m pip install -r requirements.txt`, then `python -m streamlit run app.py --server.port 8521 --server.headless true`. The local instance from the previous sprint is already running on port 8521; it uses the latest Search module on reload. Navigate Search. Do not enable paid controls merely to inspect discovery, queue, audit or the optional example.
