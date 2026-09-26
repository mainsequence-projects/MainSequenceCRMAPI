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
