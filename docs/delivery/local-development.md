# Local development

This repository owns the Python API documentation site and the FastAPI
service. The Vite/Command Center frontend lives in a separate repository.

## Install and read the docs

From this repository root:

```bash
uv sync --locked
.venv/bin/mkdocs serve --dev-addr 127.0.0.1:8002
```

Open the local documentation server printed by MkDocs. The source is `docs/`,
navigation is in `mkdocs.yml`, and generated HTML goes to ignored `site/`.
For a noninteractive link/navigation check, run `mkdocs build --strict` as
shown under [verification](verification.md).

## Run the API locally

The loopback-only launcher is `api.crm.local:app`. It validates the account
already signed in through this repository's Main Sequence SDK session and
represents that one human in this process:

```bash
set -a
source .env
set +a
uv run uvicorn api.crm.local:app --host 127.0.0.1 --port 8001
```

Keep `.env` private. Do not expose the local launcher through a public proxy:
it cannot distinguish multiple browser users. The deployed entrypoint remains
`api.crm.main:app`, where Main Sequence injects the request identity. Vite can
proxy `/api/` to the local loopback listener during frontend development.

`GET /healthz` only checks that the process responds. Protected CRM readiness
has additional dependencies described in [service and settings API](../api/service.md).
