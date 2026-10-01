# Interactions API

`Interaction` is a core CRM conversation record. Creates require `subject`,
`kind`, `status`, and a nonempty `participants` array. Each participant accepts
`contact_uid`, `email`, `display_name`, and `role` (`organizer` or `attendee`);
at least one identity field is required. Duplicate identities and links to
archived or missing Contacts are rejected. `company_uid` is optional.
Supplying `deal_uid` requires its matching `company_uid`. Preparation,
outcome, and scheduled/occurred fields are optional.

The mounted endpoints are `GET` and `POST /api/crm/v1/interactions/`, plus
`GET` and `PATCH /api/crm/v1/interactions/{uid}/`. Collection query parameters
are `page_index`, `page_size`, `search`, `company_uid`, `contact_uid`, `deal_uid`,
`kind`, and `status`. `contact_uid` finds Interactions with that linked
participant Contact. Collection responses use `items` and `pageInfo`.
Edits send `{"expected_version": 1, "changes": {…}}` and fail with `409`
if the version or a relationship precondition no longer holds. A patch may
replace `participants` but may not clear it. `GET` requires `crm.read`, `POST`
requires `crm.create`, and `PATCH` requires `crm.edit`.

Migration `0009` removes the old top-level `contact_uid` field. Existing
pre-migration rows with no Contact may read with an empty participant list;
their next edit should add a person. See the [model decision](../crm_core/adrs/0001-interaction.md).
