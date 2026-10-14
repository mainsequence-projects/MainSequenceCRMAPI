---
name: crm-prospecting
description: Resolve Companies before creating prospecting Contacts, then run Solution Selling outreach through CRM MCP using a required prompter. Record actual Interactions, Lead progress and follow-up Tasks; also use for profiles, target-role research, qualification and nurture.
---

# Prospecting outreach, profiles and Leads

Read [shared MCP guidance](skill://crm-core/references/mcp-usage.md). These tools require
the Solution Selling module to be advertised. Use
[CRM core](skill://crm-core/SKILL.md) for Contacts, Interactions, owners and Tasks,
[prompters](skill://solution-selling/crm-prompters/SKILL.md) for outreach drafts and
[discovery](skill://solution-selling/crm-discovery/SKILL.md) for diagnosis preparation.

## Company before prospecting Contact

Before creating any Contact for prospecting, resolve the person's actual
Company. Search with `crm_companies_list` and read the matching record with
`crm_companies_get`. Resolve ambiguous matches from known business facts. If
the actual Company is absent, create it with `crm_companies_create` using the
known Company name and supplied details, and inspect its successful result
before proceeding. A requested prospecting Contact creation includes this
necessary Company creation when its identity is established.

Use the confirmed Company UID in `crm_contacts_create` as
`payload.company_uid`. Do not create a prospecting Contact with a missing or
null Company and plan to link it later. If the Company is unknown, ambiguous,
unavailable or its creation outcome is uncertain, stop before saving the
Contact and resolve the missing information or state. Never create a placeholder
Company or infer employment solely from an email domain.

Check for an existing Contact before creating one; read its relevant Company
affiliations when reusing it. Follow CRM core for any requested relationship
change rather than silently overwriting its primary Company. Company and
Contact creation are separate writes: if the Company is saved but the Contact
fails, report the actual outcome and reuse the confirmed Company during recovery.

## Required prompter

Every prospecting introduction, follow-up message and conversation preparation
must use a persisted prompter and the CRM renderer. If the user indicates a
prompter by UID, name or a prior selection in this workflow, resolve and read
that record. If no prompter is indicated, create one first with
`crm_prompters_create`; do not silently choose an unrelated existing template
or substitute an ad hoc message. Follow the prompter skill to author supported
Jinja and inspect its required context.

A prospecting outreach request includes this required template creation when
none is indicated. It does not authorize sending or saving unrelated records.
Research-only requests, Lead administration and recording past events do not
require creating a template. A template created now does not prove it was used
for a message already sent.

## Tool selection

| Need | Tools |
| --- | --- |
| Resolve or create the Company before a prospecting Contact | `crm_companies_list`, `crm_companies_get`, `crm_companies_create`, `crm_contacts_list`, `crm_contacts_get`, `crm_contacts_create` via CRM core |
| Find and inspect reusable prospecting guidance | `crm_prospecting_profiles_list`, `crm_prospecting_profiles_get` |
| Save or revise that guidance | `crm_prospecting_profiles_create`, `crm_prospecting_profiles_update` |
| Find and inspect a Contact's prospecting state | `crm_leads_list`, `crm_leads_get` |
| Save or update that state | `crm_leads_create`, `crm_leads_update` |
| Resolve or create the required prompter, then render | `crm_prompters_list`, `crm_prompters_get`, `crm_prompters_create`, `crm_prompters_render` via the prompter skill |
| Record or update the actual outreach | `crm_interactions_list`, `crm_interactions_get`, `crm_interactions_create`, `crm_interactions_update` via CRM core |
| Save and link follow-up work | `crm_tasks_list`, `crm_tasks_get`, `crm_tasks_create`, `crm_leads_update` via CRM core and the Lead guidance below |

## Contact to outreach to follow-up

1. **Resolve the Company, then the person.** Apply the Company prerequisite
   above before saving a new prospecting Contact. Reuse a matching Contact
   where present; read it, the explicitly relevant Company and any selected
   profile. Query the Contact's Lead before creating one; there is one Lead per
   Contact. Ask when the intended Company is ambiguous. Profile pain and likely
   impacts remain hypotheses.
2. **Resolve or create the prompter before drafting.** Read an indicated
   prompter. Otherwise create a reusable template with a meaningful `name`,
   `kind` and `template`, using the requested purpose, channel and language.
   Use Jinja variables for Contact, Company, sender and supplied inputs; keep
   customer-specific facts out of the reusable text. Ask for an essential
   missing business fact rather than inventing it. Inspect `code: ok` and the
   confirmed prompter UID before using it. If creation is denied or uncertain,
   follow shared recovery guidance and stop draft generation until the
   required prompter is resolved. One suitable created prompter can serve a
   requested batch; render separately for each Contact and Company.
3. **Prepare the requested Lead.** If the outreach request includes new Lead
   tracking, create its initial `to_contact` record using the guidance below.
   Preserve an existing Lead's status unless a change is requested. Resolve
   any Lead reference required by the template before rendering; a draft-only
   request does not imply Lead creation.
4. **Render and review.** Call `crm_prompters_render` with the confirmed
   prompter UID and `payload` containing `contact_uid`, explicit `company_uid`,
   required string `inputs` and any deliberately selected Lead/profile/Deal
   references. Follow the prompter skill's relationship checks. Inspect
   `code: ok` and `data.text`; present the actual renderer output as an unsaved
   draft, with the prompter name/UID. Do not replace a failed render with a
   hand-written outreach draft.
5. **Establish what happened.** The CRM MCP catalogue has no delivery tool.
   Give the draft to the user to send through their chosen channel. Rendering,
   copying text or completing a Task does not establish delivery. Proceed to
   completed outreach recording only after the user reports the event or an
   authorized delivery tool supplies evidence of it. For an explicitly
   requested future call/meeting plan, use an Interaction with `planned`
   status and known `scheduled_at`; do not mark the Lead contacted yet.
6. **Record the outreach when requested.** Check for an existing matching
   Interaction so an update does not create duplicate history. Use the actual
   subject, supported `kind`, participants (including the Contact), explicit
   Company context and known offset-aware `occurred_at`. Set `completed` only
   for an event that happened. Preserve the actual sent text or user-provided
   summary in `outcome_notes`, and actual follow-up agreements in `next_steps`;
   edited sent text takes precedence over the earlier renderer output. An
   Interaction has no typed prompter or Lead link: it connects to the Contact
   through participants. Never invent those fields or claim automatic template
   provenance. CRM core owns the exact Interaction payload.
7. **Update prospecting progress when requested.** After actual outreach,
   reread the Lead and update `to_contact` to `contacted` with its current
   version. Preserve an existing qualified, nurture or disqualified state
   unless the user's request calls for a change. Interaction save and Lead
   update are separate writes; if one fails, report which record was saved and
   read state before recovery. Recording a past event never requires sending
   it again or claiming a newly created prompter was used for it.
8. **Save the next action when requested.** Create a follow-up Task on the
   same Contact with the supplied text, owner and due time. Inspect its saved
   UID, then reread the Lead and link it through `next_task_uid`. A reply may
   justify a requested `qualified`, `nurture` or `disqualified` update; it does
   not create a Deal. Route actual discovery evidence to the discovery skill
   and an explicitly requested opportunity to
   [Deals](skill://crm-deals/SKILL.md).

At completion, distinguish the prompter saved, draft rendered, outreach reported
or verified, Interaction saved, Lead state and linked Task. For a draft-only
request, stop after rendering and report the required template creation; do
not create a Lead, Interaction or Task as an implicit side effect.

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

1. Resolve the Contact through CRM core, applying the Company prerequisite
   above if a prospecting Contact needs to be created, then query Leads with
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
