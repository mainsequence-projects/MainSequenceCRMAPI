---
name: build-mainsequence-crm-frontend-transfers
description: "Build the source/upload, mapping, review, durable execution and report screens for CRM migration/export. Use for import/export UI with truthful server progress, explicit owner/stage mapping and refresh-to-resume behavior."
---

# CRM migration frontend

## Read before changing code

Read the owning repository's `AGENTS.md`, current implementation and tests,
and the maintained documentation for the affected surface. Paths below are
relative to the named checkout; API and frontend are separate repositories.

- Frontend: `engineering/README.md`, `docs/data-transfer/index.md`,
  and `src/TransferPages.tsx`.
- API: `docs/concepts/transfers.md`, `docs/api/transfers.md`,
  and current transfer models and services.

Read the matching installed SDK skills. Main Sequence and Tau guidance lives
in the API checkout; Command Center guidance lives in the frontend checkout.
Never edit SDK-owned skills during application work:

- `.agents/skills/command-center/views/build-resource-list/SKILL.md`
- `.agents/skills/command-center/views/build-resource-detail/SKILL.md`
- `.agents/skills/command-center/views/build-resource-picker/SKILL.md`
- `.agents/skills/command-center/feedback/build-application-loading-flow/SKILL.md`
- `.agents/skills/command-center/layout/compose-command-center-page/SKILL.md`

Installed package versions, public contracts and version-matched skills govern
SDK behavior. Missing installed guidance is an installation/compatibility
issue; do not substitute obsolete source snapshots or guessed APIs.

## Workflow

1. Maintain the source/upload, mapping, review, execution and report steps in the current transfer screen. Display actual profile coverage and bounds; do not call Atomic legacy JSON a full backup or promise live source-system connectors.
2. Upload through the authorized API and render server field samples/issues. Treat IDs as strings; never parse source identifiers or money through floating-point JavaScript coercion.
3. Provide explicit existing-owner, reference, stage, date/timezone/currency and conflict policy mapping. Unknown/missing values stay blocked unless deliberately resolved; no first-stage or current-user fallback.
4. Display the sealed plan's creates/updates/skips/conflicts/dependent blockers and warning acceptance. Invalidate review when mapping changes. Distinguish strict validation from explicit valid-rows-only execution.
5. After 202, observe the durable job by UID. Browser refresh resumes polling, not processing. Use server counts/status and cooperative cancel; do not derive completion from elapsed time, rows locally read or the request finishing.
6. Explain partial completion accurately and retry only eligible rows through the server's same-plan operation. Preserve error report access controls and report unported binaries/unknown-field retention.
7. Test permission changes, abandoned tabs, reconnect, terminal polling, stale plan, worker failure/retry, export fence errors and accessible narrow-layout mapping forms. Keep lifecycle loaders in the owning SDK surface.

## Required output

Source/mapping/review/run/report screens, typed job observation, safe CSV/JSON download handling and truthful partial/retry browser tests.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
