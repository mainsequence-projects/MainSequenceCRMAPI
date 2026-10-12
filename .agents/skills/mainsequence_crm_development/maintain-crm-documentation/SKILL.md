---
name: maintain-crm-documentation
description: Keep this repository's MkDocs CRM concepts, HTTP API reference, and delivery guidance current whenever a material domain model, functionality, route, persistence, or release behavior changes.
---

# Maintain CRM documentation

Use this skill in the same task as any material CRM model or functionality
change. The documentation source is `docs/`; `mkdocs.yml` is its navigation.
Do not defer the update to an unspecified later task.

1. Inspect the changed code and existing docs. Update the affected
   `docs/concepts/` page for meaning, relationships, invariants, and lifecycle.
2. Update `docs/api/` when a mounted route, query, request/response model,
   capability, status, or error behavior changes. Describe the implemented
   wire behavior, not an aspirational handoff contract. Keep
   `docs/api/route-index.md` aligned with mounted OpenAPI methods and paths.
   Add a page and nav entry only when a distinct concept or delivery surface
   warrants one.
3. Update `docs/delivery/` when configuration, migrations, local execution,
   verification gates, or release evidence changes. Keep unmounted features
   and unverified live-platform behavior explicitly labeled.
4. Keep examples consistent with the authored Pydantic models and mounted
   FastAPI routes. Use relative cross-links between concept, API, and delivery
   pages; do not copy generated OpenAPI or external SDK schemas into prose as
   a second source of truth.
5. Run `.venv/bin/mkdocs build --strict`,
   `.venv/bin/pytest tests/test_documentation.py`, and relevant code/contract tests.
   Report what actually ran and any remaining live or deployed checks.

Pure refactors that do not change public behavior need only update the code
layout or delivery page if those instructions became stale. Typos and
nonmaterial internal edits do not require every concept page to change.
