# AGENTS.md

You are a dual-mandate agent. Follow the repository-specific instructions in this file and the
relevant skills, while also keeping in mind that application surfaces, data, and implementation
operate within the Main Sequence platform and must follow Main Sequence platform instructions.

## Repository-Specific Instructions

### Main Sequence CRM implementation routing

Maintain the implemented CRM against the current `src/crm/` models, services and repositories (including the optional `src/crm/campaigns/` module and its `CampaignStore`), mounted `api/crm/` routes, `tests/`, and MkDocs pages under `docs/`. Read the relevant project skill and installed domain/SDK guidance before changing behavior. The paired frontend owns its Vite source and end-user guide. Preserve existing repository/platform instructions and scaffold markers.

Use `.agents/skills/mainsequence_crm_development/` for CRM repository implementation and maintenance, with the appropriate installed `.agents/skills/mainsequence/`, `.agents/skills/metatables/`, `.agents/skills/command-center/` or optional `.agents/skills/ms_tau_sdk/` guidance. Project skills must remain outside SDK-managed/pruned namespaces.

`.agents/skills/mainsequence_crm/` contains six business usage skills for CRM MCP operations: `crm-core`, `crm-deals`, `crm-prospecting`, `crm-prompters`, `crm-discovery`, and `crm-campaigns`. `crm-core` consolidates Contacts, Companies, affiliations, Notes, tags, activity, Tasks, Interactions, owners, settings and merge previews. Use these skills for operating the CRM through its advertised tools. They do not grant permissions or authorize repository changes. Exact enabled tool schemas and actual business results remain authoritative. The API publishes this folder directly with the Main Sequence SDK's `skills_extension` on authenticated `/mcp`.

Solution Selling usage skills are nested under `.agents/skills/mainsequence_crm/solution-selling/`: `crm-prospecting`, `crm-prompters` and `crm-discovery`. Core, Deal and Campaign skills stay directly under `mainsequence_crm/`. Shared MCP guidance and tool allocation live in `crm-core/references/mcp-usage.md` and `crm-core/references/tool-map.json`, served once and linked from other skills through `skill://` URIs. Keep the pack identical to the static repository's usage pack. `tests/test_crm_skill_pack.py` checks tool coverage with Solution Selling enabled and disabled; `tests/test_mcp_skills.py` verifies publication and authenticated file access.

Target: Python FastAPI, Main Sequence MetaTables, Vite React/TypeScript and the Command Center SDK. Reuse the platform's caller identity, which the SDK's request identity verifies in the API; do not rebuild login/users/roles or adopt Supabase/Django/Frappe/Node business backends. Atomic supplied behavioral inspiration; current CRM contracts and installed SDKs govern maintenance. Tau is not required for deterministic tracking or data transfers.

Prove atomic governed commands and fresh-process catalog binding before completing mutation changes. Report executed checks separately from specified, mocked or unexecuted tests.

User-required pre-push gate (2026-10-11): always run the actual CRM agent in
Tau local mode with the workflow's real provider/model before pushing. Run
`.venv/bin/python scripts/verify_local_agent.py`; unit tests, ASGI imports,
health alone, mocked providers and hosted-only tests do not satisfy this gate.
The check must exercise the real CRM MCP bridge, inspect actual successful tool
results, preserve local history across restart, and compare a fresh API read.
Keep CRM smoke-test calls read-only. If the live check fails or is unavailable,
fix or report the failure and do not push or bypass the gate with `--no-verify`.
Install the repository hook with `git config --local core.hooksPath .githooks`.
For changes to mutations, also verify an explicitly owned disposable fixture
through create/update/read-back and clean it up after confirming current state;
never replay an uncertain write. Retain failed-run evidence under ignored
`.local/agent-pre-push/` and distinguish a local-mode agent from hosted CRM data.

Current repository decision (2026-09-23): Alembic `0003` removes `command_receipt`; CRM commands no longer require `Idempotency-Key` or promise replay. Keep version fences and governed atomic writes, and read server state before retrying an uncertain write.

Current repository decision (2026-09-23): Alembic `0004` removes the CRM application workspace table and every `workspace_uid` column. The CRM has singleton settings and direct record foreign keys; platform-injected identity/policy remain authoritative. Do not reintroduce an application workspace, workspace-scoped keys, a workspace UID resolver, or a global workspace mutation epoch.

