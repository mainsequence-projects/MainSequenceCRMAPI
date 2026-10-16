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
An explicit preliminary SDK authentication refusal returns `401`
(`LOCAL_SIGN_IN_REQUIRED`); a forbidden user lookup returns `403`
(`LOCAL_SIGN_IN_DENIED`). A connection reset, transport failure, backend error
or unclassified SDK refresh failure returns `503`
(`LOCAL_SIGN_IN_UNAVAILABLE`), not a claim that the credentials are invalid.
Timeouts retain `LOCAL_SIGN_IN_TIMEOUT`. These errors include a request UID;
the matching `crm.readiness_check_failed` log identifies `local-sign-in-user`
or `local-sign-in-token` and the safe exception type/upstream status without
logging credentials, raw exceptions or tracebacks.
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
The VS Code local stack prints its frontend URL before checking the protected
bootstrap. If bootstrap returns a failed check or does not respond within
100 seconds, the launcher prints a warning and keeps API, Tau, guide and Vite
running. It does not report the backend as ready. The frontend's independent
110-second deadline keeps its startup screen bounded. That screen shows the
public backend error code/message and failed readiness checks when available,
or states that no complete response arrived. Resolve the error and select
**Retry** without restarting Vite. The launch terminal retains API output for
errors that cannot return a response. Failed startup prerequisites and actual
child-process crashes still stop the launch; stopping it manually stops all
four services.

For catalog or settings failures, match the CRM request UID to
`crm.readiness_check_failed` in the API output. The safe message includes the
upstream HTTP status, recognized gateway code and upstream UUID request ID
when available. A catalog failure leaves the unexecuted settings/bootstrap
checks pending. Missing active bindings are named explicitly; a failed check
does not prove the physical table is absent or that the caller lacks CRM access.
Do not log SDK exception strings to investigate this path: they may contain
URLs and arbitrary upstream content.

