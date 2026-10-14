---
name: build-mainsequence-crm-api
description: "Implement the existing-identity FastAPI CRM routes, strict domain payloads and canonical Command Center discovery/collection/action boundaries. Use for API work and contract tests without adding another login or permission database."
---

# CRM FastAPI contracts

## Read before changing code

Read the owning repository's `AGENTS.md`, current implementation and tests,
and the maintained documentation for the affected surface. Paths below are
relative to the named checkout; API and frontend are separate repositories.

- API: `docs/api/index.md`, `docs/api/route-index.md`, `docs/api/conventions.md`,
  `src/crm/models/`, `src/crm/services/`, and route/contract tests under `tests/`.
- Frontend: `src/api.ts` and the installed Command Center contract schemas/fixtures.

Read the matching installed SDK skills. Main Sequence and Tau guidance lives
in the API checkout; Command Center guidance lives in the frontend checkout.
Never edit SDK-owned skills during application work:

- `.agents/skills/mainsequence/application_surfaces/api_surfaces/SKILL.md`
- `.agents/skills/command-center/contracts/implement-command-center-contract/SKILL.md`
- `.agents/skills/command-center/contracts/implement-resource-collection-contract/SKILL.md`
- `.agents/skills/command-center/contracts/implement-bulk-actions-contract/SKILL.md`

For optional module routes and public provider ingress, also read
`.agents/skills/mainsequence_crm_development/build-mainsequence-crm-extensions/SKILL.md`.

Installed package versions, public contracts and version-matched skills govern
SDK behavior. Missing installed guidance is an installation/compatibility
issue; do not substitute obsolete source snapshots or guessed APIs.

## Workflow

1. Read the mounted route index, application capability checks and Pydantic domain models. Resolve each canonical contract through the installed manifest and its exact schema/fixtures; do not clone those definitions locally.
2. Take the authenticated human only from `authenticated_actor()` (`src/crm/platform/runtime.py`), which reads the verified `User.get_logged_user()` and uses `User.get_requester()` when present. The request identity that `create_app()` installs once has verified that caller before any route runs; see the 2026-10-04 decision in `AGENTS.md`. Use the existing application policy/directory adapters. Fail closed on missing context; never read user headers or `request.state.user_uid`, and never use process credentials or iframe identity as the caller or as authorization.
3. Implement thin routers with allowlisted typed queries, static subpaths before UUID routes, consistent slash behavior, safe error envelopes and explicit response codes. Do not expose raw import records or validation input dumps in errors.
4. Produce canonical resource collections and separate discovery. Counts and rows use the same scope/snapshot. Reject presentation parameters on discovery and do not publish a second bulk-metadata endpoint.
5. Maintain application-owned readiness/bootstrap, CRUD, merge, board and transfer contracts through the existing typed models and shared services. Propagate expected versions; the CRM no longer requires `Idempotency-Key` or stores command replay receipts. Import/worker calls use the same service boundary.
6. Validate actual serialized HTTP responses and OpenAPI route coverage, plus the indexed canonical fixtures and runtime invariants. Schema-valid does not mean an action is authorized.
7. Test forged scope/owner, stale updates, semantic filter errors, 202 versus completed-job status, and redaction. Classify a canonical-contract gap separately from a CRM implementation bug.

## Required output

Implemented routes, strict models/normalizers, canonical fixture loader, policy integration evidence and HTTP-level contract tests.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
