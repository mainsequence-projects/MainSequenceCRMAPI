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

## Tags and activity

Tags expose discovery, collection, create (`TagCreate`), detail, patch
(`TagPatch`), archive, and restore at the analogous `tags/` paths. Mutations
use `crm.create`, `crm.edit`, or `crm.archive`; reads use `crm.read`.

Activity exposes only `GET activity/discovery/`, `GET activity/`, and
`GET activity/{uid}/` with `crm.read`. It has no direct create or edit route.
See [tags and activity](../concepts/tags-activity.md) for their roles.
