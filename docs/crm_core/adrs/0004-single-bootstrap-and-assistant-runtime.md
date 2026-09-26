# ADR 0004: Persist CRM feature configuration and return one bootstrap snapshot

- **Status:** Implemented in source; deployed runtime verification pending
- **Date:** 2026-09-26
- **Scope:** Persisted deployment configuration, CRM initialization API, extension discovery, and assistant transport selection
- **Related:** [Tau CRM tools](0003-tau-crm-agent-tools.md),
  [service API](../../api/service.md), and
  [local development](../../delivery/local-development.md)

## Context

Before this ADR, the frontend requested `/api/crm/v1/readiness/` and then
`/api/crm/v1/bootstrap/`. The bootstrap response supplied the signed-in
principal, capabilities, settings, default pipeline, limits, and the mounted
Solution Selling and Google Workspace module flags. It did not supply an
assistant object. The frontend consequently hid the Assistant even when a
separate Tau local process is healthy.

Extension activation previously came from `INCLUDE_SOLUTION_SELLING` and
`INCLUDE_GOOGLE_WORKSPACE_EXTENSION` process environment variables. Those
booleans cannot grow into a coherent configuration for each extension. The
CRM needs one persisted, reviewable application configuration snapshot that
both route mounting and bootstrap read.

Tau local mode has no registered platform Agent or AgentSession and cannot
produce a platform Agent UID or Organization Environment UID. The existing
frontend assistant uses the Command Center AI connection, which requires both
identifiers. A local Tau conversation needs its own transport branch instead
of invented platform identifiers.

The assistant's repository-owned identity comes from this project's
`.agents/agent_card.json`. Its top-level `name` is the Agent name that the
platform synchronizes to the deployed Agent. This repository now contains the
card and a `harness_agent` workflow declaration but no verified managed CRM Agent.
The platform variant remains unavailable until the workflow creates an Agent runtime in
the branch Environment.

## Decision

`GET /api/crm/v1/bootstrap/` is the **single initialization request** made by
the frontend after the host or local API transport is established. The API
checks CRM readiness while handling that request. A successful response is one
snapshot containing the current principal, capabilities, settings, default
pipeline, limits, active modules, readiness, and assistant configuration. The
frontend must not make a separate `/readiness/` request to decide whether to
mount the CRM. `/readiness/` may remain a protected operational diagnostic.

### Persisted application configuration

Store the nonsecret deployment configuration in a repository-owned YAML file
at `config/crm.yaml`, included in the API release artifact. Its initial shape
is:

```yaml
extensions:
  solution_selling:
    active: true
  google_workspace:
    active: true
```

`extensions` owns a named section for each optional module. Each section
requires `active`, leaving room for typed module-specific options in later
revisions. There is **no assistant section** in this YAML. The Agent Card owns
the assistant's name and description. Do not persist the assistant runtime
mode, display name, Agent UID, Environment UID, bearer token, provider secret,
or release URL in CRM configuration. `assistant.display_name` in bootstrap is
the Agent Card's top-level `name`.

Load and validate this file once at API process boot. Reject missing, malformed,
or unknown configuration instead of silently defaulting a misspelled module
off. Use the same immutable parsed snapshot to mount extension routes and to
fill `modules` in bootstrap; a file change takes effect after process restart
or redeployment. The CRM's existing singleton business settings remain in
their governed MetaTable. Google OAuth client credentials and token-encryption
secrets remain in Main Sequence Secrets; they are never put in this YAML.

The YAML replaces the two `INCLUDE_*` extension switches as the source of
truth. Route mounting and bootstrap now read the same parsed snapshot; the
local launcher, private `.env`, and managed API workflow no longer set those
flags. There is no environment-variable activation override.

If the CRM is not ready, bootstrap returns HTTP 503 with the existing safe
`CRM_NOT_READY` error and a bounded `readiness` object containing the failed or
pending checks. No partial settings, principal, module, or assistant payload is
returned on failure. Identity and authorization failures retain their 401/403
behavior. The frontend keeps its host, transport, and readiness progress
stages, but derives the final stage from this one request.

The target not-ready body is:

```json
{
  "error": {"code": "CRM_NOT_READY", "message": "CRM setup is incomplete.", "request_uid": "<request-uuid>"},
  "readiness": {"status": "not_ready", "schema_version": "<active schema>", "application_version": "0.1.0", "checks": [{"id": "<check>", "status": "failed", "message": "<safe explanation>"}]}
}
```

