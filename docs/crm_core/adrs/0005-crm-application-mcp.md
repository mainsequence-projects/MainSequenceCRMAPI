# ADR 0005: Serve CRM tools through application MCP

- **Status:** Deployed; hosted requester create/update/persistence verified
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
`User.get_logged_user()`. Hosted MCP admits a delegated workload only through
its signed requester. Without delegation, it uses `reads_as_caller()` to look
up the verified caller and admits only an active human; an unbound workload
cannot perform these tools. The policy checks the effective person's CRM
capability on every invocation. Missing, malformed, expired or denied
delegation never falls back to workload permissions. No tool accepts an actor,
capability, caller proof, token or connection argument. The receiving API
cannot forward the requester's identity to platform directory APIs.

The 2026-10-11 amendment connects the hosted policy and directory in
`src/crm/platform/hosted_runtime.py`. Every operation evaluates the effective
identity's Organization admin flag and Team memberships (the 2026-10-15
amendment below replaces signed Team lists with fresh lookups). Existing platform
Teams can be selected with `CRM_READER_TEAM_UIDS` and `CRM_WRITER_TEAM_UIDS`
(comma-separated UUIDs). Reader Teams grant `crm.read`; Writer Teams grant
the implemented business capabilities except configuration and export.
Verified Organization admins also get `crm.configure`. Export remains hidden
until its immutable-output live gate passes. Empty Team configuration grants
no Team access. The owning storage Team is independent of these human-facing
Team selections. There is no application membership database or permission
fallback to the workload.

The directory resolves self from the verified identity. Direct hosted requests
look up other active human owners inside SDK `reads_as_caller()`, so visibility
comes from the caller. Requester-bound calls can select only that signed person;
other owner selection fails closed until the platform supports a requester
directory read. No workload-scoped directory query substitutes for it. The
bootstrap adapter uses the existing governed settings store. These adapters
do not run migrations or read settings at application startup.

The catalogue contains 69 tools with Solution Selling enabled, 46 without it.
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

Tau's application catalogue is hosted-only in 2.0.12. Locally, the project
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
The API declares view access to its own `crm-assistant` resource so bootstrap
can discover the deployed Agent. The assistant declares view access to `crm`
for application MCP. These access declarations do not add execution dependencies
or grant the assistant storage access or permission to act for a person.

The 2026-10-11 dependency amendment pins Tau 2.0.11 and requires Main Sequence
9.0.20. The public SDK sender now uses the A2A `ROLE_USER` / `ROLE_AGENT`
wire roles. Tau waits within a bounded deadline when application admission says
the runtime is waking, refreshing its access proof before dispatch. This changes
readiness handling, not the authorization or persistence boundary. An uncertain
business write still requires a fresh server read before another attempt; the
CRM does not add a retry loop. Tau 2.0.11 carries each finite MCP response
deadline through its HTTP transport without the earlier shorter backend read
cap. This repairs client timeout handling and preserves the same uncertain-write
boundary. No new architectural decision is required.

A later 2026-10-11 dependency amendment pins Tau 2.0.12 and requires Main
Sequence 9.0.22 and MetaTables 0.1.34. A hosted direct A2A Message now has the
platform's 90-second limit. When it expires, Tau stops the turn and answers
HTTP 504 `DEADLINE_EXCEEDED` with reason `MESSAGE_RESPONSE_LIMIT_EXCEEDED`, and
the SDK raises `A2AMessageLimitExceededError`. The stopped turn's work is
neither rolled back nor replayed, so an uncertain business write still requires
a fresh server read. Each CRM tool still declares 60 seconds, but the limit
covers the whole turn, including model time and every tool call, so longer
work uses Task mode. Chat, streams and Task turns are unchanged, and
MetaTables 0.1.34 changes only server-side hypertable finalization. No new
architectural decision is required.

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
all be verified before declaring the deployed assistant operational. A direct
human OAuth tool call additionally needs its own live verification. See
[verification evidence](../../delivery/verification.md) and the [MCP API
contract](../../api/mcp.md).

## 2026-10-12 amendment: direct human application MCP

`User.get_requester()` is absent on a direct human OAuth call by design: it
represents delegation, not authentication. The prior hosted admission gate
mistook every no-requester call for an unbound workload and denied it before
the CRM policy could run. Hosted MCP now resolves a no-requester caller through
SDK `reads_as_caller()` and permits only an active User with
`identity_type == "human"`. The direct person's own Team/admin facts
remain the policy input; an unbound workload, inactive identity, non-human
identity, or failed caller-scoped lookup fails closed.

Delegated calls still use only requester facts and cannot forward their
requester-bearing assertion to the directory. The SDK rejects invalid or
expired delegation before a tool starts, so it cannot fall back to caller
rights. Denial logs record a safe reason and request correlation, while the
MCP response remains the generic `forbidden` envelope. The live gate must
cover a direct human read, a capability denial, an unbound-workload denial,
and the existing delegated tool path.

## 2026-10-12 amendment: Solution Selling read compositions

Add three API-owned, read-only tools: `crm_prompters_render`,
`crm_solution_selling_context_get`, and `crm_diagnoses_prepare`. The catalogue
now has 38 reads and 31 writes when the module is active, and 46 tools when
inactive. Each new operation requires the effective person's `crm.read` and
uses the same governed stores as REST. Module list filters have closed,
resource-specific schemas. No storage migration or permission expansion is needed.

Context returns the Deal, Company, optional assessment with its key-player
and pain-chain evidence, a bounded Interaction page, and source UIDs/versions.
It does not promise a transaction-wide snapshot. Diagnosis preparation returns
an unsaved payload, copied questions with no answers, and labels the profile's
potential pain as a hypothesis. Rendering returns draft text without saving or
sending it. Existing create/update commands remain deliberate actions with the
existing version fences. No helper propagates or confirms evidence.

The project runtime skill `.tau/skills/solution-selling/SKILL.md` guides this
workflow through the generic MCP bridge. Tau's skill-scoped `read` may load it;
it adds no business tool or platform authority. The live local gate supports
all three helpers and compares actual results with fresh REST reads after restart.
Deployment evidence is recorded in the delivery verification page.


### Human directory projections

The platform may omit `identity_type` from a human directory response. An
omitted value does not establish human identity. In that case MCP admission
uses `User.filter(uid=caller.uid, identity_type="human")` within
`reads_as_caller()` and requires exactly one matching UID with `is_active`
true. Empty, mismatched, duplicate or inactive results are denied; lookup
errors fail closed. Explicit workload types still require delegation. The
effective person's capability checks remain unchanged.

## 2026-10-15 amendment: identity-only proofs and fresh Team lookup

MetaTables 0.1.38 requires Main Sequence SDK 9.0.27, which removes Team lists
from verified identities and rejects the retired `team_uids` assertion claim.
CRM now asks the effective identity's public `in_teams()` helper about the
configured reader and writer Teams with `max_age_seconds=0`. Every non-admin
operation obtains a fresh answer, even if an earlier check ran in the same
request. The signed Organization admin policy and existing capability sets
are unchanged. Delegated checks concern only the requester; a missing lookup
or backend failure cannot borrow the workload's grants or reuse cached access.
This changes no Team configuration, resource grant, storage schema or migration.
