# CRM application MCP

`POST /mcp` serves authenticated, stateless Streamable HTTP with JSON responses.
It implements MCP initialization/discovery, `tools/list`, `tools/call`,
`skills/list`, `skills/get` and `resources/read`. This endpoint
is not public ingress and is outside the REST OpenAPI route index. The Main
Sequence SDK rejects other methods and unapproved browser Origins.

The catalogue is built from the same typed models as the CRM service. It has
70 tools (39 reads, 31 writes) with Solution Selling active, or 46 tools when
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
with `{code, data?, message?, diagnostics?}`; errors set `isError: true`. Codes include `ok`,
`invalid_arguments`, `validation_error`, `forbidden`, `not_found`, `conflict`,
`unavailable`, `internal_error`, and `result_too_large`. Invalid inputs and
internal exceptions are redacted. Serialized business results exceeding
128,000 characters are replaced by a short error; page sizes remain capped at
100. A tool declares a 60-second client timeout through MCP metadata.

### Request diagnostics

Registered business tool errors include `diagnostics.request_uid`, a server-generated UUID
matching the CRM request and tool logs. When an instrumented stage raises,
`diagnostics.failed_stage` identifies `identity`, `permissions`, `catalog` or
`metatables`. The compact `result_too_large` error omits diagnostics. Successful
business envelopes retain their existing shape. Clients must preserve the
business error envelope, including its code and request reference.

The `src.crm.platform.diagnostics` logger emits `crm.mcp.tool.started`,
`crm.mcp.stage.started`, `crm.mcp.stage.completed` and
`crm.mcp.tool.completed` events. Start events identify an in-progress stage
even before a stalled call finishes. Completion events include elapsed
milliseconds; tool completion includes the business result code, failed stage
and accumulated per-stage durations. Catalog events report whether bindings
were already cached, without changing catalog or permission caching behavior.

`identity` measures CRM admission and effective-person context construction
after SDK request verification. `permissions` measures fresh capability
evaluation; `catalog` measures binding resolution; `metatables` measures the
governed operation's client round trip. These timings exclude plugin startup,
token exchange, SDK request verification and MCP discovery; they do not claim
to measure database execution alone.

Unavailable and unexpected failures log bounded exception types and stack
locations, plus an upstream HTTP status and UUID request ID when available.
Logs exclude exception messages, source lines, locals, tool arguments, record
contents, SQL, parameters, response bodies, URLs and credentials. Public error
messages remain redacted; exception details stay in protected runtime logs.

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

The hosted adapters evaluate only the requester's signed admin flag and fresh
SDK Team-membership lookup on a delegated call, never the agent's facts. A direct
human uses its own identity and memberships. Each non-admin check uses
`in_teams(..., max_age_seconds=0)`; lookup failures cannot reuse cached access or
borrow workload rights. Owner selection in a delegated tool is limited to the requester; another
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

## CRM usage skill pack

The five authored business skills live under `.agents/skills/mainsequence_crm/`:

| Skill | Primary tools | Business workflow |
| --- | --- | --- |
| `crm-core` | 37 | Contacts, Companies, affiliations, Notes, tags, activity, Tasks, Interactions, owner selection, settings and Contact merge previews. |
| `crm-deals` | 9 | Deal records, pipeline metadata, stages, boards and versioned moves. |
| `solution-selling/crm-prospecting` | 8 | Prospecting profiles and the required-prompter outreach workflow, actual Interaction recording, Lead state and linking the next Contact Task. |
| `solution-selling/crm-prompters` | 6 | Template maintenance, subject/body rendering and validation of edited unsaved drafts. |
| `solution-selling/crm-discovery` | 10 | Diagnosis preparation and records, Deal assessments and Solution Selling context. |

The allocation covers all 70 business tools exactly once; workflows can reuse
another skill's operations. With Solution Selling disabled, the 46 core/Deal tools
remain. Simple record operations stay grouped in core; separate skills cover
the workflows with distinct decisions and evidence requirements.

`crm-core/references/tool-map.json` records the exact primary allocation.
`crm-core/references/mcp-usage.md` centralizes discovery, effective-user permissions,
paging, version fences, business result interpretation and uncertain-write
recovery. A prompter reference documents supported Jinja context and an example.
Cross-skill links use published `skill://` URIs; references within a skill
use relative paths. The API and static
repositories contain identical usage packs; repository development skills stay
in their separate namespace. `tests/test_crm_skill_pack.py` checks catalogue
coverage with the module enabled and disabled, tool references and pack links.

These instructions apply to advertised CRM MCP operations, including direct
clients and generic discovery/call bridges. They follow the connected tool
schemas, effective permissions and actual business results. They do not grant
tool access, claim a draft was saved, or promise unsupported commands. Prompter
requirements are currently inferred from the retrieved template; there is no
server requirements-discovery tool.

Before saving a new prospecting Contact, the prospecting skill resolves or
creates its actual Company and passes the confirmed UID in
`payload.company_uid`. Unknown or unresolved Companies block that Contact
creation; the workflow does not save an unlinked Contact for later repair.
This prerequisite also appears in core Contact guidance for prospecting work.

