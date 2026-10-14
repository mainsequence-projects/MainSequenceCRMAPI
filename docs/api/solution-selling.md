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

Lead list and detail responses also include read-only `contact_display_name`,
`company_uid` and `company_name`, resolved from the referenced Contact and its
current primary Company. Names are not copied into the Lead MetaTable and cannot
be supplied on create or patch. Collection reads enrich only the requested page
in the same governed query as its total count. A Contact without a Company still
appears, with null Company fields. An unnamed Contact uses its first email as
the display label, or `Unnamed contact` when no label is available. The Lead's
`uid` remains its navigation and mutation identity. Lead `search` still matches
notes; it does not search these display fields.

`POST /extensions/solution-selling/prompters/{uid}/render/` accepts a required
`contact_uid` and explicit `company_uid`, optional lead/profile/deal/assessment
references, and a string-to-string `inputs` map. It returns `{text}` for human
review. It neither saves nor sends the draft. Rendering uses restricted Jinja
text features and bounded plain-data projections; missing or inconsistent
references fail clearly. It requires `crm.read`.

There is no template-specific requirements endpoint or MCP tool. Retrieve the
stored template with the existing prompter detail read to inspect its variables;
the generic render schema always requires both Contact and Company, even when
the template only uses one. Optional references and individual `inputs` keys
are not discovered before rendering. For example, `{{ inputs.topic }}` requires
an explicit `topic` input, while a profile block guarded by `{% if profile %}`
can be omitted. The signed-in sender is supplied by the API. The Company is
selected explicitly and is not inferred from Contact affiliations.

## Prompter bulk deletion

`GET prompters/discovery/` returns `command-center.resource_discovery@v1`,
including the `delete` action only for callers with `crm.read` and `crm.archive`.
It accepts optional `search`, without pagination or ordering. The action supports
explicit selection only (up to 200 unique UUIDs); selecting a page never means
all matching records. The SDK owns selection, preflight and typed confirmation.

`POST prompters/bulk-delete/preflight/` and `POST prompters/bulk-delete/` accept
the Command Center bulk execution envelope: `selection: {mode: "explicit", uids}`
and `options: {expected_versions: {"<uid>": <positive integer>}}`. The version
map must contain exactly the selected UIDs. The frontend supplies the versions
of the displayed rows. Preflight returns `allowed`, `matched_count`, `detail`
and `blockers`. Execution returns `{deleted_count}`. Both boundaries independently
check permissions and module activation.

One governed PostgreSQL statement locks the selected rows, checks every version,
sets `archived_at`, increments versions and records an activity event per row.
A missing, archived or stale row blocks the entire mutation (`409`); invalid
selection/options return `422`, and missing capability returns `403`. Deleted
templates disappear from active reads and cannot render new drafts. Existing
CRM records and audit history remain. This is archival deletion, with no normal
UI restore flow currently offered. There is no bulk-delete MCP tool.

Deletion does not promise replay. After an uncertain response, read the list
before retrying. SQLite execution of this PostgreSQL command is not verified.

## Read-only workflow helpers

`POST /extensions/solution-selling/context/` and
`crm_solution_selling_context_get` accept `deal_uid`,
`interaction_page_index` (default 0, minimum 0) and `interaction_page_size`
(default 5, range 1–20). The response contains `deal`, nullable `company`,
nullable `assessment`, `interactions: {items, pageInfo}`, and `sources` with
`resource`, `uid`, and `version` for every returned record. Assessment contains
its key players and pain chain without changing evidence statuses. Interactions
are ordered by their existing scheduled-time collection order; page information
truthfully describes the bounded history. These individual reads are not an
atomic snapshot. Use the returned versions when proposing subsequent edits.

`POST /extensions/solution-selling/diagnoses/prepare/` and
`crm_diagnoses_prepare` accept required `interaction_uid`, `contact_uid`,
`profile_uid`, and optional `solution_selling_uid`. The response contains
`draft` (a valid diagnosis-create payload), `saved: false`,
`business_issue_status: "hypothesis"`, and `sources` with UIDs/versions. It copies
profile questions with null answers and uses potential pain as the business
issue. Without a profile template all nine cells are empty. Contact is explicit;
no participant or affiliation is inferred. A linked assessment must match the
Interaction's Company and, when present, Deal.

`crm_prompters_render` takes `{uid, payload}` where `payload` is the same render
request described above. All three helpers require `crm.read`; none save, send,
confirm evidence, or update an assessment. Missing active references return
not-found; invalid relationships return validation errors. Review a prepared
payload before explicitly invoking an existing create/update tool.
