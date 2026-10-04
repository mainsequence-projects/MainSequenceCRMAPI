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

The loopback-only launcher is `api.crm.local:app`. It represents the one
human already signed in through this repository's Main Sequence SDK session:

```bash
set -a
source .env
set +a
uv run uvicorn api.crm.local:app --host 127.0.0.1 --port 38641
```

Keep `.env` private. Do not expose the local launcher through a public proxy:
it cannot distinguish multiple browser users. The deployed entrypoint remains
`api.crm.main:app`, which verifies the platform-signed caller of each request
(see [request conventions](../api/conventions.md#identity-and-scope)). Vite
proxies `/api/` and `/extensions/` to the local loopback listener during
frontend development without adding a credential. Core CRM routes use
`/api/crm/v1/`; optional module API routes use `/extensions/<module>/`.

The launcher builds that same application. Outside a deployment its request
identity runs in local mode, and the launcher refuses to start where
deployment markers such as `APP_NAME` are set. For each protected loopback
request the launcher presents this process's SDK sign-in as the
`Authorization: Bearer` credential. The request identity checks it with
`MAINSEQUENCE_ENDPOINT/api/v1/users/me/`, binds that user as the caller and
removes the header before any route runs. A request that brings its own
`Authorization`, caller assertion or user header is rejected with `401`. The
signed-in user's details, which the local policy and display name use, are
cached for at most five minutes and then revalidated; concurrent requests
share that lookup and failed lookups are never cached. The per-request check
is not cached. A responsive `/healthz` only proves the API process is running.
If protected routes stall or return `503`, check the Main Sequence
`/api/v1/users/me/` response and the SDK sign-in; Google authorization cannot
start until that identity check succeeds.
`/healthz` and the exact Google callback and completion-page routes need no
sign-in. The launcher declares them as public ingress for the application it
creates and marks their requests as the platform gateway does, so they run
without a caller, as the Google routes do in the deployed API. OAuth state
and the provider exchange still validate the callback.
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
Bootstrap runs its synchronous platform readiness work in the API worker pool,
so a slow catalog read does not block the event loop or `/healthz`. The local
signed-user lookup has a 20-second response deadline and the request
identity's check of the sign-in a 10-second one; readiness and settings reads
have 75-second deadlines. When one expires, the protected API returns HTTP
`503`, naming the failed stage for the CRM's own deadlines. The frontend
shows the bootstrap path, HTTP status, and the failed readiness check. A
process-only `/healthz` success does not imply that the Main Sequence backend
is reachable. SDK calls may
continue in their worker after the response deadline; restart the stack after
fixing a persistent backend or sign-in failure.
The VS Code local stack checks the protected bootstrap before printing its
ready message. If bootstrap returns a failed check or does not respond within
100 seconds, the launcher prints that failure and stops all four services.

## Apply migrations locally

Author and apply CRM revisions against the MetaTables local SQLite runtime,
never against a hosted database. The installed
`.agents/skills/metatables/metatables-local-development/SKILL.md` covers
`metatables init --local`, `metatables serve --local` and the explicit
`metatables --local runtime initialize`.

Each local storage directory has one local MetaTables API and one SQLite
runtime. The directory is `~/.local/share/metatables`, or
`METATABLES_LOCAL_STORAGE_DIR` when that is set, so a laptop normally runs one
local API: start `metatables serve --local` once, from this or any other
checkout. The launcher writes the API's address and private token to
`server.json` in that directory, and `metatables --local` and
`configure_local_client()`, which takes no arguments, read that file from any
checkout. A second `serve --local` for the same directory reports the running
API and exits; a different `METATABLES_LOCAL_STORAGE_DIR` gets its own API, on
another `--port`, and its own runtime. `serve --local` looks up the signed-in
user on the Main Sequence backend (`/api/v1/users/me/`) as it starts and stops
if that lookup fails or the API is not ready within its 45-second startup
deadline, so it cannot start while the backend does not answer. Commits and
branch changes do not require restarting the API. It always runs Local: there
is no switch to a hosted runtime. Checkouts that use the same storage directory
share its SQLite file. Before migrating, check that
`metatables --local runtime status` reports Local mode and `sqlite`, then run:

```bash
uv run metatables --local migrations upgrade --provider src.crm.migrations:migration
uv run metatables --local migrations current --provider src.crm.migrations:migration
```

`.venv/bin/pytest tests/test_migrations.py` also runs the whole history on a
temporary SQLite file without an API.

Hosted environments are migrated only by the deployment workflow's
`migrate-crm` Job, before the API and the CRM assistant roll out; see
[persistence and migrations](persistence.md#migration-and-runtime-boundary).
Do not run `metatables migrations upgrade` or `downgrade` without `--local`.
Before this branch is pushed, the Environment's hosted MetaTables API must be
upgraded to 0.1.19 or later; 0.1.18 is not enough. This repository's 0.1.20
client rejects the `/runtime-context/` response of an older API
([MetaTables issue #33](https://github.com/mainsequence-projects/MetaTables/issues/33)),
so the Job would fail before it migrates anything, and neither the API nor the
assistant would roll out.

The local runtime checks the migration history, not the running CRM API. The
loopback launcher does not call `configure_local_client()`, so its MetaTables
client discovers the Environment's hosted MetaTables API, and the CRM's
governed queries are written in PostgreSQL SQL. That client rejects the
runtime context of a hosted API older than 0.1.19, but the launcher's catalog
lookup and governed operations do not read it: in an offline replay of a
0.1.18-shaped API they were unaffected (see
[verification](verification.md#evidence-boundaries)). The upgrade is needed
before the push, for the migration Job.

## Optional Google Workspace extension

The [Google Workspace module setup guide](../google_workspace_module/setup.md)
lists the Google Cloud project, APIs, consent screen, OAuth Web client, exact
callback pattern, and runtime values. Set
`extensions.google_workspace.active: true` in `config/crm.yaml` to mount its
routes and include `modules.google_workspace=true` in bootstrap. The
frontend uses that bootstrap value and the user's import capability to show
the module. It never reads the YAML itself. Keep the
client ID, client secret, and 32-byte token-encryption key in separate Main Sequence
Secrets. `GOOGLE_OAUTH_REDIRECT_URI` is the API environment value. The
process expects the `0008` catalog bindings, which hosted environments receive
from the deployment workflow's migration Job. The loopback launcher is
single-user only; use a separately registered localhost Web OAuth client for
local consent testing, never the production client.

## Optional Tau runtime

The sibling static site's sole VS Code launch entry runs `scripts/dev-stack.mjs`.
It starts this API on `127.0.0.1:38641`, Tau on `127.0.0.1:38642`, the guide
on `127.0.0.1:38643`, and Vite on `127.0.0.1:38644`. Before startup the
launcher renews the machine's saved Main Sequence sign-in with
`mainsequence refresh-token`, run in this repository so that it also removes
token lines an earlier SDK left in this `.env`. It starts this API and Tau
without token variables. Tau runs with
`MAINSEQUENCE_AUTH_MODE=jwt` and `TAU_LOCAL_MODE=true`, so it takes the user's
access token from the saved CLI session (see below). It uses the same local
provider/model as Sentinel:
`TAU_LOCAL_PROVIDER=deemachine-ollama` and `TAU_LOCAL_MODEL=qwen3.8:27b`.
Vite proxies `/api/` and `/extensions/` to this API, `/tau/` to Tau, and
`/docs/` to the guide. All listeners bind to loopback; the launcher checks for
port conflicts before starting. The local Vite proxy renews its SDK access
token when near expiry; this needs a valid CLI sign-in on the same machine.
Tau `/ready` verifies provider and user
authentication. A healthy Tau process is still separate from the frontend's
platform-Agent-based Assistant flow; it does not create an Agent UID.

`ms-tau-sdk` 1.2.14 is locked to its release tag `v1.2.14` in `pyproject.toml` and
`uv.lock`. `uv sync --locked` installs it alongside the API, but CRM startup
does not start Tau. The separate ASGI entrypoint `api.tau.main:app` uses
`create_app()` and reads the SDK's normal runtime settings. For the CRM agent,
exclude Tau's coding tools and Main Sequence MCP in the process environment:

```bash
TAU_EXCLUDE_BASE_TOOLS=true TAU_EXCLUDE_MAINSEQUENCE_MCP=true \
  uv run uvicorn api.tau.main:app --host 127.0.0.1 --port 38642
```

The local Tau process exposes `GET /api/local/v1/conversations` and
`GET /api/local/v1/conversations/{contextId}/messages` for its own direct A2A
Message history. Vite serves these under `/tau/api/local/v1/`. The SDK scopes
the list to its authenticated process user and workspace; its canonical
`contextId` resumes a conversation through `message:send`. The SDK does not
reconstruct conversations that predate its new public transcript projection.
These local records are separate from deployed platform AgentSessions and A2A
Task history.

The same variables apply to the `ms-tau` command. Both default to `false`,
so the exclusion depends on how the agent process is launched.

The version-matched coding guidance is synchronized with
`uv run ms-tau skills sync --path .` into `.agents/skills/ms_tau_sdk/`.
Project-owned runtime behavior belongs under `.tau/`. The typed CRM
tools and their authorization requirements are in
[ADR 0003](../crm_core/adrs/0003-tau-crm-agent-tools.md). The
project `.tau/SYSTEM.md` replaces Tau's packaged general prompt so the chat
speaks as a CRM application assistant. Restart Tau or start a new session after
changing it, then inspect the effective session prompt. The Agent Card controls
the display name; the process settings intentionally exclude general coding
and Main Sequence MCP tools. Those settings are independent of the prompt.
The `.tau/extensions/crm.py` project extension registers tools for the shared
operations that currently exist. Mounted HTTP routes call those operations in
`src/crm/services/operations.py` and `src/crm/services/transfers.py` for
business validation, policy, and governed persistence. The installed Tau
extension API does not expose its validated caller to project tools, and this
entrypoint does not supply CRM policy or directory ports. Valid CRM tool calls
therefore return `unavailable`; they cannot use the process SDK credential as
the human caller. This is a fail-closed catalogue, not an operational CRM
agent. The managed Agent release succeeded on 2026-09-26. This prompt change
still requires deployment and verification; the separate trusted caller
binding work is not part of a prompt overlay.

With both exclusions, the agent's business tools are those registered under
`.tau/extensions/`. Tau also retains its required A2A Task controls. There
are currently 46 CRM project tools with Solution Selling disabled, or 66 with
it enabled. Managed deployments set the two values
in `harness_agent.spec.env_vars`, regardless of whether they launch the CLI
or the ASGI entrypoint. The entrypoint has been deployed as a platform Agent;
its trusted CRM caller binding remains unimplemented.

Running `ms-tau` or `api.tau.main:app` locally needs `TAU_LOCAL_MODE=true`,
`MAINSEQUENCE_AUTH_MODE=jwt`, an explicit provider and model, and the signed-in
user's access token. Since `ms-tau-sdk` 1.2.13, when neither
`MAINSEQUENCE_ACCESS_TOKEN` nor `MAINSEQUENCE_REFRESH_TOKEN` is set, local mode
asks the Main Sequence CLI for it (`mainsequence auth token --json`), so one
`mainsequence login` is enough. It uses the CLI named by `MAINSEQUENCE_CLI`,
else the one beside the Python interpreter (`.venv/bin/mainsequence` here), else
the one on `PATH`, and the CLI session must be for Tau's `MAINSEQUENCE_ENDPOINT`.
A launcher or CI may export both tokens instead. A pair read from the project
`.env` still works but is deprecated; `mainsequence refresh-token` run in this
directory removes it. Tau's `/health` reports the source in
`mainsequence_auth_source`. Do not put tokens or provider credentials in the
repository or `.tau` files. Local mode
still calls the live Main Sequence provider services; the CRM agent profile
above excludes MCP. Deploy the Tau runtime separately from
`api.crm.main:app` after a trusted per-turn identity/policy binding and the
confirmation contract are implemented and verified.
