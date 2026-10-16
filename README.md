# Main Sequence CRM API

This repository contains the Python CRM API. It uses FastAPI, authored Pydantic
request/domain models, and SQLAlchemy-authored Main Sequence MetaTables. The
separate static frontend repository consumes `/api/crm/v1/` through Command
Center's delegated transport. Maintain API behavior against the current models,
shared services, mounted routes, tests, and documentation in this checkout.

The API's own [MkDocs documentation](docs/index.md) separates CRM concepts,
mounted HTTP endpoints, and delivery guidance. Start it with
`.venv/bin/mkdocs serve --dev-addr 127.0.0.1:8002` after `uv sync --locked`.

## Code layout

- `src/crm/models/`: explicit Pydantic models grouped by business domain.
- `src/crm/contracts/`: validation and normalization against those classes.
- `src/crm/metatables/`: explicit SQLAlchemy declarations, one per governed table.
- `src/crm/repositories/`: governed queries, transfer persistence, and
  resource read/mutation/board/merge operations.
- `src/crm/platform/`: live catalog resolution, runtime ports, and loopback-only adapters.
- `src/crm/services/`: authorized settings and bootstrap reads.
- `src/crm/portability/`: pure transfer normalization helpers.
- `api/crm/resource_routes/`: concrete typed FastAPI resource endpoints;
  `api/crm/route_support.py` contains their shared authorization and handlers.
- `api/crm/routes.py` and `api/crm/transfer_routes.py`: cross-resource and
  transfer endpoints.

No runtime JSON file defines Pydantic models or MetaTable classes. JSON remains
a data interchange format for uploads and query filters.

## Local checks

```bash
uv sync --locked
.venv/bin/pytest tests -q
.venv/bin/ruff check api/crm src/crm tests
.venv/bin/ruff format --check api/crm/resource_routes src/crm/models \
  src/crm/metatables src/crm/repositories src/crm/platform src/crm/services \
  src/crm/portability src/crm/contracts tests/test_structure.py
.venv/bin/mkdocs build --strict
```

For the explicit single-user local browser workflow, run the local entrypoint
from this repository. It accepts only loopback requests and presents the
account signed in through this repository's SDK session as the caller:

```bash
set -a
source .env
set +a
uv run uvicorn api.crm.local:app --host 127.0.0.1 --port 38641
```

The deployed FastAPI entrypoint remains `api.crm.main:app`. Its factory
installs the Main Sequence SDK's request identity
(`mainsequence.server.fastapi.install_request_identity`) once. Deployed, it
verifies the platform-signed caller assertion of every request before any CRM
code runs, and Main Sequence's FastAPI launcher refuses to serve an app
without it. Protected routes take that caller from `User.get_logged_user()`
through `authenticated_actor()`. Local mode represents the one account signed
into this process; it cannot distinguish different browser users. Do not
expose it through a public proxy. Vite proxies `/api/` to this loopback
listener.
The API reports enabled modules in its bootstrap response; the frontend uses
that response to render Solution Selling, not a frontend environment variable.

`/healthz` checks only the process; deployed, it needs a verified caller like
every route outside the declared public ingress. Protected
`/api/crm/v1/readiness/` reports `not_ready` until one settings record,
existing policy and directory adapters, an active MetaTable catalog, and a
default pipeline are available. The API does not accept a caller-supplied
identity header or workspace selector.

The 27-table migration provider is `src.crm.migrations:migration`. A fresh API
process resolves its active, provider-owned MetaTables directly from the platform
catalog; no local bindings file or application tenant setting is used.
Migration `0004` replaces the old workspace table with singleton CRM settings
and removes `workspace_uid` from all CRM record tables; it seeds defaults on an
empty provider. Nothing migrates at HTTP startup. Hosted environments are
migrated only by the `migrate-crm` Job (`jobs/migrate_crm.py`), which
`.mainsequence/workflows/crm-api.yaml` runs before it deploys the API and the
CRM assistant. That file is the repository's only workflow file. The API now
uses Main Sequence 9.0.27 and MetaTables 0.1.39. Before rollout, verify the
hosted MetaTables API and its system migrations against that client version,
and provision the CRM Team's namespace access described in
[persistence and migrations](docs/delivery/persistence.md#migration-and-runtime-boundary).
The historical 0.1.19 API minimum only addressed the removed runtime-switch
fields; it is not proof of compatibility with the current client.
Local development applies revisions to the MetaTables local SQLite runtime:

```bash
uv run metatables --local migrations upgrade --provider src.crm.migrations:migration
```

See [persistence and migrations](docs/delivery/persistence.md). Governed
mutation safety must be checked separately before a mutation release;
readiness does not certify it.

The optional Tau 2.0.13 assistant discovers the API's typed CRM tools through
application MCP at `/mcp`. Local development uses the same endpoint through a
loopback transport bridge. See [ADR 0005](docs/crm_core/adrs/0005-crm-application-mcp.md)
for authorization and the resource-key cutover: `crm-api` → `crm` created a new
API release identity. It was deployed on 2026-10-11 and the frontend binds the
new release; Google OAuth registration for it remains unverified. See the
[verification evidence](docs/delivery/verification.md).

The CRM uses MCP Python SDK 2.3.0's `MCPServer` and publishes
`.agents/skills/mainsequence_crm/` directly through the Main Sequence SDK's
`skills_extension`. Its five skills and eight files are available on the same
authenticated `/mcp` endpoint as the typed business tools. See
[MCP skill publication](docs/api/mcp.md#sdk-skill-publication).
