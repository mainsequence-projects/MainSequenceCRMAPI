---
name: build-mainsequence-crm-frontend-shell
description: "Build the Vite React CRM root using Command Center embedded navigation, delegated API access and the three-stage startup/reconnection gate. Use for application root, transport, routing or startup changes; never add standalone production authentication or duplicate global navigation."
---

# CRM embedded frontend shell

## Read before changing code

Read repository AGENTS.md and `engineering/crm-handoff/START_HERE.md`. Read these application specifications:

- `engineering/crm-handoff/specs/01_architecture.md`
- `engineering/crm-handoff/specs/06_frontend.md`
- `engineering/crm-handoff/specs/08_test_acceptance.md`

Then use the installed SDK-owned skills; never edit them during application work:

- `.agents/skills/command-center/general/build-command-center-application/SKILL.md`
- `.agents/skills/command-center/navigation/compose-command-center-application-shell/SKILL.md`
- `.agents/skills/command-center/embed/integrate-static-site-iframe/SKILL.md`
- `.agents/skills/command-center/feedback/build-application-loading-flow/SKILL.md`

Pinned source IDs: C01, C05, C06, C07, C13. Resolve them through `engineering/crm-handoff/SOURCE_MAP.md` and the source lock. Missing installed guidance is an installation/compatibility task, not permission to guess an API.

## Workflow

1. Inspect installed public exports and declarations, then lock package/source compatibility. Do not import repository internals or copy Atomic's React Admin root.
2. Implement one production embedded root: first-frame viewport status → validated host context/theme → usable delegated transport → actual CRM readiness/bootstrap → depth-one navigation and route content. Keep shell/router absent from the DOM until ready.
3. Compose the declared CRM destinations with ApplicationNavigationPanelShell and stable hrefs. Preserve native link behavior. No child top bar, app switcher, one-item rail or disabled future destinations.
4. Use the SDK iframe client and fetchFastApi with a trusted release UID and exact parent-origin policy. Do not manually attach bearer/release headers or persist tokens. Forward cancellation and dispose listeners.
5. On session/context replacement or transport loss, abort stale work, clear principal and CRM data caches, unmount routes and restart the same gate. Never display records from the prior actor during reconnection. The bootstrap contract has no application workspace UID.
6. Separate app readiness polling from SDK transport retries. Respect terminal permission/origin/missing-route errors; do not wrap every request in another retry loop or replay unsafe requests without tested idempotency.
7. Add a named local/test host harness only, never a silent production bypass. Run the public shell verifier for startup and ready phases, slow readiness, retry, reconnect and phone navigation.

## Required output

Vite entry/root, typed delegated client, route definitions, safe startup state machine, explicit local test harness and shell/transport browser tests.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
