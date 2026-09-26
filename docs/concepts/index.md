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
| [Interaction](interactions.md) | Belongs to one company; may reference a primary contact or deal | Preparation and outcome of one conversation |
| [Note](tasks-notes.md) | Belongs to exactly one contact or deal | Time-stamped narrative with server-owned authorship |
| [Tag](tags-activity.md) | May label contacts | Reusable classification with a semantic tone |
| [Activity event](tags-activity.md) | Refers to an entity and command | Read-only audit history |
| [Transfer](transfers.md) | Belongs to an initiating principal | Durable import/export job state |

The optional [Solution Selling module](../solution_selling_module/index.md)
adds prospecting leads and profiles, Deal assessments, Interaction diagnoses,
and reusable prompters. It extends rather than replaces Contact, Company,
Deal, Task, or Interaction.

Optional modules expose their API routes below `/extensions/<module>/` and
mount only when enabled by the API process. Google Workspace uses
`/extensions/google/`; Solution Selling uses `/extensions/solution-selling/`.
The general Interaction model stays in the core CRM API.

Records have stable UUIDs and relationships to other CRM records. Versions protect edits from
overwriting newer data. Archive is a marker, not a general permanent delete.
The [API conventions](../api/conventions.md) explain how those rules appear on
the wire.

The optional assistant follows the same model and version rules. Its target
tool catalogue and current gaps are recorded in
[ADR 0003](../crm_core/adrs/0003-tau-crm-agent-tools.md). The agent runtime is
installed and declares typed CRM business tools. The API and agent
adapters share the operations in `src/crm` as their single business source.
Mounted HTTP routes now use that source; Tau CRM calls return `unavailable`
until the runtime supplies a trusted principal, policy, and directory. A CRM agent deployment can exclude Tau's coding
tools and Main Sequence MCP through runtime settings, leaving project-declared
business tools and the SDK's A2A Task controls.

[ADR 0004](../crm_core/adrs/0004-single-bootstrap-and-assistant-runtime.md)
defines one CRM initialization snapshot that reports active modules and the
assistant's local or platform runtime. The API now returns that snapshot. A
trusted local Tau process takes precedence; otherwise the SDK resolves a
managed Agent in the branch Environment. Missing assistant runtime leaves the
core CRM available.
