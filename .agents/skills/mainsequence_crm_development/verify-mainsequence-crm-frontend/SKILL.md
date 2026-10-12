---
name: verify-mainsequence-crm-frontend
description: "Verify Command Center contract, theme, responsive shell/layout, accessibility and same-artifact user documentation for the CRM. Use before declaring a screen or frontend release complete; do not accept screenshots or schema compilation alone as conformance."
---

# CRM frontend verification

## Read before changing code

Read repository AGENTS.md and `engineering/crm-handoff/START_HERE.md`. Read these application specifications:

- `engineering/crm-handoff/specs/06_frontend.md`
- `engineering/crm-handoff/specs/08_test_acceptance.md`
- `engineering/crm-handoff/specs/10_gaps_and_risks.md`

Then use the installed SDK-owned skills; never edit them during application work:

- `.agents/skills/command-center/navigation/compose-command-center-application-shell/SKILL.md`
- `.agents/skills/command-center/layout/compose-command-center-page/SKILL.md`
- `.agents/skills/command-center/theme/theme-command-center-app/SKILL.md`
- `.agents/skills/command-center/documentation/document-command-center-application/SKILL.md`

Pinned source IDs: C07, C11, C12, C15. Resolve them through `engineering/crm-handoff/SOURCE_MAP.md` and the source lock. Missing installed guidance is an installation/compatibility task, not permission to guess an API.

## Workflow

1. Run type checking, actual contract/normalizer tests and canonical valid/invalid fixtures against the installed version. Include cross-field runtime invariants and real HTTP serialization.
2. Run `npx command-center-sdk theme audit --path src` as a failure-producing check. Do not waive violations by inventing aliases or literal fallbacks. Use the existing SDK typography and semantic tokens.
3. Run the public application-shell verifier in startup/ready phases and the public page-layout verifier across its default coarse/fine viewport matrix. Configure touch/mobile context correctly.
4. Exercise loaded/loading/error/empty/dense/long-label states in light and dark presets, reduced motion, keyboard alternatives, focus recovery, no hover-only actions, no input zoom or page overflow.
5. Verify startup/reconnect with a real browser harness: no routes/nav before readiness, no child top bar, no stale actor data, exact-origin policy and bounded transport behavior.
6. Initialize/build end-user documentation through the official SDK workflow. Mirror visible navigation IDs and labels; keep engineering docs out of served /docs. Prove both dist/index.html and dist/docs/index.html exist and nested links work.
7. Record exact commands, exit codes, tested commit, browser states and remaining failures. Do not report mocks, a successful build or static screenshots as deployed runtime verification.

## Required output

An evidence-backed frontend report with contract, theme, geometry, accessibility, documentation and deployed/undeployed boundaries clearly separated.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
