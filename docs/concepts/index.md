# Domain map

The CRM tracks people, organizations, opportunities, follow-up work, and their
history in the CRM application. Platform identity and policy govern access;
the application does not define a workspace or tenant record.

| Concept | Relationship | Details |
| --- | --- | --- |
| [Contact](contacts.md) | May have multiple dated company affiliations; may have tags, tasks, notes, and deals | A person with names and/or email methods |
| [Company](companies.md) | May have contacts and deals | An organization record, not an account or login |
| [Deal](deals-pipelines.md) | Belongs to a pipeline and stage; may link a company and contacts | A currency-specific opportunity |
| [Task](tasks-notes.md) | Belongs to a contact | Follow-up work with explicit completion state |
| [Interaction](interactions.md) | Records participants; may reference a company and deal | Preparation and outcome of one conversation |
| [Note](tasks-notes.md) | Belongs to exactly one contact or deal | Time-stamped narrative with server-owned authorship |
| [Prompt](prompts.md) | Independent core library document | Fixed Markdown instructions to read, edit, and copy |
| [Tag](tags-activity.md) | May label contacts | Reusable classification with a semantic tone |
| [Activity event](tags-activity.md) | Refers to an entity and command | Read-only audit history |
| [Transfer](transfers.md) | Belongs to an initiating principal | Durable import/export job state |

The optional [Solution Selling module](../solution_selling_module/index.md)
adds prospecting leads and profiles, Deal assessments, Interaction diagnoses,
and reusable prompters. It extends rather than replaces Contact, Company,
Deal, Task, or Interaction.

The optional [Campaigns module](campaigns.md) defines a live DAG of task
definitions, each accompanied by a specialized Agent Prompt, and tracks
existing CRM Task instances for each enrolled Contact, with stable per-Contact
prompt assignments and descriptive A/B comparisons.

A [prompter](../solution_selling_module/index.md#prompter-lifecycle) keeps a
reusable body template, an optional subject template and optional independent
character limits. Its kind is an open purpose label. Rendering personalizes
both parts from explicitly selected records; preview validation reports excess
characters without truncating, saving or sending the draft.

Optional modules expose their API routes below `/extensions/<module>/` and
mount only when enabled by the API process. Google Workspace uses
`/extensions/google/`; Solution Selling uses `/extensions/solution-selling/`;
Campaigns uses `/extensions/campaigns/`.
The general Interaction model stays in the core CRM API.

Records have stable UUIDs and relationships to other CRM records. Versions protect edits from
overwriting newer data. Archive is a marker, not a general permanent delete.
The [API conventions](../api/conventions.md) explain how those rules appear on
the wire.

The optional assistant follows the same model and version rules. Its target
tool catalogue and current gaps are recorded in
[ADR 0005](../crm_core/adrs/0005-crm-application-mcp.md). REST and the API-owned
MCP tools share the operations in `src/crm`. Hosted operations check the
effective person's fresh SDK Team-membership lookup or signed Organization
admin status on every call. The assistant's storage or platform permissions do not
authorize a person. A delegated call can select that person as owner; direct
requests can also select active human owners visible in the caller's directory.
The CRM agent excludes Tau's coding tools and broad Main Sequence MCP while
retaining application MCP and the SDK's A2A Task controls.
The runtime's [CRM conversation directives](../crm_core/adrs/0003-tau-crm-agent-tools.md#runtime-answer-and-prompt-boundary)
are in `.tau/SYSTEM.md`. They define the assistant's CRM role and response
style independently of the intentionally restricted tool profile.

[ADR 0004](../crm_core/adrs/0004-single-bootstrap-and-assistant-runtime.md)
defines one CRM initialization snapshot that reports active modules and the
assistant's local or platform runtime. The API now returns that snapshot. A
trusted local Tau process takes precedence; otherwise the SDK resolves a
managed Agent in the branch Environment. Missing assistant runtime leaves the
core CRM available.
