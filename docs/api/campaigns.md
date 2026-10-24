# Campaigns API

These routes mount only when `extensions.campaigns.active: true` in
`config/crm.yaml`; bootstrap then reports `modules.campaigns: true`. The base
path is `/extensions/campaigns/`. Disabling the module hides the routes and
MCP tools and keeps the data. REST, MCP and the designer share
`src/crm/campaigns/service.py`; every call rechecks the effective person's
capability and validates the command again at the service boundary. Concepts
are described in [Campaigns](../concepts/campaigns.md).

## Routes

| Method | Relative path | Capability | Result |
| --- | --- | --- | --- |
| GET | `campaigns/` | `crm.read` | `{items, pageInfo}` of `CampaignSummary` with `participant_counts` |
| POST | `campaigns/` | `crm.create` | Draft `Campaign` (201) |
| GET | `campaigns/{uid}/` | `crm.read` | `Campaign` with `steps`, `transitions`, `validation` and `comparisons` |
| PATCH | `campaigns/{uid}/` | `crm.edit` | Updated campaign; lifecycle changes validate the graph |
| POST | `campaigns/{uid}/archive/`, `restore/` | `crm.archive` | Archived or restored campaign |
| POST | `campaigns/{uid}/graph/validate/` | `crm.read` | Read-only `validation`, `changes` and `impact` for a candidate graph |
| POST | `campaigns/{uid}/graph/` | `crm.edit` (`crm.archive` with `affected_open_work: cancel`) | Campaign after the atomic graph save |
| GET, POST | `prompts/` | `crm.read`, `crm.create` (`crm.edit` when specializing) | Step prompt collection and creation |
| GET, PATCH | `prompts/{uid}/` | `crm.read`, `crm.edit` | Step prompt with `content_markdown`, `inputs`, `result_fields` |
| GET, POST | `participants/` | `crm.read`, `crm.create` | Participant collection and enrollment |
| GET, PATCH | `participants/{uid}/` | `crm.read`, `crm.edit` (`crm.archive` to withdraw) | Participant with embedded `progress` |
| POST | `tasks/prepare/` | `crm.read` | Read-only briefing |
| POST | `tasks/advance/` | `crm.create`, `crm.edit` | `{created, participant}` |
| POST | `tasks/complete/` | `crm.edit` | `{accepted, reason?, participant}` |
| POST | `tasks/wait/`, `tasks/block/`, `tasks/report/` | `crm.edit` | Participant after recording |
| POST | `tasks/reconcile/` | `crm.edit` (`crm.archive` to cancel) | Participant after reconciliation |

List queries accept `page_index`, `page_size` (1–100) and `search`, plus direct
filters: campaigns `status`, `owner_uid`, `archived` (`true`, `false` or
`all`; default active); prompts `archived`; participants `campaign_uid`,
`contact_uid`, `status` and `attention=true` (blocked instances or a due next
step). Unknown filters return 422.

## Payloads

Create a campaign:

```json
{"name": "Dubai LinkedIn outreach", "objective": "# Pilots with preferred pricing",
 "owner_uid": "…", "context": {"offer": {"gpu_hours": 100, "discount": "20%"}}}
```

Patch: `{"expected_version": 1, "changes": {"status": "active"}}`. Allowed
status moves are `draft→active`, `active↔paused` and `active|paused→completed`;
other moves return 422 with code `lifecycle`. Activation returns the graph
diagnostics (for example `route_missing`) when the graph is not runnable.

Save a graph (`graph/`): `{"expected_version": 2, "affected_open_work":
"block", "graph": {"entry_step_uid": "…", "steps": [...], "transitions":
[...]}}`. The graph is complete: every active step with a client-generated
`uid`, `title`, `task_text`, `completion_criteria`, `outcomes`
(`{key, label, description?}`), `prompt_variants` (`{key, label, prompt_uid,
allocation_percent}` summing to 100), optional `prompt_comparison`
(`{key, control_variant_key, metric_step_uid, success_outcome_keys,
observation_window_seconds}`, required with two variants), `completion_mode`
(`human`|`agent`), optional `owner_uid`, `task_type_key`, `due_after_seconds`,
`input_bindings` and `position`; `archived: true` retires a step. Transitions
are `{uid, from_step_uid, outcome_key, to_step_uid|null, delay_seconds}`; a
finish connection has no delay. An active step omitted from the payload is
rejected (`step_missing`); a retired step cannot be restored through the graph.
A stale `expected_version` returns 409 and nothing changes.

