# Transfers

A transfer is a durable job initiated by an authorized existing principal.
Source connections identify an adapter and source account; they do not add
another CRM authentication system. Import profiles include generic CSV,
Atomic-shaped CSV/JSON, and the Main Sequence portable format.

An import proceeds through source selection, file staging, explicit field and
owner/stage mapping, validation, plan review, and commit. The mapping revision
and plan hash fence a commit against a stale review. Counts, issues, and job
status are read back from server state; a `202` response means accepted, not
completed. Cancellation and retry are also durable job actions.

The mounted API currently implements the import and transfer-read/action
surface. Export code and payload models exist, but export creation and download
routes are **not mounted**; do not present export as a usable endpoint yet.
The internal portable exporter uses explicit entity keys (including
`companies`) and serializes contact-company affiliation rows with their
original period precision. The portable upload parser stages those rows.
This is not yet a complete import round trip: affiliation mapping,
execution, and active export endpoints remain delivery work. Validation blocks
affiliation rows explicitly until execution exists, so a staged history is not
misreported as a successful import.

See the [transfer API](../api/transfers.md) for the exact mounted paths.

The optional [Google Workspace module](../google_workspace_module/index.md)
uses a separate user-authorized connection, bounded previews, and explicit
per-item decisions for Google Contacts, Gmail correspondents, and Calendar
meetings. It does not use the file-upload adapters or durable transfer jobs;
its source identity and CRM activity are written with each reviewed record.
Its routes mount only when `extensions.google_workspace.active: true` in
`config/crm.yaml`.
