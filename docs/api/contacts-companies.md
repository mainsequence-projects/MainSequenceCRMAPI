# Contacts and companies API

See the [contact](../concepts/contacts.md) and
[company](../concepts/companies.md) concepts for domain meaning. Every path
below is under `/api/crm/v1/`.

## Contacts

| Method | Path | Body / behavior |
| --- | --- | --- |
| `GET` | `contacts/discovery/` | Read controls and columns; `crm.read` |
| `GET` | `contacts/` | Paged collection; `crm.read` |
| `POST` | `contacts/` | `ContactCreate`, `201`, `crm.create` |
| `GET` | `contacts/{uid}/` | Detail; `crm.read` |
| `PATCH` | `contacts/{uid}/` | `ContactPatch`; `crm.edit` |
| `POST` | `contacts/{uid}/archive/` | `{ "expected_version": 3 }`; `crm.archive` |
| `POST` | `contacts/{uid}/restore/` | Same version command; `crm.archive` |
| `POST` | `contacts/{uid}/merge/preview/` | `MergePreviewRequest`; `crm.merge` |
| `POST` | `contacts/{uid}/merge/` | `MergeExecuteRequest`; `crm.merge` |
| `POST` | `contacts/{uid}/company-transition/` | `AffiliationTransition`; `crm.edit` |
| `GET` | `contacts/{uid}/affiliations/` | Paged affiliation history; `crm.read` |
| `POST` | `contacts/{uid}/affiliations/` | `AffiliationCreate`, `201`, `crm.edit` |
| `GET` | `contacts/{uid}/affiliations/{affiliation_uid}/` | Affiliation detail; `crm.read` |
| `PATCH` | `contacts/{uid}/affiliations/{affiliation_uid}/` | `AffiliationPatch`; `crm.edit` |

`ContactCreate` accepts owner/company UUIDs, optional names, email/phone
arrays, tags and descriptive fields. At least one name or email is required.
Contact social URLs belong in the closed `socials` object, not in
`linkedin_url`. Each value must be an HTTP(S) URL; unknown platform keys and
unsafe URL schemes return `422`. For example:

```json
{
  "first_name": "Ada",
  "last_name": "Lovelace",
  "socials": {
    "linkedin": "https://www.linkedin.com/in/ada-lovelace",
    "github": "https://github.com/ada"
  },
  "emails": [{"email": "ada@example.org", "type": "work"}],
  "tag_uids": []
}
```

Merge preview needs `loser_uid` and `field_resolutions`. Execution adds
`expected_version`, `loser_expected_version`, and the preview's `plan_hash`.
Re-preview after either contact changes. `field_resolutions` may name an
individual social key such as `"socials.linkedin": "loser"`; unmentioned
platforms merge with survivor precedence.

For `ContactPatch`, `changes.socials` updates only the named platform keys.
`null` for one key removes that URL; `changes.socials: null` clears the entire
object. An empty social change object is invalid. Contact responses expose
`socials` as a sparse object of the recorded URLs, and no longer expose a
contact-level `linkedin_url`.

The affiliation collection contains one record per company stint. `company_uid`
is required; `status` is `current`, `former`, or `unknown`; `is_primary` can be
true only for a current stint. Dates are optional precision-preserving strings:
`YYYY`, `YYYY-MM`, or `YYYY-MM-DD`. `current` and `unknown` stints cannot have an
`ended_period`. The create command requires `expected_contact_version`.
A patch requires both `expected_version` for the affiliation
and `expected_contact_version`, plus nonempty `changes` (`status`,
`started_period`, `ended_period`, or `job_title`). To change the primary company,
use the transition command rather than patching `is_primary`:

```json
{
  "expected_contact_version": 3,
  "previous_status": "former",
  "previous_ended_period": "2024-06",
  "new_company_uid": "a6fa604d-156e-4a2e-86ba-04e0a435e8ac",
  "new_started_period": "2024-07",
  "new_job_title": "Director"
}
```

`previous_status: "current"` retains the prior employer as a concurrent
nonprimary affiliation; `"former"` ends it, with or without a known end
period. `null` is required when no prior primary exists. `new_company_uid: null`
clears the primary projection without deleting history. All affiliation
commands are version-checked. A company must
be active when adding a new affiliation. The contact's `company_uid` remains a
single-company compatibility projection; the timeline is the source of truth.

## Companies

| Method | Path | Body / behavior |
| --- | --- | --- |
| `GET` | `companies/discovery/` | Read controls and columns; `crm.read` |
| `GET` | `companies/` | Paged collection; `crm.read` |
| `POST` | `companies/` | `CompanyCreate`, `201`, `crm.create` |
| `GET` | `companies/{uid}/` | Detail; `crm.read` |
| `PATCH` | `companies/{uid}/` | `CompanyPatch`; `crm.edit` |
| `POST` | `companies/{uid}/archive/` | Version command; `crm.archive` |
| `POST` | `companies/{uid}/restore/` | Version command; `crm.archive` |

`CompanyCreate` requires a trimmed, nonblank `name`; optional fields cover
owner, sector, size, web presence, address, context links and logo. The
response includes server-computed `contact_count` and `deal_count`.
The separate company `linkedin_url` field is unchanged by the contact social
model migration.

For both resources, patch bodies have an `expected_version` and nonempty
`changes`. See [request conventions](conventions.md) for headers and errors.
