# ADR 0005: Serve CRM tools through application MCP

- **Status:** Implemented in source; hosted deployment and live governed tool verification pending
- **Date:** 2026-10-09
- **Supersedes:** The in-process Tau business-tool transport and caller binding in
  [ADR 0003](0003-tau-crm-agent-tools.md). Its shared service, version, permission,
  confirmation and optional-runtime boundaries remain.
- **Amends:** The assistant tool availability description in
  [ADR 0004](0004-single-bootstrap-and-assistant-runtime.md). Its single-bootstrap
  contract and local/platform conversation transports remain.

## Context

The previous Tau extension imported CRM services into the assistant process.
Its runtime supplier deliberately returned `unavailable` because it had no
trusted caller, policy or directory binding. Main Sequence 9.0.19 now supports
authenticated application MCP and verified requester assertions; Tau 2.0.9
discovers workflow-declared application MCP endpoints for each active turn.
The API already owns the CRM service and persistence adapters.

## Decision

Keep Tau as the separate conversation runtime. Move the existing typed CRM
catalogue to `api/crm/mcp_tools.py` and serve it at authenticated `POST /mcp`
inside the API. Use the official MCP Python SDK's low-level Server and
stateless JSON Streamable HTTP manager to preserve the existing Pydantic input
schemas and safe error envelopes. Install it with Main Sequence `install_mcp`
after `install_request_identity`. There is no MCP session or per-person result
cache in the API; the catalogue contains only deployment-wide schemas.

```text
Tau application MCP client ──> /mcp ───┐
                                      ├──> CRMOperations ──> governed repositories
Command Center ─────────────> REST ────┘
```

REST and MCP resolve the effective actor through `authenticated_actor()`:
the signed `User.get_requester()` when present, otherwise the verified
`User.get_logged_user()`. Hosted MCP business calls additionally require a
requester. A workload alone cannot perform these tools. The policy checks
the person's CRM capability on every invocation. Missing, malformed, expired
or denied delegation never falls back to workload permissions. No tool accepts
an actor, capability, caller proof, token or connection argument. The receiving
API cannot forward the requester's identity to platform APIs: its trusted
policy/directory adapters remain a required integration, not a new permission
database or a process-credential substitute.

The catalogue retains 66 tools with Solution Selling enabled, 46 without it.
It omits archive/restore, merge execution and import commit until shared
services can verify the required confirmation evidence. Reads are annotated
read-only; mutations are non-idempotent. The agent dispatches calls sequentially.
Results have bounded JSON business data and redacted error codes. Cancellation
before dispatch starts no operation; a started synchronous write may finish
after cancellation or loss of the response. Never replay automatically: read
current server state before considering another write.

The assistant declares `mcp_applications: [{resource: crm}]`, resource-level
`acts_for_requester: true`, and view access to the CRM release. An Organization
admin must enable that delegation. It no longer needs direct MetaTables access
for CRM tools. Keep `TAU_EXCLUDE_BASE_TOOLS=true` and
`TAU_EXCLUDE_MAINSEQUENCE_MCP=true`. Application MCP is independent of broad
Main Sequence MCP. Tau retains its skill-scoped `read` and A2A Task controls.
The model discovers schemas with `crm__list_tools` and executes them through
`crm__call_tool`; there are no native per-business-operation Tau tools.

Tau's application catalogue is hosted-only in 2.0.9. Locally, the project
extension registers just those same two generic transport tools, using the
official MCP client against the loopback CRM launcher. The launcher supplies
its saved sign-in to request verification. `CRM_LOCAL_API_ORIGIN` defaults to
`http://127.0.0.1:38641`, accepts only HTTP loopback origins with a port, and is
never a model argument. No business schema or service implementation is copied
into the bridge, and it performs no automatic retry. Hosted mode registers no
project extension tools.

## Deployment and consequences

The workflow remains the sole `.mainsequence/workflows/crm-api.yaml` file.
Each service has its own image step; migration precedes API deployment, and
the assistant waits for API deployment. The migration Job still owns hosted
schema updates. This change creates no migration and performs no startup DDL.

The platform uses the resource key as the MCP application name and rejects
hyphens. Rename the API resource from `crm-api` to `crm`, retaining the workflow
filename. **This changes release identity and URL when applied.** Before
publishing, coordinate the new release with the frontend's
`VITE_CRM_FASTAPI_RELEASE_UID`, Google OAuth callback registration, workload
Team membership and resource grants. Do not invent a replacement UID or
claim that the existing frontend binding already targets the new resource.
The new API/Job must retain the CRM namespace's required table permissions.

Bootstrap readiness and Tau readiness still do not prove business-tool access.
Hosted policy/directory wiring, admin-approved delegation, hosted MetaTables
compatibility, the new API release binding and a real requester tool call must
all be verified before declaring the deployed assistant operational. See
[verification evidence](../../delivery/verification.md) and the
[MCP API contract](../../api/mcp.md).
