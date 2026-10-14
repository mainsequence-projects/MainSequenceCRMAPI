# Solution Selling module

This section holds the module's architecture decisions. The module's HTTP
routes are documented separately in the [Solution Selling API](../api/solution-selling.md).

The module's proposed models are:

- [ADR 0001: Simple assessment model](adrs/0001-simple-assessment-model.md) —
  one maintained assessment for a Deal, including a direct Company foreign key.
- [ADR 0002: Diagnosis matrix](adrs/0002-diagnosis-matrix.md) — one diagnosis
  for a particular Interaction and Contact, with an embedded 3 × 3 question
  matrix.
- [ADR 0003: Key players and pain chain](adrs/0003-key-players-pain-chain.md) —
  opportunity-specific pains for existing Contacts and directed links between
  those pains, embedded in the assessment. It amends ADR 0001's original
  free-text `pain_chain` field.
- [ADR 0004: Prospecting profiles](adrs/0004-prospecting-profiles.md) —
  reusable market-context role–pain knowledge and suggested approaches,
  distinct from findings about a named Contact.
- [ADR 0005: Lead list](adrs/0005-lead-list.md) — one prospecting record for
  a selected existing Contact, with optional profile and next Task references.
- [ADR 0006: Reusable prompters](adrs/0006-reusable-prompters.md) — one
  Jinja template model rendered with authorized CRM context supplied for
  each use; it does not store a Contact or send a message.

The five module-owned records are implemented as Pydantic contracts and
SQLAlchemy-authored MetaTables under migration `0006`. Set
`extensions.solution_selling.active: true` in `config/crm.yaml` to mount their
routes and show the module in navigation. Disabling it does not remove data. General
cross-profile pain-chain links described in ADR 0004 remain deferred; they
do not have a storage shape or API in this release.

The Lead list identifies each person by Contact name and shows the Contact's
current primary Company. The same labels appear in Lead details and reference
pickers. These are live read projections from the existing MetaTables, not a
second person record or a new Company relationship stored on the Lead. A
Contact without a primary Company remains visible as **No company**. This
Company label does not select the Company used for prompter rendering; that
choice remains explicit for each draft.

The opportunity form can search for an existing Deal or quick-add one. Quick-add
can also create the Company if needed. It creates a normal core CRM Deal first,
then selects it and its Company in the assessment draft. The assessment is a
separate save; cancelling it does not
delete the Deal or a Company created along the way. See
[Deals and pipelines](../concepts/deals-pipelines.md).

Creating an assessment requires the Deal and its matching Company only. The
`key_players` and `pain_chain` lists may be empty; their per-entry assessment
statuses apply only after an entry is added. The frontend keeps those optional
methodology details in the existing assessment's Edit view.

The [Interaction model](../crm_core/adrs/0001-interaction.md) belongs
to core CRM, not this module. An assessment may draw on conversations linked
to the same Deal, without an Interaction foreign key to Solution Selling.

## Prompter lifecycle

Prompters can be deleted in explicitly selected batches through the Command
Center list's bulk action. Deletion archives the template, preserving its
activity history while excluding it from active reads and rendering. All
selected versions must still match; one stale or missing record blocks the
whole batch. The action requires `crm.archive` and does not delete Contacts,
Companies, Interactions or previously rendered text. See the
[HTTP contract](../api/solution-selling.md#prompter-bulk-deletion).

## Assistant workflow

### Prospecting outreach

The `crm-prospecting` usage skill owns the complete outreach workflow:

1. Resolve the actual Company before creating a prospecting Contact. Reuse an
   existing Company or create it from established business facts, then pass its
   confirmed UID when saving the Contact. An unknown or unresolved Company
   blocks Contact creation. Reuse an existing Contact and inspect its relevant
   affiliations; then resolve the existing Lead.
2. Read the indicated prompter, or create a reusable Jinja prompter first when
   none is indicated. Every prospecting introduction, follow-up and conversation
   preparation uses a saved prompter and the renderer.
3. Render the personalized text and present it as an unsaved draft. Required
   template creation does not also authorize saving a Lead, Interaction or Task.
4. Establish actual delivery or occurrence before recording completed outreach.
   The CRM MCP does not send messages; a requested future Interaction remains
   `planned` until the event happens.
5. When recording is requested, save the actual Interaction and update the
   Lead's progress with fresh versions. The Contact participates in the
   Interaction; neither record has a typed prompter link.
6. Save a requested follow-up Task on the Contact and separately link its
   confirmed UID as the Lead's next Task. Qualification and Deal creation remain
   separate decisions.

One suitable prompter can be rendered for multiple people in a requested batch.
Research-only requests and Lead administration do not create templates.
When logging past outreach, preserve the actual text and event details; a
template created later does not establish how that past message was authored.
See the [MCP usage pack](../api/mcp.md#crm-usage-skill-pack) for tool routing and
the [render contract](../api/solution-selling.md) for supported context.

### Discovery evidence

The assistant discovers the module's typed MCP tools. Use prospecting profiles
as hypotheses, render outreach as a draft, record the actual Interaction, and
prepare its diagnosis questions before saving answers deliberately. The Deal
context helper reads the maintained assessment and a bounded Interaction page.
Key-player and pain-chain statuses remain `hypothesis`, `reported`, or
`confirmed` until an explicit assessment update changes them. No read helper
confirms evidence or propagates answers. See the
[workflow helper contracts](../api/solution-selling.md#read-only-workflow-helpers).
