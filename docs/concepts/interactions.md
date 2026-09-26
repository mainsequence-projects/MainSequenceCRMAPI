# Interactions

An Interaction records one planned or completed call, meeting, workshop, or
email exchange. It belongs to a Company, may identify one primary Contact,
and may refer to a Deal. It can exist before a Deal. If a Deal is selected,
its Company must match the Interaction's Company; migration `0006` enforces
this with a composite foreign key.

`objective`, `research_notes`, and `discussion_plan` capture preparation.
`outcome_notes` and `next_steps` capture what happened and what was agreed.
`scheduled_at` and `occurred_at` distinguish a plan from the actual event.
The record is core CRM, even when Solution Selling is disabled.

A [Solution Selling diagnosis](../solution_selling_module/adrs/0002-diagnosis-matrix.md)
may later reference an Interaction. Its methodology-specific questions do not
appear on the Interaction itself. See the [Interactions API](../api/interactions.md).
