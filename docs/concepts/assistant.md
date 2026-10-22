# CRM assistant

The optional assistant can find and explain CRM records and perform supported
creates and versioned edits with the signed-in person's CRM permissions.
It uses the same business rules as the forms and lists. An ordinary requested
edit reads current state and supplies its version; a conflict requires another
read before proceeding.

The available operations depend on the deployed catalogue and enabled modules.
Archive/restore, merge execution and import commit are not exposed until their
required confirmation flow can be verified. The assistant can prepare a
proposal or run an available preview without claiming the action was completed.

A healthy chat connection does not prove access to business tools. The
assistant must report a refused or unavailable operation accurately. A timed-out
write may already have completed; check current CRM state before trying again.
Business errors can include a request reference and the stage that failed.
Retain that reference when reporting a problem so protected runtime logs can
identify time spent on identity, permissions, catalog discovery and governed
data operations. The reference does not establish whether a write committed.
When the CRM application is waking, the assistant waits within a bounded
readiness deadline before calling its tools. If access still cannot be obtained,
it reports that outcome and does not replay a business write.
The rest of CRM remains usable when the assistant or its provider is unavailable.

The API owns the [MCP tool contract](../api/mcp.md), and the separate Tau runtime
owns the conversation. New conversations default to GPT-5.6 Luna through the
Codex subscription provider, with medium reasoning. The signed-in person needs
an active credential for that provider; an existing session keeps its own model
selection. A real hosted create, versioned update and independent persisted
read were verified with Luna; see [release evidence](../delivery/verification.md)
for the exact scope and remaining checks.
