# Campaigns module

The optional Campaigns module implements [ADR 0001](adrs/0001-campaign-task-graph.md):
a live DAG of prompted task definitions, explicit Contact enrollment, one CRM
Task per participant step, stable per-Contact prompt assignments with A/B
comparisons and descriptive reporting. It is enabled by
`extensions.campaigns.active` in `config/crm.yaml` and mounts below
`/extensions/campaigns/`.

- [Concept](../concepts/campaigns.md): definitions versus instances,
  lifecycle, progression, live editing and comparisons.
- [HTTP and MCP API](../api/campaigns.md): routes, payloads, error codes,
  recovery and the 21 MCP tools.
- [Persistence](../delivery/persistence.md#campaigns-revision-0013): the six
  tables added by revision `0013`.
- [Verification](../delivery/verification.md#campaigns-module-2026-10-24):
  executed checks and remaining hosted evidence.
- [Implementation plan](implementation-plan.md): the contract decisions taken
  during implementation.

The paired frontend exposes a Campaigns section with a visual designer,
participant enrollment, task execution forms and comparison tables; its user
guide documents the Dubai walkthrough. The `crm-campaigns` usage skill is
published with the API's MCP skill pack and mirrored in the frontend pack.

Status: implemented locally with unit, contract and disposable-PostgreSQL
scenario coverage. Hosted migration, deployment and live assistant execution
remain to be verified through the existing release workflow.
