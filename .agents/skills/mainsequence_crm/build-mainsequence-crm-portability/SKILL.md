---
name: build-mainsequence-crm-portability
description: "Build and test the CRM source adapters, owner/reference mapping, sealed migration plans, restartable transfer workers and consistent exports. Use for migration from exported CSV/JSON files, replay safety and normalized round trips, not for inventing live CRM connectors."
---

# CRM import and export

## Read before changing code

Read repository AGENTS.md and `engineering/crm-handoff/START_HERE.md`. Read these application specifications:

- `engineering/crm-handoff/specs/03_data_model.md`
- `engineering/crm-handoff/specs/05_import_export.md`
- `engineering/crm-handoff/specs/08_test_acceptance.md`

Then use the installed SDK-owned skills; never edit them during application work:

- `.agents/skills/mainsequence/data_publishing/meta_tables/SKILL.md`
- `.agents/skills/mainsequence/application_surfaces/api_surfaces/SKILL.md`

Pinned source IDs: A08, A09, A10, A12, A13, M02, M04. Resolve them through `engineering/crm-handoff/SOURCE_MAP.md` and the source lock. Missing installed guidance is an installation/compatibility task, not permission to guess an API.

## Workflow

1. Select the explicit input profile. Distinguish Atomic legacy JSON (five supported entity groups) from raw table bundles and the new portable format. Do not claim deals are supported by the legacy parser.
2. Stage bounded input with a server-computed checksum. Preserve opaque source IDs exactly, including integers above JavaScript safe range. Validate mappings as data, never executable expressions.
3. Resolve existing owners, companies, contacts, tags and stages using permanent source identities. Unknown owners/stages and ambiguous dates block unless the operator explicitly resolves them. Never create imported login accounts.
4. Normalize typed methods, booleans, decimal money and historic times without loss-by-coercion. Preserve raw unknown fields with warnings and documented retention. Do not request attachment URLs.
5. Generate a sealed plan with row decisions, dependent blockers and target-version checks. Preserve local edits by default. A changed input or mapping invalidates the plan.
6. Use a real durable worker with lease epochs, reauthorization and same-command replay. Commit each domain row, required associations, source mapping and checkpoint atomically. Browser lifecycle must not control execution.
7. Implement fenced/staged exports and explicit partial outcomes. Verify normalized portable round trip and formula-safe CSV; do not label external-link metadata as migrated binary content.
8. Kill/restart workers at each commit boundary, replay identical input, change source data after local edits, revoke authority and expire an export fence. Record actual persisted outcomes, not mocked progress.

## Required output

Profile adapters, mapping/plan validators, durable job integration, synthetic fixtures, replay/conflict tests and accurately scoped export support.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
