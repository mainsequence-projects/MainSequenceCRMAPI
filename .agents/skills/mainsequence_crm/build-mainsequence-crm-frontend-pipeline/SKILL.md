---
name: build-mainsequence-crm-frontend-pipeline
description: "Build the application-owned deal board and contact merge review inside Command Center pages. Use for drag/keyboard moves, board concurrency, decimal amounts or merge previews; never reimplement Atomic multi-request writes."
---

# CRM pipeline and merge UI

## Read before changing code

Read repository AGENTS.md and `engineering/crm-handoff/START_HERE.md`. Read these application specifications:

- `engineering/crm-handoff/specs/02_metatables_and_integrity.md`
- `engineering/crm-handoff/specs/04_backend_api.md`
- `engineering/crm-handoff/specs/06_frontend.md`

Then use the installed SDK-owned skills; never edit them during application work:

- `.agents/skills/command-center/layout/compose-command-center-page/SKILL.md`
- `.agents/skills/command-center/views/build-resource-detail/SKILL.md`
- `.agents/skills/command-center/views/build-resource-picker/SKILL.md`
- `.agents/skills/command-center/theme/theme-command-center-app/SKILL.md`

Pinned source IDs: A05, A06, A07, A10, A11, A15, C11, C12. Resolve them through `engineering/crm-handoff/SOURCE_MAP.md` and the source lock. Missing installed guidance is an installation/compatibility task, not permission to guess an API.

## Workflow

1. Inspect Atomic drag and merge code only for business behavior. The target uses one server command, not per-card/per-contact HTTP updates or capped page reads.
2. Build the board as a specialized domain surface inside the SDK page. Load stages, counts, board versions and paged cards; show loaded/total and explicit load-more. Group amounts by currency.
3. Submit move intent with expected deal/board versions and a real before-card UID or explicit global end. Do not infer unseen index positions from a filtered/partial page.
4. Keep an optimistic rollback snapshot; on conflict restore/refetch and explain. Provide a keyboard/touch Move dialog using the same endpoint. Do not make drag or horizontal overflow the only interaction.
5. Build contact merge as choose loser → preview → field decisions → confirm. Show survivor identity, differences, association counts, source warnings and both versions. Never optimistically delete the loser.
6. After an uncertain outcome, read the current server state before retrying; do not replay a move blindly. Invalidate relevant records after success and require a new preview after stale-plan errors. Preserve false and historical timestamps as documented.
7. Test 250+ board cards, filtered same/cross-stage moves, mobile/keyboard access, stale versions and 2,000+ related merge records with actual backend failure/rollback evidence.

## Required output

SDK-framed board and merge views, safe command controllers, accessible alternatives and concurrency/failure regression tests.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