### Successful response shape

The existing fields remain. This is the implemented source contract; a
deployed API revision has not yet been verified against it.

```json
{
  "application_version": "0.1.0",
  "current_user": {"uid": "<authenticated-user-uuid>", "display_name": "<user name>", "selectable": true},
  "capabilities": ["crm.read"],
  "settings": {"...": "existing settings fields"},
  "default_pipeline_uid": "<pipeline-uuid>",
  "limits": {"...": "existing limits fields"},
  "readiness": {"status": "ready", "schema_version": "<active schema>", "application_version": "0.1.0", "checks": []},
  "modules": {"solution_selling": true, "google_workspace": true},
  "assistant": {"enabled": true, "runtime": {"mode": "local", "base_path": "/tau"}, "agent_uid": null, "environment_uid": null, "display_name": "CRM assistant"}
}
```

The `"..."` entries above abbreviate existing settings and limits; they are
not literal wire keys. The implementation must use the authored Pydantic
models for those fields. `current_user.display_name` names the human; it is
not the assistant's display name.

The API process that mounts an extension also reports its activation in
`modules`. `modules.solution_selling` and `modules.google_workspace` come
from the corresponding `extensions.<name>.active` values in the parsed YAML.
The frontend receives those booleans from bootstrap and still applies the
user's capabilities to actions and navigation. An active extension does not
authorize the user or prove that Google OAuth credentials and consent are
complete. The frontend does not read the YAML directly.

### Assistant variants

`assistant` is always present. `enabled` means that bootstrap found a chat
transport; it does not promise that model inference or every CRM business tool
is operational. Command Center checks the user's access when platform chat
starts.
For an enabled assistant, `display_name` is the exact, nonempty `name` from
this project's Agent Card. When the card is invalid or absent, the unavailable
variant has `display_name: null`.
The runtime is a discriminated union:

| State | `enabled` | `runtime` | `agent_uid` and `environment_uid` | Frontend behavior |
| --- | --- | --- | --- | --- |
| Unavailable | `false` | `null` | `null` | Hide Assistant navigation; CRM stays available. |
| Local Tau | `true` | `{"mode":"local","base_path":"/tau"}` | Both `null` | Use the same-origin Vite proxy to the loopback Tau runtime. |
| Platform Agent | `true` | `{"mode":"platform"}` | Both real, valid UUIDs | Use the existing Command Center AI connection and platform request bridge. |

#### Runtime selection and Agent resolution

The CRM does not configure an assistant mode or Agent identifier in YAML.
Each successful bootstrap selects **one** transport from runtime evidence,
in this order:

1. Read and validate this release's Agent Card. Its exact top-level `name`
   supplies `assistant.display_name` and the name used for platform lookup.
   If the card is absent or invalid, return the unavailable variant.
2. Only in the trusted loopback launch, check the launcher-provided local Tau
   endpoint with a bounded `/ready` probe while preparing bootstrap. Require
   Tau to report `mode: local` and ready, and require the launcher to have
   supplied the same authenticated user session to the API and Tau. If all
   checks pass, return the local variant immediately: `agent_uid` and
   `environment_uid` are `null`, and the frontend talks to `/tau`. No
   platform Agent lookup is needed for this variant.
3. If that trusted local Tau is absent or unready, or if this is a deployed
   API process, resolve the platform variant at runtime. Obtain the actual
   branch Environment UID through the Main Sequence SDK, then find exactly
   one usable Agent in that Environment whose name exactly matches the card
   and whose CodeRepositoryBranch is this project. Return its real Agent and
   Environment UUIDs with `runtime.mode: platform`.
4. If neither transport passes its checks, return the unavailable variant.
   The CRM itself remains usable.

This decision is made for the bootstrap response, not at build time or from
the extension YAML. A local Tau process that starts after API boot can be
selected by a new bootstrap; if it stops, a new bootstrap can select the
platform Agent if one is resolvable. A frontend must reinitialize after a
transport change and must not silently move an existing chat session between
local and platform transports. The local readiness result is fresh for the
bootstrap request. The validated card and a successful platform Agent identity
lookup may be cached for the booted API process; recheck runtime binding before
advertising that cached Agent. Command Center enforces user access when it
starts a platform conversation. Do not cache a
failed platform lookup as a permanent absence. A changed Agent Card requires
restart or redeployment.