Current repository decision (2026-10-03): hosted CRM databases are migrated only by the `migrate-crm` Job (`jobs/migrate_crm.py`) that `.mainsequence/workflows/crm-api.yaml` runs before it deploys the API and the CRM assistant. That file is the repository's only workflow file: declare every API, agent and scheduled Job in it, give each API or agent its own `prepare_image` step and a `deploy` step downstream of `migrate`, and keep scheduled Jobs out of `execution.steps`. Local development applies revisions with `metatables --local migrations upgrade --provider src.crm.migrations:migration`. Never run `metatables migrations upgrade` or `downgrade` against a hosted runtime, and never migrate at API startup. Revisions branch raw PostgreSQL SQL on `op.get_bind().dialect.name` so the whole history also runs on local SQLite.

Current repository decision (2026-10-04): `api.crm.main.create_app()` installs `mainsequence.server.fastapi.install_request_identity` once, after every REST route is mounted; Main Sequence's FastAPI launcher (PodDeploymentOrchestrator `3057764`) refuses to serve the API without it. Deployed, it verifies the platform-signed caller assertion of every request; locally, a direct Bearer token. CRM code takes the effective actor only from `authenticated_actor()`, which reads the verified caller with `User.get_logged_user()` and uses the signed `User.get_requester()` when present. Handlers must use this integration rather than `request.state.user_uid`: the launcher does not inject that state. Never add a UID-header, request-state or process-credential fallback. Mount every route the workflow declares as `public_ingress` on the application itself, not only through an included router: FastAPI 0.141 hides included routes from `app.routes`, where the launcher and the SDK look for them, and the API then fails to start. `api.crm.local` presents its SDK sign-in as the Bearer token that the same integration verifies.

Current repository decision (2026-10-09, amended 2026-10-12; ADR 0005): CRM business tools live in `api/crm/mcp_tools.py`, served through authenticated stateless `/mcp` installed after request identity. Hosted MCP business calls use the signed requester when present and check that person's CRM capabilities on every call; never fall back to the agent's permissions. A direct hosted caller is admitted only after a caller-scoped directory lookup proves it is an active human, then its own capabilities are checked. An unbound workload remains denied, including one with privileged Team memberships. REST uses the verified requester when present, otherwise the verified caller. `.tau/extensions/crm.py` only adds the local generic MCP bridge; hosted application tools come from Tau's workflow-declared `mcp_applications`. The API resource key is `crm` because the MCP application prefix cannot contain hyphens. This key change recreates its release when applied: coordinate the frontend release UID, OAuth callbacks, workload Team membership and grants before publishing. The assistant deployment waits for API deployment, which waits for migration. Never infer that chat readiness proves MCP authorization or persistence readiness.

For every material change to a CRM model, business rule, mounted API behavior, persistence, transfer workflow, or delivery status, use `.agents/skills/mainsequence_crm_development/maintain-crm-documentation/SKILL.md` and update the relevant MkDocs concept and API/delivery pages in the same change. Run `mkdocs build --strict` and report its result; keep planned or unverified behavior labeled.

### CodeRepository-Specific Instructions

This file routes coding work in the repository. The separately deployed CRM
assistant uses `.tau/SYSTEM.md` for its conversation role and the API-owned
`/mcp` catalogue for its CRM tools. Tau also loads this file as project context, but these coding
instructions do not grant that runtime file editing, shell access, platform
MCP access, or CRM permissions. In CRM chat, follow the runtime directives and
describe only actions supported by the effective tool catalogue and verified
tool results. The Agent Card supplies the display name, not executable
capabilities.

The managed CRM assistant intentionally excludes Tau's base coding tools and
Main Sequence MCP. Treat that as its chosen runtime profile, not a capability
defect. Application MCP is independent of broad Main Sequence MCP; Tau 2.0.13
retains skill-scoped `read`. Customize conversation in `.tau/SYSTEM.md`.

Do not remove the `<!-- mainsequence-agent-scaffold:start schema=1 source=agent_scaffold -->`
or `<!-- mainsequence-agent-scaffold:end -->` markers. `mainsequence code-repository update AGENTS.md`
uses them to update only the Main Sequence section below.


<!-- mainsequence-agent-scaffold:start schema=1 source=agent_scaffold -->
## Main Sequence Instructions

Use this managed section to select the correct Main Sequence skill. Detailed
procedures belong in those skills and their referenced documentation.

## Authority

- Repository-specific instructions above this block define local intent and
  repository conventions.
- The installed SDK code, CLI help, SDK-owned skills, and version-matched SDK
  documentation define client behavior.
- Installed platform-owned skills and backend-advertised schemas, templates,
  and capabilities define the current platform contract.
- The public documentation site is supplemental when its SDK version differs
  from the installed package:
  `https://mainsequence-sdk.github.io/mainsequence-sdk/`
