# Initial local release baseline — November 7, 2026

Subsequent authorized live AI results and fixes: [live acceptance](live-ai-acceptance.md). The no-paid statements below describe the initial baseline only.

- Branch `release/final-demo`, worktree `/tmp/grantscope-integration-20261107`. Existing integration parents: Search `60ae6f5`, Dashboard `9c02d3f`; source branch references unchanged. Original checkout's app.py, Dashboard and AI cache hashes remain unchanged.
- Fresh isolated Python **3.11.18** environment installed the pinned direct requirements. `pip check`: no broken requirements. OpenAI SDK Azure client construction passed without network requests.
- Full offline suite: **232 passed, 25 skipped**. Skips explicitly identify missing archived/private benchmark or recorded-case evidence. These are not claimed as passing model evaluations. Core generic-engine, source-specific citation, Search integration and Save coverage runs.
- Compilation, shell startup syntax and `git diff --check` passed. Pattern scan of 113 tracked/nonignored release files found no potential credential matches; this is not a guarantee that a key exposed previously is safe. Rotation remains an owner action.
- Real public-data Streamlit AppTest: Dashboard loaded; DEQ watershed Search retrieved **416** unique candidates, inspected **80** official details; two cards appeared. Five queries hit the 100-record cap. No API errors were recorded. Potential Matches are screened leads, not deep-verified recommendations:
  - [364144 — Landscape Scale Restoration Grant Program for Non-Federal Lands](https://www.grants.gov/search-results-detail/364144), Grants.gov closing date 2027-01-26. Forest-land purpose, sponsorship, applicant route and match still require full-notice review for this project.
  - [363920 — Easement Restoration and Stewardship](https://www.grants.gov/search-results-detail/363920), Grants.gov closing date 2026-11-19. Easement/site conditions and readiness still require verification.
- Save from Search → My Grants, Profile and AI Help navigation passed. This was Streamlit's AppTest interaction framework, **not a browser-visual acceptance test**. Azure calls were blocked and asserted absent. Private smoke artifacts live outside the repository under `/tmp/grantscope-release-py311-smoke-v2-20261107`.
- Read-only Azure inventory: `grantscope-gpt4o` / gpt-4o 2024-11-20, `grantscope-bench-gpt55-v1` / gpt-5.5 2026-04-24 and `grantscope-bench-gpt61sol-v1` / gpt-6.1-sol 2026-09-29 all report Succeeded, GlobalStandard. No deployment changes or paid inference were made.
- Normal app launched on **http://127.0.0.1:8532**, with existing CLI Entra authentication and real-AI configuration. HTTP health returned `ok`. The original 8531 no-paid review wrapper and other servers remain intact. Health does not prove inference or browser rendering.

## Remaining checks / risks

1. **Live revised authentication + two-stage Deep Research remains untested.** Existing deployments are verified, but no new model result is claimed. The next explicit Deep Research action makes paid calls; inspect citation validation, failure handling and cache/resume on the actual UI.
2. Verify real browser layout and remote App Service identity permissions, startup, storage and outbound network before public deployment.
3. Retrieval caps and the 80-detail shortlist limit recall; only two leads for this project passed current screening. Do not force five cards or equate zero cards with no available funding.
4. Public strategic-plan verification is partial. Structured applicant categories do not prove program-specific direct eligibility. Potential Matches remain conditional leads until official restrictions are researched.
5. Optional archived demonstrations are absent. Generic Search does not require them; do not claim those fixture-based tests passed or ship private model responses to resolve skips.
6. No new commit, push or remote deployment has been made for this preparation. Release changes remain local and reviewable.
