---
name: crm-prompters
description: Select or maintain Solution Selling prompters, inspect their supported Jinja context and required inputs, and render an unsaved personalized draft through CRM MCP. Use for template authoring, draft generation or rendering failures; rendering never sends or saves a message.
---

# Render a draft with a prompter

Read [shared MCP guidance](skill://crm-core/references/mcp-usage.md). Use
[CRM core](skill://crm-core/SKILL.md) to resolve people and organizations and
[prospecting](skill://solution-selling/crm-prospecting/SKILL.md) for Lead/profile selection.

## Tool selection

| Need | Tools |
| --- | --- |
| Find a template and inspect its stored text | `crm_prompters_list`, `crm_prompters_get` |
| Save or edit a reusable template | `crm_prompters_create`, `crm_prompters_update` |
| Render the selected template from CRM records and inputs | `crm_prompters_render` |

## Resolve what the template needs

1. Find by supported search/kind filters, disambiguate matching names and get
   the stored template. Do not create or edit a template for an ordinary draft
   request when a suitable one already exists.
2. Inspect its references using the supported
   [template context](references/template-context.md). The catalogue has no
   requirements-discovery tool; explain that requirements came from inspecting
   the template, not a server-certified requirements response.
3. Rendering requires both `contact_uid` and explicit `company_uid`, even if
   the text references only a Contact. Verify both records. Use an explicit
   Company from the request/context; when several affiliations leave the
   choice ambiguous, ask instead of silently selecting the primary Company.
4. Resolve any additional Lead, profile, Deal or assessment references the
   template needs. An unguarded `profile.role` needs a profile; a section guarded
   by `{% if profile %}` can be omitted when no profile was selected.
   `{{ inputs.topic }}` requires a string `topic` input. Ask only for missing
   inputs needed by the rendered branches; do not fabricate data to suppress
   missing-context errors.
5. The service supplies `sender.uid` and `sender.display_name` from the
   effective user. Do not ask for credentials or override that identity.

## Render, inspect and present

Call `crm_prompters_render` with prompter `uid` and a `payload` containing the
selected references and string-valued `inputs`. The service checks the Lead's
Contact, the Lead's profile when both are supplied, the Deal's Company, and the
assessment's Company and Deal when supplied. Reconcile mismatched references
from actual reads; do not remove a reference just to evade its validation.

Inspect `code: ok` and `data.text`, then present the text as an unsaved draft.
Rendering does not send a communication or create a Note, Interaction or Task.
A profile's suggested pain remains a hypothesis in the rendered message.

For validation failures, check the selected relationships, missing fields,
input names and restricted syntax. Correct a known issue or obtain the missing
fact; do not repeat unchanged failing calls. If rendering is unavailable, say
so. A separately written suggestion must be identified as such.

## Author or maintain a reusable template

For an explicit template save, use create with name, kind and template, or
update with a freshly read version and requested changes. Read the context
reference for a working Jinja example and supported fields. Keep optional
context guarded and customer-specific facts in records or supplied inputs.
Validate a requested rendering with explicit records; a saved template alone
does not establish that every intended context renders successfully.
