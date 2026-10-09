# CRM application MCP

`POST /mcp` serves authenticated, stateless Streamable HTTP with JSON responses.
It implements MCP initialization, `tools/list` and `tools/call`. This endpoint
is not public ingress and is outside the REST OpenAPI route index. The Main
Sequence SDK rejects other methods and unapproved browser Origins.

The catalogue is built from the same typed models as the CRM service. It has
66 tools (35 reads, 31 writes) with Solution Selling active, or 46 tools when
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

Hosted business calls require the verified requester; the agent workload is
not an alternative actor. Local calls use verified direct Bearer identity,
supplied by the loopback launcher for the local bridge. Both paths use
`CRMOperations` and the existing policy/directory, validation, version fences,
and governed repository writes. See [identity conventions](conventions.md).
Missing policy or directory wiring returns `unavailable`.

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
