# Final Search integration and private persistence acceptance — November 8, 2026

## Requested teammate commits

Integrated exactly `0d898dca82c138efce00852463b52620f19e4443` and `3578ec5d29688a1dbd8072567d415cda7071ca5d` with `cherry-pick -x`, preserving authors and original references. Their integration commits are `19e1851` and `e292fcb`. They applied without textual conflicts. The later `06355dc` was not requested and is not included. Main and teammate branch histories are not rewritten.

Search calls the same `run_matching`, `AzureFitEvaluator`, `AzureEligibilityEvaluator` and `assess_effort` function objects as Dashboard. It keeps project-specific retrieval/activity ranking, funding preferences and the exact closing threshold. GPT-4o remains an **agency strategic-fit** assessment, not a project-purpose score or eligibility certification. Official hard exclusions remain controlling. Low strategic scores do not remove an otherwise supported project lead; high strategic scores do not rescue an irrelevant project. All retrieved records remain in the audit.

## Small integration corrections

- The caption now discloses that Find Matching Grants can make paid shared GPT-4o assessments. Deep Research is a separate Sol action.
- Search reuses Dashboard's original strategic-evidence renderer, showing the source-checked evidence without presenting a keyword baseline as AI.
- Deep cards call the original Application Effort function through its **full-announcement** argument, rather than labeling NOFO text as a synopsis. The official structured cost-share field is preserved, including an explicit No, so appendix mentions cannot incorrectly make match mandatory. Application Effort and preparation-time uncertainty remain separate.
- The AI-failure regression mocks both evaluators, avoiding any network use in the offline suite. New tests check shared function identity, zero-strategy/high-irrelevance retention policy, and full-NOFO/cost-share effort behavior.

No Dashboard implementation, app.py, evidence validator or model deployment was replaced. Sol receives original project/official evidence, not GPT-4o judgments. Existing four Search inputs, My Grants, Profile, AI Help and experimental Deep Research remain.

## Storage gate completed BEFORE final integration

Storage-only release `b6640f8e0381ca5c66db363b225fb05a495b7047` passed 258 offline tests (25 optional archived-fixture skips), GitHub CI and deployment run https://github.com/Linyue0919/grantscope/actions/runs/42454246087.

The owner approved a strict 0700 POSIX active cache plus AES-256-GCM durable snapshots on existing SMB storage. The new app-only encryption secret is managed in Azure settings, never Git or model prompts. The 0700 guard remains enforced on reads and writes. Primary plaintext files are 0600. Existing SMB research data and bookmarks were not deleted or overwritten by migration. Durable snapshot creation precedes acknowledging a write or starting the engine's next paid call. Wrong keys, tampering, swapped scopes and failed durable writes fail closed.

Public Search researched real opportunity [363920 — Easement Restoration and Stewardship](https://www.grants.gov/search-results-detail/363920) for a DEQ watershed restoration/monitoring project. Managed-identity Sol returned **RESEARCHED_AND_VALIDATED / CONDITIONAL**, project relevance **70**, strategic relevance **unavailable**. No strategy score was invented when verified goal sources were absent from the deep packet. Both analysis and decision passed source-specific citation and consistency validation:

| Stage | HTTP | Latency | Reference estimated cost |
|---|---:|---:|---:|
| Analysis | 200 | 59.173 s | $0.133781 |
| Decision | 200 | 25.652 s | $0.1243285 |

Estimates are recorded engine reference rates, not verified Azure billing. Amendment/policy completeness and human applicability review remain unresolved; a successful citation check is not an accuracy metric.

The SMB archive had **one encrypted snapshot and zero plaintext JSON files**, with the expected authenticated-encryption envelope. Then the active-cache setting was switched to a new empty POSIX directory and the App Service restarted. The archive, key, original active directory and bookmarks remained intact. A fresh public session restored the validated result with `cache_reused=true`; the analysis, decision and complete original call records matched exactly, proving **zero additional Sol calls**. The saved 363920 bookmark survived restart. No WebSocket error or application exception occurred in the completed restoration check.

Private raw model outputs and browser audits remain outside Git under `/tmp/grantscope-public-storage-acceptance-b6640f8` and `/tmp/grantscope-storage-restore-proof-b6640f8`.

## Final integration checks

The combined local suite passes **263 tests**, with **25 explicit optional archived-evidence skips**. Compilation, shell syntax and diff checks pass. Final GitHub CI and public acceptance must run on the final combined commit before declaring deployment complete. The existing 80-detail screening cap, per-query retrieval cap, incomplete strategic-plan coverage and experimental model judgments remain limitations.

Operational note: preserve `GRANTSCOPE_RESEARCH_ARCHIVE_KEY`; do not regenerate it on deployment. Its loss makes encrypted snapshots unreadable. The compromised Azure OpenAI key is not reused; its separate owner-managed rotation remains outstanding.
