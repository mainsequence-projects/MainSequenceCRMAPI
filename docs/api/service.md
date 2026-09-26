# Service, principal, and settings API

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/healthz` | Process-only status; no CRM readiness guarantee |
| `GET` | `/api/crm/v1/readiness/` | Protected readiness body; `200` ready or `503` not ready |
| `GET` | `/api/crm/v1/bootstrap/` | One authorized startup snapshot with readiness and assistant runtime |
| `GET` | `/api/crm/v1/principals/` | Selectable current principal; `crm.read` |
| `GET` | `/api/crm/v1/settings/` | CRM application settings; `crm.read` |
| `PATCH` | `/api/crm/v1/settings/` | `SettingsPatch`; `crm.configure` |

Readiness checks the active CRM MetaTable catalog, one `settings` row, the
existing policy and directory adapters, and the default pipeline. It does not
run a write proof. `/healthz` checks none of these dependencies. Bootstrap
contains safe settings, the current principal, capabilities, the default
pipeline, limits, `modules.solution_selling`, and `modules.google_workspace`.
These flags reflect `extensions.solution_selling.active` and
`extensions.google_workspace.active` in validated `config/crm.yaml`.
The repository configuration currently sets both to `true`; neither grants
permission.
Bootstrap contains no application tenant or workspace UID.

[ADR 0004](../crm_core/adrs/0004-single-bootstrap-and-assistant-runtime.md)
defines the implemented one-request startup contract. Successful bootstrap
embeds `readiness.status: ready` and an `assistant` object. A not-ready
bootstrap returns `503` with the safe error and readiness checks, without
partial CRM data. `/readiness/` remains a protected operational diagnostic.
A platform Organization Environment UID is distinct from a CRM workspace or
tenant UID. Assistant identity comes from `.agents/agent_card.json`; CRM YAML
has no assistant section. At each bootstrap, a trusted, ready local Tau is
selected in the loopback launcher. Otherwise the API attempts a platform
Agent lookup by the card's exact name, in the SDK-resolved Environment and
this project's branch. If neither transport is usable, the assistant is
unavailable while CRM remains usable. The frontend uses `/tau` for local chat
and Command Center AI for a resolved platform Agent. The platform path still
requires a deployed managed Agent; that live deployment is unverified.

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
