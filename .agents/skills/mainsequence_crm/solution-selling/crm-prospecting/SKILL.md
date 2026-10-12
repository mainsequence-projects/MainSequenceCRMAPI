---
name: crm-prospecting
description: Select or maintain Solution Selling prospecting profiles and Contact Leads through CRM MCP. Use for target-role research, potential pain hypotheses, Lead qualification or nurture status, profile assignment and linking an open next Task.
---

# Prospecting profiles and Leads

Read [shared MCP guidance](skill://crm-core/references/mcp-usage.md). These tools require
the Solution Selling module to be advertised. Use
[CRM core](skill://crm-core/SKILL.md) for Contacts, owners and Tasks,
[prompters](skill://solution-selling/crm-prompters/SKILL.md) for outreach drafts and
[discovery](skill://solution-selling/crm-discovery/SKILL.md) for diagnosis preparation.

## Tool selection

| Need | Tools |
| --- | --- |
| Find and inspect reusable prospecting guidance | `crm_prospecting_profiles_list`, `crm_prospecting_profiles_get` |
| Save or revise that guidance | `crm_prospecting_profiles_create`, `crm_prospecting_profiles_update` |
| Find and inspect a Contact's prospecting state | `crm_leads_list`, `crm_leads_get` |
| Save or update that state | `crm_leads_create`, `crm_leads_update` |

## Choose or maintain a profile

1. Resolve the intended market context and buyer role. Search profiles by
   name, market context, role or potential pain, and use advertised role/market
   filters where useful. Get a candidate before applying its guidance; do not
   select one merely because a Company name matches.
2. Explain how the profile relates to this Contact's role. Its potential pain,
   likely reasons and likely impacts are hypotheses for research, not verified
   facts about the Contact or Company.
3. On a requested profile save, supply nonblank name, `market_context`, `role`
   and `potential_pain`. Include only intended optional research guidance,
   opening message, likely reasons/impacts and suggested next commitment.
4. A `diagnosis_template` holds reusable questions across the nine diagnosis
   cells; every answer must remain null. Customer answers belong in a
   diagnosis. Use the discovery skill for that matrix and evidence workflow.
5. For edits, get the current profile version and patch requested changes.
   Do not rewrite a reusable profile solely to customize one Contact's draft.

## Maintain a Lead and its next step

1. Resolve the Contact through CRM core, then query Leads with
   `filters.contact_uid`. Lead free-text search matches notes, not Contact
   names. Narrow by profile, owner or status only with supported filters.
2. Inspect existing Leads before creating one. A create requires `contact_uid`
   and status; profile, owner, notes and next Task are optional. Pick the state
   supported by the user's request/evidence:
   `to_contact`, `contacted`, `qualified`, `nurture` or `disqualified`.
3. Verify any selected profile and owner. To assign `next_task_uid`, read the
   Task and ensure it belongs to this Contact and is currently open. If a Task
   does not exist, create one only when the user requests that follow-up; then
   link its confirmed UID. These are separate writes, not one transaction.
4. Save with create or update using a fresh Lead version. A Lead's Contact
   cannot be rebound through update. If the wrong Contact was selected, explain
   the supported choices instead of manufacturing a relink command.
5. Report the resulting Lead state and any actual next Task. If linking fails
   after a Task was saved, report both outcomes and read state before recovery.

Task completion does not automatically change the Lead's next Task reference.
Qualification does not create a Deal or establish confirmed buyer pain. Use
the Deals skill for a requested opportunity and discovery for actual evidence;
do not perform those writes as implicit side effects of a Lead status change.
