# Google Workspace API

These routes are mounted when `extensions.google_workspace.active: true` in
`config/crm.yaml`.
The module also needs the [Google Cloud and CRM setup](../google_workspace_module/setup.md)
and migration `0008`. All routes except the Google callback and its completion
page use the existing platform-injected CRM identity and require
`crm.transfer.import`. Creating a CRM record additionally requires
`crm.create`; updating a linked meeting requires `crm.edit`.
The callback and completion handlers have no CRM bearer dependency. Deployed
OAuth additionally needs exact `GET` `public_ingress` pairs on the FastAPI
release, an active revision with that policy, and external verification. See
the [public callback setup](../google_workspace_module/setup.md#configure-public-callback-routes-on-main-sequence).

| Method | Path | Request and result |
| --- | --- | --- |
| `POST` | `/extensions/google/oauth/start/` | `{ "source": "contacts" \| "gmail" \| "calendar" }` returns an `authorization_url`, `attempt_uid`, and 600-second lifetime. The URL opens in a separate browser tab. |
| `GET` | `/extensions/google/oauth/callback/` | Google sends `code` and `state`, or `error` and `state`. The backend consumes state once, exchanges the code with PKCE, validates the ID token, and redirects to the fixed completion page. The handler has no CRM bearer dependency; deployed public ingress is not yet verified. |
| `GET` | `/extensions/google/oauth/done/` | Token-free browser page telling the user to return to CRM; the status query contains no credential or completion handle. |
| `GET` | `/extensions/google/oauth/attempts/{uid}/` | Only the actor who started this attempt can read `waiting`, `ready`, `completed`, `failed`, or `expired`. `ready` returns a short-lived `completion_handle` through the authenticated CRM transport. A denial or failed exchange returns `failed` promptly. |
| `POST` | `/extensions/google/oauth/complete/` | `{ "completion_handle": "…" }` activates the grant for the same actor and returns a token-free connection summary. |
| `GET` | `/extensions/google/connections/` | `{ "items": [...] }`, containing at most the actor's own connection: UID, display email, granted source names, status, and version. This read works while Google operator credentials are not yet configured, so the module can show its setup state. |
| `POST` | `/extensions/google/connections/{uid}/disconnect/` | Removes local token access, then attempts Google revocation; returns `google_revoked`. Imported CRM records remain. |
| `GET` | `/extensions/google/calendars/` | Lists up to 100 calendars when calendar-list permission was granted. |
| `POST` | `/extensions/google/preview/` | Source selection and optional `page_token`; Gmail also needs `gmail_query`, `time_min`, and `time_max`; Calendar needs `calendar_id`, `time_min`, and `time_max`. Date ranges are limited to 90 days. Returns bounded candidates, matches/links, opaque preview tokens, and a next page token. Source links and Contact matches use up to two governed batch reads per page after the Google read. |
| `POST` | `/extensions/google/imports/` | One reviewed decision: `preview_token`, `action` (`create`, `link`, `update`, `skip`), and selected CRM references. Contact creation may include `contact_fields` with reviewed `first_name`, `last_name`, `title`, `emails`, and `phones`; the API validates this through `ContactCreate` and accepts it only for Contact creation. Meeting creation requires `company_uid`; update requires linked `target_uid` and `expected_version`. Returns the imported target UID or `skipped`. |

The frontend sends Google preview and import requests through the normal
delegated FastAPI transport. Google access and refresh tokens never appear in
these responses. A preview token is encrypted for the actor and connection and
expires after 15 minutes. A repeated source item is recognized through its
source identity; a new create or link then returns a conflict rather than a
duplicate. Gmail preview reads selected message headers only.
The Contact form is prefilled from the candidate, but nothing is saved until
the user presses **Create Contact**. A successful response gives the CRM
record UID for an **Open in CRM** link.

These routes exist in source code. A deployed connection has **not** been
verified; see [release evidence](../delivery/verification.md).
