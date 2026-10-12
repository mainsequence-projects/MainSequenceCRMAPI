---
name: integrate-mainsequence-crm-tau
description: "Add a separately deployed Tau assistant to an already functioning CRM using the pinned ms-tau-sdk skills. Use only for an explicitly requested agent workflow; ordinary tracking and migration remain deterministic and independent of the agent runtime."
---

# CRM optional Tau integration

## Read before changing code

Read repository AGENTS.md and `engineering/crm-handoff/START_HERE.md`. Read these application specifications:

- `engineering/crm-handoff/specs/09_tau_optional.md`
- `engineering/crm-handoff/specs/10_gaps_and_risks.md`

Then use the installed SDK-owned skills; never edit them during application work:

- `.agents/skills/ms_tau_sdk/tau_repository_integration/SKILL.md`
- `.agents/skills/ms_tau_sdk/tau_project_customization/SKILL.md`
- `.agents/skills/ms_tau_sdk/tau_local_development/SKILL.md`
- `.agents/skills/ms_tau_sdk/tau_a2a_runtime_adapter/SKILL.md`

Pinned source IDs: T01, T02, T03, T04, T05. Resolve them through `engineering/crm-handoff/SOURCE_MAP.md` and the source lock. Missing installed guidance is an installation/compatibility task, not permission to guess an API.

## Workflow

1. Confirm the task actually requires an agent; do not add Tau to normal API startup or use a conversation as an import queue.
2. Read all four Tau SDK skills and preserve their ownership boundaries. Use a thin create_app integration in a separate runtime and keep business mutations in authorized CRM services.
3. Distinguish coding guidance under .agents from runtime skills under .tau. Do not copy Atomic's assistant harness or put runtime secrets into a skill.
4. Give the runtime typed read/propose/execute tools with the same validation, permission, version and confirmation boundaries as the application. Do not add a receipt-based replay contract. No direct MetaTable SQL bypass.
5. Follow platform A2A discovery/proof/lifecycle contracts; never fabricate AgentSession, lease holder, caller proof or user identity. Keep proof private and out of model-visible arguments/logs.
6. Test local/deployed differences, cancellation, provider failure, unauthorized tool calls and no effect on CRM availability when Tau is disabled.

## Required output

Optional thin Tau runtime, bounded business skills/tools and evidence that core CRM availability and authorization remain independent.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
