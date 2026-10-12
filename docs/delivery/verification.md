# Verification and release

Run the repeatable local checks from the repository root:

```bash
uv sync --locked
.venv/bin/pytest -q
.venv/bin/ruff check api/crm src/crm tests
.venv/bin/mkdocs build --strict
```

The strict MkDocs build catches broken navigation and local links. It does
not prove that the described API behavior works; tests and runtime evidence
must accompany material changes. The running FastAPI OpenAPI document can be
compared with the [mounted route index](../api/route-index.md);
`tests/test_documentation.py` enforces method/path parity.

## Evidence boundaries

### Solution Selling MCP read workflows (2026-10-12)

Implemented `crm_prompters_render`, `crm_solution_selling_context_get` and
`crm_diagnoses_prepare` in the API-owned catalogue, sharing the governed service
with REST. The active catalogue contains 69 tools: 38 reads and 31 writes.
All 205 tests, Ruff, strict MkDocs and mounted-route documentation parity pass.
These are code/contract checks; they are separate from the live evidence below.

Before committing, the real local Tau 2.0.12 agent ran with the workflow's
`openai-codex/gpt-5.6-luna/medium` configuration and the normal CLI login.
It loaded the project Solution Selling skill, discovered MCP schemas, and
executed exactly the three new reads in order, each with successful business
results. The context returned actual fixture Interaction history and source
versions. Diagnosis preparation copied nine questions with null answers,
labelled its business issue a hypothesis, and returned `saved: false`.
After restarting both processes, public local history retained the same calls
and every fresh REST result equalled its actual MCP result. Sanitized evidence
is retained under ignored `.local/agent-pre-push/`.

This is local agent/conversation verification against the configured hosted CRM
dataset, not proof of local SQLite persistence for CRM records. The test used
marked disposable records and a separate owned pipeline/stage; the agent calls
were all read-only. Setup saved exact ownership, UIDs and versions for scoped
cleanup. Fixture data and credentials are excluded from the commit.

The push must pass the unchanged mandatory Contact smoke scenario on the
committed revision. After push, verify the workflow's migration, API and
assistant steps for that exact commit, and initialize the deployed MCP to
confirm all 69 tools and the three new read-only schemas. Keep subsequent
platform evidence separate from the local results above; neither bootstrap
nor a Git push alone proves deployment or hosted business authorization.

### Main Sequence 9.0.22, MetaTables 0.1.34 and Tau 2.0.12 (2026-10-11)

The repository now requires `mainsequence[mcp]>=9.0.22` and
`mainsequence-metatable>=0.1.34`, and pins `ms-tau-sdk==2.0.12` to its release
tag `v2.0.12`, commit `f3cb704a7a5ab5b722782bdc7c016dd352f16852`. `uv lock`
moved only those three packages; the local environment and the deployment
`requirements.txt` export match. The managed skill copies were refreshed from
the installed packages: Main Sequence 9.0.6 to 9.0.22, MetaTables 0.1.33 to
0.1.34 and Tau 2.0.9 to 2.0.12. No CRM code, migration, workflow declaration
or resource key changed; [ADR 0005](../crm_core/adrs/0005-crm-application-mcp.md)
records the new direct-Message limit.

Executed checks: all 201 tests, Ruff, strict MkDocs and the documentation test
pass. The unchanged workflow passes live backend validation of the committed
file with `valid: true`, API 2.3.0, no errors or warnings and
`applicable: null`. Its three resource keys are unchanged from `origin/main`.

The required local agent check passed on commit
`13c214b728f3a85b0cad599abaaee7e7b43539bb` with a clean tree, Tau 2.0.12 and
`openai-codex/gpt-5.6-luna/medium`. Protected bootstrap returned HTTP 200 with
all six checks ready. The real turn called `crm__list_tools`, then one
`crm__call_tool` running `crm_contacts_list` for a unique marker, which
returned no items. After both processes restarted, the local history was
unchanged and a fresh REST read matched the MCP result. The check's stream
client disconnected at its 5-second read limit after about 13 seconds; it
recovered the same persisted turn from local history without sending again.
This supersedes the blocked status recorded below for this gate.

The earlier catalog failure is gone because of an access change made outside
this repository. Read-only inspection at about 21:00 UTC shows the developer
reaching the CRM tables as a member of the owning Team
`mainsequence-crm-production`, which makes the developer's effective access
Writer rather than the Reader grant this gate documents. The Team also lists
the API and migration Job workload Users recorded below and a service account,
`ae0690b5-a8e9-4996-ad90-d1c40daf1dec`, that this documentation does not
record. The namespace's only grant is still Writer to that Team. This update
changed no grant or membership. The hosted deployment of these versions and its
MCP verification remain to be done after the push.

### Mandatory local agent pre-push check (2026-10-11)

