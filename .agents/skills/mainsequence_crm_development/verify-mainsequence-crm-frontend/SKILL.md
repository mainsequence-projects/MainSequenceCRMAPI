---
name: verify-mainsequence-crm-frontend
description: "Verify Command Center contract, theme, responsive shell/layout, accessibility and same-artifact user documentation for the CRM. Use before declaring a screen or frontend release complete; do not accept screenshots or schema compilation alone as conformance."
---

# CRM frontend verification

## Read before changing code

Read the owning repository's `AGENTS.md`, current implementation and tests,
and the maintained documentation for the affected surface. Paths below are
relative to the named checkout; API and frontend are separate repositories.

- Frontend: `engineering/README.md`, `package.json`, `tests/`,
  `documentation/navigation.json`, and affected user-guide pages under `docs/`.
- API: `docs/delivery/verification.md` and relevant API/contract tests.

Read the matching installed SDK skills. Main Sequence and Tau guidance lives
in the API checkout; Command Center guidance lives in the frontend checkout.
Never edit SDK-owned skills during application work:

- `.agents/skills/command-center/navigation/compose-command-center-application-shell/SKILL.md`
- `.agents/skills/command-center/layout/compose-command-center-page/SKILL.md`
- `.agents/skills/command-center/theme/theme-command-center-app/SKILL.md`
- `.agents/skills/command-center/documentation/document-command-center-application/SKILL.md`

Installed package versions, public contracts and version-matched skills govern
SDK behavior. Missing installed guidance is an installation/compatibility
issue; do not substitute obsolete source snapshots or guessed APIs.

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
