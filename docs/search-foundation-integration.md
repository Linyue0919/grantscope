# Search competition integration handoff

> Current architecture update: [Generic research integration](general-research-integration.md) supersedes the earlier discovery-plus-recorded-case scope below. The example is now optional/off by default; dynamic per-grant research is connected and tested with mocked inference.

November 7, 2026. The default Search now connects the gate engine, mixed research queue and shared decision contract. It performs public Grants.gov discovery and reads existing project-scoped evaluations without making new AI calls. Live Sol research is **not** connected; the actual previously validated case is the experimental research demonstration.

## What is integrated

- `modules/search.py` adds a default evidence-first view and keeps the existing view available by unchecking **Evidence-first review (no new AI calls)**. New GPT-4o calls in fallback require a separate explicit opt-in. The assistant made no paid calls in this sprint.
- `services/search_foundation.py` keeps 100 seed results plus bounded diversified queries, retains partial results on diversified-query failures and merges cached IDs outside the seeds. Duplicate variants survive into the queue. This remains bounded retrieval, not exhaustive federal coverage.
- Every retained candidate gets preliminary hard-gate results and a typed `SharedResult`. Missing attested official requirements remain INSUFFICIENT_EVIDENCE. Legacy eligibility/model labels are review signals, not invented human attestations. The engine accepts confirmed exclusions only with reviewed source support and route/exception review. No score can override those gates.
- Cached project GPT-4o scores may prioritize. Without those, an explicitly labeled keyword aid may organize the queue; it is never displayed as an AI recommendation. No minimum score removes a candidate. Queued candidates appear first; the entire pool remains in the table, CSV and paginated cards.
- User-selected IDs, uncertainty, diversity, low-ranked recall audit and priority provide queue entry paths. Budget and availability constrain coverage; queue selection is not completed research. Default Balanced plans 30, Quick 10, Deep 50, Custom 5–100. The UI explicitly reports zero newly deep-researched records.
- Original input packets are built separately from cached scores using the shared contract. Actual proposed activities, applicant category, sites and strategy verification remain unknown unless supplied/verified; they are not extracted as confirmed facts from free text. The current adapter does not perform automated full-NOFO adjudication.
- Cards separately show Can Apply, Should Apply and Act in Time, the state, unresolved gates, available official applicant notes and next verification action. Confirmed-excluded records remain in the retained pool/audit rather than being deleted.
- Save to My Grants uses the existing store contract. Preliminary status and original project are preserved in notes; prior coordinator notes are retained. The legacy store has no typed research-result fields or multi-project key: agency/opportunity remains its identity. Structured result persistence is deferred.

## Previously researched demonstration

`data/researched_cases/364144-sol.json` contains only the actual accepted Sol decision, its revalidated original analysis, original project/agency, official source packet and provenance. `manifest.json` binds its SHA-256. Loading verifies bundle integrity and source-specific quotations with the shared conservative validator. No historical failure is relabeled and no model answer is invented.

The expander is separate from the submitted project, labels the original DEQ scope, research timestamp, experimental provider and lack of independent human adjudication, and never treats the scores as a judgment on a different project. It displays CONDITIONAL, project/strategy 45/75, DEQ route uncertainty, required State Forester sponsorship, qualifying rural forest land, 1:1 nonfederal match, next actions and source-specific quotes/links.

Dates were verified against the actual official NOFO: December 17, **2026** draft narrative/budget deadline; January 26, **2027**, 11:59 p.m. Eastern final deadline (PDF pp4,14). Applicant p5, match p6, land p7, outcomes p8 and equipment p10 provide the other context. Missing amendments/forms remain disclosed.

The UI does not claim current opening from frozen research. **Check current official status (no AI call)** fetches Grants.gov and shows listed status/date and check time, without asserting readiness. A separate live check during this sprint reported POSTED / 2027-01-26 at 2026-11-08 00:00:48 UTC (November 7 Eastern). That is point-in-time evidence, not an evergreen opening claim. Status-check failures explicitly leave availability unverified.

The researched case can be saved under its original DEQ/project scope; it is not silently merged into arbitrary projects. No live Sol controls or credentials were added.

## Validation evidence and limits

