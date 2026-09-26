# Main Sequence CRM API

This repository contains the Python CRM API. It uses FastAPI, authored Pydantic
request/domain models, and SQLAlchemy-authored Main Sequence MetaTables. The
separate static frontend repository consumes `/api/crm/v1/` through Command
Center's delegated transport. The authoritative handoff pack is in that paired
frontend repository; it is not vendored into this API checkout.

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
from this repository. It accepts only loopback requests and validates the
account signed in through this repository's SDK session:

```bash
set -a
source .env
set +a
uv run uvicorn api.crm.local:app --host 127.0.0.1 --port 38641
```

The deployed FastAPI entrypoint remains `api.crm.main:app`, where the platform
injects the request user. Local mode represents the one account signed into
this process; it cannot distinguish different browser users. Do not expose it
through a public proxy. Vite proxies `/api/` to this loopback listener.
The API reports enabled modules in its bootstrap response; the frontend uses
that response to render Solution Selling, not a frontend environment variable.

`/healthz` checks only the process. Protected `/api/crm/v1/readiness/` requires
the platform-injected `request.state.user_uid` and reports `not_ready` until
one settings record, existing policy and directory adapters, an active
MetaTable catalog, and a default pipeline are available. The API does not
accept a caller-supplied identity or workspace selector.

The 18-table migration provider is `src.crm.migrations:migration`. A fresh API
process resolves its active, provider-owned MetaTables directly from the platform
catalog; no local bindings file or application tenant setting is used.
Migration `0004` replaces the old workspace table with singleton CRM settings
and removes `workspace_uid` from all CRM record tables. Migrations run outside
HTTP startup; the migration seeds defaults on an empty provider. Governed
mutation safety must be checked separately before a mutation release;
readiness does not certify it.
