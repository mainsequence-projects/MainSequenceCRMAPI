# Request conventions

## Identity and scope

Protected routes use the human UID injected by the Main Sequence platform.
An application policy adapter checks the
required capability (`crm.read`, `crm.create`, `crm.edit`, `crm.archive`,
`crm.merge`, `crm.transfer.import`, or `crm.configure`). Owner UUIDs are checked
against the existing platform directory. Do not send user or role headers as a
substitute for that context. Missing adapters, settings, or catalog state
fail closed.

## Collections and discovery

Collection responses contain `items` and `pageInfo` with `pageIndex`,
`pageSize`, `totalItems`, `hasNextPage`, and `hasPreviousPage`. Resource
discovery is a separate `GET /{resource}/discovery/` response describing the
visible controls and columns; pipelines currently have no discovery route.

| Collection parameter | Rule |
| --- | --- |
| `page_index` | Zero-based, default `0` |
| `page_size` | Default `25`, range `1`–`100` |
| `search` | Trimmed literal text, maximum 200 characters |
| `ordering` | A published key, optionally prefixed with `-` |
| `filters` | URL-encoded JSON object of that resource's semantic filters |

Discovery accepts only `search` and `filters`; it rejects pagination and
ordering. Unknown parameters and filter keys are rejected. UUID filters must
be UUID strings. `archived` accepts `true`, `false`, or `"all"` in the filter
object. Pydantic URL models in `api/crm/query_models.py` validate the query
shape; semantic filter models in `src/crm/models/queries.py` validate resource
filters. `api/crm/query.py` parses the HTTP parameters.
The storage layer receives only the resulting typed scope. Discovery supplies UI metadata,
but its filter list is currently empty and must not be mistaken for the full
set of accepted semantic filters.

## Commands and concurrency

JSON mutation bodies use closed Pydantic models: unknown fields are rejected.
Commands no longer accept or replay an `Idempotency-Key`. After an uncertain
write outcome, read the affected resource before deciding whether to submit
another command; a repeated create can create a second record.

Patches and state-changing commands carry `expected_version` as a positive
integer. A stale version returns a conflict rather than overwriting a newer
record. Board moves also carry `expected_board_version`; merge execution uses
both contact versions and a preview plan hash. Omitted patch fields remain
unchanged, while an explicitly supplied `null` has the field's documented
meaning. A patch's `changes` object must not be empty.

```json
{
  "expected_version": 3,
  "changes": {"status_key": "warm"}
}
```

## Responses and errors

Creates generally return `201`; an accepted import commit or transfer action
returns `202` and does **not** mean the job is finished. The current exception
handler wraps most errors in an `error` object with `code`, `message`, and
`request_uid`; validation errors add safe field paths. Readiness is an
exception: it returns its readiness body with `200` or `503`.

| Status | Typical meaning |
| --- | --- |
| `401` | Platform-injected human identity absent |
| `403` | Caller lacks the required CRM capability |
| `404` | Record missing |
| `409` | Version, board, or plan conflict |
| `413` | Upload or row limit exceeded |
| `422` | Invalid body, query, owner, or relationship |
| `503` | Required CRM settings, policy, directory, or catalog unavailable |

The mounted routes currently emit generic `CRM_REQUEST_ERROR` for many
non-authentication HTTP exceptions; do not assume more specific error codes
until the implementation and tests establish them.
