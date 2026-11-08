# Search integration — defect and verification log (2026-11-08)

Scope: `fix/demo-search-precision` only. Do not change Dashboard's original matching, eligibility, evidence validator, or Codex's active worktree. Statuses below distinguish observed behavior from hypotheses.

| ID | Severity | Evidence / reproduction | Root cause or hypothesis | Status / next verification |
|---|---|---|---|---|
| S-01 | P0 | Rural NC opioid prevention project surfaced prison-focused RSAT and juvenile-justice treatment programs as Potential Matches. | Search activity matching treated shared treatment vocabulary as sufficient; target population was not checked. | **Mitigation committed**: official-summary population mismatch hold; new synthetic regression test. Not yet run or verified against live Grants.gov. |
| S-02 | P0 | Search cards displayed `Project Fit: Not AI assessed or official evidence was insufficient`. | Search reused Dashboard's **strategic-goal** GPT-4o evaluator but labeled the result as project fit. Missing result may be a shortlist limit, missing profile/config, model error, or rejected evidence; screenshots alone cannot distinguish. | **UI fix committed**: strategic alignment label, per-card status, batch accepted/rejected/error counts. Azure runtime verification pending. |
| S-03 | P1 | Clicking Search Deep Research on local port 8511 produced `Deep research could not start safely`. | Search environment/provider/store configuration unknown; Codex separately reported Sol progress in Azure. | **UI mitigation committed**: hide Search Deep Research by default behind `GRANTSCOPE_ENABLE_SEARCH_DEEP_RESEARCH=1`; preserve backend and explicit-action tests. Not a claim that Sol itself is broken. |
| S-04 | P1 | Two Project Fit headings appeared in each Search result. | Official keyword/activity evidence and Dashboard strategic AI were conflated. | **UI labels corrected**, runtime verification pending. |
| S-05 | P1 | Some relevant records with unknown closing dates were omitted from open recommendations. | Unknown status/deadline cannot be certified open. | Prior Copilot branch added Needs Verification and Forecasted groups; preserve these distinctions. |
| S-06 | P1 | Forecasted ALACRITY opportunity 361521 showed estimated post/due dates on Grants.gov. | Estimated forecast dates were previously not separated from confirmed open deadlines. | Prior Copilot branch added Forecasted group; verify after integration. |
| S-07 | P1 | Department of Public Schools mental-health Search returned no AI assessment. | **Confirmed from repository:** Department of Public Schools is in `unprofiled_agencies`, while Dashboard strategic AI requires a verified agency goals profile. Thus this agency cannot receive the same strategic-goal AI assessment. This does not establish project-specific irrelevance. | Added coverage diagnostic; do not invent strategic goals. A separate project-specific evaluator would need its own design and evidence contract. |
| S-08 | P1 | Project-fit candidate selection may miss good opportunities. | Confirmed code: `run_matching` loads at most 80 official details and evaluates at most 12 fit candidates; title/activity ranking happens before full details, and Search's final potential filter is outside the shared engine. | Audit recall using a known-open, officially eligible grant and compare pre-/post-shortlist stages. Do not claim exhaustive search. |
| S-09 | P1 | Project-specific GPT-4o assessment is not implemented by the Dashboard evaluator. | Confirmed code: `services.ai_matching.SYSTEM_PROMPT` explicitly evaluates **verified agency strategic goals**, not the user's project text. Search must not present it as a project-specific AI suitability score. | Preserve Dashboard as-is; keep official activity screening clearly labeled until an independently validated project-fit evaluator exists. |

## Current patch branch
- Base: `feature/unified-search-analysis` at `ab464a49bd0e5455ad5f66e2fd745e8eccc191a0`.
- Changes: `services/integration_search.py`, `modules/integrated_search.py`, `tests/test_integration_search.py`, this log.
- **Not merged, deployed, or fully tested.** Local Codex/Copilot worktrees are independent and may be ahead.
- Do not represent synthetic tests as evidence of live funding availability.

## Required acceptance checks
1. Run `python -m pytest tests/test_integration_search.py -q`, then full suite. Check that hidden Deep Research tests opt in explicitly.
2. Run live Search with a profiled agency such as NC DHHS and check AI coverage: `evaluated`, `accepted`, `rejected`, `errors`; inspect sanitized failures without exposing credentials.
3. Repeat the rural opioid prevention case: prison/juvenile-justice-only programs must not be presented as ordinary community-service Potential Matches.
4. Verify one or two *currently posted* opportunities on their official pages, including applicant types, program purpose, geography, final due date, and award range. Do not label Forecasted or Needs Verification as open.
5. Confirm Search, Dashboard, My Grants, and Sol persistence still work after integration. No production deployment until tested.
