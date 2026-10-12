---
name: build-mainsequence-crm-frontend-transfers
description: "Build the source/upload, mapping, review, durable execution and report screens for CRM migration/export. Use for import/export UI with truthful server progress, explicit owner/stage mapping and refresh-to-resume behavior."
---

# CRM migration frontend

## Read before changing code

Read repository AGENTS.md and `engineering/crm-handoff/START_HERE.md`. Read these application specifications:

- `engineering/crm-handoff/specs/04_backend_api.md`
- `engineering/crm-handoff/specs/05_import_export.md`
- `engineering/crm-handoff/specs/06_frontend.md`

Then use the installed SDK-owned skills; never edit them during application work:

- `.agents/skills/command-center/views/build-resource-list/SKILL.md`
- `.agents/skills/command-center/views/build-resource-detail/SKILL.md`
- `.agents/skills/command-center/views/build-resource-picker/SKILL.md`
- `.agents/skills/command-center/feedback/build-application-loading-flow/SKILL.md`
- `.agents/skills/command-center/layout/compose-command-center-page/SKILL.md`

Pinned source IDs: A08, A09, A10, C08, C09, C11, C13. Resolve them through `engineering/crm-handoff/SOURCE_MAP.md` and the source lock. Missing installed guidance is an installation/compatibility task, not permission to guess an API.

## Workflow

1. Implement the five visible steps from spec 06. Display actual profile coverage and bounds; do not call Atomic legacy JSON a full backup or promise live source-system connectors.
2. Upload through the authorized API and render server field samples/issues. Treat IDs as strings; never parse source identifiers or money through floating-point JavaScript coercion.
3. Provide explicit existing-owner, reference, stage, date/timezone/currency and conflict policy mapping. Unknown/missing values stay blocked unless deliberately resolved; no first-stage or current-user fallback.
4. Display the sealed plan's creates/updates/skips/conflicts/dependent blockers and warning acceptance. Invalidate review when mapping changes. Distinguish strict validation from explicit valid-rows-only execution.
5. After 202, observe the durable job by UID. Browser refresh resumes polling, not processing. Use server counts/status and cooperative cancel; do not derive completion from elapsed time, rows locally read or the request finishing.
6. Explain partial completion accurately and retry only eligible rows through the server's same-plan operation. Preserve error report access controls and report unported binaries/unknown-field retention.
7. Test permission changes, abandoned tabs, reconnect, terminal polling, stale plan, worker failure/retry, export fence errors and accessible narrow-layout mapping forms. Keep lifecycle loaders in the owning SDK surface.

## Required output

Source/mapping/review/run/report screens, typed job observation, safe CSV/JSON download handling and truthful partial/retry browser tests.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
