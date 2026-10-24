# Main Sequence CRM API

This site documents the CRM service in this repository:

- [Concepts](concepts/index.md) explain what contacts, companies, deals, tasks,
  notes, tags, activity, and transfers mean. They are not endpoint instructions.
- [API](api/index.md) documents the **mounted** FastAPI surface and its request
  rules. The running service also generates an OpenAPI document at
  `/openapi.json` and an interactive view at `/docs`.
- [Delivery](delivery/local-development.md) covers running, schema ownership,
  migrations, and verification for this Python API release.
- [Module documentation](google_workspace_module/index.md) includes the
  optional Google Workspace extension and its
  [Google Cloud setup guide](google_workspace_module/setup.md). The
  [Solution Selling module](solution_selling_module/index.md) has its own
  decisions and status.
- [Campaigns proposal](campaigns_module/adrs/0001-campaign-task-graph.md)
  describes the task DAG, prompt specialization and per-contact progress for
  review. This module is not implemented.

The frontend is a separate Command Center application. This site does not
describe an independent CRM login or a second user/role database: the API
verifies the Main Sequence user making each request and relies on the existing
platform policy. There is no application-owned workspace or tenant identity.

## Implementation status

The pages describe the implemented models, shared services, and mounted routes
in this checkout. Export HTTP routes are not mounted. Local tests alone do not
establish governed mutation safety or deployed behavior; consult the dated
[verification and release evidence](delivery/verification.md) for each change.
Maintain behavior using `AGENTS.md`, the project development skills, current
code and tests, and installed SDK/client guidance. Keep planned work and
unverified integration checks explicitly labeled.
