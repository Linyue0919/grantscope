# Strict private research cache with encrypted durability

Approved by the owner on November 8, 2026: keep a POSIX 0700 active store and persist authenticated-encrypted backups on the existing SMB2 volume. Do not relax the 0700 requirement or delete existing data.

## Behavior

- App Service startup selects `/tmp/grantscope-private-research-v1` for the active store. `ResearchStore` checks 0700 on reads and writes, rejects symlink roots/entries, and writes plaintext files as 0600. A 0777 primary root still fails closed.
- `/home/grantscope/research_encrypted_v1` contains only AES-256-GCM encrypted snapshots. Each write has a fresh random 12-byte nonce. Authentication binds the encrypted data to its exact agency/project context hash. Tampered data, wrong keys and swapped scopes fail closed.
- A new app-only `GRANTSCOPE_RESEARCH_ARCHIVE_KEY` holds a base64-encoded random 32-byte key in Azure App Service settings. Never put it in Git, logs, startup arguments or model prompts. Configure once and preserve it across deployments; changing or losing it makes old backups unreadable. The compromised Azure OpenAI key is not used.
- The durable encrypted snapshot is saved before acknowledging a write and before the engine's next paid request. Failed durable writes fail the research action. Loading an authenticated snapshot restores a 0700/0600 active copy. Version histories and complete original research records are preserved.
- Existing `/home/grantscope/research_v1`, bookmarks, legacy local caches and source evidence remain untouched. No automatic plaintext migration, cache clearing or old-data deletion occurs.
- Local development keeps the existing store behavior unless both archive and active-cache settings explicitly enable this mode. Missing or malformed encryption configuration is an error, never a plaintext fallback.

## Configuration

Startup supplies these defaults only on App Service:

```text
GRANTSCOPE_RESEARCH_CACHE=/tmp/grantscope-private-research-v1
GRANTSCOPE_RESEARCH_ARCHIVE_DIR=/home/grantscope/research_encrypted_v1
```

The encryption secret must be set privately before deploying this version. The active directory must be on POSIX storage, separate from the SMB archive. My Grants continues to use the unchanged persistent data directory. This remains a single-worker demo; no distributed database or multi-worker consistency claim is made.

For a non-destructive restoration test, switch the active-cache setting to a new empty POSIX directory and restart while keeping the archive and key unchanged. Verify original call timestamps, source validation and `cache_reused`; do not delete the original active directory or any durable snapshots. A normal deployment/container replacement can likewise restore from the encrypted snapshots.

## Tests and scope

Synthetic tests verify strict mode rejection, 0700/0600 restoration after loss of an ephemeral fixture directory, tamper/wrong-key/scope-swap rejection, no plaintext in 0777 durable storage, fail-closed missing key/backup failure, version preservation and generic-engine reuse without repeat model calls. Live Sol and restoration must pass before final Copilot integration/deployment.

Only storage/startup/dependency code is changed in this stage. No citation check, matching decision, Search or Dashboard UI is weakened or replaced.
