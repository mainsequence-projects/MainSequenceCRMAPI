# Persistence and migrations

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
executor. `repositories/resources/` owns shared CRUD mechanics;
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
provider on 2026-09-23; other environments still need their own upgrade and
fresh-process binding verification before using the new routes.

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
The configured local CRM provider was upgraded on 2026-09-24; other providers
must run their own provider-scoped upgrade before using this contact contract.

Revision `0006` creates core `Interaction` and the five Solution Selling
tables, and adds a Deal `(uid, company_uid)` uniqueness constraint to support
composite foreign keys. It was generated from the SQLAlchemy MetaTable
declarations and applied to the configured local `mainsequence-crm` provider
on 2026-09-24. The upgrade finalized six new catalog entries; it did not
delete existing records. Other providers must upgrade before running code
that expects these tables. `extensions.solution_selling.active` in
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

## Migration and runtime boundary

The migration provider is `src.crm.migrations:migration`. Migrations run
outside HTTP startup. A fresh API process queries the platform catalog
for the 26 authored identifiers, validates active Alembic-managed bindings,
namespace, provider, revision, physical names and one data source, then caches
the typed bindings in memory. It must not register tables or repair schema
during a request. No CRM bindings file, finalization hook, or path variable is
required by the CLI or API. Run `mainsequence migrations upgrade --provider
src.crm.migrations:migration head` through the SDK lifecycle. The provider uses
namespace `mainsequence-crm`, the repository-prefixed Alembic table
`mainsequence_crm__alembic_version`, and repository-prefixed application names.

This repository has no manual workspace initializer or persistent atomic-proof
gate. The API validates one settings row and a default pipeline through
governed reads; zero or multiple rows fail closed. Live
disposable-provider checks of governed multi-table mutations remain a release
verification task, not an API startup dependency. See the [live gates](verification.md).

The API uses the existing platform identity, policy and user directory. None
of these tables is a replacement login or role database.
