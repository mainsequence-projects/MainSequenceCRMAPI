# Interactions API

`Interaction` is a core CRM conversation record, independent of Solution Selling.
It has a required `company_uid`, optional primary `contact_uid`, and optional
`deal_uid`. The database enforces that a supplied Deal belongs to the selected
Company. The record holds `subject`, `kind` (`call`, `meeting`, `workshop`, or
`email`), `status` (`planned`, `completed`, or `cancelled`), optional scheduled
and occurred instants, and preparation/outcome text.

The mounted endpoints are `GET` and `POST /api/crm/v1/interactions/`, plus
`GET` and `PATCH /api/crm/v1/interactions/{uid}/`. Collection query parameters
are `page_index`, `page_size`, `search`, `company_uid`, `contact_uid`, `deal_uid`,
`kind`, and `status`. Collection responses use `items` and `pageInfo` as in
other CRM lists. Creates use the Pydantic `InteractionCreate` contract; edits
send `{"expected_version": 1, "changes": {…}}` and fail with `409` if the
version or a relationship precondition no longer holds. `GET` requires
`crm.read`; `POST` requires `crm.create`; `PATCH` requires `crm.edit`.

There is no methodology field on Interaction. A Solution Selling diagnosis
references an Interaction separately, when the optional module is enabled.