The prospecting skill requires a persisted prompter for introductions,
follow-up messages and conversation preparation. It reads an indicated
prompter; when none is indicated, it creates one before rendering. The workflow
then distinguishes the unsaved draft, actual delivery, requested Interaction
recording, Lead progress and follow-up Task linking. Required template creation
does not authorize sending or other record saves. The current MCP has no
delivery tool, and neither Lead nor Interaction has a typed prompter reference.
These are agent workflow requirements. The record API contracts are unchanged;
they have not gained a prospecting-specific Company or template requirement,
or automatic outreach logging.

Repository implementation and maintenance skills live separately under
`.agents/skills/mainsequence_crm_development/`. Only the business usage folder
is published; development skills are excluded.

## SDK skill publication

Main Sequence 9.0.23 includes `mainsequence.server.mcp_skills.skills_extension`
and version-matched publishing instructions in its `api_surfaces` skill. With
MCP Python SDK 2.x, the CRM server installs it using:

```python
from mcp.server.mcpserver import MCPServer
from mainsequence.server.mcp_skills import skills_extension

mcp = MCPServer("crm", extensions=[skills_extension(".agents/skills/mainsequence_crm")])
```

The implementation subclasses `MCPServer`'s public tool methods to preserve
the existing CRM catalogue and strict, redacted business validation. The SDK
owns skill discovery, manifests and resource serving. `install_mcp` mounts its
stateless HTTP app after request identity. A request-scoped binding retains
the owning FastAPI application and its CRM services while the nested MCP app
handles the protocol; it never supplies or replaces a caller identity.

The publisher reads the selected folder directly at application creation;
there is no generated package or second publication folder:

```text
.agents/skills/mainsequence_crm/
  crm-core/
    SKILL.md
    references/mcp-usage.md
    references/tool-map.json
  crm-deals/SKILL.md
  solution-selling/
    crm-prospecting/SKILL.md
    crm-prompters/
      SKILL.md
      references/template-context.md
    crm-discovery/SKILL.md
```

Each skill's frontmatter name matches its folder. Group names use hyphens;
supporting files belong to a skill. Shared guidance is stored and served once
from `crm-core`, at `skill://crm-core/references/mcp-usage.md`. The three module
skills have URIs such as `skill://solution-selling/crm-prompters/SKILL.md`.
Relative folder resolution is independent of the process working directory.
Changes to the pack take effect after restarting the API.

Clients discover `io.modelcontextprotocol/skills` through modern MCP discovery,
list skills with `skills/list`, get a manifest with `skills/get` and read its
files with `resources/read`. Legacy 2025-11-25 initialization omits extension
capabilities, but the registered skill methods and file reads are available.
Manifests contain the byte size and SHA-256 digest of every served file.
Unpublished files and unknown URIs return MCP errors.

All five skills remain published when Solution Selling is disabled. Its tools
then disappear from `tools/list`; skill presence does not enable a module.
Discovery and file reads require the same verified HTTP identity and permitted
Origin as tools. They expose authored instructions, require no CRM database
readiness and grant no business permissions. Every business operation retains
its effective-person capability checks.

In-process tests exercise the actual CRM application with local Bearer and
signed hosted caller verification, all five manifests, all eight file digests,
published links, denied unauthenticated reads, URI isolation, module activation
and modern client discovery. Hosted release availability remains unverified
until these changes are deployed; no deployment or push was performed.

## Solution Selling read workflows

When the module is active, `crm_prompters_render`, `crm_prompters_validate`,
`crm_solution_selling_context_get`, and `crm_diagnoses_prepare` require
`crm.read`. They share the REST service and never persist or dispatch drafts.
Their inputs and results are described in the
[Solution Selling API](solution-selling.md). The five module resources retain
their existing list/get/create/update tools. Lists advertise only their own
UUID or text filters; unknown filter keys fail input validation.

Prompter create/update tool schemas include optional `subject_template` and the
typed `constraints` object. Render retains `data.text` and adds optional subject,
separate counts/limits, `is_valid` and per-field violations. Business-limit
violations are successful read results (`code: ok`, `isError: false`) with
`is_valid: false`; inspect that flag before presenting a draft as validated.
`crm_prompters_validate` takes `{uid, payload: {text, subject}}`, reads current
saved limits and validates manual edits without Jinja, persistence or dispatch.

Context includes the assessment's existing evidence statuses and a bounded
Interaction page, with source UIDs and versions. It is a composition of reads,
not an atomic snapshot. Preparing a diagnosis copies profile questions with
empty answers; its business issue is explicitly a hypothesis. Saving a diagnosis
or updating an assessment remains a separate, explicitly requested command.


### Human directory projections

The platform may omit `identity_type` from a human directory response. An
omitted value does not establish human identity. In that case MCP admission
uses `User.filter(uid=caller.uid, identity_type="human")` within
`reads_as_caller()` and requires exactly one matching UID with `is_active`
true. Empty, mismatched, duplicate or inactive results are denied; lookup
errors fail closed. Explicit workload types still require delegation. The
effective person's signed capability checks remain unchanged.
