# Campaigns implementation plan

**Status:** Executed on 2026-10-24; see the [module index](index.md) for the
implemented surfaces and [verification](../delivery/verification.md#campaigns-module-2026-10-24)
for the executed checks. The contract decisions are recorded as ADR amendments.
**Reviewed:** 2026-10-24, API branch `campaigns` at `e6957ca` and the paired
frontend's `main` checkout at `8d7aaf2`.

This plan implements [ADR 0001](adrs/0001-campaign-task-graph.md). It preserves
its five domain models, one live DAG, explicit Contact enrollment, existing
CRM Task instances, shared Agent Prompt identity, and one current Task per
participant. Single-prompt and A/B workflows are both required for the complete
first delivery. Intermediate milestones below are development checkpoints.

The review found no Campaigns implementation under `src/`, `api/` or `tests/`.
The module currently consists of the ADR and its documentation links.
Installed API packages are Main Sequence `9.0.30`, MetaTables `0.1.51` and Tau
`2.0.23`; the paired frontend pins Command Center SDK `0.5.17` and Command
Center AI `0.0.13`. Use those installed contracts when implementing; this plan
does not request dependency updates.

## 1. Settle the contracts before adding persistence

Record these decisions in the ADR and executable contract tests first. The
defaults below are recommendations, not newly implemented behavior.

| Decision | Recommended initial contract |
| --- | --- |
| Existing capabilities | Correct the ADR's `crm.update` to `crm.edit`. Reuse `crm.read`, `crm.create`, `crm.edit` and `crm.archive`; check every capability needed by the related Task and Prompt mutations. |
| Wait, block and reconcile commands | Add typed commands for reporting a wait, a block, an observed effect and explicit reconciliation. Their precise REST/MCP schemas must be added to the ADR's proposed surface. Do not expose arbitrary writes to participant progress. |
| Deadline meaning | Persist `wake_at` and `eligible_at` as offset-aware server-validated datetimes. A wake permits reconsideration; it does not infer an outcome from a due date or Markdown. Automatic expiry requires an explicit structured rule and evidence policy. |
| Stale results and actual effects | Distinguish recording facts from accepting completion and routing. Preserve a reported real effect against a fresh Participant/Task version while marking stale definition provenance and blocking advancement; reconcile explicitly against current definitions. An ordinary rejected version conflict must not be described as a successfully saved report. |
| Campaign and participant lifecycle | Specify allowed transitions, enrollment into draft/paused campaigns, archive/restore and completion with unfinished work. Default: pause preserves instances, timestamps and facts, prevents new Task creation, and does not authorize new external work. Already-observed facts may be recorded without creating a next Task. Withdrawal archives open Tasks and marks their progress cancelled. Completed/withdrawn participants do not resume automatically. |
| Visited or cancelled steps | Enforce one Task and assignment per participant/Step for the entire enrollment. A live edit can create a route back to historical work even when the new graph is acyclic; diagnose and block that participant instead of creating a second instance or replaying its old outcome. Specify explicit restoration/reconciliation for a cancelled instance. |
| Core Task changes | Core completion without a Campaign outcome sets `outcome_required`; reopening completed work exposes an inconsistency and never replays downstream Tasks. Reject Contact reassignment for linked Tasks. Define the impact of archive/restore and explicit owner/text/due-time changes. |
| Base Prompt changes | Both specialized and ordinary Prompt update/archive/restore paths participate in campaign validation, invalidation and comparison-change handling. Preserve the subtype and shared Prompt version. A removed assigned variant or archived Prompt blocks affected open work. |
| Contact merge | Initially reject merges involving campaign enrollments, with a useful preview/execution error, until an explicit policy covers immutable enrollment identity, duplicate enrollment, Task ownership and A/B provenance. Do not silently combine assignments. |
| Progress storage | Expose `Participant.progress` as embedded values. Prefer an internal relational association keyed by `(participant_uid, step_uid)`, with unique `task_uid` and foreign keys, so the database can enforce Task ownership and uniqueness. It has no independent domain UID, API or version; Participant version protects writes. Clarify that five domain models need not mean five physical tables, and prove provider/catalog support before committing this layout. |
| Comparison accounting | Group by `(campaign_uid, step_uid, comparison_key)`. Use server-owned assignment time; retain cancelled, withdrawn and unsent assignments in matured denominators. Define the success timestamp and late-report policy, machine-readable evidence for verified sends, change flags and comparison-key reuse rules. Keep changed exposures visible and distinct. |
| Finite limits and binding types | Set graph, text, input/result field, evidence, JSON depth/size and progress limits, plus aggregate serialized graph/briefing budgets. The existing MCP wrapper caps results at 128,000 characters; valid campaign responses must not depend on its truncation. Specify missing versus null, strict value types, reserved keys and allowed binding paths. At convergence, a predecessor may not exist on the participant's actual path. |
| Durable advancement authority | Start with explicit authenticated person/assistant advancement over persisted eligibility. Before adding a scheduled mutating worker, prove a supported effective-person delegation and permission-recheck mechanism. `owner_uid` is not delegation, and the existing MCP boundary denies unbound workloads. |

**Exit evidence:** agreed lifecycle/command schemas, finite limits, error
codes, authorization matrix, serialized examples and test cases for each rule.
These are contract decisions, not reasons to defer unrelated authoring work.

## 2. Prove the governed storage and concurrency design

Add a focused prototype before building the full runtime:

- Use the existing provider, namespace and `GovernedGateway`. Prove that the
  proposed progress association can be migrated, finalized and bound in a fresh
  process, including its composite key and foreign keys.
- Prove one atomic operation creates the Task, assignment, association,
  Participant update and activity, or rolls all of them back. Use the repository's
  governed final-INSERT DML CTE pattern and actual table permissions.
- Establish one consistent locking/version protocol across Campaign, Prompt,
  Participant and Task changes. A Python version check or an ordinary snapshot
  SELECT alone does not protect against a simultaneous graph or Prompt edit.
  Shared graph reads should allow different participants to progress concurrently.
  Do not add a campaign-wide write/version bump to every participant advance.
- Exercise two independent connections: duplicate enrollment; duplicate advance;
  graph edit versus advance/complete; Prompt edit/archive versus complete;
  core Task complete/reopen versus Campaign completion; and stale graph saves.
- Include a forced constraint failure after dependent writes and confirm no
  partial Task, assignment or progress survives.

Local PostgreSQL race tests and SQLite migration tests provide different
evidence. Compilation or mocks do not prove governed locking, permissions,
rollback or hosted catalog binding. If the actual gateway cannot support the
required atomicity/locking, resolve that capability before implementing runtime
progression; do not add a direct database fallback.

## 3. Add domain contracts and additive migrations

Create an application-owned `src/crm/campaigns/` package for typed models,
configuration, graph validation, input binding, lifecycle and comparison logic.
Keep transport and persistence separate from these rules.

Add MetaTable declarations in `src/crm/metatables/campaigns.py` and register
them in `src/crm/metatables/__init__.py`. Add the next revision after current
head `0012` under the existing `src.crm.migrations:migration` provider; confirm
the head again when implementation starts.

- Store Campaign, Step, Transition, Participant and the one-to-one Prompt
  extension; add the internal progress association if the prototype proves it.
- Add uniqueness for enrollment, source-step/outcome routing and Task
  association, and same-campaign/same-Contact foreign-key integrity. Add the
  required unique referenced keys to existing tables additively.
- Store immutable assignment facts separately from current briefing provenance,
  actual results/evidence and mutable reconciliation flags.
- Add indexes for campaign/status lists, prompt references, Contact enrollment
  and eligible/waiting participants. Pagination must bound collections;
  progress length is bounded by the graph/enrollment contract.
- Preserve ordinary Prompt behavior. Subtype creation/specialization and base
  edits use one shared version fence and one governed command.
- Keep all migration-owned tables in the provider when Campaigns is disabled.
  Disablement hides functionality; it does not delete data.

**Exit evidence:** full-history and upgrade-with-existing-data SQLite tests,
private PostgreSQL constraints, catalog/model parity, fresh-process reads and
rollback checks. Raw PostgreSQL migration SQL branches on the connection
dialect so local SQLite remains supported.

## 4. Implement authoring and live-edit services

Add focused services and repositories, composed by the existing service/runtime
wiring rather than expanding route handlers into a second business layer.

1. Implement draft creation and Campaign/Prompt read/edit operations.
2. Implement pure candidate graph validation: one entry, same-campaign
   endpoints, reachability, acyclicity, unique outcome routes, explicit finish
   routes, valid variants/weights, compatible Prompt contracts, valid metric
   reachability and documented predecessor bindings. Incomplete drafts return
   diagnostics; activation and active edits require a runnable graph.
3. Implement a read-only impact preview containing affected open Tasks,
   assignments and scheduled next steps, including historical-step conflicts.
4. Commit each graph change atomically against Campaign version. Step and edge
   changes advance that version. Preserve Step UIDs and retire referenced
   identities; apply explicit versioned instance updates/cancellations or block
   affected participants for reconciliation.
5. Wire base Prompt edits and archive/restore into the same invalidation
   protocol. Preserve completed results; expose current Prompt/version changes
   during preparation without writing on reads.

**Exit evidence:** diagnostic fixtures for invalid graphs and bindings; draft
versus active behavior; impact preview/save races; shared Prompt edits across
multiple campaigns; cancellation archives Tasks without false completion.

## 5. Implement participant progression as the first complete workflow

Build and verify a small single-prompt campaign through shared services before
adding the designer. Use two explicitly owned disposable Contacts with distinct
results.

1. Enroll an existing authorized Contact once, validate the Campaign and owner,
   and set its service-owned next step and eligibility.
2. Advance an eligible active participant: check current authorization, lifecycle
   and versions; choose/persist its assignment; create one core Task from the
   live Step defaults and one association atomically. Return the existing
   instance on repeat access without changing its assignment or evidence.
3. Prepare a briefing read-only from current Campaign/Step/Prompt definitions,
   authorized Contact data, participant context and actual predecessor results.
   Return Task/Participant versions plus definition provenance. Missing required
   values produce an actionable block/diagnostic, never invented inputs.
4. Implement the typed wait, block, effect-report and reconciliation commands
   agreed in step 1. Restart with waiting/delayed work persisted; a read,
   preparation or wake does not complete work or send a message.
5. Complete through one governed command: validate versions, outcome, strict
   result fields and evidence; settle Task/progress; select the live transition;
   set next eligibility or finish. Creating a subsequent Task is a separately
   authorized advance, making pauses and delays explicit.
6. Integrate existing core Task completion/reopening/archive/update and Contact
   merge guards. Preserve actual effects on stale briefings; reconciliation
   never retries an uncertain external send automatically.

**Exit evidence:** branching and converging paths, exactly one current Task,
duplicate/concurrent advance protection, independent Contact data, restart
recovery, permission loss, stale results, core completion without outcome and
reopened Task behavior. Verify read-after-uncertain-write recovery explicitly.

An optional scheduler follows only after its identity contract is proven. It
calls these same services, rechecks authority at execution and persists no
invented person identity or bearer token. Declare any scheduled Job in the
existing `.mainsequence/workflows/crm-api.yaml`, outside `execution.steps`.
No new harness or channel-delivery connector is required by this plan.

## 6. Add A/B assignment, change handling and descriptive reporting

Use the same assignment path for one variant (100%) and two weighted variants.
Test allocation with an injected random source; correctness does not depend on
equal counts in a small sample. An assignment is persisted with Task creation
and reused through preparation, retries and process restart.

Capture the original Prompt UID/version, allocation, comparison metric/window
and assignment time. Reconcile current variant mappings and Prompt versions
without overwriting assignment facts. Changes to offer/context, Prompt,
variants, weights, task rules or measurement require comparison-change
handling and a fresh key for new comparable assignments. Layout-only edits
must not invalidate an experiment.

Compute server-side assigned counts, verified sends where meaningful, immature
and matured observations, successes and rates per Step/comparison/variant.
Keep all matured assignments in the denominator, count binary success once
and apply the explicit timing/late-report policy from step 1. Keep comparison
keys and changed exposures distinct; do not report an automatic winner.

**Exit evidence:** deterministic clock/assignment tests, concurrent creation,
restart stability, downstream metrics, unsent/withdrawn/cancelled assignments,
window boundaries, repeated replies, late reports and changed configurations.

## 7. Expose the shared services through HTTP, MCP and discovery

Thin adapters can be added alongside steps 4–6, with service parity tests at
each checkpoint. Do not postpone all transport integration until the end.

- Add `extensions.campaigns.active` to `config/crm.yaml` and the strict config
  model, initially disabled. Add `bootstrap.modules.campaigns`.
- Mount protected routes only below `/extensions/campaigns/` when enabled.
  Provide canonical discovery and authoritative normalized collections for
  campaign, specialized Prompt and participant lists, using the installed
  Command Center schemas/fixtures. Keep resource summaries bounded.
- Add the ADR's 17 proposed MCP tools and the agreed wait/report/reconcile
  surface with typed inputs, expected versions, accurate read-only annotations
  and actual business results. Define precise schemas before publishing names.
- Use `authenticated_actor()`/`CRMContext` and the existing MCP human/requester
  admission on every call. Apply fresh capability checks and owner selection;
  refuse workload-permission fallback.
- Test module-off/on route and tool inventories, retained data, discovery,
  pagination/search/filter/sort, serialized responses, redacted errors and
  requester denial. Advertise no tools when the module is unavailable.

## 8. Build the paired frontend against those contracts

The frontend remains on `main` during this planning task. Select/create its
implementation branch separately and coordinate compatible API/frontend
contracts before release.

1. Extend Bootstrap types, module navigation, routes and adapters in
   `src/models.ts`, `src/App.tsx`, `src/navigation.tsx`, `src/routes.ts` and
   `src/api.ts`. Show Campaigns from backend availability and preserve the
   existing startup/identity gate and delegated transport.
2. Build Campaign and Campaign Prompt resource lists and details with
   `ResourceListPage`, `ResourceDetailShell` and canonical adapters. Add shared
   Prompt specialization forms and authorized Contact/Prompt/owner pickers.
3. Add an application-owned DAG canvas and keyboard/phone outline inside the
   SDK detail shell. The installed SDK has no graph editor. Select a canvas
   approach after a small accessibility/bundle-size prototype; a new dependency
   requires its own review and lockfile synchronization.
4. Keep an unsaved candidate graph locally; validate it read-only, display
   node/edge diagnostics, review impact, then save one expected-version change.
   Expose prompts, weights, bindings, criteria, outcomes and transition delays.
   Preserve drafts after conflicts and uncertain writes.
5. Add participant enrollment/list/detail and read-only progress overlays, then
   briefing, result, wait and reconciliation forms using server-provided allowed
   actions. Link actual core Tasks and Contacts. Core Task detail currently has
   no full completion editor, so these are new execution screens.
6. Display server-calculated comparison counts, denominators, windows and
   changed-exposure flags. The client chooses neither variants nor destinations
   and performs no independent graph progression.

**Exit evidence:** isolated API-fixture browser tests for pointer/keyboard
authoring, phone outline, enrollment, read-only overlays, version conflicts,
uncertain writes, wait/reconcile and A/B reporting. Run SDK shell/layout
verification, light/dark and coarse/fine viewport matrices, focus checks and
reduced-motion coverage.

## 9. Deliver documentation, skills and release evidence together

Update API concepts, mounted route index, API/MCP schemas, persistence,
enablement and durable-wake documentation as their implementation lands.
Keep unfinished behavior labeled. Add the paired frontend's Campaigns guide,
designer walkthrough and two-contact Dubai example, including A/B windows,
live edits and recovery. Put frontend engineering plans in `engineering/`,
outside its served user guide.

Publish `crm-campaigns` in the API-owned business usage pack only when its tools
exist. Cover create/edit/read, explicit enrollment, assigned-prompt execution,
evidence, waits, live-edit reconciliation, uncertain writes and honest
comparison interpretation. Update shared tool allocation, feature-aware skill
publication tests and pack-count assumptions; mirror the pack identically into
the frontend. Explain composition with `crm-core` and optional Solution Selling.

Required implementation verification, kept separate in the delivery report:

| Evidence | Required checks |
| --- | --- |
| API/domain contracts | `.venv/bin/pytest -q`, `.venv/bin/ruff check api/crm src/crm tests`; add focused Campaign graph, lifecycle, HTTP/MCP, skill, config and core-integration suites. |
| Persistence and concurrency | Disposable SQLite full-history migrations; private PostgreSQL constraints/races/rollback; governed operation permission proof and fresh-process catalog binding. Local SQL is not hosted proof. |
| API documentation | `.venv/bin/mkdocs build --strict` and `.venv/bin/pytest tests/test_documentation.py`; mounted route index matches enabled OpenAPI. |
| Frontend typecheck/build | `npm test`, `npm run docs:check`, `npm run build` (includes `tsc -b`, application and guide); report typecheck/build results separately. |
| Theme and browser | `npx command-center-sdk theme audit --path src`, focused Campaign browser suite, affected existing suites and `node tests/docs-artifact.browser.mjs`. |
| Real local agent | Before any API push, `.venv/bin/python scripts/verify_local_agent.py` using the workflow's real provider/model, successful CRM MCP reads, retained history across restart and a fresh API comparison. Also verify the owned disposable Campaign mutation fixture and clean it up after reading current state. |
| Hosted integration | Existing migration Job succeeds before API deployment, followed by assistant/frontend rollout; verify exact commits, readiness, module availability, permissions, persisted two-contact progression, restart behavior and matching frontend API release routing. |

Keep the module disabled until its complete release gates pass. Hosted schema
changes use only the existing workflow's migration Job; do not migrate at API
startup or manually against a hosted runtime. Preserve the existing workflow
version and validate any modification against the current platform template.
Do not introduce manual grants or push/deploy as part of this planning task.

## Implementation seams and sequencing

| Area | Existing integration points |
| --- | --- |
| Module configuration and bootstrap | `src/crm/config.py`, `config/crm.yaml`, `src/crm/services/application.py`, `api/crm/main.py` |
| Shared policy and operations | `src/crm/platform/runtime.py`, `src/crm/services/operations.py`, `api/crm/service_adapter.py` |
| Governed persistence | `src/crm/repositories/gateway.py`, `src/crm/repositories/resources/`, `src/crm/metatables/__init__.py`, `src/crm/migrations/registry.py` |
| Core consistency | `src/crm/repositories/tasks.py`, `src/crm/repositories/resources/writes.py`, `src/crm/repositories/contacts/merge.py`, `src/crm/models/tasks.py`, `src/crm/models/prompts.py` |
| HTTP/MCP | `api/crm/query_models.py`, `api/crm/discovery.py`, `api/crm/mcp_tools.py`, `api/crm/mcp_server.py` |
| Deployment and real-agent checks | `.mainsequence/workflows/crm-api.yaml`, `jobs/migrate_crm.py`, `scripts/verify_local_agent.py` |

The critical path is contract decisions → governed proof → schema → authoring
and live-edit services → single-prompt progression → A/B → complete UI and
release evidence. Once contracts stabilize, frontend resource scaffolding and
designer prototyping can run alongside backend services; tests and documentation
land with each slice. HTTP/MCP adapters are added incrementally over the same
services. Automatic background advancement has its own authorization proof and
must not delay unrelated deterministic authoring work.

No Campaigns feature, migration, operational skill, commit, push or deployment
is created by this plan. Only the plan and its MkDocs navigation entry are added.
