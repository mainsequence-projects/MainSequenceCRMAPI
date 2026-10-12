# Request conventions

## Identity and scope

`create_app()` installs the Main Sequence SDK's request identity once. It
verifies the caller of every request before any CRM middleware or route runs:

- Deployed, Main Sequence's gateway forwards a platform-signed caller
  assertion (`X-MainSequence-Caller-Assertion`). The SDK checks its Ed25519
  signature, issuer, audience, this release, the Environment and its lifetime
  of at most five minutes against the deployment's trusted configuration.
  SDK 9.0.19 also requires the signed `team_uids` list and Boolean
  `is_organization_admin` claim. Missing or malformed caller facts are rejected
  before CRM code runs; the platform supplies these claims.
- Outside a deployment, the request must carry a direct `Authorization:
  Bearer` token, which the SDK checks with
  `MAINSEQUENCE_ENDPOINT/api/v1/users/me/`. The
  [loopback launcher](../delivery/local-development.md#run-the-api-locally)
  presents its own SDK sign-in this way.

Protected routes use `authenticated_actor()`: it reads the verified caller
with `User.get_logged_user()` and selects the signed `User.get_requester()`
when present. Hosted [MCP business tools](mcp.md) use the requester on a
delegated call, never the agent's permissions. Without delegation, they admit
only a verified direct caller whose caller-scoped directory record is active
and human; an unbound workload is denied. A user header (`X-User-UID`,
`X-User-ID`) or the process's own SDK credential never substitutes for the
verified caller, and a request without one never reaches CRM code. An application policy adapter
checks the required capability (`crm.read`, `crm.create`, `crm.edit`,
`crm.archive`, `crm.merge`, `crm.transfer.import`, or `crm.configure`). Owner
UUIDs are checked against the existing platform directory. Missing adapters,
settings, or catalog state fail closed.

Only the routes the deployment declares as public ingress, and the platform
gateway admits as such, run without a caller: the Google OAuth callback and
completion page. Credentials are stripped from those requests, and CRM code
finds no caller there.

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

Core resource collections select the requested page of filtered record IDs
before computing full records and display-only related fields. Only that
page is returned. `totalItems` is an exact count of all matches using the same
filters and archive rules, not the number of returned records. The page and
count run in one governed statement; related fields are not computed for
off-page records merely to calculate the total. Ordering uses the published
key with nulls last and a UID tie-breaker, preserved in the response array.
Deal amounts sort numerically while remaining decimal strings in responses.

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
exception: it returns its readiness body with `200` or `503`. A request that
caller verification rejects never reaches that handler: it gets `401`, or
`503` while verification is unavailable, with only a `detail` message.

| Status | Typical meaning |
| --- | --- |
| `401` | No verified caller: a missing or invalid caller assertion (deployed) or Bearer token (local) |
| `403` | Caller lacks the required CRM capability |
| `404` | Record missing |
| `409` | Version, board, or plan conflict |
| `413` | Upload or row limit exceeded |
| `422` | Invalid body, query, owner, or relationship |
| `503` | Required CRM settings, policy, directory, or catalog unavailable; or caller verification unavailable |

The mounted routes currently emit generic `CRM_REQUEST_ERROR` for many
non-authentication HTTP exceptions; do not assume more specific error codes
until the implementation and tests establish them.
