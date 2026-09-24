## Main Sequence CRM implementation routing

CRM source authority, specifications and test gates live at `engineering/crm-handoff/START_HERE.md` and `engineering/crm-handoff/sources.lock.json`. Preserve existing repository/platform instructions and scaffold markers.

Use `.agents/skills/mainsequence_crm/` for CRM work, with the appropriate installed `.agents/skills/mainsequence/`, `.agents/skills/command-center/` or optional `.agents/skills/ms_tau_sdk/` guidance. Project skills must remain outside SDK-managed/pruned namespaces.

Target: Python FastAPI, Main Sequence MetaTables, Vite React/TypeScript and the Command Center SDK. Reuse platform-injected identity; do not rebuild login/users/roles or adopt Supabase/Django/Frappe/Node business backends. Atomic is the pinned behavioral reference, not the retained application architecture. Tau is not required for deterministic tracking or data transfers.

Implement tickets in dependency order. Prove atomic governed commands and fresh-process catalog binding before completing mutations. Report executed checks separately from specified, mocked or unexecuted tests.

Current repository decision (2026-09-23): Alembic `0003` removes `command_receipt`; CRM commands no longer require `Idempotency-Key` or promise replay. Older handoff text mandating receipts is superseded for this repository. Keep version fences and governed atomic writes, and read server state before retrying an uncertain write.

Current repository decision (2026-09-23): Alembic `0004` removes the CRM application workspace table and every `workspace_uid` column. The CRM has singleton settings and direct record foreign keys; platform-injected identity/policy remain authoritative. Older handoff instructions for workspace-scoped keys, a workspace UID resolver, or a workspace mutation epoch are superseded. Do not reintroduce them.

For every material change to a CRM model, business rule, mounted API behavior, persistence, transfer workflow, or delivery status, use `.agents/skills/mainsequence_crm/maintain-crm-documentation/SKILL.md` and update the relevant MkDocs concept and API/delivery pages in the same change. Run `mkdocs build --strict` and report its result; keep planned or unverified behavior labeled.