- If the installed client and platform contract disagree, do not guess or
  update automatically. Use the bug-auditor skill to record the evidence and
  identify the owning side.

## Updates Are Explicit

Do not run any of these commands unless the user explicitly requests that
specific update:

- `mainsequence code-repository update-sdk --path .`
- `mainsequence code-repository update-agent-skills --path .`
- `mainsequence code-repository update-platform-skills --path .`
- `mainsequence code-repository update AGENTS.md --path .`
- `uv run ms-tau skills sync --path .`

A missing or mismatched `.agents/skills/mainsequence/PINNED_FROM.txt` is state
to report, not permission to mutate the repository. The same rule applies to
`.agents/skills/ms_tau_sdk/PINNED_FROM.txt`. When a Main Sequence update is
requested, use the `code_repository_maintenance` skill. The `mainsequence` CLI
never owns or updates the `ms_tau_sdk` namespace.

The SDK owns all of `.agents/skills/mainsequence/`. Its skill copy is local,
requires no sign-in, and deletes everything absent from the installed SDK
bundle. Platform skills are installed separately under
`.agents/skills/mainsequence_platform/` by the authenticated platform update.

## Route By Task

- Product architecture, platform ontology, and CodeRepository Blueprint work:
  use the matching platform-owned design skill declared by the installed
  platform catalog. Do not assume its filesystem path.
- CodeRepository context, local SDK execution, repository structure, and
  implementation routing:
  `.agents/skills/mainsequence/sdk_code_repository_execution/SKILL.md`
- Local environment repair, authentication, explicitly requested updates,
  dependency sync after a dependency change, and publishing with Git:
  `.agents/skills/mainsequence/maintenance/code_repository_maintenance/SKILL.md`
- Blocker analysis, failure classification, and SDK/platform contract mismatches:
  `.agents/skills/mainsequence/maintenance/bug_auditor/SKILL.md`
- MetaTable modeling, queries, external registration, table updates, Alembic
  schema changes, and data discovery: use the skills the `metatables` package
  installs under `.agents/skills/metatables/` and its documentation.
- Code that still imports `mainsequence.meta_tables` or
  `mainsequence.client.metatables`, or calls the retired `mainsequence` table
  and migration commands:
  `.agents/skills/mainsequence/maintenance/metatables_transition/SKILL.md`
- FastAPI APIs serving the Command Center frontend:
  `.agents/skills/mainsequence/application_surfaces/api_surfaces/SKILL.md`
- Jobs, schedules, images, resources, releases, and Artifacts:
  `.agents/skills/mainsequence/platform_operations/orchestration_and_releases/SKILL.md`
- RBAC, sharing, constants, secrets, and access verification:
  `.agents/skills/mainsequence/platform_operations/access_control_and_sharing/SKILL.md`
- Direct recorded model calls, structured extraction, thinking/provider options,
  inference history and idempotent replay:
  `.agents/skills/mainsequence/mainsequence-inference/SKILL.md`
- A2A session discovery, messages, files, and SDK response handling:
  `.agents/skills/mainsequence/a2a_sdk_execution/SKILL.md`
- Turning a CodeRepository into a platform coding agent or selecting other
  platform-owned capabilities: use the matching skill declared by the installed
  platform catalog. Do not hardcode a platform-owned skill path.
- Implementing or debugging a TAU-based Harness Agent: after the platform skill
  establishes the platform contract, use the version-matched skills under
  `.agents/skills/ms_tau_sdk/`. If they are absent and the user requested the
  update, run `uv run ms-tau skills sync --path .`; do not reconstruct those
  SDK instructions from platform documentation.

## Core Working Rules

- Read the relevant skill before acting on a Main Sequence domain.
- Use the current Git checkout as repository, branch, and commit identity. Do
  not ask users to inject CodeRepositoryBranch or Environment identity.
- Use the `mainsequence` CLI as the default platform control surface. Prefer
  `--json` when output will be parsed or used as evidence.
- Use the owning domain package before designing against an unfamiliar domain contract.
- Keep reusable business logic under `src/` and keep API, job, and other
  integration layers thin.
- Verify only the platform objects relevant to the requested outcome.
- Separate verified facts from assumptions and report blockers with the exact
  failing operation.

## Completion

Before implementation, identify the requested end state and the evidence that
will prove it. Do not claim completion until the relevant code or documentation
checks pass and any required platform state has been verified. If live
verification is unavailable, state what remains unverified.
<!-- mainsequence-agent-scaffold:end -->
