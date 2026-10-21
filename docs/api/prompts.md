# Prompts API

The frontend names this library **Agent Prompts**. Resource discovery supplies
that display label and the singular **Agent Prompt**; the resource ID and API
paths remain `prompts`.

Core fixed-Markdown documents use `/api/crm/v1/prompts/`. They do not require
Solution Selling or Google Workspace. They are REST resources; this change
does not add Prompt tools to the assistant's MCP catalogue.

| Method | Relative path | Capability | Result |
| --- | --- | --- | --- |
| GET | `discovery/` | `crm.read` | Canonical resource discovery |
| GET | empty | `crm.read` | Metadata collection, no Markdown bodies |
| GET | `{uid}/` | `crm.read` | Full Prompt, including Markdown |
| POST | empty | `crm.create` | Created Prompt (201) |
| PATCH | `{uid}/` | `crm.edit` | Updated Prompt |
| POST | `{uid}/archive/` | `crm.archive` | Archived Prompt |
| POST | `{uid}/restore/` | `crm.archive` | Restored Prompt |

Identity and fresh policy checks use the same verified actor integration as
other CRM routes. Clients cannot set audit fields, UUIDs, or versions.

## Create and edit

Create:

```json
{
  "name": "Research checklist",
  "description": "Instructions to copy before researching a company",
  "content_markdown": "# Research\n\n- Verify public sources.\n- Separate facts from hypotheses.\n"
}
```

`name` is trimmed, non-blank, and at most 255 characters. `description` is
optional/nullable and at most 2,000 characters. `content_markdown` is required,
non-blank, and at most 65,536 UTF-8 bytes. NUL characters and unknown fields are
rejected. Markdown is preserved as submitted; there is no template rendering
endpoint, variable interpolation, or execution step.

Patch:

```json
{
  "expected_version": 1,
  "changes": {"content_markdown": "# Updated fixed instructions\n"}
}
```

Changes must be non-empty. Name and Markdown cannot be explicitly null;
description can be cleared with null. `expected_version` must be a positive
integer, not a boolean. Editing an archived Prompt is rejected until it is
restored. Successful mutations increment the version and atomically record an
activity event. Activity records mark body changes without duplicating the body.

Archive and restore accept `{"expected_version": 2}`. A stale version or an
archived edit returns 409; a missing UID returns 404; invalid input returns 422;
missing capability returns 403. Read current state before retrying a conflict
or uncertain write. There is no idempotency/replay guarantee.

## List

Use the standard `page_index`, `page_size` (default 25, maximum 100), `search`,
`ordering`, and JSON `filters` query parameters. The frontend requests 50 rows.
The collection envelope is `items` plus `pageInfo` from
`command-center.resource_collection@v1`. Each item contains all Prompt audit
and metadata fields **except** `content_markdown`. The detail/create/update
responses also include the Markdown body.

Search covers `name` and `description`. Ordering accepts `name`, `created_at`,
or `updated_at`, optionally prefixed by `-`; default is `-updated_at`, with UUID
as a deterministic tie-breaker. `filters={"archived":false}` is the default;
true selects archived records, and `"all"` selects both. Other filters and
ordering keys are rejected. The bounded list SQL never selects the body.
