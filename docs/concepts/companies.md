# Companies

A company represents an organization in the CRM. It can be linked from
[contacts](contacts.md) and [deals](deals-pipelines.md). A company is not a
tenant, login, or permission group. Authorization comes from the platform.

Creation requires a nonblank name after trimming. Optional fields include an
owner, sector key, size category, website and LinkedIn URLs, phone, address,
description, tax identifier, context links, and logo reference. The normalized
domain is stored for matching and is not a user-editable create field. Read
responses include contact and deal counts as projections. `contact_count`
counts distinct, non-archived contacts with a current affiliation, whether or
not this company is their primary one.

Company edits use the same expected-version and nonempty-change rules as other
resources. Archiving marks the company; it is not a cascade delete of related
people, their affiliation history, or opportunities. Existing history stays
visible after archival; new affiliations require an active company.

See the [company API](../api/contacts-companies.md) for collection and command
paths.
