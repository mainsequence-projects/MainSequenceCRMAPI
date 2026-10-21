# Companies

A company represents an organization in the CRM. It can be linked from
[contacts](contacts.md) and [deals](deals-pipelines.md). A company is not a
tenant, login, or permission group. Authorization comes from the platform.

Creation requires a nonblank name after trimming. Optional fields include an
owner, sector key, size category, website and LinkedIn URLs, phone, address,
description, tax identifier, context links, and logo reference. The normalized
domain is stored for matching and is not a user-editable create field. Read
responses include nonnegative integer contact and deal counts as projections,
displayed as numeric columns in the company list. `contact_count`
counts distinct, non-archived contacts with a current affiliation, whether or
not this company is their primary one.

The optional address is stored as separate `address` (street/address text),
`zipcode`, `city`, `state_abbr`, and `country` fields, not a nested object.
Company Overview displays each recorded value and marks missing values as
"Not provided". The relationship owner is a responsible CRM teammate, not a
legal owner or parent company; an unassigned owner is displayed explicitly.

Company edits use the same expected-version and nonempty-change rules as other
resources. Archiving marks the company; it is not a cascade delete of related
people, their affiliation history, or opportunities. Existing history stays
visible after archival; new affiliations require an active company.

See the [company API](../api/contacts-companies.md) for collection and command
paths.
