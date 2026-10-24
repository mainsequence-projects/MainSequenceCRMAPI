---
name: crm-campaigns
description: "Design, edit, read and run Campaigns through CRM MCP: a live DAG of prompted task definitions with outcome connections, explicit Contact enrollment, one prompt or A/B prompt variants per step, and campaign task briefings, outcomes, waits, blocks and reconciliation. Use whenever a request names a campaign, sequence, outreach graph, step prompt or a Task that belongs to a campaign."
---

# Campaigns: graphs, enrollment and task execution

Read [shared MCP guidance](skill://crm-core/references/mcp-usage.md). Resolve
people with [CRM core](skill://crm-core/SKILL.md); these tools require the
Campaigns module to be advertised. A campaign step is a reusable **task
definition**; the actual work for one Contact is an ordinary CRM Task created
by `crm_campaign_tasks_advance` and tracked on the **participant**.

## Tool selection

| Need | Tools |
| --- | --- |
| Find or read a campaign with its graph, validation and A/B counts | `crm_campaigns_list`, `crm_campaigns_get` |
| Create a draft or change fields/lifecycle | `crm_campaigns_create`, `crm_campaigns_update` |
| Check a candidate graph and its impact before saving | `crm_campaigns_graph_validate` |
| Save the complete graph atomically | `crm_campaigns_graph_update` |
| Step prompts (Agent Prompts with inputs and result fields) | `crm_campaign_prompts_list`, `crm_campaign_prompts_get`, `crm_campaign_prompts_create`, `crm_campaign_prompts_update` |
| Enrollment and progress of one Contact | `crm_campaign_participants_list`, `crm_campaign_participants_get`, `crm_campaign_participants_create`, `crm_campaign_participants_update` |
| Read the current briefing for a campaign Task | `crm_campaign_tasks_prepare` |
| Create the next Task once | `crm_campaign_tasks_advance` |
| Submit an outcome with evidence and route | `crm_campaign_tasks_complete` |
| Record a wait, a block or observed facts | `crm_campaign_tasks_wait`, `crm_campaign_tasks_block`, `crm_campaign_tasks_report` |
| Resolve blocked work explicitly | `crm_campaign_tasks_reconcile` |

## Create and edit a campaign

1. Create the draft with `name`, Markdown `objective`, a selectable `owner_uid`
   and bounded `context` (audience, offer terms, channel). The offer lives in
   context as user-supplied facts; do not invent terms.
2. Resolve or create step prompts. A new one needs `name`, `content_markdown`
   and optional `inputs`/`result_fields` (`string`, `boolean`, `number`,
   `datetime`, `object`, `array`). To reuse a saved Agent Prompt, pass its
   `prompt_uid` and current `expected_version`; its UID and version are shared.
3. Build the complete graph: every active step with a client-generated UUID,
   `title`, `task_text`, `completion_criteria`, `outcomes`, one
   `prompt_variants` entry (100%) or two A/B entries whose allocations sum to
   100 plus a `prompt_comparison` (key, control variant, metric step, success
   outcomes, observation window). Add one transition per declared outcome to a
   next step or `to_step_uid: null` (finish). `input_bindings` map prompt inputs
   to `campaign.context.<key>`, `contact.<field>`, `participant.context.<key>`
   or `previous.<step_uid>.result.<field>`.
4. Call `crm_campaigns_graph_validate` with the candidate and read
   `validation.diagnostics` (missing routes, cycles, unreachable steps, unknown
   outcomes, prompt contract mismatches) and `impact` (open Tasks and
   participants affected). Fix the graph, then save with
   `crm_campaigns_graph_update` using the campaign's current `expected_version`.
   The payload is the whole graph: omit nothing active, and retire a step with
   `archived: true` rather than deleting it. Choose `affected_open_work`:
   `block` (default) keeps retired steps' open Tasks for reconciliation;
   `cancel` archives them and needs `crm.archive`.
5. Activate with `crm_campaigns_update` `changes.status: active`; activation
   fails with the same diagnostics when the graph is not runnable. Live edits
   keep stable step UIDs, block affected open work with `step_changed` or
   `step_retired`, and flag A/B assignments as changed exposure. Position-only
   edits change nothing else.

## Enroll and read progress

Enroll only when asked, one participant per Contact and campaign, with
`crm_campaign_participants_create`. Reading a campaign or participant never
enrolls, advances or sends anything. `progress` lists each step's Task UID,
`prompt_assignment`, `state` (`open`, `waiting`, `blocked`, `completed`,
`cancelled`), `outcome_key`, `result`, `evidence` and `blocked_reason`.
`next_step_uid`/`eligible_at` show what is scheduled; the `attention` filter
lists blocked or due participants.

## Execute a campaign task

1. `crm_campaign_tasks_advance` with the participant `uid` and fresh
   `expected_version` creates the eligible Task and persists its variant
   assignment once, or returns the existing instance (`created: false`). It
   refuses paused/completed campaigns, delays that have not elapsed and steps
   already visited.
2. `crm_campaign_tasks_prepare` returns the briefing: objective and context,
   step instructions, criteria and outcomes, the **assigned** variant's current
   prompt, resolved `inputs`, authorized Contact data, prior results, the Task,
   permitted `transitions` and `prepared_with`. Follow the assigned variant; never
   choose or swap one. `ready: false` with `diagnostics` (missing input,
   retired step, archived prompt, inactive campaign) means stop and explain.
   `changed_exposure: true` means the definition changed since assignment.
3. Do the work the briefing describes using the user's channels and
   permissions. Preparation and Task creation do not send a message.
4. Report what actually happened:
   - `crm_campaign_tasks_wait` with `wake_at` when the step waits on the
     Contact; `crm_campaign_tasks_block` with an actionable `blocked_reason`;
     `crm_campaign_tasks_report` to record `evidence` or partial `result`.
   - `crm_campaign_tasks_complete` with the participant and Task expected
     versions, an `outcome_key` the step declares, a `result` matching the
     prompt's `result_fields`, at least one `evidence` item and the briefing's
     `prepared_with`. `accepted: true` means the Task was completed and the
     participant routed (`next_step_uid`, `eligible_at` or finished).
     `accepted: false` with `reason: stale_briefing` means the definition
     changed: the facts were saved and the work is blocked; prepare again and
     use `crm_campaign_tasks_reconcile`.
5. Reconcile blocked work only on explicit instruction: `resume` accepts the
   stored result against the current graph, `reopen` refreshes the briefing
   (also after a core Task completion left `outcome_required` or a reopen left
   `task_reopened`), `cancel` archives the Task and either reroutes with
   `next_step_uid` or `finish`es the participant. Cancelling needs `crm.archive`.

Do not complete a campaign Task with `crm_tasks_complete`: the graph blocks it
as `outcome_required`. A delay, wait or wake does not infer an outcome; a real
event or explicit human report does. After a timeout or lost response, read the
participant before any further write.

## Interpret A/B results

`crm_campaigns_get` returns `comparisons` per step and comparison key:
`assigned`, `completed`, `cancelled`, `matured` (window elapsed), `successes`
(metric outcome reached within the window), `success_rate` over matured
assignments and `changed_exposures`. Report these descriptively with their
denominators and window. Never declare a winner, stop early or change
allocations from a small or changed sample; `current: false` groups belong to
an earlier comparison key and are not pooled with the current one.
