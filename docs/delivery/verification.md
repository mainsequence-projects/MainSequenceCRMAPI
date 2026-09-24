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

## Keeping this site current

A material change to a CRM model, business rule, mounted route, payload,
authorization, persistence behavior, transfer lifecycle, or delivery status
must update the relevant [concept](../concepts/index.md) and API/delivery page
in the same change. Add new pages to `mkdocs.yml`, use relative links, and run
the strict build. The repository's
`maintain-crm-documentation` skill records this workflow for coding agents.
