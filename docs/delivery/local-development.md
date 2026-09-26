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
uv run uvicorn api.crm.local:app --host 127.0.0.1 --port 38641
```

Keep `.env` private. Do not expose the local launcher through a public proxy:
it cannot distinguish multiple browser users. The deployed entrypoint remains
`api.crm.main:app`, where Main Sequence injects the request identity. Vite
proxies `/api/` and `/extensions/` to the local loopback listener during
frontend development. Core CRM routes use `/api/crm/v1/`; optional module API
routes use `/extensions/<module>/`.
The local launcher shares a verified SDK user lookup across requests for at
most 30 seconds, then revalidates it. Concurrent requests share the lookup;
failed lookups are never cached. A responsive `/healthz` only proves the API
process is running. If protected routes stall, check the Main Sequence
`/api/v1/users/me/` response and the SDK sign-in; Google authorization cannot
start until that identity check succeeds.
The backend mounts optional modules from the strict, persisted
`config/crm.yaml` and reports those same values in bootstrap. Both
`extensions.solution_selling.active` and `extensions.google_workspace.active`
are `true` in this repository. Changing the file requires an API restart.
Normal policy checks still govern each request. See the
[single-bootstrap ADR](../crm_core/adrs/0004-single-bootstrap-and-assistant-runtime.md)
for the one-request initialization and assistant runtime contract. The YAML
has no assistant section: the assistant name comes from `.agents/agent_card.json`.
In a deployed API process, the Main Sequence SDK resolves the Environment UID
at runtime and the API looks up the Agent by that card name in the same
Environment and project branch. The local launcher passes its Tau loopback
origin to the API. Bootstrap checks Tau `/ready` on each request; a healthy
local Tau selects `/tau` chat without platform UUIDs. Otherwise bootstrap
attempts platform Agent resolution or reports the assistant unavailable.

`GET /healthz` only checks that the process responds. Protected CRM readiness
has additional dependencies described in [service and settings API](../api/service.md).

## Optional Google Workspace extension

The [Google Workspace module setup guide](../google_workspace_module/setup.md)
lists the Google Cloud project, APIs, consent screen, OAuth Web client, exact
callback pattern, and runtime values. Set
`extensions.google_workspace.active: true` in `config/crm.yaml` to mount its
routes and include `modules.google_workspace=true` in bootstrap. The
frontend uses that bootstrap value and the user's import capability to show
the module. It never reads the YAML itself. Keep the
client ID, client secret, and 32-byte token-encryption key in separate Main Sequence
Secrets. `GOOGLE_OAUTH_REDIRECT_URI` is the API environment value. Apply migration `0008` before starting a
process that expects the new catalog bindings. The loopback launcher is
single-user only; use a separately registered localhost Web OAuth client for
local consent testing, never the production client.

## Optional Tau runtime

The sibling static site's sole VS Code launch entry runs `scripts/dev-stack.mjs`.
It starts this API on `127.0.0.1:38641`, Tau on `127.0.0.1:38642`, the guide
on `127.0.0.1:38643`, and Vite on `127.0.0.1:38644`. The launcher refreshes
this repository's local SDK user session, explicitly renews its access token
before startup, and passes the resulting JWT pair to
Tau in process environment with `MAINSEQUENCE_AUTH_MODE=jwt` and
`TAU_LOCAL_MODE=true`. It uses the same local provider/model as Sentinel:
`TAU_LOCAL_PROVIDER=deemachine-ollama` and `TAU_LOCAL_MODEL=qwen3.8:27b`.
Vite proxies `/api/` and `/extensions/` to this API, `/tau/` to Tau, and
`/docs/` to the guide. All listeners bind to loopback; the launcher checks for
port conflicts before starting. The local Vite proxy renews its SDK access
token when near expiry; this needs a valid CLI sign-in on the same machine.
Tau `/ready` verifies provider and user
authentication. A healthy Tau process is still separate from the frontend's
platform-Agent-based Assistant flow; it does not create an Agent UID.

`ms-tau-sdk` 1.2.8 is locked to the latest release commit in `pyproject.toml` and
`uv.lock`. `uv sync --locked` installs it alongside the API, but CRM startup
does not start Tau. The separate ASGI entrypoint `api.tau.main:app` uses
`create_app()` and reads the SDK's normal runtime settings. For the CRM agent,
exclude Tau's coding tools and Main Sequence MCP in the process environment:

```bash
TAU_EXCLUDE_BASE_TOOLS=true TAU_EXCLUDE_MAINSEQUENCE_MCP=true \
  uv run uvicorn api.tau.main:app --host 127.0.0.1 --port 38642
```

The same variables apply to the `ms-tau` command. Both default to `false`,
so the exclusion depends on how the agent process is launched.

The version-matched coding guidance is synchronized with
`uv run ms-tau skills sync --path .` into `.agents/skills/ms_tau_sdk/`.
Project-owned runtime behavior belongs under `.tau/`. The typed CRM
tools and their authorization requirements are in
[ADR 0003](../crm_core/adrs/0003-tau-crm-agent-tools.md). The
`.tau/extensions/crm.py` project extension registers tools for the shared
operations that currently exist. Mounted HTTP routes call those operations in
`src/crm/services/operations.py` and `src/crm/services/transfers.py` for
business validation, policy, and governed persistence. The installed Tau
extension API does not expose its validated caller to project tools, and this
entrypoint does not supply CRM policy or directory ports. Valid CRM tool calls
therefore return `unavailable`; they cannot use the process SDK credential as
the human caller. This is a fail-closed catalogue, not an operational CRM
agent. No agent deployment or live provider check is claimed here.

With both exclusions, the agent's business tools are those registered under
`.tau/extensions/`. Tau also retains its required A2A Task controls. There
are currently 46 CRM project tools with Solution Selling disabled, or 66 with
it enabled. Managed deployments set the two values
in `harness_agent.spec.env_vars`, regardless of whether they launch the CLI
or the ASGI entrypoint. The entrypoint has not been deployed as a platform
Agent.

Running `ms-tau` locally needs the SDK's documented authenticated user token
handoff, explicit provider/model, and `TAU_LOCAL_MODE=true`. Do not put those
tokens or provider credentials in the repository or `.tau` files. Local mode
still calls the live Main Sequence provider services; the CRM agent profile
above excludes MCP. Deploy the Tau runtime separately from
`api.crm.main:app` after a trusted per-turn identity/policy binding and the
confirmation contract are implemented and verified.
