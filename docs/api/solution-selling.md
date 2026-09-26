# Solution Selling API

These routes mount only when `extensions.solution_selling.active: true` in
`config/crm.yaml`. Bootstrap then reports `modules.solution_selling: true`.
The persisted activation value controls deployment
availability, not platform identity or permission. Disabled routes do not
delete existing records. Enabled routes use the existing `crm.read`,
`crm.create`, and `crm.edit` capabilities.

All five resource collections below support `GET` and `POST` on their base
path, and `GET` and `PATCH` on `/{uid}/`. Collections return `{items, pageInfo}`;
each patch uses `{expected_version, changes}`. The base path is
`/extensions/solution-selling/`.

| Resource path | Pydantic record | Purpose |
| --- | --- | --- |
| `leads/` | `SolutionSellingLead` | Prospecting an existing Contact; optional profile and next Task. |
| `prospecting-profiles/` | `SolutionSellingProspectingProfile` | Reusable role and potential-pain hypothesis. |
| `prompters/` | `SolutionSellingPrompter` | Reusable draft template. |
| `assessments/` | `SolutionSelling` | One maintained assessment for a Deal and its Company. |
| `diagnoses/` | `SolutionSellingDiagnosis` | One Interaction-specific nine-cell diagnosis matrix. |

List queries accept `page_index`, `page_size`, and `search`, plus resource-specific
direct field filters. Reference fields are UUIDs, and relationships are
validated in governed writes or database foreign keys. In particular,
`SolutionSelling.company_uid` must match its Deal; a Lead's next Task must
belong to its Contact and be open when assigned (later Task completion does
not automatically edit the Lead); a linked diagnosis must match its
Interaction's Company and, when present, Deal. Embedded matrix, key-player,
pain-chain, and profile guidance content is Pydantic-validated, not a
collection of generic JSON-registered models.

`POST /extensions/solution-selling/prompters/{uid}/render/` accepts a required
`contact_uid` and explicit `company_uid`, optional lead/profile/deal/assessment
references, and a string-to-string `inputs` map. It returns `{text}` for human
review. It neither saves nor sends the draft. Rendering uses restricted Jinja
text features and bounded plain-data projections; missing or inconsistent
references fail clearly. It requires `crm.read`.
