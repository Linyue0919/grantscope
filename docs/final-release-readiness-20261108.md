# Final release verification — November 8, 2026

Baseline: deployed cc0530b1362ef59fd36cbfcf720379efbbfb0a3f.
Candidate: be12b11b97ea85a3f05e96bd10901ccb532f0869, audited in an isolated worktree.

## Preserved application

The candidate changes only app navigation, Search screening and an optional Search-specific AI candidate priority, plus tests. Dashboard's default matching behavior, original shared GPT-4o evaluators, Application Effort, Profile, My Grants, Sol provider, strict citation validation, private 0700 store and authenticated-encrypted snapshots are preserved. AI Help removal is intentional candidate work. Existing worktrees and uncommitted files were untouched.

## Actual checks and demonstrated defects

- Full Python 3.11 offline suite: 268 passed, 25 optional archived-fixture skips. Compilation, startup shell syntax and diff checks passed.
- Live DEQ wetlands/riparian restoration search: 416 distinct real Grants.gov opportunities, 80 official details; 12/12 GPT-4o strategic assessments and 12/12 eligibility interpretations accepted, no validation/transport errors. Keyless Azure CLI identity used locally. The App Service remains configured for managed identity with Cognitive Services OpenAI User; all existing model deployments report Succeeded.
- The earlier local no-assessment report is not reproducible with valid keyless configuration. The local candidate test worktree lacks secrets.toml and this audit shell had no Azure environment configuration. This is a supported explanation, not proof of the earlier browser process environment. Unassessed may also mean not selected within the 12-record budget; it must never be invented as a score.
- Actual official synopsis text exposed three false positives: Gulf Coast-restricted Direct Component and Centers of Excellence programs, and energy transformational/applied R&D matching generic restoration/monitoring terms. Targeted Search-only holds now inspect the full synopsis for these explicit conditions, retaining records and reasons in the audit. They do not change applicant eligibility or Dashboard behavior. A regression checks long descriptions, audit retention and a negative control permitting an incidental Gulf Coast mention.
- Fixed live search returned only 363920 and 364144 as Potential Matches; each had validated strategic relevance 80/100 in this run. Strategic alignment is not project suitability or confirmed eligibility.
- Navigation AppTest replayed those actual official/Azure records: Dashboard, Search, My Grants and Profile loaded; 363920 rendered with its assessment and could be saved and reloaded from a fresh store instance. This UI replay is not a second live Azure inference test.
- Read-only Azure logs scanned two available top-level log files: no observed Cached ForwardMsg MISS, PermissionError, authentication failure, quote-not-found, HTTP 401 or HTTP 403 strings. Log coverage is limited; absence is not proof of no historical errors.
- Durable archive inspection: one AES-GCM snapshot, no plaintext JSON in the archive directory, expected GSRC01 envelope. Existing archive key/settings/data were not modified. Previously verified real Sol 363920 result and restart restoration are regression acceptance targets after deployment.

## Official example and caveats

363920: https://www.grants.gov/search-results-detail/363920 — Easement Restoration and Stewardship. Live official closing date: November 19, 2026. State governments are listed; direct eligibility remains an interpretation requiring notice review. The work is for lands protected through WRE/ACEP or FPE/EWPP, not arbitrary wetlands. Verify qualifying sites, NRCS coordination, funding scope and preparation requirements.

364144: https://www.grants.gov/search-results-detail/364144 — Landscape Scale Restoration Grant Program for Non-Federal Lands. Live official final closing date: January 26, 2027. Rural eligible forest-land conditions remain material. Sponsorship, intermediate steps and applicant route require full notice verification; summary screening does not certify them.

## Release conditions and remaining limits

Deploy only the exact reviewed commit after CI passes, through the existing final-demo manual workflow. Verify public managed-identity GPT-4o, cached validated Sol, source correspondence and saved-grant persistence after restart. Do not claim a public acceptance result until observed.

Coverage remains bounded at eight queries, 100 rows per query and 80 detailed records. Some queried pools are capped; no exhaustive recall or accuracy claim is justified. Full amendments and legal applicant/site conditions require human review. Previously compromised API-key rotation remains owner action; this release uses managed identity and never reuses that key. Preserve the encryption key across deployments. Main/source branches, production configuration, existing bookmarks and archive data must remain intact.
