# Tasks, notes, tags, and activity API

These resources are under `/api/crm/v1/`. All mounted collection routes accept
the common [query parameters](conventions.md).

## Tasks

| Method | Path | Body / behavior |
| --- | --- | --- |
| `GET` | `tasks/discovery/`, `tasks/`, `tasks/{uid}/` | Discovery, list, detail; `crm.read` |
| `POST` | `tasks/` | `TaskCreate`, `201`, `crm.create` |
| `PATCH` | `tasks/{uid}/` | `TaskPatch`; `crm.edit` |
| `POST` | `tasks/{uid}/archive/` | Version command; `crm.archive` |
| `POST` | `tasks/{uid}/complete/`, `tasks/{uid}/reopen/` | Version command; `crm.edit` |

`TaskCreate` requires `contact_uid` and nonblank `text`. It may include an
owner, type key and offset-aware `due_at`. Completion is not a generic patch.
There is no mounted task restore route.

## Notes

| Method | Path | Body / behavior |
| --- | --- | --- |
| `GET` | `notes/discovery/`, `notes/`, `notes/{uid}/` | Discovery, list, detail; `crm.read` |
| `POST` | `notes/` | `NoteCreate`, `201`, `crm.create` |
| `PATCH` | `notes/{uid}/` | `NotePatch`; `crm.edit` |
| `POST` | `notes/{uid}/archive/`, `notes/{uid}/restore/` | Version command; `crm.archive` |

`NoteCreate` requires nonblank `text`, an offset-aware `occurred_at`, and
exactly one of `contact_uid` or `deal_uid`. The server supplies live authorship.

`title` is optional and nullable. When supplied it is a plain-text single line
of 1–255 characters after trimming surrounding whitespace; blank titles and
embedded NUL/newline characters are rejected. Omitting it on creation stores
null. `text` is Markdown source, at most 100,000 characters; category, status,
and attachments are not required. The contact editor defaults the date to
now, while HTTP and MCP callers must supply `occurred_at` explicitly.

The authenticated MCP tool `crm_notes_create` accepts the same payload:

```json
{
  "payload": {
    "contact_uid": "22222222-2222-4222-8222-222222222222",
    "title": "Relationship context",
    "occurred_at": "2026-10-16T14:30:00+02:00",
    "text": "## Relationship context\n\nPrefers **email**.\n"
  }
}
```

Use an existing Contact UID. `crm_notes_update` takes `uid` and a `payload`
containing `expected_version` and `changes` (for example `title`, `text` and
`occurred_at`). A title-only edit is supported. Omit `title` to preserve it;
`{"expected_version": 3, "changes": {"title": null}}` clears it. Both use the same service and governed writes as REST and
check the effective caller's create/edit capability. Caller-supplied authorship
and two simultaneous parents are rejected. Note bodies round-trip unchanged;
renderers must treat Markdown as content, never executable HTML or code.
List/detail responses include nullable `title`, and Notes search matches title
and body. Discovery presents Title as the primary column, with Body and Date.

## Tags and activity

Tags expose discovery, collection, create (`TagCreate`), detail, patch
(`TagPatch`), archive, and restore at the analogous `tags/` paths. Mutations
use `crm.create`, `crm.edit`, or `crm.archive`; reads use `crm.read`.

Activity exposes only `GET activity/discovery/`, `GET activity/`, and
`GET activity/{uid}/` with `crm.read`. It has no direct create or edit route.
See [tags and activity](../concepts/tags-activity.md) for their roles.
