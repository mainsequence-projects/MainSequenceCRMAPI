# ADR 0003: A Tau agent uses the CRM's governed operations

- **Status:** In progress; managed Agent deployed, trusted caller binding and live tool verification pending
- **Date:** 2026-09-24
- **Scope:** Optional CRM agent runtime and its business tools
- **Sources:** Sibling project's
  `engineering/crm-handoff/specs/09_tau_optional.md` and source lock;
  `ms-tau-sdk` 1.2.8 at pinned release commit
  `1308a65a724ca8bf2e0f02d39a5fbd072cd8eec6`;
  upstream [ADR 0011](https://github.com/mainsequence-sdk/ms-tau-sdk/blob/1308a65a724ca8bf2e0f02d39a5fbd072cd8eec6/docs/adrs/0011-independent-base-tool-and-main-sequence-mcp-exclusion.md)

The repository also contains historical `v4` tags for the earlier
`mainsequence-astro` distribution. The latest tag for the current
`ms-tau-sdk` package is `v1.2.8` at the commit above.

## Context

The CRM has an authenticated FastAPI surface and governed, versioned MetaTable
commands. An assistant should be able to find, create, change, and remove CRM
business records in the same way as a human using the application. Those
capabilities cannot be inferred from a model prompt or from direct table
access. Several resources have specialized lifecycle commands or no write
route yet. The current Tau dependency and separate ASGI entrypoint supply a
runtime, and the project extension now declares tools for implemented service
operations. Calls fail closed until the runtime can supply a trusted CRM
context.

## Decision

Run `ms-tau-sdk` in a separately deployed process through `api.tau.main:app`.
Keep `api.crm.main:app` available if Tau or its provider is unavailable. Put
CRM tool adapters in project-owned `.tau/extensions/`. **`src/crm` is the single
source of truth for every CRM query, command, validation rule, permission
check, version fence, relationship rule, and governed write.** The API and
agent tools are thin adapters around the same application operations. A Tau
tool imports and calls the shared `src/crm` service in its own process; it does
not call a FastAPI route or implement a parallel CRM client/backend.
Install Tau's version-matched coding guidance in `.agents/skills/ms_tau_sdk/`.
Runtime instructions under `.tau/` and coding guidance under `.agents/` have
different purposes.

### Project tools and runtime configuration

Keep `api.tau.main:app` as a standard `create_app()` entrypoint. The deployer
selects its tool profile with the SDK's process settings. For the CRM agent,
set `TAU_EXCLUDE_BASE_TOOLS=true` to omit Tau's `read`, `write`, `edit`, and
`bash`, and `TAU_EXCLUDE_MAINSEQUENCE_MCP=true` to omit Main Sequence MCP
tools, resources, and their prompt. Both settings default to `false` and
apply to either the ASGI entrypoint or the `ms-tau` CLI. In a managed
deployment, put the two nonsecret values in `harness_agent.spec.env_vars`:

```yaml
env_vars:
  - name: TAU_EXCLUDE_BASE_TOOLS
    value: "true"
  - name: TAU_EXCLUDE_MAINSEQUENCE_MCP
    value: "true"
```

Tau composes the tools explicitly registered in this repository's
`.tau/extensions/` with the selected host tool sources. With both exclusions,
the CRM agent's business tools come only from those project extensions. Tau
also retains `task_request_input` and `task_request_authorization` as required
A2A Task controls. The SDK checks the effective catalogue on session load and
extension reload. A prompt or Agent Card does not configure executable tools.
The project extension registers its declared tools and returns `unavailable`
for every valid call while the trusted actor and policy binding described
below is absent. Removing coding tools does not sandbox extension Python
code.

This is a process-wide deployment choice. The CRM API continues as a separate
process and does not inherit the Tau tool settings. A managed deployment still
needs its own Agent identity, provider/model selection, runtime credentials,
exact image, workflow declaration, and release verification; the importable
entrypoint alone does not create or deploy an Agent.

### Shared operation boundary

The target architecture is:

```text
FastAPI route ───────┐
                    ├──> src/crm/services/ (typed queries and commands)
Tau tool adapter ────┘              │
                                   ├──> src/crm/models/ and contracts
                                   └──> src/crm/repositories/ (governed MetaTable access)
```

Each service operation receives a trusted execution context and a typed
request, and returns a typed result or a transport-independent domain error.
The context contains the platform-validated actor and the policy, directory,
catalog, and confirmation evidence needed for that operation. The HTTP or
Tau adapter constructs this context from its own trusted runtime; no
model-visible argument can set any of those values. The service evaluates
the required capability and business preconditions at execution time, then
uses the same repository and atomic command path regardless of caller. A
separate Tau process resolves its own fresh, validated catalog bindings; it
does not borrow in-memory API state.

The wrappers may parse transport input, establish authenticated identity,
invoke the shared operation, and translate its result or error into HTTP or
tool output. They must not normalize business fields, select an owner,
validate relationships, check a version, execute SQL, or decide whether an
archive, merge, move, or transfer is allowed. Confirmation can be collected
by the host workflow, but the shared command must verify trusted confirmation
evidence for any operation that requires it.

The mounted resource, Interaction, Solution Selling, affiliation, board,
merge, settings, and transfer routes now call shared operations in
`src/crm/services/operations.py` and `src/crm/services/transfers.py`.
Normalization, owner eligibility, patch candidate checks, semantic scope
validation, transfer direction authorization, and import row interpretation
live there. `api/crm` retains HTTP request parsing, identity extraction,
response shaping, and error translation. Keep future business decisions in
the shared service; do not make Tau call HTTP helpers or duplicate their
behavior under `.tau/extensions/`.

Each tool accepts a typed, narrow request and returns a typed result or a
bounded, safe error. The model supplies business arguments such as record UID,
field changes, and an observed `expected_version`; it never supplies an actor
UID, permission grant, access token, caller proof, database connection, or
SQL. A trusted adapter obtains the active principal from validated platform
context and calls the shared service; it cannot import a repository to bypass
authorization. A remote agent call must have a real, validated delegated principal and request
provenance. If the runtime cannot establish that context, CRM tools fail
closed. If a future deployment enables Main Sequence MCP, its projected
catalogue remains the source for platform tools. This CRM deployment excludes
that catalogue; project extensions must not manufacture A2A identity or
session proof.

### Tool contract

Tool names use `crm_<resource>_<operation>` (for example,
`crm_contacts_create`), with a distinct
schema for each resource. `list` is paged and filtered; `get` retrieves one
record; `create` uses that resource's Create model; `update` uses its Patch
model and `expected_version`. `archive` represents the CRM's reversible
delete operation and takes an expected version. `restore` is exposed only
where the application supports it. There is no generic tool that takes an
arbitrary table name, arbitrary JSON patch, SQL, or HTTP URL. Collection
reads and all mutations recheck authorization at execution time. Tools
return the resulting record and version when available, so a later action
can use a fresh fence. An uncertain write outcome requires a fresh `get`
before any retry; there is no command receipt or `Idempotency-Key` contract.

| CRM object | Target agent operations | Current HTTP availability / gap |
| --- | --- | --- |
| Contact | `list`, `get`, `create`, `update`, `archive`, `restore`; `merge_preview`, `merge` | CRUD endpoints are mounted. Merge has its own reviewed, versioned command. |
| Company | `list`, `get`, `create`, `update`, `archive`, `restore` | Mounted routes; archiving must honor related-record rules. |
| Deal | `list`, `get`, `create`, `update`, `archive`, `restore`; `move` | Mounted routes. Move uses deal and board versions; pipeline/stage cannot be changed by a generic patch. |
| Task | `list`, `get`, `create`, `update`, `archive`; `complete`, `reopen` | Mounted routes. Restore is not mounted; add a governed restore contract before exposing `restore`. |
| Note | `list`, `get`, `create`, `update`, `archive`, `restore` | Mounted routes; authorship remains server supplied. |
| Tag | `list`, `get`, `create`, `update`, `archive`, `restore` | Mounted routes. |
| Contact affiliation | `list`, `get`, `create`, `update`; `transition_company` | Mounted under Contact. No removal/archive contract yet; define one that preserves history before exposing it. |
| Interaction | `list`, `get`, `create`, `update` | Core mounted routes. Archive/restore need governed commands and HTTP contracts. |
| Pipeline | `list`, `get`, `create`, `update`, `archive`, `restore`; `board`, `stages` | Only collection, board, and stage reads are mounted. The proposed write tools require new governed application operations. |
| Stage | `list`, `get`, `create`, `update`, `archive`, `restore`; `reorder` | Stage reads are mounted through Pipeline. All writes require application contracts; removal must protect Deals and board ordering. |
| Solution Selling lead, prospecting profile, prompter, assessment, diagnosis | For each: `list`, `get`, `create`, `update`, `archive`, `restore`; prompter also `render_preview` | Five collections have list/get/create/update routes only when the module is enabled. Archive/restore require new governed contracts; embedded values are edited through their parent record. |
| Activity | `list`, `get` | Derived history is read only. The agent creates activity through authorized business commands, never direct CRUD. |
| Singleton settings | `get`, `update` | One settings record; no create or delete. Updates use the mounted versioned settings command. |
| Principal directory | `list` | Platform identity is read only; no CRM user CRUD. |
| Source connection | `list`, `create` | Existing file-source routes only. Update/disconnect needs a separate credential-safe contract. |
| Import/transfer job | `list`, `get`, `create_import`, `upload_file`, `save_mapping`, `validate`, `get_plan`, `commit`, `get_issues`, `cancel`, `retry` | A durable workflow, not generic CRUD. Commit needs an explicit plan review and current plan hash; `202` does not mean completed. |
| Export job | `create_export`, `get`, `download`, `cancel`, `retry` | Export creation/download are not mounted. Do not advertise these tools until the deterministic API and worker are released. |

The HTTP column records which capabilities are mounted today; it is not the
agent's call path. Both transports must invoke the same `src/crm` operation.
The target inventory covers every current CRM business object. Read only
resources and singleton settings have intentionally narrower lifecycles.
Email and phone methods, social links, diagnosis cells, key-player pains,
pain-chain links, and import mappings are value types within their parent
records or workflows; they are edited through those typed parent contracts,
not through independent generic CRUD tools.
For resources with missing archive/restore support, complete the CRM service,
governed atomic command, typed HTTP contract, and tests first, then register
the corresponding agent tool. Hard delete is not a default CRM operation.

### Authorization and confirmation

Use the application's capabilities: `crm.read` for business reads,
`crm.create` for ordinary creates, `crm.edit` for patches and transitions,
and `crm.archive` for archive/restore. Transfer operations retain their
direction-specific capabilities. The optional Solution Selling flag limits
which tools are registered; it grants no permission. Tool availability must
be derived from registered shared operations, module configuration, and the
principal's policy, not a static claim in a prompt.

Before merge, archive, bulk mutation, import commit, or another destructive
or externally consequential action, show a concrete proposal with targets,
field changes, expected versions, and likely effects. Execute only after the
applicable user confirmation is recorded by the host workflow. A draft or
model statement is not approval. A normal single-record create or patch may
execute under a user's explicit request and capability, while still using
the same version and validation checks as the UI. Never hide a write inside
a read, preview, render, or search tool.

### Failure and rollout

Expose 401/403, validation, missing-record, stale-version, and readiness
failures as distinct safe tool outcomes. A 409 requires rereading and a new
decision, not blind replay. Propagate cancellation to the runtime and avoid
claiming a canceled request rolled back a command that may have committed.
Do not persist credentials, caller proof, or whole CRM records in prompts or
diagnostic logs. Keep result pages bounded and redact fields according to the
same policy as the CRM API.

Implement the catalogue in slices: the shared `src/crm` operations and HTTP
adapters for mounted behavior are in place. The `.tau/extensions/crm.py`
extension declares 46 typed tools with the optional module disabled: core
list/get/create/update, Activity and Pipeline reads, Interaction CRUD,
affiliations, settings, task completion, deal movement, and merge preview.
It adds 20 Solution Selling tools when that module is enabled. The extension
uses `api/tau/crm_tools.py` to translate schema input and safe results; it
calls only `CRMOperations`. Mutation tools run sequentially and report an
unknown outcome if cancellation arrives during an in-flight write. Tool
output is capped at 128,000 characters; an oversized result asks the agent to
narrow its query. Archive, restore, merge execution, transfer commit, and
other destructive commands
remain unregistered pending shared confirmation verification. Missing CRM
lifecycle operations also remain unregistered. For each slice, run the same
behavior cases through the API and
the agent adapter to prove that they share one domain implementation. Verify
denied access, stale versions, atomic
rollback, uncertain-response reread, cancellation, disabled-module behavior,
and CRM availability with Tau stopped. Live platform and provider behavior
remain unverified until exercised in a deployed environment.

## Consequences

The latest SDK release commit and separate Tau runtime entrypoint can be
installed and imported now. The shared service and HTTP adapters are
implemented and tested locally. The project tools are registered but do not
make an operational CRM agent: the installed Tau extension API exposes session
details but no validated per-turn CRM actor and policy context to project
tools. Each call therefore fails closed in the current entrypoint. Confirmation flow, missing
CRM lifecycle operations also need implementation and verification. A managed
Agent release deployed on 2026-09-26, but its CRM tool context and a live
conversation remain unverified. The two A2A Task controls remain present even with both tool
exclusions. This decision avoids a second CRM backend and preserves the
platform's identity and policy authority.
