---
name: build-mainsequence-crm-metatables
description: "Build the CRM storage and integrity layer using SQLAlchemy-authored Main Sequence MetaTables, migration providers and governed atomic commands. Use for table design, schema evolution, governed queries, merges, pipeline moves or runtime catalog binding; not for creating authentication."
---

# CRM MetaTables backend

## Read before changing code

Read the owning repository's `AGENTS.md`, current implementation and tests,
and the maintained documentation for the affected surface. Paths below are
relative to the named checkout; API and frontend are separate repositories.

- API: `docs/delivery/persistence.md`, affected pages under `docs/concepts/`,
  `src/crm/metatables/`, `src/crm/migrations/`, `src/crm/repositories/`, and
  `tests/test_migrations.py` / `tests/test_catalog.py`.

Read the installed MetaTables client skills in the API checkout; never edit
them during application work:

- `.agents/skills/metatables/metatables-meta-tables/SKILL.md`
- `.agents/skills/metatables/metatables-migrations/SKILL.md`

Installed package versions, public contracts and version-matched skills govern
SDK behavior. Missing installed guidance is an installation/compatibility
issue; do not substitute obsolete source snapshots or guessed APIs.

Repository decision (2026-09-23): revision `0004` replaced the old workspace
table and all CRM `workspace_uid` columns with singleton `settings` and direct
record foreign keys. Do not reintroduce an application workspace tenant,
composite workspace keys, or a global workspace mutation epoch.

## Workflow

1. Confirm the actual installed `mainsequence` and `mainsequence-metatable` versions, selected provider, current repository branch and trusted runtime scope. Resolve active bindings using the verified application adapter; do not ask the user to supply an environment or data-source UID that the platform normally derives.
2. Verify governed multi-table writes with a real final-INSERT DML CTE, database-enforced table permissions, rollback and typed bindings. A local SQL compilation is not the platform test.
3. Implement current SQLAlchemy model contracts with meaningful labels/descriptions and repository-prefixed table names. Use direct CRM-record foreign keys, not an application tenant key. Do not add User, Role or Sale tables.
4. Use the `metatables` migration provider and `metatables migrations` CLI lifecycle. Generate and inspect revisions, then apply them to the local SQLite runtime with `metatables --local migrations upgrade --provider src.crm.migrations:migration` and verify finalization. Branch raw PostgreSQL SQL in a revision on `op.get_bind().dialect.name`, name new CHECK constraints, and keep each revision usable by the release still deployed. Hosted environments are migrated only by the `migrate-crm` Job that `.mainsequence/workflows/crm-api.yaml` runs (`jobs/migrate_crm.py`) before the API deploys; never run `metatables migrations upgrade` or `downgrade` against a hosted runtime, and never migrate at API startup. After a deployment, verify fresh-process binding. Do not directly register platform-managed models or rewrite applied revisions.
5. Send governed SQL operations with the resolved catalog's one DataSource UID; the database enforces table permissions on the tables the SQL touches, so declare no table scope. Fence writes with the affected entity or board version; do not recreate a global workspace CAS gate. Pass the platform actor explicitly; never accept client SQL. The CRM has no command-receipt table or request-key replay contract.
6. Implement merge and board operations set-wise over all related records, communicating CTE results through RETURNING. Never mutate the same row twice in one statement. Ensure dependent writes cannot commit when their record/version precondition fails.
7. Test direct foreign-key integrity, stale versions, unknown outcomes, injected constraint failure, and data type round trips. After an uncertain outcome, read current state before retrying; do not assume once-only execution. Record exact failing capability instead of adding a direct database fallback.

## Required output

Verified migration/provider files, governed gateway/repositories, data-integrity tests and actual platform evidence. Report any atomicity or runtime-binding blocker explicitly.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