The read-only 2026-10-15 investigation found a gateway failure on the full CRM
catalog query, reported as
[infrastructure #90](https://github.com/Main-Sequence-Server-Side/infrastructure/issues/90),
and a separate hosted catalog still reporting `0009` without an active core
Prompt binding. The revision `0010` is already authored in this repository.
Repair/finalize hosted application migrations only through the deployment's
`migrate-crm` Job; isolated local development uses `--local` below. No hosted
migration was performed by that investigation or the CRM diagnostic fix.

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
Before rollout, verify the hosted MetaTables API and its system migrations
against client 0.1.35 and complete the CRM Team/namespace setup documented in
[persistence](persistence.md#migration-and-runtime-boundary). A failed migration
Job prevents the API and assistant from rolling out.

After a local upgrade, use a fresh client process to verify the same catalog
and settings check used by CRM readiness:

```bash
uv run python - <<'PY'
from metatables import configure_local_client
configure_local_client()
from metatables.runtime_context import get_runtime_context
from src.crm.platform.catalog import CatalogRegistry

runtime = get_runtime_context()
assert runtime.local_mode and runtime.dialect == "sqlite"
registry = CatalogRegistry()
registry.validate_settings()
print(f"{len(registry.bindings)} active CRM bindings; singleton settings ready")
PY
```

The settings query infers the dialect from that runtime and fails if it no
longer matches the catalog's DataSource. Repeat migration runs must still check
physical contracts even when they report `already current`. See the
[0.1.33 migration verification](verification.md#metatables-0133-upgrade-and-push-preflight-2026-10-10)
for the repaired metadata-refresh and SQLite downgrade behavior.

The isolated local runtime checks the migration history and catalog binding,
not the running CRM API. The CRM loopback launcher does not call
`configure_local_client()`, so it discovers the Environment's hosted MetaTables
API, and its business queries use PostgreSQL SQL. SQLite verification does not
prove those production commands or hosted table permissions.

## Collection query regression checks

Run the focused request-shape and PostgreSQL collection checks:

```bash
.venv/bin/pytest tests/test_resource_collections.py -q
```

The PostgreSQL checks require existing `postgres`, `initdb`, and `pg_ctl`
binaries on `PATH`, the installed `psycopg` driver, and a non-root POSIX user.
They create a temporary UTF-8 cluster reachable only through a private Unix
socket, seed disposable rows, roll back each test, and stop/remove that cluster
on exit. They never connect to an existing database, change MetaTables runtime
selection, or migrate hosted data. When those prerequisites are missing, the
engine-specific cases are explicitly skipped; the request-shape checks still
run.

On 2026-10-12, PostgreSQL 14.15 executed the actual collection SQL against
1,000 active fixture contacts. `EXPLAIN ANALYZE` showed each of the three
display-enrichment subqueries running 50 times for a 50-record second page,
compared with 1,000 times in the previous full-projection/count query. Checks
also cover null-last ordering, UID ties, numeric deal sorting, filters,
archives, empty pages, exact totals and HTTP permission revocation.
The MetaTables transport is captured for these tests: they verify SQL and
application behavior, not hosted authorization or end-to-end latency. Platform
cold starts remain expected behavior and are outside this query change.

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

### Required live check before every push

Run the actual local-mode agent before publishing:

```bash
.venv/bin/python scripts/verify_local_agent.py
git config --local core.hooksPath .githooks
```

The repository's executable `.githooks/pre-push` runs this check on every push
and rejects a failed check. It tests the checked-out revision being pushed;
commit pending changes first. Do not bypass it with `--no-verify`.

The check starts the real `api.tau.main:app` and `api.crm.local:app` on unused
loopback ports. It selects the workflow's provider, model and thinking level
(currently `openai-codex/gpt-5.6-luna/medium`), keeps broad coding and platform
MCP tools excluded, and uses the existing Main Sequence CLI sign-in. Protected
CRM bootstrap must report ready before it sends one real chat turn that
discovers CRM MCP and performs a uniquely scoped,
read-only contact search. Actual successful MCP tool results are required;
an assistant's success claim alone does not pass. Both processes are restarted
to verify local conversation persistence and compare a fresh CRM API read.
`--contact-uid <UID>` instead verifies one explicitly selected record.

Tau's state and private process logs stay under ignored
`.local/agent-pre-push/<run>/`; each `report.json` records the version, model,
result and evidence boundary. Tau runs locally, but its provider and user
authentication are real remote services, and CRM business reads still use the
Environment's hosted PostgreSQL MetaTables. This check creates no CRM fixture
and runs no migration. An unavailable provider, sign-in or database blocks the
push. If legacy credentials in `.env` override the saved CLI login, repair
the sign-in with `.venv/bin/mainsequence refresh-token`; never print or copy
the token values. The developer also needs Reader access to the CRM namespace
for this read-only gate: workload Team grants do not grant the developer access,
and administrator rights to manage grants do not grant table reads. Obtain the
namespace owner's approval for any additional grant. Tests and ASGI imports
remain useful separate checks.

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

`ms-tau-sdk` 2.0.13 is locked to its release tag `v2.0.13` in `pyproject.toml` and
`uv.lock`. `uv sync --locked` installs it alongside the API, but CRM startup
does not start Tau. The separate ASGI entrypoint `api.tau.main:app` uses
`create_app()` and reads the SDK's normal runtime settings. For the CRM agent,
exclude Tau's coding tools and Main Sequence MCP in the process environment:

```bash
TAU_LOCAL_MODE=true MAINSEQUENCE_AUTH_MODE=jwt \
TAU_EXCLUDE_BASE_TOOLS=true TAU_EXCLUDE_MAINSEQUENCE_MCP=true \
CRM_LOCAL_API_ORIGIN=http://127.0.0.1:38641 \
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

The installed SDK provides coding guidance that can be synchronized with
`uv run ms-tau skills sync --path .` into `.agents/skills/ms_tau_sdk/` when that
separate repository update is requested.
Project-owned runtime behavior belongs under `.tau/`. The typed CRM
tools and their authorization requirements are in
[ADR 0005](../crm_core/adrs/0005-crm-application-mcp.md). The
project `.tau/SYSTEM.md` replaces Tau's packaged general prompt so the chat
speaks as a CRM application assistant. Restart Tau or start a new session after
changing it, then inspect the effective session prompt. The Agent Card controls
the display name; the process settings intentionally exclude general coding
and Main Sequence MCP tools. Those settings are independent of the prompt.
The `.tau/extensions/crm.py` extension registers only `crm__list_tools` and
`crm__call_tool` in local mode. They use the official MCP client against the
loopback API's `/mcp`; `CRM_LOCAL_API_ORIGIN` defaults to
`http://127.0.0.1:38641`. Start `api.crm.local:app` first. That launcher supplies
its saved sign-in to the API's request verification and connects local policy
and directory adapters. The bridge accepts no credentials or endpoint from
model arguments and never retries a tool call. It contains no business schemas
or persistence logic. The API catalogue contains 46 tools with Solution Selling
disabled, 69 with it enabled; see the [MCP contract](../api/mcp.md).

Main Sequence 9.0.23 and Tau 2.0.13 require MCP Python SDK 2.x; the lock installs
2.3.0. The API uses `MCPServer` with its existing typed CRM tool boundary and
the SDK's skill publisher, and the local bridge
uses the required `httpx2` transport and two-stream client context. It serializes
results with wire aliases so the model still receives `inputSchema`,
`structuredContent` and `isError`. Business schemas, caller checks and the
no-retry boundary remain in the CRM service. See the
[MCP skill publication](../api/mcp.md#sdk-skill-publication) for the selected
folder and the five workflows exposed by the API. Restart the API after
editing a published skill: the SDK captures its files at application creation.

In hosted mode the project extension registers nothing: Tau's declared
application MCP supplies the same two discovery/call tools with per-turn
access. The workflow enables requester delegation and grants the assistant view
access to the CRM application. Hosted assistant calls use the signed requester.
A direct human OAuth MCP caller is also supported after the API's caller-scoped
directory check proves that it is active and human; an unbound workload remains
denied. The hosted policy/directory/bootstrap adapters are installed by
`api.crm.main.create_app()`; see the [hosted authorization decision](../crm_core/adrs/0005-crm-application-mcp.md).
Unavailable storage, failed caller-type resolution, or failed authorization
still fail closed; workload access alone never substitutes for the person.
Hosted Contact create/update and independent persistence read-back have been
verified through Command Center Chat with GPT-5.6 Luna on its recorded runtime.
Main Sequence 9.0.20 and Tau 2.0.10 were deployed successfully. The new Tau
2.0.11 sender recovered a successful MCP create/update/get turn after the
platform returned an ambiguous HTTP 502. Both hosted releases were promoted to
Tau 2.0.11, and after the platform repair an independent read-back confirmed
that turn's writes and the fixture was cleaned up. The current Main Sequence
9.0.23 and Tau 2.0.13 update needs its own hosted check after deployment. See
[verification evidence](verification.md).

Both tool exclusions remain enabled. They omit broad Main Sequence MCP and
replace general coding tools with Tau's skill-scoped `read`; A2A Task controls
remain. These exclusions do not disable application MCP.

In hosted mode Tau 2.0.13 verifies platform-signed caller assertions and
requires the launcher's projected workload identity token file for its runtime
credential exchange. Those hosting settings belong to the platform launcher;
they are not local-mode flags or repository credentials. The hosted entrypoint
served the earlier verified Chat MCP turn; that proof does not establish the
fresh updated-runtime test. Tau 2.0.13 waits for a waking application
within a bounded readiness deadline before admitting its MCP calls; it does not
retry an uncertain business write.

Since 2.0.11, Tau also honors a finite MCP per-call response deadline through
its HTTP transport. A longer explicit tool deadline is no longer cut short by
the default backend HTTP read timer. Startup/catalog and connection limits
remain bounded. A timeout or disconnect still leaves the remote write outcome
unknown; read current CRM state before issuing another write.

Since 2.0.12, Tau enforces the platform's 90-second limit on a hosted direct A2A
Message and answers HTTP 504 `DEADLINE_EXCEEDED` when it expires. Send longer
work as a Task, and never resend a Message that ran out of time: its work is
not rolled back. Local mode has no platform Message limit and refuses to start
with `MAINSEQUENCE_A2A_MESSAGE_LIMIT_SECONDS`, which only the platform sets.

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
above excludes broad Main Sequence MCP, while CRM application MCP remains
available. Deploy Tau separately from `api.crm.main:app` using the workflow
and rollout checks in ADR 0005. Confirmation-dependent operations remain absent.

## Solution Selling live agent check

After a Solution Selling tool change, run the real local agent against explicit,
owned fixture references before committing:

```bash
.venv/bin/python scripts/verify_local_agent.py --solution-selling-fixture /absolute/path/to/fixture.json
```

The untracked JSON contains `deal_uid`, `company_uid`, `contact_uid`,
`interaction_uid`, `profile_uid`, and `prompter_uid`, with optional
`solution_selling_uid` and `inputs`. Use a profile with unanswered questions and
an Interaction belonging to the selected Deal. The gate provisions nothing.
It discovers current schemas and runs exactly the three read-only helpers,
checks a rendered draft, copied unanswered questions and source versions,
restarts both processes, and compares each actual result with a fresh REST read.
The workflow's real provider/model and the normal saved CLI login remain required.
Local mode describes the agent/conversation store; the CRM dataset remains the
configured environment. Remove only disposable records explicitly owned by the
test, after verifying their current state. Never replay an uncertain setup write.
The pre-push hook still runs its read-only Contact gate on the committed revision.
