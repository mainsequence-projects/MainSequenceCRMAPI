# Persistence and migrations

The CRM requires `mainsequence-metatable>=0.1.39,<0.2`; the lockfile and runtime
requirements select `0.1.39` and its required Main Sequence SDK `9.0.27`.
Migration execution continues through the public
`upgrade_application` entry point in the deployment Job, which receives the
installed package's migration improvements automatically. Updating the client
does not deploy the shared MetaTables API or apply CRM revisions to hosted data.

## Prompter subjects and constraints (revision 0011)

Revision `0011`, downstream of `0010`, adds nullable `subject_template` and nonnull
JSON `constraints` (default `{}`) to `mainsequence_crm__solution_selling_prompter`.
Existing prompters keep their body, open kind, identity and versions. Constraints
are a typed value object on that record; no new table or application scope is
introduced. Existing governed atomic create/update/activity writes and version
fences cover the new fields. SQLite uses native additive DDL to preserve the
unnamed checks from revision `0006` during upgrade and downgrade.

This change is local implementation, not a hosted migration or deployment.
Hosted schema changes remain exclusively the workflow's `migrate-crm` Job.

## Core Prompts (revision 0010)

Revision `0010`, downstream of `0009`, adds `mainsequence_crm__prompt` to the
existing `mainsequence-crm` provider/namespace (27 managed tables). It does not
alter Solution Selling Prompters or their contents. Prompt mutations use the
existing atomic governed record/activity command and actor/version fences.
Lists select metadata only. PostgreSQL and SQLite migrations enforce the
65,536-byte body limit using their respective byte-length expressions.

This feature is implemented locally, not deployed by this change. Hosted
application of the revision remains exclusively the workflow's `migrate-crm`
Job before API deployment; never upgrade a hosted database manually. Local
verification uses disposable SQLite files and a private PostgreSQL Unix socket,
not the normal local CRM runner's hosted DataSource.

The two model layers serve different purposes:

- `src/crm/models/` contains core Pydantic domain and HTTP payload classes;
  `src/crm/solution_selling/models.py` contains the optional module's Pydantic
  contracts. `src/crm/contracts/` validates and normalizes the original core
  resources against their classes.
- `src/crm/metatables/` contains 26 explicit SQLAlchemy-authored,
  platform-managed MetaTable classes. The migration
  provider uses their shared metadata. No JSON file creates classes at runtime.

The tables cover singleton CRM settings; pipelines and stages; companies,
contacts, contact-company affiliation periods, and tag links; deals and
deal-contact links; notes, tasks and activity; redirects; source connections
and identities; transfer jobs and rows; core Interactions; and five optional
Solution Selling record types.
Two private Google OAuth tables store single-use attempts and encrypted
per-user grant state. They are not exposed as CRM resources. The nonsecret
Google source account is represented in `SourceConnection` for provenance;
source identities link reviewed imports to CRM records.

## Code boundaries

HTTP collection, discovery, board, and transfer-page parsing lives in
`api/crm/query.py` with closed Pydantic URL models in
`api/crm/query_models.py`; only validated semantic filter and scope models
live in `src/crm/models/queries.py`. Command Center
discovery columns and labels live in `api/crm/discovery.py`; they are not
storage definitions. The repository receives validated semantic scopes and
uses only allowlisted SQL ordering expressions.

`src/crm/repositories/gateway.py` is the small provider-bound MetaTable
executor. It uses the `metatables` client from the `mainsequence-metatable`
package. Each operation sends its SQL, bound parameters, row limit, statement
deadline and the one DataSource UID shared by the resolved CRM catalog; it
declares no table list. The database enforces table permissions on the tables
the SQL actually touches. `repositories/resources/` owns shared CRUD mechanics;
`repositories/records.py` serves core Interaction and optional module records
through the same governed operation boundary; the module's business contracts
remain in `src/crm/solution_selling/`.
`repositories/companies/`, `repositories/contacts/`, and
`repositories/deals/` own their concept-specific read projections. Contact
affiliation history and merge live with contacts; board queries and moves live
with deals. Task and settings commands
have separate modules. These components are composed explicitly, with no
multiple-inheritance operation mixins. `repositories/transfers/` separates
source connections, jobs, plan persistence, reports, and export reads/writes.
Pure import assessment, export serialization, and spreadsheet-safe CSV
formatting live under `src/crm/portability/`, outside the MetaTable gateway.

