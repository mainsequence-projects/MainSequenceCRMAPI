# Interactions

An Interaction records one planned or completed call, meeting, workshop, or
email exchange **between people**. It has one or more participants; each may
link to a CRM Contact or be identified by an email or name. An imported
Calendar attendee does not automatically become a Contact.

Company is optional context. A Deal is optional, but requires its Company
when selected. Neither Company nor Contact affiliation is inferred from the
participants. `objective`, `research_notes`, and `discussion_plan` capture
preparation; `outcome_notes` and `next_steps` capture what happened and what
was agreed. `scheduled_at` does not imply completion.

Migration `0009` moves the previous single `contact_uid` into the participant
list and makes `company_uid` nullable. The record remains core CRM when
Solution Selling is disabled. A [Solution Selling diagnosis](../solution_selling_module/adrs/0002-diagnosis-matrix.md)
may reference an Interaction. See the [ADR](../crm_core/adrs/0001-interaction.md)
and [Interactions API](../api/interactions.md).