Tau `/ready` alone does not identify its user. The API must accept the local
endpoint and session provenance only from the trusted launcher, never from a
browser header or public request parameter. A deployed API never probes
loopback Tau or advertises `/tau`. The frontend never receives the local user
JWT or provider credential. Vite's `/tau/` proxy is development-only and
loopback-bound. The local frontend adapter must speak Tau's documented local
A2A Message/Task or chat contract; it cannot pass null UUIDs to the platform
Agent client.

For the platform path, API runtime resolves the current Organization
Environment UID through the pinned Main Sequence SDK's
`resolve_organization_environment_uid` repository context. This is the
backend-derived Environment of the actual API release branch; the YAML and
browser do not select it. Read the repository's validated Agent Card from the
same release artifact. Within that Environment, resolve the one Agent by the
card's exact top-level `name` using the SDK's Environment-scoped `Agent`
`filter(name=...)` lookup. The resulting Agent UID and resolved Environment
UID fill the platform bootstrap variant. Validate that the Agent belongs to
that exact Environment and this project's CodeRepositoryBranch, that its live
name matches the card, and that it has a bound runtime release. A
local API process without a resolvable branch Environment can still select
local Tau; it cannot claim the platform variant. No Agent name, Agent UID, or
Environment UID is configured in CRM YAML.

If the Agent Card is missing or invalid, Environment resolution fails, the
exact-name lookup returns no Agent or multiple Agents, or the Agent has no
bound runtime release, return the unavailable assistant variant and
report a safe operational diagnostic. Do not choose a same-named Agent from
another Environment or default to production. The core CRM remains available.

Local Tau currently has healthy chat/provider startup but its project CRM
tools still fail closed without trusted caller, policy, and directory binding,
as recorded in [ADR 0003](0003-tau-crm-agent-tools.md). Enabling local chat
does not bypass that boundary. The user interface must not present an
unverified business action as available merely because `assistant.enabled` is
true.

## Implementation and verification

1. Add `config/crm.yaml` to the API repository and release artifact. Parse it
   once at boot with a strict typed schema. Move route mounting and bootstrap
   module flags to that one parsed snapshot, then remove the two extension
   environment switches from local and managed launch configuration.
2. Add and validate the repository Agent Card as a separate Agent deployment
   prerequisite. Implement the bootstrap-time local Tau probe and the
   SDK-backed platform fallback in the order above. Resolve the deployed
   Environment through the Main Sequence SDK at API runtime; read the card
   and resolve exactly one Environment-scoped Agent by its name, verifying
   this project's branch binding. Add a strict, discriminated assistant model
   and embedded readiness to the authored bootstrap contract. Build the
   object server-side from verified request identity and runtime evidence.
   Never return secret values.
3. Replace the frontend's sequential readiness and bootstrap requests with
   one bootstrap request. Keep the progress gate and handle 401, 403, 503,
   retries, and a successful snapshot explicitly.
4. Branch the assistant frontend by runtime mode. The platform branch requires
   valid UUIDs; the local branch uses the same-origin Tau transport with no
   platform Agent UID. An unavailable assistant leaves the rest of CRM usable.
5. Contract-test the serialized bootstrap response and failure envelope in
   local and deployed entrypoints. Verify YAML-to-route/bootstrap agreement,
   missing or malformed configuration, absent or invalid Agent Card,
   missing/ambiguous card-name matches, Environment or branch mismatch,
   Tau ready/unready transitions, user identity
   consistency, and the frontend's one-request startup. Exercise a real local
   chat separately from CRM tool authorization.

**Current delivery status:** The repository loads `config/crm.yaml`, mounts
both extensions from it, and returns `readiness` and `assistant` in bootstrap.
The frontend makes one initialization request and routes local chat through
Tau's A2A Message endpoint. A live local bootstrap selected Tau and reported
both extensions active. A live A2A request reached inference, where this
machine's provider TLS certificate validation failed; a chat reply remains
unverified. The Agent Card and automatic `harness_agent` workflow are declared.
The platform branch has not been verified with a live managed Agent in this
source change. Local chat does not grant CRM tool authorization;
the caller, policy, and directory binding gap in ADR 0003 remains.
