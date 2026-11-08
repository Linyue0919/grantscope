# Final demo release — local integration, November 7, 2026

Worktree: `/tmp/grantscope-integration-20261107`, branch `release/final-demo`.
The existing integration merge contains both Search and Dashboard source branches. Latest Search recall-audit fixes remain included. Original branches and original checkout are preserved. This is not a production approval or an accuracy claim.

## Local launch (real AI enabled)

Use Python 3.11 and install `requirements-dev.txt`. For the existing authenticated CLI session:

```sh
export AZURE_OPENAI_ENDPOINT=https://grantscope-ai-team07.openai.azure.com/
export AZURE_OPENAI_AUTH_MODE=azure_cli
export GRANTSCOPE_AZURE_CLI=/tmp/grantscope-azure-cli/bin/az
export AZURE_OPENAI_DEPLOYMENT=grantscope-gpt4o
export AZURE_OPENAI_API_VERSION=2024-10-21
export AZURE_OPENAI_RESEARCH_DEPLOYMENT=grantscope-bench-gpt61sol-v1
export AZURE_OPENAI_RESEARCH_MODEL_VERSION=gpt-6.1-sol-2026-09-29
python -m streamlit run app.py --server.port 8532
```

The existing 8531 review wrapper deliberately disables paid AI. Launch the normal `app.py` above to enable it; no existing process needs to be stopped. Environment values take precedence over optional Streamlit secrets. Do not reuse the previously exposed API key; an owner must rotate it separately. Never put credentials into Git, commands, screenshots or logs.

Dashboard's enabled AI review can incur calls when matching runs. Search screening uses official records and heuristics; Potential Matches are not verified recommendations. Per-candidate Deep Research explicitly starts Sol's analysis and decision stages, with existing citation, source identity, claim-registry and consistency checks. There are no automatic paid retries. Resumable research persists in its existing versioned cache. The existing per-opportunity call/token/spending safeguards remain; they do not disable real AI.

## Azure deployment (approval required; not executed)

See [read-only Azure findings and the exact approval/deployment sequence](azure-final-demo-prerequisites.md) for the verified current configuration and unresolved credential rotation.

1. Review this branch and configure GitHub environment `final-demo` with a required reviewer. The workflow no longer automatically deploys on a push to main. Do not dispatch deployment until separately approved.
2. Use the existing Linux App Service `grantscope-team07`, Python **3.11**, startup command `bash startup.sh`, WebSockets enabled and `SCM_DO_BUILD_DURING_DEPLOYMENT=true`.
3. Set the nonsecret endpoint, GPT-4o deployment/API version and Sol deployment/model-version values above in App Service configuration. Existing model deployments are reused, not recreated or upgraded.
4. Preferred authentication: enable the app's managed identity and grant it **Cognitive Services OpenAI User** on the existing Azure OpenAI resource. Set `AZURE_OPENAI_AUTH_MODE=managed_identity`. This is a future resource/role change requiring approval. Alternatively use a rotated key from an approved secret store and `AZURE_OPENAI_AUTH_MODE=api_key`; never use local CLI paths in the cloud.
5. Set `GRANTSCOPE_DATA_DIR=/home/grantscope` on persistent App Service storage and ensure it is writable. My Grants and research records use this directory. `GRANTSCOPE_RESEARCH_CACHE` optionally overrides only research storage. Storage is local to the app, not a multi-instance database; use one worker/instance for this demo.
6. After approved push, manually dispatch the workflow **on release/final-demo**, setting `deploy=true`, then approve the environment. Artifact packaging allowlists runtime code, requirements, startup script and the public strategic-plan dataset. It excludes caches, keys, private benchmark responses and unrelated data.
7. Verify Dashboard, Search, per-candidate research, Save/My Grants, Profile and AI Help. Verify deployed identity permissions, writable persistent storage, outbound Grants.gov/Azure access and timeout behavior before public use. Remote deployment/auth/network behavior has not been tested by local offline tests.

## Coverage and progressive screening

Current Search makes up to eight diversified queries, each capped at **100 records without pagination**. It retains the retrieved pool but retrieves official details for only the **80-candidate screening shortlist**; up to five passing leads are displayed. Further candidates can remain uninspected. Zero cards does not establish that no suitable funding exists. Latest recall fixes improve activity/geography/date and negative-purpose screening, and include a bounded official-document check for selected rolling-intake leads; they do not remove these coverage limits.

Planned, **not implemented**: continue screening the next unscreened batch after rejections/document failures; show retrieved/inspected/remaining coverage and stop reason; cache official detail responses with timestamps and versioned project-specific screening, retain failures for audit but allow explicit bounded retries, and preserve a resume cursor. Add retrieval pagination separately. No claim of exhaustive recall is justified today.

## Validation limits

The full suite reports explicit skips for archived/private benchmark and recorded-case fixtures absent from this checkout. These assets are not required for generic production Search and are not copied into the deployment. Synthetic citation and generic-engine tests still run. A previously validated single case does not demonstrate model accuracy. Subsequent authorized live inference is documented in [live acceptance](live-ai-acceptance.md); remote deployment configuration still requires post-approval checks.

Authentication follows the [OpenAI Python Azure client documentation](https://developers.openai.com/api/reference/python) and [Microsoft keyless connection guidance](https://learn.microsoft.com/en-us/azure/developer/ai/keyless-connections). Startup follows [App Service Python configuration](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python).