Create a step prompt: `{"name": "GPU first", "content_markdown": "# …",
"inputs": [{"key": "first_name", "type": "string", "required": false}],
"result_fields": [{"key": "message", "type": "string", "required": true}]}`.
Specialize an existing Agent Prompt instead with `{"prompt_uid": "…",
"expected_version": 3, "inputs": [...], "result_fields": [...]}`; the Prompt's
version advances once. Value types are `string`, `boolean`, `number`,
`datetime`, `object` and `array`; `outcome_key`, `result` and `evidence` are
reserved completion fields.

Enroll: `{"campaign_uid": "…", "contact_uid": "…", "context": {}}` (409 when
already enrolled, the Contact is archived or the campaign is archived or
completed). Participant patch changes: `context`, `status` (`active`,
`paused`, `withdrawn`) or an explicit `next_step_uid` reroute to an active step
without an instance.

Task commands identify the instance by `participant_uid` and `step_uid` and
carry the participant `expected_version`:

- `advance`: `{"participant_uid", "expected_version"}` → `created: true` with
  the new Task, or `created: false` with the existing instance. Validation
  codes: `nothing_scheduled`, `not_yet_eligible`, `step_retired`,
  `step_already_visited`, `lifecycle`.
- `prepare`: `{"participant_uid", "step_uid"}` → `campaign`, `step`,
  `prompt`, `assignment`, `changed_exposure`, `inputs`, `contact`,
  `participant`, `previous_results`, `task` (with its version), `transitions`,
  `progress`, `prepared_with`, `diagnostics`, `ready`.
- `complete`: adds `task_expected_version`, `outcome_key`, `result`,
  `evidence[]` (≥ 1 of `{summary, resource_type?, resource_uid?}`) and the
  briefing's `prepared_with`. Returns `accepted: true`, or `accepted: false`
  with `reason: stale_briefing` after recording the facts. Validation codes:
  `outcome_unknown`, `route_missing`, `not_open`, `step_retired`,
  `result.<field>` with `missing`, `type` or `unknown_field`.
- `wait`: `wake_at` (offset-aware) and optional `evidence`; `block`:
  `blocked_reason`; `report`: `evidence` and optional `result` merged into the
  stored result.
- `reconcile`: `action` `resume`, `reopen` or `cancel`; `cancel` needs exactly
  one of `next_step_uid` or `finish: true`; `task_expected_version` is
  optional and defaults to the current Task version.

## Errors and recovery

Version fences on the campaign, participant, Task and Prompt return 409; the
whole statement rolls back, including dependent Task, progress and activity
writes. An uncertain write (timeout, lost response) must be followed by a read
of the participant or campaign before any retry; `advance` cannot create a
second instance for the same participant and step, so a lost response is
resolved by reading. Every mutation records an activity event
(`campaign`, `campaign_participant`, `prompt` or `task` entity types).

## MCP tools

With the module enabled, the authenticated `/mcp` catalogue advertises 21
tools through the same service and effective-person checks: `crm_campaigns_
{list,get,create,update,graph_validate,graph_update}`,
`crm_campaign_prompts_{list,get,create,update}`,
`crm_campaign_participants_{list,get,create,update}` and
`crm_campaign_tasks_{prepare,advance,complete,wait,block,report,reconcile}`.
Reads carry read-only annotations. Schemas mirror the HTTP payloads
(`payload` wrappers for create/update, `uid` for one record). The
`crm-campaigns` usage skill in `.agents/skills/mainsequence_crm/` explains the
workflows; see [application MCP](mcp.md).
