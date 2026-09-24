# Main Sequence CRM API

This site documents the CRM service in this repository. It is organized along
two boundaries:

- [Concepts](concepts/index.md) explain what contacts, companies, deals, tasks,
  notes, tags, activity, and transfers mean. They are not endpoint instructions.
- [API](api/index.md) documents the **mounted** FastAPI surface and its request
  rules. The running service also generates an OpenAPI document at
  `/openapi.json` and an interactive view at `/docs`.
- [Delivery](delivery/local-development.md) covers running, schema ownership,
  migrations, and verification for this Python API release.

The frontend is a separate Command Center application. This site does not
describe an independent CRM login or a second user/role database: the API uses
the existing platform-injected human identity and policy. There is no
application-owned workspace or tenant identity.

## Implementation status

The pages describe the code currently present here, not every feature in the
engineering handoff. In particular, export HTTP routes are not mounted, and
local tests alone do not establish governed mutation safety. The CRM-only
`0005` migration, fresh-process governed reads, and a synthetic contact social
create/patch probe were verified on the configured disposable provider. A
deployed release and nonempty legacy backfill remain unverified.
See [verification and release](delivery/verification.md) before treating the
service as deployment-ready.