Revision `0002` creates the affiliation table and backfills an undated primary
current affiliation for each existing contact with `company_uid`. It does not
guess historical start or end periods. It was applied to the configured local
provider on 2026-09-23. Hosted environments receive it from the deployment
workflow's migration Job; each still needs fresh-process binding verification
before using the new routes.

Revision `0003` removes the obsolete `command_receipt` table. Its upgrade
deletes existing receipt rows; its downgrade restores the table schema, not
those rows. The API no longer requires idempotency headers or stores command
replay responses.

Revision `0004` removes the application-owned workspace table and
`workspace_uid` from the other 17 CRM application tables. It replaces
workspace configuration with one `settings` record, changes composite
workspace foreign keys into direct CRM-record foreign keys, and preserves the
existing pipeline and stages. For an uninitialized provider it seeds settings,
a default pipeline, and six stages. This provider-scoped migration is
intentionally irreversible: an application tenant cannot be reconstructed
from the new records. Historical revisions `0001`–`0003` are retained to
upgrade older installations; they are not the current model.

Revision `0005` replaces the contact table's standalone `linkedin_url` with a
non-null JSONB `socials` object checked to be a JSON object. It first validates
and backfills non-null legacy URLs into `socials.linkedin`; invalid legacy
URLs stop the upgrade without dropping them. The downgrade restores LinkedIn
only when no other platform is populated, otherwise it refuses to lose data.
The configured local CRM provider was upgraded on 2026-09-24. Hosted
environments receive the revision from the deployment workflow's migration Job
before the API that uses this contact contract rolls out.

Revision `0006` creates core `Interaction` and the five Solution Selling
tables, and adds a Deal `(uid, company_uid)` uniqueness constraint to support
composite foreign keys. It was generated from the SQLAlchemy MetaTable
declarations and applied to the configured local `mainsequence-crm` provider
on 2026-09-24. The upgrade finalized six new catalog entries; it did not
delete existing records. Hosted environments receive it from the migration Job
before code that expects these tables rolls out. `extensions.solution_selling.active` in
`config/crm.yaml` controls API/UI
availability, not whether the tables exist.

Revision `0007` widens `ActivityEvent.entity_type` to 100 characters so the
module's full record identifiers fit in the audit stream. It was generated
from the MetaTable declaration and applied to the same provider on
2026-09-24.

Revision `0008` declares the backend-only `google_oauth_attempt` and
`google_oauth_connection` MetaTables. It has been authored locally but has
been applied to the configured local provider on 2026-09-24. A fresh process
resolved all 26 active bindings, including both Google tables. The OAuth
extension is gated by
`extensions.google_workspace.active` in `config/crm.yaml`; the migration-owned tables remain part
of the provider catalog even when the routes are off.

Revision `0009` adds the non-null JSONB `participants` list to Interactions,
moves each existing `contact_uid` into one participant entry, checks that the
list is a JSON array and that a Deal requires a Company, drops the old
`contact_uid` column with its index and foreign key, and makes `company_uid`
nullable. Its downgrade refuses while companyless, multi-person or unlinked
Interactions exist.

## Bounded core collection reads

`src/crm/repositories/resources/reads.py` builds one governed read with a
narrow filtered set of record IDs and the selected sort value. The page
applies the bound `LIMIT` and `OFFSET` before the full resource projection.
Company/contact counts, tag arrays and linked deal contacts are computed only
for the page IDs; the exact total counts the narrow filtered set in the same
statement. The response array uses the same null-last ordering and UID
tie-breaker as the page selection. Numeric deal ordering uses the physical
amount rather than the projected decimal string.

