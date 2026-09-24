---
name: build-mainsequence-crm-metatables
description: "Build the CRM storage and integrity layer using SQLAlchemy-authored Main Sequence MetaTables, migration providers and governed atomic commands. Use for table design, schema evolution, scoped queries, merges, pipeline moves or runtime catalog binding; not for creating authentication."
---

# CRM MetaTables backend

## Read before changing code

Read repository AGENTS.md and `engineering/crm-handoff/START_HERE.md`. Read these application specifications:

- `engineering/crm-handoff/specs/02_metatables_and_integrity.md`
- `engineering/crm-handoff/specs/03_data_model.md`
- `engineering/crm-handoff/specs/10_gaps_and_risks.md`

Then use the installed SDK-owned skills; never edit them during application work:

- `.agents/skills/mainsequence/data_publishing/meta_tables/SKILL.md`
- `.agents/skills/mainsequence/data_publishing/meta_table_migrations/SKILL.md`

Pinned source IDs: M01, M02, M03, M04, M07, M08, A02, A06, A11. Resolve them through `engineering/crm-handoff/SOURCE_MAP.md` and the source lock. Missing installed guidance is an installation/compatibility task, not permission to guess an API.

Repository decision (2026-09-23): revision `0004` replaced the old workspace
table and all CRM `workspace_uid` columns with singleton `settings` and direct
record foreign keys. Older handoff instructions requiring a workspace tenant,
composite workspace keys, or a global workspace mutation epoch are superseded.

## Workflow

1. Confirm the actual installed `mainsequence` version, selected provider, current repository branch and trusted runtime scope. Resolve active bindings using the verified application adapter; do not ask the user to supply an environment or data-source UID that the platform normally derives.
2. Verify governed multi-table writes with a real final-INSERT DML CTE, scope enforcement, rollback and typed bindings. A local SQL compilation is not the platform test.
3. Implement current SQLAlchemy model contracts with meaningful labels/descriptions and repository-prefixed table names. Use direct CRM-record foreign keys, not an application tenant key. Do not add User, Role or Sale tables.
4. Use the SDK migration scaffold/provider/CLI lifecycle. Generate and inspect revisions, apply outside API startup, then verify finalization and fresh-process binding. Do not directly register platform-managed models or rewrite applied revisions.
5. Compile governed SQL operations with all touched MetaTable read/write scopes. Fence writes with the affected entity or board version; do not recreate a global workspace CAS gate. Pass the platform actor explicitly; never accept client SQL. The CRM has no command-receipt table or request-key replay contract.
6. Implement merge and board operations set-wise over all related records, communicating CTE results through RETURNING. Never mutate the same row twice in one statement. Ensure dependent writes cannot commit when their record/version precondition fails.
7. Test direct foreign-key integrity, stale versions, unknown outcomes, injected constraint failure, and data type round trips. After an uncertain outcome, read current state before retrying; do not assume once-only execution. Record exact failing capability instead of adding a direct database fallback.

## Required output

Verified migration/provider files, governed gateway/repositories, data-integrity tests and actual platform evidence. Report any atomicity or runtime-binding blocker explicitly.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
