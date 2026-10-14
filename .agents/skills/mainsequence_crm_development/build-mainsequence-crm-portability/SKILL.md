---
name: build-mainsequence-crm-portability
description: "Build and test the CRM source adapters, owner/reference mapping, sealed migration plans, restartable transfer workers and consistent exports. Use for migration from exported CSV/JSON files, replay safety and normalized round trips, not for inventing live CRM connectors."
---

# CRM import and export

## Read before changing code

Read the owning repository's `AGENTS.md`, current implementation and tests,
and the maintained documentation for the affected surface. Paths below are
relative to the named checkout; API and frontend are separate repositories.

- API: `docs/concepts/transfers.md`, `docs/api/transfers.md`,
  `src/crm/portability/`, `src/crm/services/transfers.py`,
  `src/crm/repositories/transfers/`, and `tests/test_transfer_store.py`.

Read the installed MetaTables client and Main Sequence skills in the API
checkout; never edit them during application work:

- `.agents/skills/metatables/metatables-meta-tables/SKILL.md`
- `.agents/skills/mainsequence/application_surfaces/api_surfaces/SKILL.md`

Installed package versions, public contracts and version-matched skills govern
SDK behavior. Missing installed guidance is an installation/compatibility
issue; do not substitute obsolete source snapshots or guessed APIs.

## Workflow

1. Select the explicit input profile. Distinguish Atomic legacy JSON (five supported entity groups) from raw table bundles and the new portable format. Do not claim deals are supported by the legacy parser.
2. Stage bounded input with a server-computed checksum. Preserve opaque source IDs exactly, including integers above JavaScript safe range. Validate mappings as data, never executable expressions.
3. Resolve existing owners, companies, contacts, tags and stages using permanent source identities. Unknown owners/stages and ambiguous dates block unless the operator explicitly resolves them. Never create imported login accounts.
4. Normalize typed methods, booleans, decimal money and historic times without loss-by-coercion. Preserve raw unknown fields with warnings and documented retention. Do not request attachment URLs.
5. Generate a sealed plan with row decisions, dependent blockers and target-version checks. Preserve local edits by default. A changed input or mapping invalidates the plan.
6. Use a real durable worker with lease epochs, reauthorization and persisted row checkpoints. Commit each domain row, required associations, source mapping and checkpoint atomically. Browser lifecycle must not control execution.
7. For export work, implement fenced/staged exports and explicit partial outcomes; advertise only mounted, tested support. Verify normalized portable round trip and formula-safe CSV; do not label external-link metadata as migrated binary content.
8. Kill/restart workers at each commit boundary, replay identical input, change source data after local edits, revoke authority and expire an export fence. Record actual persisted outcomes, not mocked progress.

## Required output

Profile adapters, mapping/plan validators, durable job integration, synthetic fixtures, replay/conflict tests and accurately scoped export support.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
