# Targeted adaptive Search check

November 7, 2026. Base `b88ede4`, branch `feature/search-reliability`. No commit, push, merge, deployment or teammate-file change.

## Changes

- Existing Sol orchestration is reused in adaptive two-record batches. A failed, unavailable or unsuitable lead is replaced. All IDs and previous outcomes remain in the audit cache.
- Default safeguards: at most 48 summary inspections, 12 deep-research paths, 24 Sol call slots and $18 Sol reference reservations; summary triage is separately bounded to six batches at $0.20 reservation each. Server configuration may change these limits. These ceilings are operational safety controls, not claims of adequate research.
- Stop on pool exhaustion, five qualified results with no remaining high-priority candidates, diminishing returns after six paths/two overlooked audits/two fruitless batches with only low priorities remaining, an operational/provider stop, or a safeguard. A safeguard or incomplete notice must never be called an evaluated no-match.
- Official summaries (purpose, applicant rules, geography, dates, award limits) are sent in efficient GPT-4o batches. Low scores retain uncertainty/audit paths. Summary triage is not eligibility verification. Main results require validated Sol analysis/decision, compatible purpose/applicant findings, current Posted status, acceptable dates and no sourced disqualifying contradiction. Preliminary, failed, expired, forecasted and rejected records are audit-only.
- Timing now precedes the preliminary-state branch, fixing CAMEL K-12 361008 with the reported October 5, 2026 deadline. Refreshed official dates override discovery dates; a Posted/expired contradiction is disclosed. No claim was made that a live amendment for 361008 was inspected in this check.
- Four inputs: agency, specific project, optional funding USD, optional exact earliest closing date (default NY today). Amount/date enter ResearchInput and cache identity. Vague categories stop before inference. Funding shortfalls are explained as possible partial funding, not silently excluded.
- Source-specific quote matching and Stage Two claim IDs are retained. One observed validator false positive was corrected: the phrase “eligible total costs” in sourced cost-share arithmetic is not an applicant-eligibility assertion. Applicant/allowable-activity inference checks and wrong-source/altered-quote tests remain enforced.
- Main page has at most five qualified cards, concise decisions/concern/action, readable source expanders and My Grants Save. Audit data is retained behind a compact coverage section and diagnostic download; no raw JSON widget or operational controls.

## One live check, with fresh discovery and existing Entra authentication

Project: Wildlife Resources Commission coastal NC wetland/riparian restoration, fish passage, monitoring, local-government/nonprofit partners, $300,000, earliest closing date November 7, 2026. Isolated new storage only; no unrelated production cache edits. Test-specific safety cap: six candidate paths, twelve Sol slots, fifteen total HTTP requests, $9 conservative reservations. No paid retry.

109 unique opportunities retained; 24 official summaries triaged in three calls. Six replacement paths were reviewed, rather than two attempts:

| ID | Outcome |
|---|---|
| 362498 — Great Lakes aquatic invasive species | Stage One passed; Stage Two proposed confirmed exclusion without a typed cited disqualifying contradiction. Strict consistency guard rejected it. |
| 364124 — Flood Mitigation Assistance | Source quotations matched, but a sourced 75/25 cost-share calculation triggered the overly broad eligibility-assertion guard. After the targeted fix, all 36 analysis source checks pass in an **offline replay of actual output**. No Stage Two was run or claimed. |
| 364176 — Great Rivers CESU | No identified readable full notice; no Sol request. |
| 364171 — Crash Causal Factors | Overlooked-candidate audit path; packet exceeded conservative input bound before HTTP. It was not recommended. |
| 364177 — Great Plains CESU | No identified readable full notice; no Sol request. |
| 364178 — Californian CESU | No identified readable full notice; no Sol request. |

Six real HTTP calls: three GPT-4o and three Sol. Prompt tokens 131,630; completion tokens 9,935; reference-rate estimate $0.4284205 including recorded cache writes. Conservative HTTP reservations $2.4925. All HTTP responses were 200. Sol latencies: 45.425 and 21.377 seconds for 362498; 53.280 seconds for 364124. No authentication/global provider abort. Raw outputs remain private under `/tmp/grantscope-adaptive-acceptance-20261107`.

The UI displayed **No suitable opportunities verified yet** and explicitly incomplete coverage (103 retained opportunities not fully resolved). It did not manufacture recommendations. Save and widget rerun did not create repeat calls; no Save card was available because nothing qualified, so **real Save/fresh My Grants reload was not exercised in this run**. Existing persistence regression tests pass.

## Acceptance and limitations

162 offline tests passed, compilation and diff checks passed. The one live check demonstrates real discovery, semantic triage, failure replacement and honest non-recommendation, **not successful recommendation acceptance**. Triage still overvalued thematic Great Lakes/CESU opportunities for a coastal NC implementation project. Selection quality, primary-notice coverage and oversized-input handling remain blockers. The cost-share fix has recorded-output replay coverage, not a fresh paid continuation. Do not claim full product completion.

Browser control failed selecting the local Chrome tab with `Cannot read properties of undefined (reading 'timeoutMs')`. Streamlit AppTest is not browser acceptance. Manual check: launch below; verify the four controls, exact amount/date, one button, progress, absence of excluded/preliminary recommendation cards, evidence and Save on a qualifying case; inspect My Grants after reload and compare request-ledger counts. A normal new Search may incur bounded charges.

```sh
GRANTSCOPE_AZURE_CLI=/tmp/grantscope-azure-cli/bin/az python -m streamlit run app.py --server.port 8524
```

Dashboard handoff: appended optional `funding_needed_usd` and `earliest_closing_date` fields in ResearchInput preserve existing callers. Agency-first mode still omits project; unavailable goals stay unavailable. `qualified_records` is project recommendation policy, not a replacement for the Dashboard's agency-only presentation. The new adaptive Search wraps the shared engine; Dashboard must not reuse project-specific cached judgments. No teammate file was edited.

Changed files: modules/search_workflow.py; services/search_workflow.py, research_priority.py, official_evidence.py, research_engine.py; research_foundation/contract.py, protocol.py, citations.py; tests/test_adaptive_search.py, test_dynamic_research.py, test_citation_normalization.py; this report. Pre-existing app.py and untracked Dashboard/data/benchmark files remain untouched.
