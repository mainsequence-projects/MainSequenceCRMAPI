---
name: integrate-mainsequence-crm-tau
description: "Add a separately deployed Tau assistant to an already functioning CRM using the installed ms-tau-sdk skills. Use only for an explicitly requested agent workflow; ordinary tracking and migration remain deterministic and independent of the agent runtime."
---

# CRM Tau integration

## Read before changing code

Read the owning repository's `AGENTS.md`, current implementation and tests,
and the maintained documentation for the affected surface. Paths below are
relative to the named checkout; API and frontend are separate repositories.

- API: `docs/concepts/assistant.md`, `docs/api/mcp.md`,
  `docs/crm_core/adrs/0005-crm-application-mcp.md`, `.tau/SYSTEM.md`,
  `api/crm/mcp_tools.py`, `api/tau/`, and `tests/test_tau_runtime.py`.

Read the matching installed SDK skills. Main Sequence and Tau guidance lives
in the API checkout; Command Center guidance lives in the frontend checkout.
Never edit SDK-owned skills during application work:

- `.agents/skills/ms_tau_sdk/tau_repository_integration/SKILL.md`
- `.agents/skills/ms_tau_sdk/tau_project_customization/SKILL.md`
- `.agents/skills/ms_tau_sdk/tau_local_development/SKILL.md`
- `.agents/skills/ms_tau_sdk/tau_a2a_runtime_adapter/SKILL.md`

Installed package versions, public contracts and version-matched skills govern
SDK behavior. Missing installed guidance is an installation/compatibility
issue; do not substitute obsolete source snapshots or guessed APIs.

## Workflow

1. Confirm the task actually requires an agent; do not add Tau to normal API startup or use a conversation as an import queue.
2. Read all four Tau SDK skills and preserve their ownership boundaries. Use a thin create_app integration in a separate runtime and keep business mutations in authorized CRM services.
3. Distinguish coding guidance under .agents from runtime skills under .tau. Do not copy Atomic's assistant harness or put runtime secrets into a skill.
4. Use the API-owned authenticated `/mcp` catalogue for hosted business tools; `.tau/extensions/crm.py` supplies only the local bridge. Preserve the same requester authorization, validation, version and confirmation boundaries as the application. Do not add a receipt-based replay contract. No direct MetaTable SQL bypass.
5. Follow platform A2A discovery/proof/lifecycle contracts; never fabricate AgentSession, lease holder, caller proof or user identity. Keep proof private and out of model-visible arguments/logs.
6. Test local/deployed differences, cancellation, provider failure, unauthorized tool calls and no effect on CRM availability when Tau is disabled.

## Required output

Optional thin Tau runtime, bounded business skills/tools and evidence that core CRM availability and authorization remain independent.

List actual files changed and tests run. Clearly distinguish implementation, local checks, mocked behavior and verified platform behavior. Preserve existing repository instructions and scaffold markers.
