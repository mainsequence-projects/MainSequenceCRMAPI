# Imports and transfers API

See the [transfer concept](../concepts/transfers.md) for lifecycle terms. Paths
are under `/api/crm/v1/`.

## Source connections and imports

| Method | Path | Body / behavior |
| --- | --- | --- |
| `GET`, `POST` | `source-connections/` | Paged list or `SourceConnectionCreate` (`201`); `crm.transfer.import` |
| `POST` | `imports/` | `CreateImport`, `201`; `crm.transfer.import` |
| `POST` | `imports/{uid}/file/` | Multipart `file` upload; `crm.transfer.import` |
| `PUT` | `imports/{uid}/mapping/` | `ImportMapping`; `crm.transfer.import` |
| `POST` | `imports/{uid}/validate/` | Revalidate staged rows; `crm.transfer.import` |
| `GET` | `imports/{uid}/plan/` | Current plan, counts and issues; `crm.transfer.import` |
| `POST` | `imports/{uid}/commit/` | `ImportCommitRequest`, `202`; `crm.transfer.import` |

`CreateImport` names the adapter, source connection, nullable `entity_type`,
and display name. CSV requires an entity type; bundle formats carry types in
the uploaded data. The upload is UTF-8, at most 20 MiB and 20,000 rows.

`ImportMapping` explicitly maps fields, owners, stages, statuses, date format,
timezone, currency, duplicate/update policy and boolean spellings. `commit/`
requires the current `plan_hash`, `mapping_revision`, `accept_warnings`, and
`mode` (`strict` or `valid_rows_only`). Do not treat a successful `202` as
completed import work.

## Job inspection and actions

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `transfers/discovery/`, `transfers/` | Discovery and paged list; `crm.read` |
| `GET` | `transfers/{uid}/`, `transfers/{uid}/issues/` | Job and paged issues; `crm.read` |
| `GET` | `transfers/{uid}/errors.csv` | CSV error report; `crm.read` |
| `POST` | `transfers/{uid}/cancel/`, `transfers/{uid}/retry/` | Durable action, `202`; direction-specific transfer capability |

Transfer writes do not require an `Idempotency-Key`. After an uncertain
response, inspect the job state before repeating an action. Import job state,
the sealed plan hash, and mapping revision still fence commit and retry.

Export creation and download functions are present in Python but **not mounted
as HTTP routes**. They are not an available API delivery surface.