An exact count still visits matching base records, and relationship filters
still inspect the relations needed to decide membership. This is not a
constant-time count or a limit on legitimate filter work. The change needs no
schema revision, does not cache permissions or contact results, and does not
alter platform cold-start behavior. See the
[isolated collection SQL checks](local-development.md#collection-query-regression-checks)
for local evidence; hosted latency after deployment remains unverified.

## Migration and runtime boundary

The migration provider is `src.crm.migrations:migration`. It uses namespace
`mainsequence-crm`, the repository-prefixed Alembic table
`mainsequence_crm__alembic_version`, and repository-prefixed application
names. The `metatables` client from `mainsequence-metatable` runs its Alembic
revisions with the selected environment connection; the MetaTables API
reserves and finalizes the catalog bindings.

Nothing migrates at HTTP startup. A fresh API process queries the platform catalog
for the 26 authored identifiers, validates active Alembic-managed bindings,
namespace, provider, revision, physical names and one data source, then caches
the typed bindings in memory. Governed operations select that data source. It
must not register tables or repair schema during a request. No CRM bindings
file, finalization hook, or path variable is required by the CLI or API.
The singleton-settings readiness read uses the public SQLAlchemy compiler to
take the SQL dialect from the API's current runtime. It requires that runtime
to match the validated catalog's DataSource, with a two-row limit and a
five-second statement timeout. This check works with local SQLite and hosted
PostgreSQL; it does not make the CRM's PostgreSQL business commands portable.

Hosted environments are migrated only by the deployment workflow.
`.mainsequence/workflows/crm-api.yaml` is the repository's only workflow file.
It declares the CRM API (`crm`), the CRM assistant (`crm-assistant`) and
the `migrate-crm` Job, which runs `jobs/migrate_crm.py` from the candidate
image. The Job calls
`metatables.upgrade_application("src.crm.migrations:migration")` and prints the
resulting revision and successful catalog reconciliation. It enables INFO
logging for `metatables.migrations.runner`, which reports preparation, database
setup, table checks, Alembic execution, finalization and total duration.
Measure these separately from platform scheduling and workflow delays.
Its graph prepares the `crm` image, runs the Job from
it, and deploys the API and the assistant only after the Job succeeds. A
deployment must use its own resource's image step, so the assistant has its
own:

```yaml
execution:
  steps:
    image: {prepare_image: crm}
    migrate: {run_job: migrate-crm, image_from: image, needs: [image]}
    deploy_api: {deploy: crm, image_from: image, needs: [migrate]}
    image_assistant: {prepare_image: crm-assistant}
    deploy_assistant: {deploy: crm-assistant, image_from: image_assistant, needs: [deploy_api, image_assistant]}
```

At the current head, the Job still checks physical tables and reconciles
catalog bindings; `migrated=False` only means the revision did not change.
Never skip the upgrade helper or finalization based on that flag. A failed migration blocks both
rollouts and the previous releases keep serving. Do not run
`metatables migrations upgrade` or `downgrade` against a hosted runtime by
hand. The assistant calls the API-owned MCP tools, so its deployment waits
for the API deployment as well as its own prepared image. All business writes
continue through the API's governed CRM operations.

The repository locks `mainsequence-metatable` 0.1.39. Before rollout, verify
the Environment's hosted API and its system migrations against this version.
The historical 0.1.19 minimum addressed only the removal of runtime-switch
fields ([MetaTables issue #33](https://github.com/mainsequence-projects/MetaTables/issues/33));
it does not establish current compatibility. `upgrade_application()` reads the
runtime context before migrating. An incompatible API or missing permissions
fails the Job and blocks both deployments.

The API installs the hosted policy, directory and governed bootstrap adapters;
see [ADR 0005](../crm_core/adrs/0005-crm-application-mcp.md). No startup migration
or workload-permission fallback is added. The governed settings/default-pipeline
bootstrap read uses the installed MetaTables SQLAlchemy compiler, selecting the
runtime's actual SQL dialect and retaining its two-row bound. This also lets
the isolated local agent gate validate real persisted SQLite settings before
the hosted migration Job has published new model bindings.
The workflow retains automatic promotion and its migration-before-deploy graph.
The former `DISABLED-until-orchestrator-push` transport gate was removed after
the user confirmed the Production Writer grant was resolved; the required
real-agent pre-push hook remains enabled. A tested
provisioning variant with initial automatic deployment disabled was rejected
by the backend because new services then require pinned image UIDs; that
invalid variant was not committed or pushed.

After the API has an active MCP revision, run the API project's rollout helper:

```bash
.venv/bin/python -m scripts.bind_crm_frontend \
  ../main-sequence-crm-5f1b0619-9997-449c-b986-36990ae49e14/.mainsequence/workflows/crm-site.yaml --apply
```

It resolves the active CRM release from the current Git branch, checks the
Environment and advertised MCP revision, and replaces only the frontend
workflow's release binding. It rejects the old inactive release and never
creates a release, grants access or pushes a repository. Validate and build
that frontend before its push. The helper also reports the callback URI from
the backend's MCP URL for Google-side registration. Hosted Google OAuth can
use the launcher's actual `FASTAPI_PUBLIC_BASE_URL` when no explicit
`GOOGLE_OAUTH_REDIRECT_URI` is set; an explicit URI still takes precedence and
must be updated if it names a former release.

Since 0.1.33, MetaTables uses batched table inventories and physical inspection. Client
finalization sends at most ten tables per request, starting with the version
table: the CRM's 27 catalog entries need three requests. After a partial
finalization failure, inspect the failed tables and rerun the same upgrade;
committed revisions are not reapplied. The client now explicitly names removed
models or tables dropped during a downgrade, distinguishing them from
unexpectedly missing tables. The previous SQLite downgrade-finalization defect
is fixed in 0.1.33: the isolated CRM fixture downgraded to `0007`, removed only
its two OAuth bindings, and returned to `0009` through the normal upgrade.
Do not delete catalog bindings to repair an unexpected absence. Misplaced
provider tables or inaccessible owners require database-administrator repair,
not stamping or rewriting CRM revisions.

The client also waits up to five minutes for hosted API discovery during a
migration. Client changes need a rebuilt CRM image; shared API reflection
improvements require deploying the MetaTables API too. The package upgrade
does not deploy that shared service.

Authored metadata refresh at an unchanged head is verified with client/API
0.1.33. Description, labels and column metadata changes were read back through
the API with the same table UID; a repeat upgrade succeeded and the fixture's
original metadata was restored. The earlier 0.1.31 defects are tracked by
MetaTables issues #57 and #58, now closed. See the
[verification evidence](verification.md#metatables-0133-upgrade-and-push-preflight-2026-10-10).
Both the client and API need the fix. Keep the public upgrade path without
private registration helpers or revision changes for descriptive metadata.

Every API, agent and scheduled Job of this repository belongs in that one
file, because steps can only reference resources in their own file. A
scheduled Job stays out of `execution.steps`: the backend gives a
step-referenced Job its new image when the workflow run is admitted, before the
migration runs, so a step could not make its schedule wait. The repository has
no scheduled Job today.

The API and migration Job declare
`access.branches: [{repository: MetaTables, level: view}]` for hosted API
discovery. This platform access does not grant table access. With MetaTables
0.1.35, an Organization admin must create the `mainsequence-crm` namespace in
each Environment and grant Writer to its CRM Team. That Team needs the workload
Users of the migration Job and API as members. The assistant accesses the
CRM application and no longer needs direct table permissions for these tools. Use a separate Team
per Environment, and add replacement workload Users when resources are
recreated. The Production Team, grant and members are recorded in the
[verification evidence](verification.md#hosted-adapter-repair-and-controlled-provisioning-2026-10-11);
package upgrades do not change them.

The current local backend accepted this API workflow and the sibling
frontend's single `crm-site.yaml` on 2026-10-09, using workflow API 2.3.0 with
no errors or warnings. The frontend has an explicit `deploy_site` step; its
Static Site build is owned by that deployment. The MCP migration renames the API resource key from `crm-api` to `crm`,
changing its release identity when applied. Coordinate frontend, OAuth and
workload grants as described in [ADR 0005](../crm_core/adrs/0005-crm-application-mcp.md).
Validation does not apply either workflow or verify a rollout.

Local development applies the same revisions to the MetaTables local SQLite
runtime, after `metatables --local runtime status` confirms Local mode and
`sqlite`:

```bash
uv run metatables --local migrations upgrade --provider src.crm.migrations:migration
uv run metatables --local migrations current --provider src.crm.migrations:migration
```

See [local development](local-development.md#apply-migrations-locally).

Revisions are written for PostgreSQL. On SQLite, MetaTables runs column and
constraint changes through Alembic batch mode. Raw PostgreSQL SQL in a
revision (regex `~` checks, `jsonb_*` functions, `::` casts, `NOW()`, `md5()`)
branches on `op.get_bind().dialect.name`; its PostgreSQL branch keeps the
original statement. A SQLite table rebuild keeps only named CHECK constraints,
so name new ones. `tests/test_migrations.py` runs the whole history, with
legacy rows, on a temporary SQLite file.

Each revision must stay usable by the release that is still serving: the Job
runs before the rollout, and the previous release keeps serving during it and
after a failure. Add tables and nullable or defaulted columns first; drop or
rename in a later release. Redeploying an older image does not roll back the
schema, and a downgrade is never a deployment step.

This repository has no manual workspace initializer or persistent atomic-proof
gate. The API validates one settings row and a default pipeline through
governed reads; zero or multiple rows fail closed. Live
disposable-provider checks of governed multi-table mutations remain a release
verification task, not an API startup dependency. See the [live gates](verification.md).

The API uses the existing platform identity, policy and user directory. None
of these tables is a replacement login or role database.