The user requires a real local-mode agent test before every push. The
repository now provides `scripts/verify_local_agent.py` and the executable
`.githooks/pre-push` gate, installed per checkout with
`git config --local core.hooksPath .githooks`. The live check uses the workflow's
real provider/model, the project prompt and local CRM MCP bridge, verifies an
actual governed read, then restarts Tau and the CRM API to check persisted
local history and independent read-back. CRM calls are read-only; hosted
storage and credentials are not replaced by mocks. See the
[local check procedure](local-development.md#required-live-check-before-every-push).

The first executed 2.0.11 local run failed during startup with
`Main Sequence JWT refresh failed`. Tau was reading legacy access/refresh
entries from `.env` rather than the current saved CLI sign-in. No chat turn
or CRM tool ran, and nothing was pushed. The supported CLI `refresh-token`
removed those legacy entries and renewed the saved session without printing
credential values.

The next real local turn used Tau 2.0.11 and
`openai-codex/gpt-5.6-luna/medium`, discovered CRM MCP, then called
`crm_contacts_get` once for the existing owned verification record. Its bridge
returned `outcome_unknown` after 60 seconds. The completed public local history
was recovered after restarting Tau; it proves the call failed the verification
gate, even though the turn itself completed. No write or retry was sent.

The protected bootstrap preflight then returned HTTP 503 `CRM_NOT_READY` with
an unavailable catalog. Read-only diagnostics verified the intended Production
Environment and the same human UID used by the hosted MCP test. Both the current
GET filter and supported body filter returned zero of the 26 required CRM
tables. The namespace's only grant is Writer to the approved API/migration
workload Team; the human has no table-read contribution. Adding Reader for the
developer requires a separate access decision. This local failure is therefore
an access prerequisite, not evidence of another SDK defect. A passing end-to-end
local run and fresh read-back remain unverified; no changes from this gate task
have been pushed.

All 27 focused Tau, MCP, local-auth and documentation tests passed; Ruff and
strict MkDocs also passed. The installed hook rejected an uncommitted checkout,
and the gate correctly rejected the recovered real `outcome_unknown` result.
These checks do not substitute for the still-blocked live end-to-end check.

After the user reported the Django repair, another local run at approximately
12:27 UTC started Tau 2.0.11 with the real Luna provider successfully. Protected
CRM bootstrap still returned HTTP 503 `CRM_NOT_READY` at the catalog check, so
no chat or business call was dispatched by this run. Fresh namespace inspection
confirmed the existing workload Team assignments were unchanged, with no human
read contribution; the signed-in developer still sees zero of the 26 CRM tables.
The previously requested Reader approval remains pending. No grant was added,
and this failure continues to block pushing the pre-push gate changes.

### Tau 2.0.11 and the MCP persistence retest (2026-10-11)

[Tau issue #90](https://github.com/mainsequence-sdk/ms-tau-sdk/issues/90) is
closed and its fix is released as
[v2.0.11](https://github.com/mainsequence-sdk/ms-tau-sdk/releases/tag/v2.0.11),
commit `7a17e86293d14120fe79c8165bc74054c4279c36`. The repository pins that
release and the canonical dependency sync refreshed `uv.lock`, the local
environment and deployment `requirements.txt`. Main Sequence remains 9.0.20
and MetaTables remains 0.1.33. All 201 CRM tests and Ruff pass. The existing
migration-gated workflow and `openai-codex/gpt-5.6-luna/medium` default remain.

[Platform issue #932](https://github.com/Main-Sequence-Server-Side/tdag-django/issues/932)
was initially closed after the maintainer repaired redundant billing allocation
work. Its final resolution at 12:19:40 UTC corrected that diagnosis: the billing
change removed unnecessary load, while the worker restart temporarily drained
overlapping runtime-monitor passes. The monitor's 60-second target lock was not
renewed during long passes, so overlapping chains occupied worker slots and
delayed activation claims. The maintainer reports
[issue #934's fix](https://github.com/Main-Sequence-Server-Side/tdag-django/issues/934),
commit `487f4512d`, renews each running pass's existing lock without changing
public contracts, permissions or migrations. This is owner evidence of the
internal cause; the consumer read-back below verifies the repaired path.

Independent public session entries recovered the earlier uncertain turn's
final error: only `crm__list_tools` ran, and no business create or update was
executed. A fresh authenticated REST contact search for the exact earlier
marker returned HTTP 200, no items and `totalItems=0`. This resolves the prior
unknown outcome without replaying its message. A new bounded verification
used owned session `ac48ff04-8bf5-4310-b341-c81cf0db33f2`, a new unique fixture
marker and message `1df84d82-96ae-4578-aacd-8950bcb2751a`. Its Tau 2.0.11 sender
outlived the previous 60-second cutoff, then received structured HTTP 502
`a2a_transport_outcome_ambiguous` after 118.75 seconds, correlation
`d21852d9988d4aa79fcd7725933b8dde`. The message was not replayed. Operational
events proved that the original turn continued, and public session entries
recovered successful CRM MCP list/create/update/get calls and the final answer.
Contact `ac06d52f-298a-41b2-9dc6-c04ace99e0af` advanced from version 1 to 2 with
title `MCP updated and persisted`; both attribution fields identify the human
requester `e2a4f38a-1b5f-40a3-974f-70bc8f065b3f`.

This retest used the new 2.0.11 **sender** against the still-active Tau 2.0.10
assistant revision `3a389ee8-e6ff-46a9-aff0-44e74be22ed5` and API revision
`3d740d54-39f5-4c28-a9b5-d23008bf370d`. The recovered turn's MCP results and
the independent read-back are separate evidence: the fresh external detail
read was blocked before its REST request at 10:51:05 UTC by another
`The runtime activation could not be scheduled.` refusal. A second attempt
recorded public operation `6b209537-6469-4a44-b17a-953c9c5cd1ef`, created
10:53:37 UTC and failed without a start time at 10:54:37 UTC. Admission became
`unavailable`, with `can_request=false` and replicas 0/0. Issue #932 was reopened
with this exact recurrence; its fresh internal cause was not established then.
Admission subsequently recovered in operation
`dd662d44-39f2-4d76-8890-415ca07a9c90`, with the caller ready at 11:07:55 UTC.
The admitted contact detail read nevertheless returned HTTP 500 at 11:09:04 UTC
after 66.940 seconds, request `c1e542cb1e404248f24b4af6cfefd8e2`.
Public API logs identify `ApiResolutionError` and two approximately 20-second
timeouts reaching the MetaTables release's platform runtime-access endpoint.
This establishes the failing dependency path, not the platform's internal cause.
A further read-only attempt after catalog reconciliation failed admission at
11:16:35 UTC. Operation `1c90c639-0ca4-4a57-9c12-8c4c1261cb51` failed without
a start time after approximately 61 seconds. No additional business write
or archive was issued.
Those attempts left independent persistence confirmation and fixture cleanup
unverified. After the final Django repair, the same contact was read without
replaying its original message or business writes. Runtime admission operation
`f6b0c32d-0fd1-4326-bc16-e36bed7103b7` was requested at 12:27:46 UTC and started
at 12:27:48 UTC; the client observed `can_request=true` at 12:28:59 UTC.
Independent REST read-back returned HTTP 200 against API revision
`11ec7117-d090-47e0-b302-9548a81e1d7b`, with the exact marker, updated title,
version 2 and both attribution fields set to the human requester. This confirms
that the earlier MCP create and update persisted outside their original turn.
After a fresh exact-state check, one archive with `expected_version=2` returned
HTTP 200 and version 3 at 12:33:15 UTC. An independent detail read confirmed
the archive, and an exact-marker active collection read returned no items and
`totalItems=0`. The fixture is cleaned up; no original create/update or uncertain
write was replayed. Hosted MCP persistence and cleanup are now verified. The
developer's local-mode table-access prerequisite above remains unresolved.

The dependency update was pushed as `be0e5fc0943dc65a28ac373e2615a974323632ae`.
Its workflow `d21a34c8-58af-4f99-bfce-f8d97e0abfa6` completed both candidate
images; both full build logs confirm Main Sequence 9.0.20, MetaTables 0.1.33
and Tau 2.0.11. Migration Job `832cacc7-ca36-46b7-8238-5a126b31f142` reported
`0009 (already current; catalog reconciled)` at 11:07:01 UTC, total 538.849
seconds. The graph confirmed migration success, and both release deployment
runs succeeded. Both
releases subsequently reached their intended active and desired revisions:
API `8e88bf90-65fd-44a1-84c6-004eff66db6f` and assistant
`1d078f53-565c-4336-92e8-f01862127d77`. The public Agent record independently
confirms `openai-codex/gpt-5.6-luna/medium`. This verifies Tau 2.0.11 promotion;
the earlier successful business turn remains scoped to its recorded 2.0.10
host. The later updated API runtime's independent persistence and cleanup
verification passed as recorded above; no new business write was sent through
the 2.0.11 assistant during this retest.
The older documentation
push `7df453c` failed at its migration Job before the reported platform repair,
because MetaTables runtime discovery timed out. Neither that older failure nor
the new release promotion establishes uninterrupted runtime availability.

Tau's timeout repair changes no CRM wire contract, authorization, schema or
write-retry policy. [ADR 0005](../crm_core/adrs/0005-crm-application-mcp.md)
is amended for dependency and timeout behavior; no new ADR is needed.
Managed Main Sequence/Tau skill copies remain pinned to 9.0.6/2.0.9; the
installed 2.0.11 package guidance was read without refreshing those namespaces.

### Public A2A fixes and Tau 2.0.10 uptake (2026-10-11)

[Platform issue #931](https://github.com/Main-Sequence-Server-Side/tdag-django/issues/931)
and [SDK issue #211](https://github.com/mainsequence-sdk/mainsequence-sdk/issues/211)
are closed. The platform maintainer reports that the sender uses public A2A
roles and preserves structured runtime rejection instead of masking it during
HTTP stream cleanup. This is upstream evidence, not a new CRM persistence test.

The canonical SDK update and repository sync installed Main Sequence 9.0.20
and pinned Tau to [v2.0.10](https://github.com/mainsequence-sdk/ms-tau-sdk/releases/tag/v2.0.10),
commit `39c144f24695b7aaf2fc245e25e13cb51c4ce665`. MetaTables remains 0.1.33.
Tau adds bounded waiting for waking application runtimes and preserves MCP
timeouts. The installed Main Sequence sender emits `ROLE_USER` and validates
the public response role. No CRM role override, credential fallback or write
retry was added. New conversation defaults remain
`openai-codex/gpt-5.6-luna/medium`.

All 201 API tests, Ruff, strict MkDocs and the documentation contract pass with
the new dependencies. Commit `82aae9b9c245612c8b199078b9ff35226682808a` was
pushed. Workflow `8dd2983c-9846-409e-a7fd-095e704cb372` succeeded in all five
steps at 08:38:05 UTC, including migration Job run
`17ba919c-0473-45eb-bdc2-6bf5eee1b2fc`: schema `0009` was already current and
the application catalog was reconciled. Both completed image logs confirm
Main Sequence 9.0.20, MetaTables 0.1.33 and Tau 2.0.10. The API active and desired
revision became `3d740d54-39f5-4c28-a9b5-d23008bf370d`; the assistant's became
`3a389ee8-e6ff-46a9-aff0-44e74be22ed5`. Fresh authenticated readiness and
bootstrap returned HTTP 200 around 08:55–08:57 UTC, with all six checks ready,
the human identity and `assistant.enabled=true`. No GitHub check runs were
configured for that commit; these are executed local and platform checks.

The fresh canonical platform MCP sender test used owned session
`b17527e1-4d74-49bb-8f24-8826b4005f67` and message
`dede0066-e2d6-450e-a19b-d7f5f3e6f6ab`. Its first attempt received structured
HTTP 409 `a2a_runtime_submission_blocked`, with `can_submit=false`, rather than
the old masked HTTP 500. Only after that explicit pre-dispatch refusal and
public admission becoming ready was the same message identity sent once.
The admitted call then raised `ReadTimeout` after approximately 60 seconds,
despite its 420-second per-call MCP deadline. Tau's platform MCP client keeps
the backend HTTP read timeout independently of that per-call session timeout;
this separate surface is tracked in
[Tau issue #90](https://github.com/mainsequence-sdk/ms-tau-sdk/issues/90).
The application MCP timeout fixes are not shown to have regressed.

The server-side turn survived the sender timeout. Its operational log records
`runtime.mcp_application.failed` with `BackendError` at 09:02:44 UTC, and public
session reads continued to report `running`. Independent read-back was blocked
before the REST request: supported API runtime admission failed with
`The runtime activation could not be scheduled.` around 09:05:52 and again
09:16:38 UTC. Public snapshots showed a queued wake with `can_request=false`.
The runtime scheduling/access incident is tracked in
[platform issue #932](https://github.com/Main-Sequence-Server-Side/tdag-django/issues/932);
its internal cause remains unverified. The API and migration workload Team
membership and approved namespace grant were checked unchanged.

No admitted or uncertain write was replayed. The new fixture's existence and
persistence remain **unverified** because normal read-back could not be
admitted; this requires reading the existing marked fixture and turn outcome
after access is restored, before any new write. The earlier successful Chat
persistence proof below remains valid for its recorded runtime. A successful
deployment or transient readiness does not establish later runtime availability
or completion of this new MCP test. The version and readiness amendment belongs in
[ADR 0005](../crm_core/adrs/0005-crm-application-mcp.md), without a new ADR.
Managed Main Sequence and Tau guidance remain pinned to 9.0.6 and 2.0.9;
the installed 9.0.20 and 2.0.10 package source and guidance were used without
silently refreshing those separately managed namespaces.

### Hosted adapter repair and controlled provisioning (2026-10-11)

The hosted entrypoint now installs policy, directory and bootstrap adapters.
Six new signed-request tests exercise default bootstrap wiring, Writer/Reader
Team decisions, Organization admin access, Team removal between MCP calls,
requester isolation from an admin workload, self-only delegated ownership and
caller-scoped direct owner reads. Settings and business stores in those tests
are stand-ins; they do not prove hosted persistence. The real SDK verifies the
test assertions, using a test signing key.

The one workflow retains its validated migration-before-deploy graph and
automatic promotion policy. A proposed paused provisioning variant failed
backend validation because disabling initial deployment requires pinned image
UIDs. It was restored without selecting image UIDs or publishing that variant.

On 2026-10-11 the user explicitly approved the Production owning Team and
namespace grant. Team `mainsequence-crm-production`
(`6b4a3104-e2e3-4c09-b746-418283f3720e`) has Writer only on namespace
`mainsequence-crm` (`ca53e776-00bd-4ee9-ad83-dc0f49f798b1`). Its verified
members are the new API workload User
`c9b66783-8ce0-48d3-9b92-415a1b26fdec` and migration Job workload User
`8c307bb6-a7b2-4ef0-8617-e47e9c055340`. The assistant has no storage grant.
The earlier automatic approval rejection is superseded by that explicit approval.

API commit `4705782` was pushed through the existing GitHub remote. The push
webhook created workflow run `58fce803-5bbf-473c-9870-8259ff2b1203` for that
exact commit. Its image preparation completed and migration Job run
`9fb62849-8cb8-4b09-b5f7-8694019561b0` succeeded against the verified Production
MetaTables runtime: PostgreSQL advanced `0008` to `0009` and all application
catalog bindings were reconciled. All five workflow steps succeeded, including
API deployment `f8d88cb3-d8dd-48e3-9730-ef082bebb497` and assistant deployment
`780a777e-8f91-4abe-af2f-08df58729bb1`.

API release `2de75e21-bfe1-4b77-b668-6916488ed317` initially activated MCP revision
`8b8985d9-f7e2-4465-96be-6f293f37955a`. A real authenticated readiness call
returned HTTP 200 with all six checks ready; bootstrap also returned 200 and
the verified human identity. The official MCP client initialized the hosted
endpoint, listed 66 tools including `crm_contacts_create`, and verified that a
business read without a signed requester returns `forbidden`. These checks
prove admission and fail-closed delegation, **not successful MCP writes**.

Bootstrap initially reported the assistant disabled. Public sharing inspection
confirmed the API workload had no view grant on the assistant Agent. Commit
`fa5ef89` added API view access to `crm-assistant` for discovery. Workflow
`3e1ea9c6-2fdd-4264-acfa-70fccbe60b21` succeeded in all five steps, including
migration Job run `e41d8659-0ab5-4345-89c2-a6014ea562c7`. The API's active and
desired revision became `949a023b-4472-48ad-8ecb-6cca3f20551d`; the assistant's
became `32778bb1-bd6f-45de-a510-705fcf63b131`. The applied Agent view grant and
a fresh authenticated bootstrap with `assistant.enabled=true` are verified.
All six readiness checks pass. The assistant's API view grant and
`acts_for_requester=true` were also verified through public platform reads.

The bounded real write test created an owned AgentSession
`199f74fe-6397-4714-a410-2fb2d3460973`, then the SDK's public A2A sender failed
with HTTP 400: `A2A v1 Message role must be ROLE_USER or ROLE_AGENT`.
Main Sequence 9.0.19 emits the internal `ROLE_REQUESTER`, while Tau 2.0.9 accepts
the public roles. This matched the then-open
[SDK issue #211](https://github.com/mainsequence-sdk/mainsequence-sdk/issues/211).
That direct request failed before a model turn or CRM write. The user then
completed the supported CLI browser login. Tau's credential-owning
`MainSequenceMCPClient` invoked canonical `a2a.send_message` in Message mode,
using the same owned session and stable message identity. It returned HTTP 500
with correlation ID `0c6137c8cfbb4a218b703d3640f1d37c`, now tracked in
[platform issue #931](https://github.com/Main-Sequence-Server-Side/tdag-django/issues/931).
No retry followed that uncertain outcome. The public session remained
`pending`, and a fresh authenticated REST search through the governed
MetaTables store returned zero contacts for the exact verification marker.
These checks do not establish successful MCP persistence or the platform's
dispatch outcome. No runtime assertion, token or SDK role was patched to
bypass these boundaries.

The supported Command Center Chat reached a real model turn in owned session
`954916fc-bc49-4cb5-ae45-cea2a6b18f0f`, using the existing Codex subscription
and GPT-5.6 Sol. At 07:29 UTC, while the deployment above was still finishing,
`crm__list_tools` returned `Main Sequence could not provide access to the crm
application.` No business tool ran in that turn. Its operational log records
`runtime.mcp_application.failed` with `BackendError`. At 07:38 UTC, after
startup, a read-only discovery succeeded and exposed create, update and get.
The earlier access failure is no longer reproducible after that startup;
the logs do not establish its exact cause. A platform-advertised
GPT-6 Astra selection previously failed before tools because Tau's installed
model catalogue does not include it; that mismatch is tracked in
[Tau issue #89](https://github.com/mainsequence-sdk/ms-tau-sdk/issues/89).

At the user's request, the workflow now selects `openai-codex`,
`gpt-5.6-luna` and `medium` for new conversations. Tau 2.0.9's installed
catalogue includes that model and reasoning level. The exact workflow passes
live backend validation without errors or warnings. Commit `c813a6d` was
pushed, and a public Agent read confirms those exact applied defaults.
Its migration-gated workflow `90f09ddd-ee88-4998-a50d-a071d8b47aab` was still
running when this evidence was recorded. Existing sessions retain their
selected model.

The browser session then selected `openai-codex/gpt-5.6-luna/medium`, confirmed
by a fresh public AgentSession read. A real turn created exactly one marked
disposable Contact through application MCP, updated only its title with the
current version, and read it back. Contact
`f173c54f-1234-4274-a1f3-9fde344d9355` advanced from version 1 to 2 with title
`MCP updated and persisted`. Both attribution fields contain the signed
human requester UID `e2a4f38a-1b5f-40a3-974f-70bc8f065b3f`, rather than a
workload User. A separate authenticated Python process performed a fresh REST
detail read through the API's governed MetaTables store and independently
confirmed the UID, exact marker, version, title and both attribution fields.
This proves hosted MCP create/update persistence for that Contact path. It
does not establish every tool, Team permission combination or transfer gate.
After read-back, the exact fixture was soft-archived through the REST version
command at expected version 2. A fresh detail read confirms `archived_at` and
version 3, and the default active collection has zero matches for its exact
marker. No other record was changed.

Frontend commit `bfa90b0` binds its build to the active API UID above. Workflow
`03a4e19e-1529-4505-884d-389b7222fd40` and Static Site deployment
`7243e9c7-66a4-4638-919c-67df680a666c` succeeded. The active frontend revision
is `f4485067-625e-4909-b41b-9905dfc0b11f`. Real CRM frontend embedding and
Google OAuth provider registration remain unverified. The browser proof above
uses Command Center Chat with the deployed CRM assistant, rather than the
CRM Static Site's embedded chat.

Executed checks pass: all 201 API tests, Ruff and strict MkDocs. Both current
workflow files pass live backend validation with no errors or warnings. The
rollout helper replaces the frontend binding only after the backend advertises
the new API's active MCP revision in this branch Environment. It resolved and
applied that binding. The frontend's ten tests, documentation checks,
TypeScript, Vite and Docusaurus builds passed with the new release UID.

The authored-metadata and downgrade fixes verified with MetaTables 0.1.33 on
2026-10-10 remain the MetaTables dependency baseline. Main Sequence 9.0.20 and
Tau 2.0.10 supersede the client/runtime versions used for this recorded proof.
The application authorization amendment is in
[ADR 0005](../crm_core/adrs/0005-crm-application-mcp.md).

### MetaTables 0.1.33 upgrade and push preflight (2026-10-10)

The two reported MetaTables issues are closed, and PyPI publishes client/API
0.1.33. The CRM minimum requirement, lockfile, environment and canonical runtime
export now use this version. The canonical SDK update command completed;
Main Sequence 9.0.19 remains the latest published SDK and was already installed.
Tau remains 2.0.9. MetaTables' managed guidance was refreshed in both CRM
projects. The SDK-owned guidance remains pinned to 9.0.6; the updater reports
that mismatch and leaves it untouched because no SDK scaffold refresh was
requested.

Executed verification:

- The 183 API tests pass, including the real SQLite migration-history/backfill
  test. Ruff passes. Frontend verification from `npm ci` and the committed
  lockfile on Node 24 passes all ten tests, documentation checks, TypeScript,
  Vite and Docusaurus builds.
- **Issue #57:** on the verified isolated SQLite API, an authored description,
  table-label and column-description/label change at `0009` persisted through
  `upgrade_application()` and fresh API reads. `migrated=False`, the same table
  UID and a successful repeat upgrade were verified. Original metadata was
  restored through the same public helper.
- **Issue #58:** the same real API-backed downgrade `0009` to `0007` now
  succeeds. Exactly the two explicitly dropped OAuth bindings disappear,
  leaving 25 active entries at `0007`. The actual migration Job restores
  `0009`, with 27 active entries, 26 fresh application bindings and singleton
  settings readable. Another upgrade at head succeeds.
- The current backend accepts both single workflow files under API 2.3.0 with
  `valid: true`, no errors and no warnings. `applicable: null` is validation
  evidence, not an applied deployment.
- Read-only hosted verification reports the Production Environment, system
  revision `0012_table_creator`, and OpenAPI support for `authored_metadata`
  and `removed_meta_table_uids`. These advertised fields establish the relevant
  wire compatibility; they do not identify the exact running package version
  or prove PostgreSQL migration behavior.

The following deployment blockers were recorded at this preflight and resolved
by the 2026-10-11 work above; they are retained as historical evidence rather
than current status:

1. **Production ownership is missing.** Namespace search returns no
   `mainsequence-crm`, and the platform Team list contains no CRM owning Team.
   The migration Job and API workload Users need membership in a Production
   CRM Team with namespace Writer. The old API has no active revision, and
   `migrate-crm` has not yet been created by a workflow push. The earlier
   automatic approval review refused creation of this persistent Production
   permission grant without explicit approval; that approval is still pending.
2. **Frontend release binding needs coordinated rollout.** The site workflow
   still builds with `VITE_CRM_FASTAPI_RELEASE_UID=e3cfd6ae-8fd1-4060-9a55-efb0ca9768b8`.
   The candidate API resource key `crm` replaces `crm-api`, which creates a
   new release UID. Publish the frontend only after that UID is resolved and
   its workflow binding, OAuth callbacks and required access are coordinated.
   A successful static build does not validate this live binding.
3. **Hosted application services are not wired.** `api.crm.main.create_app()`
   installs identity and mounts REST/MCP but supplies no `crm_policy`,
   `crm_directory` or `crm_bootstrap` adapter. The only assignments to those
   ports in application source are in `api.crm.local`. The hosted bootstrap
   and business tools consequently retain their fail-closed readiness checks.
   Connect those ports to the existing platform services and verify signed
   caller/requester authorization before declaring the application usable.

Both local branches have no remote divergence. The API was 29 commits ahead
of `origin/main`, and the frontend five ahead, before this update's commit.
Both local Git remotes still have the explicit
`PUSH-DISABLED-during-mt014-wave` push guard. No push or Production mutation
was performed during these checks. Do not interpret passing local tests and
workflow validation as a guarantee that the deployment workflow will succeed
while these blockers remain.

### MetaTables 0.1.31 upgrade (2026-10-10)

PyPI reported `mainsequence-metatable` 0.1.31 as the latest stable release
(published 2026-10-10). `pyproject.toml`, `uv.lock`, the local environment and
the canonical `requirements.txt` export now use it. Main Sequence remains
9.0.19 and Tau remains 2.0.9. The six managed MetaTables skills were refreshed
from the installed 0.1.31 package in both CRM repositories; the frontend has
no MetaTables runtime dependency to upgrade.

The CRM migration Job now enables the package's phase timings and explicitly
reports catalog reconciliation, including when Alembic is already current.
The fresh-process settings check now compiles for the API's advertised dialect,
requires the catalog's DataSource to match, and retains its bounded read.
The PostgreSQL-only probe failure recorded below for 0.1.27 is fixed.
Provider identity, namespace, version table, revisions `0001`–`0009`, workflow
ordering and public API response contracts are unchanged. ADR 0004's readiness
boundary and ADR 0005's deployment boundary still apply; no ADR amendment or
new schema revision is needed for these implementation fixes.

Executed checks:

- **183 tests pass**, including real SQLite Alembic history/backfill checks
  and mocked tests for both query dialects, a changed runtime DataSource,
  current/new migration outcomes and failure propagation. Ruff and the strict
  MkDocs build pass; documentation contract tests also pass.
- An isolated API running 0.1.31 opened the previous 0.1.27 test database,
  verified Local/SQLite/system revision `0012_table_creator`, and reconciled
  `0009` with all 27 entries active and their UIDs preserved. A fresh process
  bound all 26 application tables and passed `validate_settings()`.
- A second, fresh isolated SQLite runtime was explicitly initialized to
  `0012_table_creator`. The actual Job applied `0001`–`0009`, emitted phase
  timing logs and finalized 27 entries in three successful HTTP requests.
  Fresh-process governed reads verified singleton settings and six stages.
  A repeat upgrade reported `migrated=False` and preserved catalog UIDs.

Two upstream MetaTables limitations were reproduced against its installed API,
separately from the passing CRM tests:

1. **Authored metadata is not refreshed on a repeated upgrade.** With an active
   settings table, changing `Settings.__metatable_description__` in an isolated
   test process and calling `upgrade_application("src.crm.migrations:migration")`
   returned `migrated=False`, revision `0009`, but a fresh
   `MetaTable.get_by_uid(...)` still returned the original description. The
   client's `prepare_for_alembic()` reuses active rows, and finalization sends
   UIDs and revision facts without changed authored metadata. This contradicts
   the bundled migration guide. The test restored the authored value; CRM
   metadata was not changed in source.
2. **Dropping tables during a local downgrade can fail finalization.** On the
   fresh, empty fixture,
   `metatables --local migrations downgrade 0007 --provider src.crm.migrations:migration`
   applied the DDL, then failed the first `/meta-tables/finalize-managed/` batch
   with HTTP 400 `ordinary_table_required`. `migrations current` confirmed
   `0007`: the failed command had already changed the physical schema.
   The API's SQLite access validator raises that code for missing physical
   tables. This is an API/finalization failure, not a CRM Alembic failure;
   broader hosted behavior was not tested. After inspecting the actual
   revision, a normal local upgrade restored `0009` successfully; a fresh
   process verified all 27 entries active and singleton settings ready. Do not
   describe the new removal handling as end-to-end verified for CRM downgrades.

No package internals or applied CRM revisions were patched to hide these
failures. After checking for duplicates, both were reported in MetaTables:
[issue #57](https://github.com/mainsequence-projects/MetaTables/issues/57)
tracks authored-description refresh, and
[issue #58](https://github.com/mainsequence-projects/MetaTables/issues/58)
tracks SQLite downgrade finalization. Both were verified open on 2026-10-10.
Hosted PostgreSQL operations, deployed permissions and shared API performance
remain unverified. No Production mutation or deployment was performed.
The earlier deployment is still awaiting approval for the Production CRM
Team/namespace Writer grant, and the Git push guard remains in place.

### Earlier MCP and dependency verification (2026-10-09)

On 2026-10-09 the CRM assistant's business tools moved from native Tau
extensions to the API-owned authenticated `/mcp` endpoint, as recorded in
[ADR 0005](../crm_core/adrs/0005-crm-application-mcp.md). The installed versions
are Main Sequence 9.0.19, MetaTables 0.1.27, Tau 2.0.9 and MCP 1.30.0. Canonical
`mainsequence code-repository sync --path .` refreshed dependency artifacts;
`ms-tau skills sync --path .` refreshed all five Tau skills to 2.0.9.

Executed after the migration:

- All **178 API repository tests** passed. Protocol tests exercise initialize,
  catalogue discovery and tool calls through ASGI, using signed test assertions
  and fake policy/directory/stores. REST/MCP create and update parity, strict
  arguments, permission denial, missing or malformed requester, concurrent
  requester isolation, unavailable adapters, disabled modules, bounded results,
  cancellation, and redacted failures are covered. These are not live database
  mutation proofs.
- The official MCP client traversed the local bridge and loopback launcher's
  verified identity boundary in-process. Its sign-in and persistence were test
  fixtures. The extension loader exposes only two generic tools locally and no
  native business tools when hosted. A lost write response is not retried.
- Ruff passed for `api/crm`, `api/tau`, `src/crm` and `tests`; strict MkDocs and
  `git diff --check` passed. The catalogue's operation bindings and schemas
  match the previous transport, with 66 tools enabled or 46 without Solution
  Selling.
- The current local platform's `validate-workflow` endpoint accepted the
  actual updated `crm-api.yaml`: workflow API 2.3.0, `valid: true`, no errors or
  warnings, and `applicable: null`. This validates the declaration without
  applying it or establishing deployment permissions.

No MCP migration commit, push, deployment, hosted migration or real provider
turn was performed. Before rollout, verify hosted policy/directory wiring,
admin-approved requester delegation, MetaTables compatibility and table grants.
The API key changes from `crm-api` to `crm`, so applying the workflow creates a
new API release identity. Coordinate the frontend release UID, Google OAuth
callbacks, replacement workload Team membership and grants; then verify a real
requester read/write and denial through the deployed assistant. The current
frontend release UID has deliberately not been replaced with a guessed value.

On 2026-10-09 the optional Tau dependency advanced from 1.2.14 to the
published `v2.0.9` release. The two frontend packages advanced to Command
Center SDK 0.5.17 and Command Center AI 0.0.11. The locked Python and npm
dependencies installed locally; all 167 CRM API tests, all 10 frontend tests,
and the frontend application build passed. The upgraded local Assistant was
also exercised against a disposable browser fixture: it sent a message,
displayed the response, and restored both after reload. The fixture servers
were stopped afterwards. These checks do not prove that the new Tau version
starts in a hosted Agent or that the updated frontend works against a deployed
Command Center session. The Tau coding-skill copy was subsequently refreshed
to 2.0.9 as part of the authorized MCP migration.

On 2026-10-09 the CRM API upgraded to `mainsequence` 9.0.19 and
`mainsequence-metatable` 0.1.27, the latest stable releases reported by the SDK
release check and PyPI. Both minimum dependency versions, `uv.lock`, the local
environment and `requirements.txt` now agree. The MetaTables client skills were
refreshed in both CRM projects. SDK-owned skills remain pinned to 9.0.6; their
separate refresh and the managed `AGENTS.md` refresh were not requested. The
installed 9.0.19 SDK code and bundled guidance were used for this upgrade.

The SDK now requires signed `team_uids` and `is_organization_admin` caller
claims. The HTTP fixtures supply those platform facts, and malformed team or
admin facts are rejected by the real verifier. The 167 repository tests pass,
including all CRM migrations on isolated SQLite; Ruff and the strict MkDocs
build pass. No CRM model,
revision, route or business rule changed.

Both projects retain exactly one workflow file. The API keeps the
`prepare_image` → `run_job` → `deploy` graph, with the API and assistant waiting
for the migration. Each workload now declares view access to the `MetaTables`
branch for discovery, as the current client deployment guidance requires. The
frontend adds an explicit `deploy_site` step to `crm-site.yaml`. The configured
local backend's branch-scoped `workflow-template/` and `validate-workflow/`
endpoints were called for both repositories. They advertise API 2.3.0 and
accepted both final files with `valid: true`, no errors and no warnings.
Validation returned `applicable: null`; it did not apply a workflow or verify
release readiness. Resource keys, workflow paths and every-push policies stay
the same.

The installed MetaTables 0.1.27 API was also exercised on a fresh isolated
local SQLite runtime, with system revision `0012_table_creator`. The CRM
provider applied `0001`–`0009` and finalized 27 catalog entries: all active,
none reserved or failed. A fresh process bound all 26 CRM tables at `0009`.
Explicit SQLite governed reads found the default settings row and six seeded
pipeline stages. Running `jobs/migrate_crm.py` against that same local runtime
then reported `0009 (already current)`.

The CRM's unmodified `CatalogRegistry.validate_settings()` probe emits the
default PostgreSQL operation dialect. Calling it against SQLite returned
`422 compiled_sql_dialect_mismatch`; the explicit SQLite reads above do not
certify CRM readiness or its PostgreSQL business commands. No hosted governed
write, rollback or deployed caller assertion was exercised.

The hosted MetaTables API version, CRM Team membership and namespace Writer
grant still need verification before rollout; see
[persistence](persistence.md#migration-and-runtime-boundary). No hosted migration,
deployment, commit or push was performed for this update.

Revision `0009` changes Interactions to a participant list and optional Company.
It has not been applied to a hosted environment. The deployment workflow's
migration Job applies it before the API that serves this contract rolls out.
Before using the new Calendar import against a live API, verify fresh-process
catalog binding and exercise governed create/update plus rollback on a
disposable provider. A running API still on `0008` does not serve this contract.

On 2026-10-04 the API moved to `mainsequence` 9.0.6, `mainsequence-metatable`
0.1.20 and `ms-tau-sdk` 1.2.14 (release tag `v1.2.14`), the latest releases, and
the vendored SDK, MetaTables and Tau skills were copied again from those
versions. No CRM code, model, revision or workflow changed:

- SDK 9.0.6 never replays a POST, PUT, PATCH or DELETE by itself. Read-only
  retries, their backoff and token renewal share one timeout budget per call,
  which replaces an outer loop of up to 60 attempts. Every governed CRM
  operation is a POST, so an uncertain write now fails instead of running
  twice, as the rule to read server state before retrying expects. PyJWT and
  cryptography are now base SDK dependencies and the `server` extra is gone;
  the CRM keeps its own requirements on both because its Google OAuth code
  imports them.
- MetaTables 0.1.19 runs one local API per local storage directory and removes
  the Local/Hosted switch; 0.1.20 retries runtime-access requests that time out
  during hosted discovery and requires SDK 9.0.6. See
  [local development](local-development.md#apply-migrations-locally).
  The 0.1.17 and 0.1.18 foreign-key rules are unchanged, and every CRM foreign
  key stays `ON DELETE RESTRICT`.
- `ms-tau-sdk` 1.2.13 lets local mode take the user's access token from the
  Main Sequence CLI session; 1.2.14 changes only documentation. The sibling
  launcher starts Tau without token variables, which the previously locked
  1.2.12 rejected in local mode. This follows from the two releases' settings;
  no local Tau process was started. See the
  [optional Tau runtime](local-development.md#optional-tau-runtime).

**Hosted prerequisite:** upgrade the Environment's hosted MetaTables API to
0.1.19 or later before this branch is pushed; 0.1.18 is not enough. The
client's `RuntimeContext` rejects fields it does not know, 0.1.19 removed
`runtime_switch_available`, `runtime_switch_error` and
`hosted_environment_target` from it, and an API on 0.1.18 or older still sends
all three in its `/runtime-context/` response
([MetaTables issue #33](https://github.com/mainsequence-projects/MetaTables/issues/33)).
`upgrade_application()` reads that response before it migrates anything, so
against an older API the `migrate-crm` Job fails, `deploy_api` and
`deploy_assistant` never run, and the rollout stops. An offline replay of a
0.1.18-shaped API with the locked client showed this: the Job's first request,
`GET /runtime-context/`, failed with `extra_forbidden` on those three fields. In
the same replay the CRM's catalog lookup and governed operations, which the API
and the loopback launcher run, sent only their own requests, did not read the
runtime context and were unaffected. The incompatibility therefore stops the
deployment at its migration Job.

Offline, the lock and `requirements.txt` agree,
`python -m metatables.sdk_compat` accepts SDK 9.0.6, the 131 repository tests
pass, including the whole `0001`–`0009` history with legacy rows on a temporary
SQLite file, and the strict MkDocs build passes. The backend workflow
validator, replayed offline from tdag-django `5a6c9280b` (`development`),
accepted the unchanged `crm-api.yaml` with no errors or warnings. The
branch's `validate-workflow/` endpoint was not called.

Later on 2026-10-04 the isolated local migration proof was repeated on 0.1.20 at
commit `569e77a`, once the local development backend answered and the CLI was
signed in to it. A local MetaTables API ran from a fresh, isolated storage
directory, never the default one, and was stopped afterwards. `metatables --local
runtime initialize` brought the SQLite runtime to system migration
`0010_cascade_targets` (none pending), and
`metatables --local migrations upgrade --provider src.crm.migrations:migration head`
applied `0001` through `0009` and finalized 27 catalog entries, the 26 tables and
the Alembic registry: 27 `active`, 0 `reserved`, 0 `failed`.
`migrations current` reported `0009 (head)`, and a second upgrade finalized
nothing and reported `migrated: False`. All 27 `mainsequence-crm` catalog rows
were `active`, `alembic_managed` and at `0009` on the local DataSource. The
CRM's catalog resolver bound all 26 tables; revision `0004` had seeded the
`default` settings row, the default `Sales` pipeline and its six stages. The
impact pre-flight on Company reported deleting rows allowed with five `restrict`
edges, and updating keys allowed with no edges. The Job script, run against that
runtime through `configure_local_client()`, reported
`src.crm.migrations:migration: 0009 (already current)`. Nothing hosted was
exercised.

Later on 2026-10-04 the API installed the SDK's request identity
(`install_request_identity`) in `create_app()` and moved its caller lookup,
`authenticated_actor()`, onto `User.get_logged_user()`. Since
PodDeploymentOrchestrator `3057764` the platform's FastAPI launcher no longer
resolves callers itself. It serves an app only when that integration declares
itself installed, in the caller mode the deployment selects and with exactly
the deployment's public ingress, so every new revision of the previous code
stopped at startup while the old one kept serving. The two Google public
routes are now mounted on the application itself: the locked FastAPI 0.141
lists an included router in `app.routes` as one entry, so the launcher's own
`FASTAPI_PUBLIC_INGRESS` check, and the request identity, could not find them.
That stopped startup too, independently of the identity change. The API
release's failed runtime activation, recorded below with the Google Workspace
extension, is consistent with it, but its logs were not inspected. The OpenAPI
document did not change. Checked locally:

- With a simulated deployment environment (assertion mode, trusted issuer, key
  URL, release and Environment, and the workflow's public ingress),
  PodDeploymentOrchestrator's `require_request_identity` and `serve_fastapi`,
  imported from its checkout, accepted the app. On the previous commit the
  first raised "Application request identity is not installed" and the second
  "Invalid FASTAPI_PUBLIC_INGRESS configuration". The launcher's runtime app
  started, answered `/ms-health-deployment` as ready, rejected requests without
  a valid caller assertion or with only `X-User-UID` (`401`), passed a request
  with a platform-signed assertion to CRM code, and served the completion page
  without a caller only when it was admitted as public ingress.
- `tests/test_request_identity.py` covers the declaration, signed and local
  callers, and their rejection; every other HTTP test now authenticates
  through the same verification. The 165 repository tests and the strict
  MkDocs build pass.
- The loopback launcher, run against the local development backend with the
  saved sign-in, returned the signed-in user from `/principals/`, rejected
  caller identity headers and served the Google completion page anonymously,
  as the previous commit's launcher does. Readiness reported the same
  unavailable catalog on both.

Not verified: a deployed release. It needs Main Sequence's caller-assertion
signing, published keys and gateway forwarding for this release. Deployed CRM
routes still fail closed after verification because no hosted policy,
directory or bootstrap adapter is wired; that predates this change.

On 2026-10-03 the API moved to `mainsequence` 9.0.5 and `mainsequence-metatable`
0.1.18. Since 0.1.14, MetaTables migrates hosted application databases only
from a Job in the application's own deployment workflow, so `crm-api.yaml` now
runs the `migrate-crm` Job (`jobs/migrate_crm.py`) from the candidate image and
deploys the API only after it succeeds. The backend workflow validator's
execution check accepted that graph when run offline; the exact branch's
`validate-workflow/` endpoint was not called.

Later on 2026-10-03 the CRM assistant's declaration moved from
`crm-assistant.yaml` into `crm-api.yaml`, which is now the repository's only
workflow file, and the assistant now deploys only after the `migrate-crm` Job
succeeds. Its key and settings did not change; only the `migrate-crm`
description now names the assistant. The tdag-django workflow validator at
`35ad44ce0` (`development`) was replayed offline from its source, with only the
branch-bound checks skipped as the validator itself skips them without a
branch: source indexing and the release create serializer. It accepted the new
file with no errors or warnings, and it also accepted the two previous files.
It rejected the new file next to the old `crm-assistant.yaml` with
`cross_file_conflict`, so the two must never be pushed together. The branch's
`validate-workflow/` endpoint was not called, because the local backend did not
answer. See [moved workflow resources](#moved-workflow-resources) for what the
push changes on the platform.

MetaTables 0.1.17 accepts foreign keys with `CASCADE`, `SET NULL` and
`SET DEFAULT` actions, records each table's cascade targets (system migration
`0010_cascade_targets`) and adds the `MetaTable.get_impact()` pre-flight.
0.1.18 makes write on a table depend only on that table's own grants. Every
CRM foreign key is `ON DELETE RESTRICT` by design, because CRM records are
archived rather than cascade-deleted, so neither release changes a CRM model
or revision.

Revisions `0001`, `0002`, `0004`, `0005`, `0006` and `0009` gained SQLite forms
of their PostgreSQL-only SQL. Their PostgreSQL statements did not change: on a
throwaway PostgreSQL 14 database, the original and the changed history, run
empty and with legacy rows seeded at `0001` and `0008`, issued the same
statements against the CRM tables with the same parameters, left the same rows
and produced the same `pg_dump --schema-only` output. Only the order of
catalog reflection queries varied, as it does between two runs of the
original.

On a fresh, isolated local SQLite runtime that MetaTables 0.1.18 initialized
through system migration `0010_cascade_targets`,
`metatables --local migrations upgrade --provider src.crm.migrations:migration head`
applied `0001` through `0009` and finalized 27 catalog entries, the 26 tables
and the Alembic registry, all `active`. `migrations current` reported
`0009 (head)` and a second upgrade changed nothing. The CRM's catalog resolver
bound all 26 tables, and revision `0004` had seeded the settings row, the
default pipeline and its six stages. The impact pre-flight for deleting Company
rows reported the action allowed, with five `restrict` edges from the tables
that reference Company. The Job script, run against that runtime through
`configure_local_client()`, reported `0009 (already current)`. No hosted
MetaTables API, Job run or deployment was exercised. The first hosted run of
the Job follows the next push, which since the 2026-10-04 move needs the
Environment's MetaTables API on 0.1.19 or later; check its workflow run and
DeploymentRuns before calling the API deployed.

On 2026-10-01 the API moved to `mainsequence` 9 and the separate
`mainsequence-metatable` 0.1.5 client (`metatables`). Governed operations now
send one DataSource UID with their SQL and no declared table scope. This move
was checked offline only: imports, provider loading and the unchanged
`0001`–`0009` revision history, operation payloads against the installed client
model, unit/route tests, Ruff and a strict MkDocs build. No MetaTables API,
catalog resolution, governed read or write, or migration was exercised. Before
a release, verify a fresh process against the MetaTables API deployment and
repeat the governed mutation and rollback gates below.

Later on 2026-10-01 the API moved to `mainsequence` 9.0.2 and
`mainsequence-metatable` 0.1.6 with no CRM code change. The client wheel now
installs only the `metatables` package, so this repository's top-level `api`
package no longer shares an import name with the bundled MetaTables server.
Hosted API discovery selects the one `metatables` deployment in the caller's
Organization Environment; `METATABLES_API_URL` is accepted only for a loopback
development API, and the CRM does not set it. This upgrade was also checked
offline only, with network access blocked: the client's SDK compatibility
check, provider loading and the unchanged `0001`–`0009` revision chain, the
unit/route tests, Ruff with no new findings, and a strict MkDocs build. The
live checks above remain outstanding.

| Gate | Evidence needed |
| --- | --- |
| Local unit and route checks | Passing test output for the changed code |
| Documentation | `mkdocs build --strict` with no warnings |
| Package contents | Build source and wheel artifacts containing the docs-independent Python packages |
| Migration and catalog | Local SQLite upgrade of the provider, the deployment workflow's `migrate-crm` Job succeeding before the API and the assistant roll out, and a fresh process resolving active MetaTables from the platform catalog |
| Governed mutation | Separate live multi-table commit and intentional failure rollback on a disposable provider; API readiness does not establish this |
| Release | Exact tested commit/image/resource and a deployed frontend/API contract check |

On 2026-09-23, the configured local provider upgraded through `0004`. The
provider-scoped migration removed physical workspace columns/table, preserved
its one pipeline and six stages, and created the `settings` table. The two
obsolete catalog entries (`command_receipt` and `workspace`) were deleted
individually after dependency checks, with dependent-table deletion disabled.
A fresh process resolved all 18 current CRM bindings at revision `0004` and
read the settings, empty company/contact/deal collections, the pipeline
collection, and all six board columns through governed MetaTable operations.
Live governed probes on the user-confirmed disposable CRM provider then
created a company with its activity event, verified an intentionally invalid
activity insert rolled back both rows, created a contact with its primary
affiliation, and transitioned its primary company while retaining a former
stint. Transfer probes created a source connection and import job, staged one
row, saved mapping, and validated its plan. All successful probe records were
deleted by exact UID; none are production data. These checks establish the
tested command paths, not all possible concurrent interleavings. A deployed
frontend/API release remains unverified. Do not describe an unmounted endpoint,
mocked test, or planned handoff ticket as a deployed feature.

The repository-layer refactor was checked locally with route/unit tests,
Ruff, a strict MkDocs build, and an offline source/wheel build. These checks
cover query-boundary validation and package inclusion. The broad live
multi-table rollback probes above predate that refactor. The contact social
probe below exercises one post-refactor write path, but does not repeat every
earlier rollback or concurrency gate; deployed release verification remains
outstanding.

On 2026-09-24, provider-scoped revision `0005` applied the contact social
schema change. A preflight governed count found zero contacts and zero
standalone LinkedIn values in this provider. After upgrade, a fresh process
resolved all 18 CRM bindings and read the new `socials` column through a
governed query. A subsequent governed live probe created one synthetic contact
with LinkedIn and X links, patched it to remove LinkedIn and add GitHub while
retaining X, and read back the incremented version. Its contact and activity
rows were then removed by exact UID. The test proves this create/patch path on
the disposable provider, but does not exercise legacy URL backfill on
nonempty data, every merge write interleaving, or a deployed API release.

On 2026-09-24, provider-scoped revisions `0006` and `0007` added core
Interaction, five Solution Selling tables, and the wider activity event
type. The local provider finalized six new table bindings and a fresh process
resolved all 24 at the new head. A governed empty prompter collection read
passed. A live governed prompter create and versioned patch wrote its activity
events; the synthetic prompter and those events were deleted by exact UID.
An intentional invalid activity insert in a two-table command rolled back
its prompter insert; a governed count confirmed zero residual rows. These are
local provider checks. A separate governed profile create/read passed with a
typed nine-cell JSONB template and the full-length activity entity type; its
synthetic profile and activity rows were also deleted by exact UID. A fresh
local FastAPI process with `INCLUDE_SOLUTION_SELLING=true` returned enabled
bootstrap state and empty module/core Interaction collections through HTTP.
These checks are
not proof of every new relationship path or a deployed
frontend/API release.

The shared-service refactor on 2026-09-24 moved mounted CRM business
operations from HTTP helpers into `src/crm/services/`. Local tests compare
direct service and HTTP Contact commands, permission denial, semantic scope
validation, and transfer direction authorization using injected stores. The
full local test suite, Ruff, and strict MkDocs build passed. These tests use
fakes for the parity cases; they do not prove a live Tau tool, a new governed
mutation path, or a deployed release.

The optional Tau dependency was updated to the pinned `ms-tau-sdk` 1.2.8
release commit. The ASGI entrypoint reads process settings; local tests verify
that setting both exclusion variables removes the optional SDK tool sources
from its configuration, while unset exclusions retain the SDK defaults. SDK
catalogue tests cover composition with project tools and A2A Task controls.
The project extension registers 46 typed CRM tools with Solution Selling
disabled, or 66 when enabled. Local fake-store tests verify the tool and HTTP
Contact commands reach the same shared service behavior, deny unauthorized
calls, reject model-supplied actor arguments, and fail closed without a trusted
runtime context. They do not establish a live principal or policy binding.
The managed Agent release was deployed on 2026-09-26; provider, identity, and
deployed-catalog behavior remain unverified through a live CRM conversation.

The Google Workspace extension is implemented in source and enabled by
`extensions.google_workspace.active: true` in `config/crm.yaml`. Local Google
Contacts consent and preview were verified as described below; the deployed
frontend/API handoff remains **unverified**. The CRM API workflow
declares exact FastAPI `public_ingress` for
`GET /extensions/google/oauth/callback/` and
`GET /extensions/google/oauth/done/`. The exact branch's Main Sequence
`validate-workflow/` endpoint accepted the API 2.3.0 declaration with no
errors or warnings. The API release deployment failed during runtime activation,
so its public ingress has not been externally probed. Confirm the release's
`effective_public_ingress` and backend-issued `public_url` before registering
the Google redirect URI; see the
[setup procedure](../google_workspace_module/setup.md#configure-public-callback-routes-on-main-sequence).
Migration `0008` applied to the configured local provider and a
fresh process resolved 26 active bindings. A synthetic governed probe
created an OAuth attempt, activated a token-shaped connection, imported a
Contact with source identity and activity event, disconnected, and removed all
probe rows. The probe used no Google account or real credentials. The
governed import rollback probe forced the activity insert to fail and
confirmed that neither the Contact nor source identity committed; its
synthetic setup rows were removed. These checks prove the selected local
command paths. A further synthetic Calendar probe created a Company and
Google connection, imported a meeting Interaction with source provenance,
updated it with the expected version, and removed all probe rows. A denied
OAuth attempt also reached a terminal failure state in the governed local
store and was removed. These checks do not prove live Google consent or
production deployment. With the ignored local API `.env` flag set to `true`,
a loopback FastAPI process returned ready status, bootstrap
`modules.google_workspace=true`, the signed-in user's import capability, and
an empty Google connection list. A local Chrome session displayed the
**Google Contacts**, **Gmail correspondents**, and **Calendar events**
destinations and the setup guidance when the OAuth client was absent. This is
local UI evidence, not a real Google grant or deployed Command Center check.
The Google Cloud app also needs the audience and scope review described in the
[setup guide](../google_workspace_module/setup.md) before production use.
Local tests of OAuth and source parsing are not evidence of those live gates.
The later unified consent change requests Contacts, Gmail, and Calendar read
permissions in one authorization. Its local scope and partial-grant tests do
not establish that a live Google account granted all three or that the
updated API and frontend are active in a deployed release.

On 2026-09-26, a local Chrome session completed Google Contacts consent for the
signed-in user and the CRM showed the connected account. A prior preview click
returned HTTP `503` because the loopback API's SDK signed-user revalidation
exceeded its 10-second deadline; the UI placed the error below the cards. The
local launcher now revalidates at most every five minutes with a 20-second
deadline. The preview button now displays loading progress and errors appear
above the account card. Calendar and Company reads no longer start when the
Calendar destination opens. Contact source links and matches are resolved in
bounded batch reads. After restarting the full local stack, the live Google
Contacts preview returned HTTP 200 and rendered four candidates, all defaulted
to Skip. No import was committed. This is a verified local Google read, not a
deployed release, Gmail, Calendar, or import verification.

The follow-up source-navigation fix shares the connection read across Google
destinations for one signed-in CRM session and checks a pending OAuth attempt
on tab return or explicit **Check connection**, rather than continuous
background polling. The Contact candidate now opens a prefilled create modal;
the reviewed fields are accepted only by the Contact-create import path.
In the local Chrome session, switching from Contacts to Gmail and back caused
no additional Google extension request after the first connection read.
Clicking a Contact name opened a modal with its Google name and email, and
Cancel produced no import request. The edited-field import contract passed a
fake-store test. A live save through the modal and a deployed OAuth flow
remain unverified.

Earlier on 2026-09-26, the local stack was relaunched with
`INCLUDE_SOLUTION_SELLING=true` and
`INCLUDE_GOOGLE_WORKSPACE_EXTENSION=true`. Its protected bootstrap returned
HTTP 200 with both `modules.solution_selling` and
`modules.google_workspace` set to `true`; live OpenAPI included both
`/extensions/solution-selling/` and `/extensions/google/` paths. The managed
CRM API workflow at that time declared both values. This is historical local
evidence for the previous environment-switch version.

[ADR 0004](../crm_core/adrs/0004-single-bootstrap-and-assistant-runtime.md)
is now implemented in source: the API loads `config/crm.yaml`, emits embedded
readiness and runtime-selected assistant state in one bootstrap response, and
the frontend makes that single startup request. The local Tau adapter sends
A2A Messages through the Vite `/tau` proxy. A live local bootstrap returned
HTTP 200 with readiness `ready`, both extensions active, and assistant runtime
`local`. Tau accepted the A2A Message shape and reached model inference, but
the model provider request failed with `CERTIFICATE_VERIFY_FAILED` on this
machine. An end-to-end chat reply remains unverified. Repository tests and a
frontend build verify the source behavior.

On 2026-09-26, CodeRepository sync, which still committed and pushed with the
SDK installed then, published API commit `5f639dc5` and
frontend commit `a6506358`. The managed CRM assistant DeploymentRun succeeded
and bound Agent `CRM assistant` to its active runtime release. The Static Site
DeploymentRun also succeeded and published the protected frontend. The CRM
FastAPI DeploymentRun passed workflow validation and image build, then failed
at `deploy_runtime` with `runtime_deployment_failed`; it has no active revision.
Local import and `/healthz` checks passed in a stripped environment. The
platform exposed no more specific failure in that run or its available
application logs. An offline wheel build then showed that the required
`config/crm.yaml` was absent from the Python package, a plausible startup
cause; the package definition now includes that file. The deployed
frontend/API contract, public Google callback, and managed assistant
bootstrap remain unverified until the API is active.

The API retry with the packaged YAML still failed at `deploy_runtime` and
produced no application logs. The API workflow now requests 0.5 CPU and 1 GiB
memory explicitly, matching the resource fields used by other FastAPI
releases. This is a deployment configuration attempt, not evidence that the
resource request caused the earlier failure.

That explicit-resource attempt also failed at `deploy_runtime` while the
assistant deployed from the same image. A local file-path load of the declared
FastAPI `source_path` raised an ImportError because its entrypoint used
relative imports. The entrypoint now uses package-absolute route imports and
loads both by module name and by file path. The platform's loader behavior
is not exposed in the public error, so this check identifies a possible
startup cause rather than proving the prior failure's root cause.

On 2026-09-27, the optional Tau dependency was updated to `ms-tau-sdk`
1.2.11 and its version-matched skills were synchronized. `uv sync --locked`
installed the tagged release, `api.tau.main:app` exposed both new local
conversation-history routes in its OpenAPI schema, all 125 repository tests
passed, and `mkdocs build --strict` passed. A separate frontend browser fixture
exercised conversation listing, reload hydration, selection, and continuation
through the local API shape. This does not establish that a live Tau process
has persisted a new conversation; no local Tau process was listening during
that browser check.

Later on 2026-09-27, the running local stack at `127.0.0.1:38644` exposed a
ready CRM bootstrap and Tau runtime. A live browser send initially failed with
HTTP 400 because the frontend still sent the old `ROLE_REQUESTER` Message role;
Tau 1.2.11 requires `ROLE_USER`. After updating the frontend wire format, the
same browser received a real Tau reply, and reloading the session URL restored
both public messages from Tau's history API. This verifies local Message
send and persisted history through the Vite proxy, not a deployed Agent run.

## Publishing

> The following consolidation notes describe the earlier move of the assistant
> declaration. The new MCP migration additionally renames API resource `crm-api`
> to `crm`; its release identity and frontend/OAuth bindings must change on
> rollout. Follow [ADR 0005](../crm_core/adrs/0005-crm-application-mcp.md).

Since SDK 9.0.5, `mainsequence code-repository sync` only refreshes the local
dependency files: `uv lock`, `uv sync` and
`uv export --locked --no-dev --no-hashes`. It no longer bumps the version,
tags, commits or pushes. Publishing is a plain `git push`, and
`.mainsequence/workflows/crm-api.yaml`, the repository's only workflow file,
decides what deploys: it runs the `migrate-crm` Job and then deploys the API
and the CRM assistant. Push only after the Environment's hosted MetaTables API
runs 0.1.19 or later. Against an older API the Job fails before it migrates
anything and neither the API nor the assistant rolls out; see
[persistence and migrations](persistence.md#migration-and-runtime-boundary).
The API also needs Main Sequence to sign and forward a caller assertion for
each request to this release: without one, every route outside the declared
public ingress answers `401`.

## Moved workflow resources

The backend identifies a workflow resource by its branch, workflow file and
key. The push that removes `crm-assistant.yaml` moves one declaration into
`crm-api.yaml`:

| Old workflow file | Key | Kind | Display name |
| --- | --- | --- | --- |
| `.mainsequence/workflows/crm-assistant.yaml` (workflow `crm-assistant`) | `crm-assistant` | `harness_agent` | `CRM assistant` (from `.agents/agent_card.json`) |

**Delete nothing after the push.** A Harness Agent is the exception to the
rule that a moved declaration creates a new target. The backend finds the
branch's Agent by its CodeRepositoryBranch, not by workflow file, and
reconciles the release bound to that Agent. The push keeps the same Agent, with
its UID and sessions, and the same release, with its UID, revision history and
runtime URL. Do not delete the assistant's release or Agent: that release is
the live assistant, and deleting the Agent also deletes its sessions.

What else the push does depends on the tdag-django code that processes it:

- From `bd89608b4` (ADR-077 §5, issue #767), the push first moves the release's
  workflow binding from `crm-assistant.yaml` to `crm-api.yaml`. The execution
  graph then owns the assistant's deployment and holds it until `migrate`
  succeeds. From `4a2833f12` (ADR-077), a push also deletes workflow targets
  that no file declares any more. The assistant is still declared, so nothing
  is deleted.
- Before `bd89608b4`, the release keeps its binding to the removed file. The
  Agent and release are still kept, but the generic per-push deployment does
  not see that the graph owns the assistant and can deploy it without waiting
  for the migration. Push only to a backend that runs `bd89608b4` or later.

After the push, check that:

1. The repository-event result lists only `crm-api.yaml`, valid, with
   `crm-assistant` queued in its workflow run. On a backend with ADR-077, its
   `deletions` list is empty.
2. The branch read with `include=workflow_runs` shows `deploy_assistant`
   starting only after `migrate` succeeded.
3. `CRM assistant` has the same Agent UID and runtime release UID as before the
   push.

Nothing that refers to the assistant's identity needs to change, because the
identity is kept:

- `src/crm/assistant_runtime.py` finds the Agent at each bootstrap by the Agent
  Card name, this branch and the Environment, and requires a bound runtime
  release. This repository stores no Agent or release UID.
- The frontend repository reads `agent_uid` from the bootstrap response. Its
  `crm-site.yaml` pins only `VITE_CRM_FASTAPI_RELEASE_UID`, which belongs to
  `crm-api`; that declaration did not move.
- Command Center's per-user Agent shortcuts and the Agent's sessions point at
  the Agent row, so they stay valid while the Agent exists.

`crm-api` and `migrate-crm` stay in `crm-api.yaml` under the same keys and keep
their identities.

## Keeping this site current

A material change to a CRM model, business rule, mounted route, payload,
authorization, persistence behavior, transfer lifecycle, or delivery status
must update the relevant [concept](../concepts/index.md) and API/delivery page
in the same change. Add new pages to `mkdocs.yml`, use relative links, and run
the strict build. The repository's
`maintain-crm-documentation` skill records this workflow for coding agents.
