# Service, principal, and settings API

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/healthz` | Process-only status; no CRM readiness guarantee |
| `GET` | `/api/crm/v1/readiness/` | Protected readiness body; `200` ready or `503` not ready |
| `GET` | `/api/crm/v1/bootstrap/` | Authorized startup state after readiness |
| `GET` | `/api/crm/v1/principals/` | Selectable current principal; `crm.read` |
| `GET` | `/api/crm/v1/settings/` | CRM application settings; `crm.read` |
| `PATCH` | `/api/crm/v1/settings/` | `SettingsPatch`; `crm.configure` |

Readiness checks the active CRM MetaTable catalog, one `settings` row, the
existing policy and directory adapters, and the default pipeline. It does not
run a write proof. `/healthz` checks none of these dependencies. Bootstrap
contains safe settings, the current principal, capabilities, the default
pipeline, and limits; it contains no application tenant or workspace UID.

Settings changes require a positive `expected_version` and nonempty `changes`.
Editable fields include default currency, timezone, and the configured
company-sector, contact-status, deal-category, and task-type choices.

```json
{
  "expected_version": 2,
  "changes": {"timezone": "Europe/Vienna"}
}
```

The platform supplies the authenticated principal. The application neither
accepts a caller-selected workspace nor maintains a separate user/role store.
See [persistence and migrations](../delivery/persistence.md).
