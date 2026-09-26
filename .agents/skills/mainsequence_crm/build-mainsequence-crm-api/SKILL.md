---
name: build-mainsequence-crm-api
description: "Implement the existing-identity FastAPI CRM routes, strict domain payloads and canonical Command Center discovery/collection/action boundaries. Use for API work and contract tests without adding another login or permission database."
---

# CRM FastAPI contracts

## Read before changing code

Read repository AGENTS.md and `engineering/crm-handoff/START_HERE.md`. Read these application specifications:

- `engineering/crm-handoff/specs/01_architecture.md`
- `engineering/crm-handoff/specs/04_backend_api.md`
- `engineering/crm-handoff/specs/08_test_acceptance.md`

Then use the installed SDK-owned skills; never edit them during application work:

- `.agents/skills/mainsequence/application_surfaces/api_surfaces/SKILL.md`
- `.agents/skills/command-center/contracts/implement-command-center-contract/SKILL.md`
- `.agents/skills/command-center/contracts/implement-resource-collection-contract/SKILL.md`
- `.agents/skills/command-center/contracts/implement-bulk-actions-contract/SKILL.md`

For optional module routes and public provider ingress, also read
`.agents/skills/mainsequence_crm/build-mainsequence-crm-extensions/SKILL.md`.

Pinned source IDs: M05, M06, C02, C16, C17, C18, C19, C20. Resolve them through `engineering/crm-handoff/SOURCE_MAP.md` and the source lock. Missing installed guidance is an installation/compatibility task, not permission to guess an API.

## Workflow

1. Read the route catalogue, capability map and domain schema. Resolve each canonical contract through the installed manifest and its exact schema/fixtures; do not clone those definitions locally.
2. Consume `request.state.user_uid` as the authenticated human and use the existing application policy/directory adapters. Fail closed on missing context; never use process credentials or iframe identity as authorization.
3. Implement thin routers with allowlisted typed queries, static subpaths before UUID routes, consistent slash behavior, safe error envelopes and explicit response codes. Do not expose raw import records or validation input dumps in errors.
4. Produce canonical resource collections and separate discovery. Counts and rows use the same scope/snapshot. Reject presentation parameters on discovery and do not publish a second bulk-metadata endpoint.
5. Implement application-owned readiness/bootstrap, CRUD, merge, board and transfer contracts from the pack. Propagate expected versions; the CRM no longer requires `Idempotency-Key` or stores command replay receipts. Import/worker calls use the same service boundary.
6. Validate actual serialized HTTP responses and OpenAPI route coverage, plus the indexed canonical fixtures and runtime invariants. Schema-valid does not mean an action is authorized.
7. Test forged scope/owner, stale updates, semantic filter errors, 202 versus completed-job status, and redaction. Classify a canonical-contract gap separately from a CRM implementation bug.

## Required output

Implemented routes, strict models/normalizers, canonical fixture loader, policy integration evidence and HTTP-level contract tests.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
