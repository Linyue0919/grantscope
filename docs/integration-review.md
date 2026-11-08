# Isolated Dashboard + Search integration review

November 7, 2026. Worktree: `/tmp/grantscope-integration-20261107`; branch `integration/search-dashboard-review-20261107`.

Inputs: Search `60ae6f59258ff44ee1677788953aed475d2c3c0d`; Dashboard `9c02d3f9715b8673a3f84cef3901b853355bfde4`. The original working tree and its modified/untracked files were not moved, copied, deleted or overwritten. Original feature branches are preserved. Nothing is pushed or deployed.

## Integrated behavior

- Dashboard's `modules/dashboard.py` is byte-identical to its branch. Strategic-plan quotes, eligibility rules, official evidence, separate strategic fit and application effort remain intact. Its checked-in public `data/agency_strategic_plans.json` is included; private/local recorded-case and benchmark data are not copied.
- `app.py` conflict resolution retains Dashboard routing AND My Grants navigation. Profile retains Search's broader/custom agency support and the preference contract Dashboard reads. Dependencies are the union: streamlit, requests, openai>=1.40, pypdf>=5,<7. OpenAI's optional package is not installed in the current Python environment; no SDK installation or paid calls were needed for the no-AI smoke.
- Default Search now calls Dashboard's `run_matching`, normalized official-details adapter and eligibility/deadline/funding functions. Additive hooks allow project-first detail prioritization and refreshed official dates without changing Dashboard defaults. All underlying records, including forecasted/low-evidence exclusions, remain in `all_records` and the audit download.
- Search queries prioritize project activities, then agency goals. Display ranking uses explicit project-activity evidence, direct applicant route, geography, requested funding adequacy and exact closing-date preference. Strategic scores remain separately labelled heuristics, never relabelled project AI matches.
- Up to five **Potential Matches** display immediately after official-summary screening. They are not fully researched or guaranteed eligible. Expired, forecasted, confirmed/likely-ineligible, unsupported applicant-specific/affiliation titles, explicit non-NC location lists, and incompatible R&D-purpose leads are held in the audit pool. Missing or unresolved full-NOFO requirements are labelled openly.
- Each card's **Deep Research** action invokes the existing two-stage Sol engine for exactly that ID; Search, Save and rerenders do not instantiate providers. Context includes agency, original project, geography, amount and date. Same-context/evidence cache reuse and failed/in-flight protections remain. Only citation/consistency-validated records display the passed-checks label; model rejection/conflicting outcomes are removed from Potential Matches and retained in audit. Paid deep research was not live-tested in this integration.

## Real-data Streamlit smoke (no paid calls)

Specific DEQ project: restore riparian vegetation/stream habitat in rural NC watersheds, monitor water quality, reduce nutrient runoff, work with local governments/landowners; $300,000; earliest close November 7, 2026.

Fresh Grants.gov discovery returned 416 unique opportunities; 80 official details were inspected. Five of eight queries reached the 100-record cap, so coverage is incomplete. The real Streamlit app entry was exercised through AppTest: Dashboard → Search → Save → My Grants → Profile. Private normalized outputs and checks are under `/tmp/grantscope-integration-smoke-accepted-20261107`. Inference providers were blocked; paid calls: **zero**.

Actual final displayed candidates:

| ID / title | Official listed close | Official funding range | Why only potential |
|---|---|---|---|
| [364144 — Landscape Scale Restoration Grant Program for Non-Federal Lands](https://www.grants.gov/search-results-detail/364144) | Jan 26, 2027; Posted | $100,000–$600,000 | Watershed/water-quality restoration appears in the synopsis; state governments are listed. Eligible rural non-industrial private or state/local forest land must be established; sponsorship, match and controlling notice conditions remain unverified by this screening. |
| [363920 — Easement Restoration and Stewardship](https://www.grants.gov/search-results-detail/363920) | Nov 19, 2026; Posted, 12 days left | $250,000–$5,000,000 | Synopsis describes wetland/floodplain restoration and assessment, but only on lands protected through the specified NRCS easement programs. Applicant/site roles, detailed costs and readiness remain unresolved. |

Neither is called Sol-verified. The final run saved 364144 with unverified screening/project context and loaded it in My Grants. Four inputs, dedicated Deep Research buttons, source evidence and Profile were present. No paid provider was called by Search, Save, navigation or rerun.

Failures found by real smoke and corrected:

1. Tribal-only 363611 originally slipped through because official notes only said “See Section 2.” Applicant-specific titles now create a hold pending a supported route; no fabricated confirmed-eligibility finding is created.
2. Exact adjacent phrases missed “restore … in watersheds.” Activity grouping now recognizes separated watershed/restoration evidence and still requires independent activity signals for broad environmental descriptions.
3. 362755 WaterSMART passed state-applicant screening, but its full official eligibility text lists eligible states/territories excluding NC. The explicit location list now creates a project-geography hold.
4. 361080 ERDC had broad water/wetland vocabulary but an R&D purpose unsupported by this implementation project. It is retained in audit, not promoted.

## Tests and practical limits

- Focused shared Dashboard/integration tests: **78 passed**. They cover project-vs-strategy separation, expiry/ineligibility/geographic/purpose holds, only-clicked-ID deep research with synthetic Azure responses, strict successful engine validation, cache reuse, Save and reruns. The model outputs in these tests are mocks, not live model acceptance.
- Full clean-worktree offline suite: **221 passed, 26 failed**. All failures depend on benchmark/recorded-case evidence assets that were not committed on either source branch (or demo widgets absent because those files are missing). They are documented pre-existing clean-checkout limitations, not silently skipped or supplied from private data. Logs: `/tmp/grantscope-integration-offline-final.txt`.
- Compilation and diff whitespace checks pass. Dependency SDK installation was not exercised. Dashboard code remains unchanged; Search adds optional shared-engine hooks rather than replacing strategic matching.
- No real browser visual/click acceptance: CUA failed opening localhost with `Cannot read properties of undefined (reading 'timeoutMs')`. AppTest with fresh real Grants.gov data is evidence of Streamlit execution, not a claim of visual browser validation.
- Screening is transparent deterministic activity/eligibility evidence, not semantic suitability certification. Affiliation/region/title holds can miss valid alternative routes; all remain auditable. Inspection is bounded to 80 details; uninspected grants cannot become Potential Matches. No measured accuracy/recall or universal funding coverage is claimed.
- The user's $300,000 preference is compared to official ranges, not treated as a minimum that deletes partial-funding options. Agency strategic evidence is displayed separately; the Sol adapter does not fabricate verified strategic-goal attestations from dataset excerpts.

A read-only/no-paid review server runs at `http://localhost:8531`; it wraps this unchanged app entry with Dashboard AI and Search providers disabled. Launch the normal isolated app only when normal model permissions/configuration are intended:

```sh
cd /tmp/grantscope-integration-20261107
python -m streamlit run app.py --server.port 8532
```

Normal Dashboard retains its existing optional AI behavior when configured; Deep Research is a separate explicit Search action. This task made no paid calls. **Qualified integration review GO; not a release or full live deep-research/browser acceptance.**
