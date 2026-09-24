---
name: build-mainsequence-crm-frontend-resources
description: "Build CRM contacts, companies, deal lists, tasks, notes, details and pickers with Command Center resource contracts. Use for tracking screens and business forms while leaving list/detail/loading/selection ownership with the SDK."
---

# CRM resource screens

## Read before changing code

Read repository AGENTS.md and `engineering/crm-handoff/START_HERE.md`. Read these application specifications:

- `engineering/crm-handoff/specs/04_backend_api.md`
- `engineering/crm-handoff/specs/06_frontend.md`

Then use the installed SDK-owned skills; never edit them during application work:

- `.agents/skills/command-center/resource/adapt-resource-backend/SKILL.md`
- `.agents/skills/command-center/views/build-resource-list/SKILL.md`
- `.agents/skills/command-center/views/build-resource-detail/SKILL.md`
- `.agents/skills/command-center/views/build-resource-picker/SKILL.md`
- `.agents/skills/command-center/views/add-resource-actions/SKILL.md`
- `.agents/skills/command-center/layout/compose-command-center-page/SKILL.md`

Pinned source IDs: A01, A04, C08, C09, C10, C11, C16, C17. Resolve them through `engineering/crm-handoff/SOURCE_MAP.md` and the source lock. Missing installed guidance is an installation/compatibility task, not permission to guess an API.

## Workflow

1. Start from the API resource and discovery contracts, not Atomic's dataProvider methods. Use public UUID action identity and locally trusted renderer IDs; never evaluate API-supplied code.
2. Implement an adapter around the delegated client. Translate page/filter/sort inputs, preserve authoritative totals, forward abort signals and keep discovery separate from pagination/sort changes.
3. Use ResourceListPage for collections and embedded related lists. Do not rebuild toolbar/search/filter/selection/pagination/loading or Card-wrap a view that already owns its frame.
4. Use ResourceDetailShell with controlled summary/tabs/headerActions and ResourcePicker for authorized references. Keep router effects, API clients, cache and permissions outside reusable resource definitions.
5. Build typed create/edit forms with server-assigned authors, existing-owner references, decimal-string money and omission-versus-null semantics. A stale edit retains user input and shows a conflict; it does not silently overwrite.
6. Discover only permitted explicit bulk actions and let the SDK own preflight/confirmation lifecycle. Selection of one page is not all-matching. Merge is a separate preview workflow.
7. Test loading/error/empty/no-results, cancellation, page boundaries, stable discovery, safe generic columns, activation, mutation refresh and adaptive phone presentation. Use the published layout/theme checks.

## Required output

Thin resource definitions/adapters, list/detail/picker compositions, CRM-owned forms and complete lifecycle/contract/browser tests.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
