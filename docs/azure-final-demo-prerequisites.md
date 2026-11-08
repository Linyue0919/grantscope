# Azure release prerequisites — November 7, 2026

Read-only inspection for `release/final-demo`. No Azure resource, identity, role assignment, app setting or credential was changed. No inference was made during this release checkpoint.

## Verified current state

- App Service `grantscope-team07`, resource group `rg-primary-unc-sdis-solveathon-team07`, is Running. Host: `grantscope-team07-h7b6d2gwephmdmdr.westus3-01.azurewebsites.net`.
- Runtime is already `PYTHON|3.11`.
- Current startup launches Streamlit on `0.0.0.0:8000`; replace with `bash startup.sh` to use the release's persistent-path setup.
- WebSockets **disabled**; Always On **disabled**. Always On is optional and depends on the hosting tier; a cold start remains possible without it.
- The only app setting returned is `SCM_DO_BUILD_DURING_DEPLOYMENT=1`. The required Azure AI settings and persistent application-data setting are absent.
- No managed identity is enabled on this web app.
- Azure OpenAI resource `grantscope-ai-team07` has Succeeded deployments: `grantscope-gpt4o` (gpt-4o 2024-11-20), `grantscope-bench-gpt55-v1` (gpt-5.5 2026-04-24), `grantscope-bench-gpt61sol-v1` (gpt-6.1-sol 2026-09-29). Reuse these; no new model deployment is required.

## Previously exposed credential

**Rotation is NOT verified.** The read-only 90-day resource activity query returned no key-regeneration events. Activity logs alone cannot establish whether a particular old key is currently active or prove revocation. No API key was retrieved, compared, printed or used in this checkpoint. Previous successful inference used Entra CLI authentication and does not prove key revocation.

Before public deployment, the credential owner should approve rotation, identify affected consumers privately, rotate the exposed key in Azure, update approved secret-store references if still needed and verify consumers. Verify revocation using an approved private procedure that does not put the old key into chat, shell history, screenshots or logs. Do not rely on the old key for this deployment. This remains a separate approval action.

## Exact deployment sequence (requires separate approval)

1. Review the pushed `release/final-demo` commit and its [live acceptance](live-ai-acceptance.md). Keep main unchanged. In GitHub Settings → Environments, create/configure **final-demo**, require a reviewer and restrict deployment branches to `release/final-demo` where the repository plan supports these controls. These GitHub protection settings were not verified by this Azure inspection.
2. Verify that the repository or environment has the existing publish-profile secret referenced by `.github/workflows/main_grantscope-team07.yml`: `AZUREAPPSERVICE_PUBLISHPROFILE_FBC12AA9C7104497B4BAC8A3F8DE7A72`. Its presence and validity have not been verified; do not paste its value into the repository or logs. If publish-profile authentication is disabled by tenant/app policy, configure an approved OIDC deployment path instead before dispatch.
3. In Azure Portal → App Service `grantscope-team07` → Identity, enable **System assigned** identity. On Azure OpenAI resource `grantscope-ai-team07` → Access control (IAM), grant that app identity **Cognitive Services OpenAI User**. These are resource changes requiring approval; allow role propagation before testing.
4. In the app's environment variables, set the following **nonsecret** values. Do not copy the local CLI path or an exposed key into Azure:

   ```text
   AZURE_OPENAI_ENDPOINT=https://grantscope-ai-team07.openai.azure.com/
   AZURE_OPENAI_AUTH_MODE=managed_identity
   AZURE_OPENAI_DEPLOYMENT=grantscope-gpt4o
   AZURE_OPENAI_API_VERSION=2024-10-21
   AZURE_OPENAI_RESEARCH_DEPLOYMENT=grantscope-bench-gpt61sol-v1
   AZURE_OPENAI_RESEARCH_MODEL_VERSION=gpt-6.1-sol-2026-09-29
   GRANTSCOPE_DATA_DIR=/home/grantscope
   SCM_DO_BUILD_DURING_DEPLOYMENT=true
   WEBSITES_ENABLE_APP_SERVICE_STORAGE=true
   ```

   Ensure `/home/grantscope` is writable persistent storage. My Grants and research cache use it; do not upload local caches. Keep one worker/instance for this file-backed demo. Do not set `GRANTSCOPE_RESEARCH_CACHE` unless a separate persistent research directory is intended. If managed identity is prohibited, use a newly rotated credential via an approved secret reference and `AZURE_OPENAI_AUTH_MODE=api_key` instead; that alternative is not preconfigured here.
5. Keep Python **3.11**, set startup command **`bash startup.sh`**, enable WebSockets, and optionally enable Always On if the plan permits. Confirm outbound HTTPS to Grants.gov attachment hosts and the Azure OpenAI endpoint; check any resource firewall/private-endpoint restrictions for the app's network.
6. After approval of the preceding changes, open GitHub Actions → workflow file **`main_grantscope-team07.yml`** → Run workflow → select **release/final-demo** → set **deploy=true**. The displayed workflow name may still reflect main's version. Approve the final-demo environment gate. Do not dispatch on main. This release workflow builds/tests on push but deploys only for an explicitly confirmed manual dispatch on the release branch.
7. Confirm the build/test job passed, the exact reviewed SHA was packaged and the deployment job succeeded. The artifact allowlists runtime application code, pinned requirements, startup script and public agency strategic plans; it excludes credentials, private inference outputs and local caches.
8. After deployment, check startup logs without printing environment values. Open Dashboard, Search, My Grants, Profile and AI Help. Perform an explicitly authorized bounded Dashboard AI and one-candidate Sol check, verify source citations and honest failure states, then confirm cache reuse and Save/My Grants persistence across app restart. A local success does not verify deployed identity/network/storage. The current branch's 80-detail and per-query coverage limits remain documented.

The workflow has not been dispatched. No deployment or credential rotation is authorized by this document.
