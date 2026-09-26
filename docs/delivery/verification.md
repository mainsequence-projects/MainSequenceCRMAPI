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

| Gate | Evidence needed |
| --- | --- |
| Local unit and route checks | Passing test output for the changed code |
| Documentation | `mkdocs build --strict` with no warnings |
| Package contents | Build source and wheel artifacts containing the docs-independent Python packages |
| Migration and catalog | Provider-scoped migration plus a fresh process resolving active MetaTables from the platform catalog |
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
**Google Contacts**, **Gmail correspondents**, and **Calendar meetings**
destinations and the setup guidance when the OAuth client was absent. This is
local UI evidence, not a real Google grant or deployed Command Center check.
The Google Cloud app also needs the audience and scope review described in the
[setup guide](../google_workspace_module/setup.md) before production use.
Local tests of OAuth and source parsing are not evidence of those live gates.

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

On 2026-09-26, CodeRepository sync published API commit `5f639dc5` and
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

## Keeping this site current

A material change to a CRM model, business rule, mounted route, payload,
authorization, persistence behavior, transfer lifecycle, or delivery status
must update the relevant [concept](../concepts/index.md) and API/delivery page
in the same change. Add new pages to `mkdocs.yml`, use relative links, and run
the strict build. The repository's
`maintain-crm-documentation` skill records this workflow for coding agents.
