---
name: crm-discovery
description: Prepare Solution Selling conversations, record diagnosis questions and answers, and maintain Deal assessments through CRM MCP. Use for business pain, key players, pain chains, evaluation plans and evidence review while distinguishing hypotheses, reported facts and confirmed evidence.
---

# Discovery and Deal evidence

Read [shared MCP guidance](skill://crm-core/references/mcp-usage.md). Resolve Deals with
[crm-deals](skill://crm-deals/SKILL.md), Contact/Interaction records with
[CRM core](skill://crm-core/SKILL.md), and reusable hypotheses/questions with
[prospecting](skill://solution-selling/crm-prospecting/SKILL.md).

## Tool selection

| Need | Tools |
| --- | --- |
| Read a Deal, Company, assessment and bounded conversation context | `crm_solution_selling_context_get` |
| Find and inspect saved conversation diagnoses | `crm_diagnoses_list`, `crm_diagnoses_get` |
| Prepare a diagnosis from a profile without saving | `crm_diagnoses_prepare` |
| Save a diagnosis or update its answers/conclusion | `crm_diagnoses_create`, `crm_diagnoses_update` |
| Find and inspect a Deal assessment | `crm_assessments_list`, `crm_assessments_get` |
| Save or revise that assessment | `crm_assessments_create`, `crm_assessments_update` |

## Review evidence or prepare for a conversation

1. Resolve the Deal and call `crm_solution_selling_context_get` with `deal_uid`.
   Request Interaction pages with `interaction_page_index` and
   `interaction_page_size` (default 5, maximum 20). Inspect `pageInfo` and source
   UIDs/versions before claiming a complete history.
2. The Company or assessment may be null. Report that absence; do not create
   records merely to fill the context. The context combines separate reads,
   not an atomic snapshot, and does not include diagnosis records.
3. Fetch relevant diagnoses separately by Interaction, Contact or assessment
   filters, then get details as needed. Distinguish recorded answers and their
   sources from profile hypotheses and your proposed questions.
4. For a new diagnosis draft, resolve an explicit Interaction, Contact and
   prospecting profile. Call `crm_diagnoses_prepare` with their UIDs and
   optional `solution_selling_uid`. Check the optional assessment matches the
   Interaction's Company/Deal context when present.
5. Inspect `draft`, `saved: false`, `business_issue_status: hypothesis` and
   `sources`. The draft copies profile questions with null answers. A profile
   with no template yields nine empty cells; propose questions as suggestions,
   not previously recorded buyer statements. Present the draft without claiming
   that an Interaction, diagnosis or assessment was saved.

## Save answers and conclusions

Use `crm_diagnoses_create` only for a requested save, passing the reviewed
`draft` as its `payload`, not the entire prepare response. A diagnosis needs
Interaction, Contact and a nonblank `business_issue`; the assessment link and
conclusion are optional.

The matrix has approaches `open`, `control`, `confirming`, each with subjects
`reasons`, `impact`, `capabilities`: nine lists of `{question, answer}` entries.
Keep unanswered entries null. Preserve a buyer's actual answer and clarify
uncertain attribution; do not fill answers from a profile or generated text.

For edits, reread the diagnosis and patch its current version, requested matrix
changes and/or conclusion. Matrix replacement must preserve unaffected answers.
The Contact and Interaction links cannot be rebound through update. Saving a
diagnosis does not automatically update a Deal assessment or mark its evidence
confirmed; those require a separately requested operation.

## Maintain the Deal assessment

1. Query assessments by Deal and read the existing record before deciding to
   create. There is one maintained assessment per Deal. A create needs the
   Deal and its matching Company; those links are immutable on update.
2. Update only the requested pain, power, vision, value, control or evaluation
   plan evidence. Resolve pain/power/sponsor Contact references through actual
   CRM records. Do not invent buyer authority, commitments or expected value.
3. Key players contain Contact, pain, reasons and an evidence `status`.
   Pain-chain links contain from/to Contact, explanation and status. Preserve
   `hypothesis`, `reported` and `confirmed` distinctions. Use confirmed only
   when the user's evidence supports it; a generated draft is not confirmation.
   There is no generic assessment-status field to set.
4. Key-player Contacts must be unique. Each directed pain-chain link must have
   distinct endpoints, be unique, and connect two key players with recorded
   pains. When changing the graph, retain unaffected entries and keep both
   arrays consistent; do not silently remove other people's evidence.
5. Save with a fresh version and inspect the returned assessment. A context
   read may be stale by the time of an edit; reread on conflict. Report saved
   facts separately from open questions, unsaved suggestions and follow-up work.