- **121 offline tests passed**, including real Streamlit AppTest interaction tests for default Search, fallback Search, retained low-score and outside-seed candidates, source-backed high-score exclusion, unknown eligibility, no new AI/cache writes, duplicate retention, truthful keyword labels, source attribution, conditional case/date rendering and Save/My Grants flow. Compilation and diff checks passed.
- The existing full fallback pipeline test still exercises mocked Grants.gov/Azure, resume/cache reuse, thresholds, recommendation cards, Save and My Grants navigation. It explicitly selects fallback and authorizes its mocked evaluator.
- A real Streamlit Search AppTest executed nine live public Grants.gov queries: counts 100 plus eight ×25, deduplicated to **168 retained candidates**, **30 queued**, **zero new AI evaluations**, no UI exceptions. Azure evaluation and production AI-cache writes were explicitly blocked; saves used temporary storage. This proves actual public retrieval through Search, not general match quality. Some returned metadata is old or poorly targeted; retaining it is not endorsing suitability. The final ordering/label refinements also passed offline UI tests.
- `app.py` starts on local port 8521. Actual Chrome control could not be completed: browser creation/tab calls failed with an undefined `timeoutMs` error. Do not call this browser validation. Record is in `integration-evidence/search-foundation-live.json`.
- SHA-256 confirms `app.py`, `modules/dashboard.py`, the production semantic service and persistent AI recommendation cache unchanged from the pre-sprint snapshots. The preexisting app.py modification and untracked Dashboard file remain the teammate's work. No deployment/secret modification, paid inference, commit, push or deployment occurred.

## Launch and manual acceptance

From the repository root with the existing Python environment:

```sh
python -m streamlit run app.py --server.port 8521 --server.headless true
```

An instance is already running at **http://localhost:8521**. Navigate **Search**. Leave evidence-first enabled. Choose the agency and enter a project, then **Find Matching Grants**. Inspect retained/queued counts, page through low-priority records, inspect gate unknowns and save a candidate. Confirm it appears in **My Grants** with preliminary context. Test stores and recommendation caches are distinct; a manual Save intentionally updates only the existing grant workspace.

Open the previously researched DEQ expander and verify CONDITIONAL/45/75, original scope, dates and official quotations. Use the public status-check button if desired. Save the case and confirm the DEQ record/context. Never enable paid GPT-4o merely to test this path.

For fallback, uncheck evidence-first. Leave paid evaluation unchecked to use retrieval/existing caches without new inference. Legacy “Recommended” is explicitly a relevance label, not verified viability. Filters affect fallback only; the advanced panel says so. Returning to Search may reset widgets to the safer default view; select fallback again if needed. Analyze More is disabled unless paid evaluation is explicitly enabled.

Collect browser evidence manually: screenshot of controls, candidate counts and three-question card, conditional case with checked status/date timestamp, citation source/link, saved My Grants record and browser console/server errors if any. Do not capture secrets or the Azure keys page.

## Dashboard teammate boundary

No changes were made to `app.py` or `modules/dashboard.py`. Do not import a project-scoped precomputed decision as an agency-only recommendation.

Reuse `research_foundation.hard_gates.evaluate_gates`, `research_foundation.contract.SharedResult` and `research_foundation.research_queue.build_queue`; the current `build_project_review` adapter requires project context. Agency-first Dashboard needs `ResearchInput(mode='agency_first', project_description=None, proposed_activities=())` and separately scoped verified goals/research, not an empty-string call into the project adapter. Strategy must stay unavailable/null when unverified. Keyword scores remain labeled baseline, never AI matches.

Render the same viability states, evidence completeness, unresolved conditions and next actions. SharedResult's consistency checks do not prove entailment. Agree on persistent structured-result and multi-project Save semantics after the final; do not duplicate eligibility logic in UI code. Separate deployment/cache-version/inference approval is still needed before connecting any live deep provider. No integrated Dashboard accuracy/browser acceptance claim is made here.

## Remaining risks and demo recommendation

**GO for a bounded, honestly narrated Search discovery + uncertainty + previously researched case demo**, subject to the manual browser rehearsal above. **NO-GO for claiming fully automated application suitability, live deep research or validated integrated Dashboard/Search matching.** Most discovery records remain insufficient evidence by design. Official-package intake, amendment verification, automatic rule extraction, human claim entailment, broad retrieval coverage and applicant readiness are not solved by this sprint.

Protect the current working path. Do not change models or migrate caches before the final. The exposed key remains an owner-coordinated rotation blocker; it was not tested or changed. Internet/API failures can limit discovery; the precomputed case remains available offline with current status explicitly unknown. No accuracy, recall, savings, user-study or model-superiority metrics are claimed.

Changed files this sprint: `modules/search.py`, new `modules/search_research.py`, new `services/search_foundation.py`, `data/researched_cases/364144-sol.json`, `data/researched_cases/manifest.json`, new `tests/test_search_foundation.py`, updated `tests/test_search_integration.py`, this document and `docs/integration-evidence/search-foundation-live.json`. Earlier benchmark/foundation work remains uncommitted and was not bundled into any commit.
