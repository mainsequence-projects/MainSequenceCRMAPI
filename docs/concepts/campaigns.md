# Campaigns

A **Campaign** is one live directed acyclic graph of prompted task
definitions, implemented by the optional Campaigns module
(`extensions.campaigns.active` in `config/crm.yaml`). Each enrolled Contact
follows the graph according to the outcomes recorded for that person. The
module uses existing [Contacts](contacts.md), [Tasks](tasks-notes.md) and the
[Agent Prompt](prompts.md) library; it adds no user, tenant, permission or
delivery system. [ADR 0001](../campaigns_module/adrs/0001-campaign-task-graph.md)
records the design decisions; this page describes the implemented behavior.

## Definition versus instance

| Model | Meaning | Identity |
| --- | --- | --- |
| Campaign | Name, Markdown objective, owner, bounded `context` (offer terms, audience), `status` and `entry_step_uid` | UUID, version, audit fields, archive marker |
| CampaignStep | Reusable task definition: title, Markdown `task_text`, `completion_criteria`, declared `outcomes`, one or two `prompt_variants`, optional `prompt_comparison`, `input_bindings`, task defaults and designer `position` | UUID stable across edits; retired with an archive marker |
| CampaignTransition | One connection per declared outcome: `from_step_uid` + `outcome_key` → `to_step_uid` or finish (`null`) with `delay_seconds` | UUID; unique per source step and outcome |
| CampaignStepPrompt | An Agent Prompt specialized with declared `inputs` and `result_fields` | Shares the Prompt's UID, version and audit fields |
| CampaignParticipant | One Contact's enrollment with its `progress` records, `next_step_uid`, `eligible_at` and `finished_at` | UUID; unique per campaign and Contact |

A **progress record** is an embedded value of the participant, stored in an
internal association table keyed by participant and step with a unique Task
UID. It holds the actual CRM Task, the immutable `prompt_assignment`, the
`state` (`open`, `waiting`, `blocked`, `completed`, `cancelled`), the
validated `outcome_key`, `result`, `evidence`, `wake_at`, `blocked_reason` and
`prepared_with` provenance. The participant version fences every progress
change. Task text, owner, due date and completion metadata stay on the core
Task.

## Lifecycle

Campaign status moves `draft → active`, `active ↔ paused` and `active|paused →
completed`. Activation and every save of an active or paused campaign require
a **runnable graph**: one entry step, every declared outcome connected exactly
once, same-campaign endpoints, reachability, no cycles, existing active step
prompts, compatible A/B prompt contracts and a reachable comparison metric
step. Drafts may be saved with diagnostics.

Participants are enrolled explicitly and start `active` with the campaign's
entry step scheduled (`eligible_at` now). Enrolling into a draft schedules the
entry step at activation. `paused` participants keep their instances and may
record facts but receive no new Task. `withdrawn` archives open Tasks, cancels
open progress and is terminal; `completed` is reached through a finish
connection or an explicit cancel-and-finish reconciliation.

## Progression

1. **Advance** creates the eligible Task and the progress record in one
   governed statement, locked on the participant row, after checking the
   participant version, lifecycle, `eligible_at`, the current step version and
   the assigned prompt version. A repeat call returns the existing instance;
   two concurrent calls cannot create two Tasks. The variant is chosen by
   weighted random selection in the service and persisted with the Task,
   including the prompt version, comparison metadata and allocation at that
   moment. A route back to a visited step is diagnosed (`step_already_visited`)
   and never replayed.
2. **Prepare** assembles the briefing read-only: objective and context, the
   current step, the assigned variant's current prompt, inputs resolved from
   documented paths (`campaign.*`, `contact.*`, `participant.context.*`,
   `previous.<step_uid>.result.*`), authorized Contact fields, prior results,
   the Task, permitted transitions and `prepared_with` provenance. Missing
   required inputs, retired steps, archived prompts and inactive campaigns are
   diagnostics; nothing is invented and nothing is written.
3. **Wait**, **block** and **report** record a wake time, an actionable reason
   or observed evidence and partial results on the open instance. A wake date
   never infers an outcome.
4. **Complete** validates the allowed outcome, the prompt's typed result
   fields and at least one evidence item, then settles the Task, records the
   result and selects the live transition atomically. When `prepared_with` no
   longer matches the current campaign, step and prompt versions, the facts are
   saved and the instance is blocked as `stale_briefing`; nothing routes.
5. **Reconcile** resolves blocked work explicitly: `resume` accepts the stored
   result against the current graph, `reopen` refreshes the instance, `cancel`
   archives the Task (never completes it) and either reroutes to an unvisited
   step or finishes the participant.

Core Task commands are guarded: completing a campaign Task through
`/api/crm/v1/tasks/{uid}/complete/` blocks the instance as `outcome_required`;
reopening a completed instance blocks it as `task_reopened`; reassigning the
Task to another Contact is rejected; archiving the Task or its assigned Prompt
blocks open work. Contacts with an enrollment cannot be merged until an
explicit merge policy exists.

## Live editing

The graph is saved whole against the campaign version. Only new or changed
steps and transitions are written, so unchanged definitions keep their
versions and open briefings; position-only edits never bump a version.
Retired steps keep their identity and history. A material edit blocks that
step's open work (`step_changed`), a retirement blocks (`step_retired`) or,
with `affected_open_work: cancel`, archives the open Tasks and cancels their
progress. Changes to prompt mapping, allocation, comparison, task rules or
criteria mark existing assignments `comparison_changed`; a prompt content or
contract change blocks open work (`prompt_changed`) and flags its assignments.
Participants scheduled to a retired step are listed in the validation impact
and rerouted explicitly through the participant command.

## A/B comparisons

A step carries one prompt (100 %) or two variants whose allocations sum to
100, with a `prompt_comparison` naming the control variant, the metric step,
the success outcomes and an observation window. Assignment is per Contact at
that step and is reused by preparation, retries and restarts; an agent cannot
choose a variant. The campaign detail reports, per step and comparison key,
the number of assigned, completed, cancelled and matured participants, the
successes whose metric outcome was reached within the window, the success rate
over matured assignments and changed exposures. Late successes do not count,
cancelled assignments stay in the denominator and groups with an earlier key
are shown as `current: false`. The module never declares a winner or changes
allocations automatically.

## Bounds

Fifty active steps and two hundred transitions per campaign; twenty outcomes
per step; thirty declared inputs, result fields or bindings; fifty evidence
items per instance; 16 KiB JSON values for context, results and assignments;
64 KiB Markdown. Collections are paged (at most 100 per page).

See the [Campaigns API](../api/campaigns.md) for routes, payloads and MCP
tools, and [persistence](../delivery/persistence.md#campaigns-revision-0013)
for the tables.
