# CRM application MCP

`POST /mcp` serves authenticated, stateless Streamable HTTP with JSON responses.
It implements MCP initialization, `tools/list` and `tools/call`. This endpoint
is not public ingress and is outside the REST OpenAPI route index. The Main
Sequence SDK rejects other methods and unapproved browser Origins.

The catalogue is built from the same typed models as the CRM service. It has
69 tools (38 reads, 31 writes) with Solution Selling active, or 46 tools when
disabled. Tool names retain `crm_<resource>_<operation>`. Discover the exact
schema through `tools/list`; for example:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "crm_contacts_create",
    "arguments": {"payload": {"first_name": "Ada", "emails": []}}
  }
}
```

The call result contains `content` JSON text and matching `structuredContent`
with `{code, data?, message?}`; errors set `isError: true`. Codes include `ok`,
`invalid_arguments`, `validation_error`, `forbidden`, `not_found`, `conflict`,
`unavailable`, `internal_error`, and `result_too_large`. Invalid inputs and
internal exceptions are redacted. Serialized business results exceeding
128,000 characters are replaced by a short error; page sizes remain capped at
100. A tool declares a 60-second client timeout through MCP metadata.

Hosted business calls use the verified requester when a workload is delegated
to serve a person. A direct hosted caller has no requester: the API looks up
that caller through the caller-scoped platform directory and admits it only
when the record is active and `human`. An unbound workload remains denied,
including one with privileged Team memberships. Local calls use verified direct
Bearer identity, supplied by the loopback launcher for the local bridge. Every
admitted call rechecks the effective person's capability through
`CRMOperations`; authentication never grants a CRM capability. See [identity
conventions](conventions.md). Missing policy or directory wiring returns
`unavailable`.

The hosted adapters evaluate only the requester's signed Team/admin facts on a
delegated call, never the agent's facts. A direct human uses its own signed
facts. Owner selection in a delegated tool is limited to the requester; another
owner returns `validation_error` without querying the workload's directory.
Safe denial logs include the tool, request correlation, identity mode, denial
reason, and—when policy rejects the call—the required capability. They never
include credentials, assertions, or tool arguments. See [the authorization
amendment](../crm_core/adrs/0005-crm-application-mcp.md).

Archive/restore, merge execution and import commit are absent. Merge preview,
ordinary typed create/update, task completion/reopen, pipeline reads, deal
moves, settings and the enabled module operations remain available. A missing
tool name returns `not_found`. MCP annotations describe behavior; they never
grant permission or substitute for confirmation.

There is no write replay contract. A timeout, cancellation or lost response
may follow a committed write. Read the record before retrying. The local bridge
reports `outcome_unknown` when a sent call loses its response, and never retries
it automatically. Tau's hosted transport is SDK-owned and must likewise be
treated as uncertain when it reports a failed call.

## Solution Selling read workflows

When the module is active, `crm_prompters_render`,
`crm_solution_selling_context_get`, and `crm_diagnoses_prepare` require
`crm.read`. They share the REST service and never persist or dispatch drafts.
Their inputs and results are described in the
[Solution Selling API](solution-selling.md). The five module resources retain
their existing list/get/create/update tools. Lists advertise only their own
UUID or text filters; unknown filter keys fail input validation.

Context includes the assessment's existing evidence statuses and a bounded
Interaction page, with source UIDs and versions. It is a composition of reads,
not an atomic snapshot. Preparing a diagnosis copies profile questions with
empty answers; its business issue is explicitly a hypothesis. Saving a diagnosis
or updating an assessment remains a separate, explicitly requested command.
