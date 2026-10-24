# ADR 0001: Campaigns as a live DAG of prompted task definitions

- **Status:** Proposed for review; no Campaigns models, routes, tools or runtime are implemented.
- **Date:** 2026-10-24
- **Scope:** Optional Campaigns module, visual design, contact progression, application MCP and agent usage skills.
- **Related:** Existing [Contacts](../../concepts/contacts.md), [Tasks](../../concepts/tasks-notes.md), [Agent Prompts](../../concepts/prompts.md), [application MCP](../../api/mcp.md) and [module boundaries](../../concepts/index.md).

## Context

A user wants to design a multi-step campaign, such as LinkedIn outreach to
Dubai prospects offering preferred pricing and free GPU access. Each contact
progresses according to their own results: connection acceptance, a reply,
interest, a question or an expired waiting period.

Every graph node defines a task accompanied by a prompt. The user connects
task outcomes to subsequent tasks. The graph should be readable and editable
in a visual designer and through the assistant.

The distinction between definition and instance is fundamental:

- **CampaignStep:** reusable task definition, such as "Present the offer".
- **CRM Task:** work for one existing Contact, such as "Present the offer to Sarah".
- **CampaignParticipant:** that Contact's enrollment, task references and results.

## Decision

Introduce the optional **Campaigns** module with the five domain models below.
Use existing CRM Contacts, Tasks and the Agent Prompt library. Campaigns is
independent of the optional Solution Selling module; a Lead is not required.

The campaign has one live graph. Editing it changes the campaign. There is
**no CampaignRevision, published graph snapshot or frozen participant plan**.
Ordinary record versions remain concurrency fences, as in the existing CRM.

The initial graph supports conditional branching and convergence of alternative
paths. Each participant has at most one current task. Different participants
can progress concurrently. Parallel task forks and all/any joins for the same
participant are outside this first design.

```text
Campaign
  |-- CampaignStep --prompt variants--> CampaignStepPrompt extends Agent Prompt
  |       |
  |       +-- CampaignTransition: outcome --> next CampaignStep or finish
  |
  +-- CampaignParticipant --contact_uid--> existing Contact
          |
          +-- step progress[] --step_uid--> CampaignStep definition
                            +--task_uid--> existing CRM Task instance
```

## Model conventions

Campaign, CampaignStep, CampaignTransition and CampaignParticipant use the
existing CRM record conventions: UUID `uid`, integer `version`, server-owned
creation/update timestamps and actor UIDs, and nullable `archived_at`.
CampaignStepPrompt shares the underlying Prompt's UID, version and audit
metadata. References never introduce a new user, tenant or permission database.

The tables below define the proposed business fields. Embedded values have no
independent identity or CRUD API. Inputs, results, graph size and progress
arrays must have documented finite bounds when implemented.

### 1. Campaign

| Field | Type / requirement | Meaning |
| --- | --- | --- |
| `name` | Required nonblank string | Display name, for example "Dubai LinkedIn outreach". |
| `objective` | Required nonblank Markdown | Intended business outcome and success criteria. |
| `owner_uid` | Required platform user UID | Responsible person and default Task owner. Subject to existing owner-selection authorization. |
| `context` | Object; default `{}` | Shared, bounded JSON business values such as audience description, offer terms, language and channel. Values are facts supplied by the user. |
| `status` | `draft`, `active`, `paused`, `completed`; default `draft` | Whether participants may begin or advance. Editing remains possible in these states. |
| `entry_step_uid` | Nullable Step UID in draft; required before activation | The starting task definition, belonging to this campaign. |

An offer is initially campaign context, with explicit user-supplied terms.
There is no separate Offer, Audience, CampaignRun or campaign-wide execution
engine entity. Contacts are enrolled explicitly; a saved audience-query system
is outside this ADR.

### 2. CampaignStep — the task definition

| Field | Type / requirement | Meaning |
| --- | --- | --- |
| `campaign_uid` | Required Campaign UID | Owning graph. A step cannot be moved to another campaign. |
| `title` | Required nonblank string | Label on the designer's task card. |
| `task_text` | Required nonblank Markdown | Work to perform and additional instructions. Combined with the title into existing `Task.text`; core Tasks do not currently have a title field. |
| `prompt_variants` | Required list of one or two embedded PromptVariant values | One prompt normally, or A/B alternatives. Each task receives exactly one selected prompt. One prompt may serve several steps. |
| `prompt_comparison` | Optional embedded PromptComparison | Required with two variants; defines the comparison label and measurable success criterion. |
| `completion_mode` | `human` or `agent` | Who supplies the result. This is an execution choice, not authorization or proof of external delivery. |
| `owner_uid` | Optional platform user UID | Task owner override; otherwise use the Campaign owner. |
| `task_type_key` | Optional existing CRM task type key | Classification used when creating the CRM Task. |
| `due_after_seconds` | Optional nonnegative integer | Due-time offset from Task creation. A due date alone does not complete or fail a task. |
| `input_bindings` | Map from prompt input name to context source | Selects the data supplied to the prompt; see the prompt context contract. |
| `completion_criteria` | Required nonblank Markdown | Evidence needed to finish, including any explicit deadline rule for a waiting task. |
| `outcomes` | Nonempty list of `{key, label, description}` | Allowed terminal business outcomes, with stable keys unique within this step. |
| `position` | Optional `{x, y}` numbers | Designer layout only; position has no execution meaning. |

Research, sending, evaluating a reply and waiting for acceptance all use this
same model. There are no separate Action, Decision or Wait models. A decision
task produces an outcome. A waiting task remains open until its completion
criteria support an outcome such as `accepted` or `expired`.

#### Prompt variants and A/B comparison

**A/B compares two alternatives.** Comparing more alternatives is commonly
called **A/B/n**. Start this module with one prompt or two A/B variants, defaulting
to a 50/50 allocation for A/B. Store a list rather than dedicated `prompt_a`
and `prompt_b` fields so a later A/B/n requirement does not change the model's
shape. Initial validation still limits the list to two. See the
[Optimizely A/B/n definition](https://www.optimizely.com/optimization-glossary/abn-testing).

Each embedded **PromptVariant** contains:

| Field | Type / requirement | Meaning |
| --- | --- | --- |
| `key` | Required stable string, unique within the Step | Variant identity, for example `A` or `B`. |
| `label` | Required nonblank string | Designer label, such as "GPU first" or "Pricing first". |
| `prompt_uid` | Required CampaignStepPrompt UID | The alternative's instruction document. |
| `allocation_percent` | Positive integer | Allocation weight; all variants sum to 100. A single variant uses 100. |

The alternatives must accept the same declared input contract and produce the
same result fields; they share the Step's task defaults, completion criteria
and outcomes. The selected wording/instructions vary. Keep the audience, offer,
timing and execution settings comparable when attributing a difference to the
prompt. For example, both variants offer the same GPU terms, but lead with
different parts of that offer.

An embedded **PromptComparison** contains:

| Field | Type / requirement | Meaning |
| --- | --- | --- |
| `key` | Required stable comparison label | Groups observations from the same planned comparison, such as `dubai-offer-copy-1`. |
| `control_variant_key` | Required variant key | Baseline, normally `A`. |
| `metric_step_uid` | Required same-campaign Step UID | This Step or a reachable downstream Step whose outcome measures success. |
| `success_outcome_keys` | Required nonempty list | Outcomes at the metric Step that count as success, such as `interested`. |
| `observation_window_seconds` | Required positive integer | Equal period after assignment in which each participant's success is measured. |

Randomly assign a variant when creating the participant's Task, according to
the configured weights, and persist that assignment in the same operation.
The randomization unit is the Contact at this campaign Step. Preparation,
agent retries and restarts reuse the assignment; an agent must not choose
the variant it prefers. A 50/50 probability does not guarantee exact equal
counts in a small campaign. Stable assignment is established experimentation
practice; see [Statsig persistent assignment](https://docs.statsig.com/server/concepts/persistent_assignment).

Store the selected Prompt UID/version, the comparison's metric/window and
allocation at assignment, and actual produced or sent text in the task's
progress/result evidence. This measurement provenance does not freeze task
definitions. Report assigned counts, verified sends
where relevant, matured observation counts and successes by variant. For the
primary comparison, count all assigned participants whose observation window
has matured; a failure to send is visible and remains in that denominator.
Do not silently analyze only successful sends or count an unfinished window
as a failure. Repeated reads and replies count once per assigned participant
for this binary success metric.

Live editing remains available. A change to prompt content, variants, weights,
offer, task rules or measurement invalidates pooling old and new observations
as one unchanged test. Preserve assignments and evidence, mark the comparison
changed, and require a fresh comparison key for subsequent assignments to be
reported as a new comparison. The key labels measurements; it does not select
or freeze a campaign graph. Existing open Tasks follow live-edit reconciliation
and retain their original assignment; changed exposure is flagged, not silently
relabeled into the new comparison.

An assignment keeps its variant key. Preparation resolves that key's current
prompt mapping; a changed mapping or Prompt version requires the same
live-edit reconciliation as other step edits and is flagged as changed
exposure. Original assignment facts remain available alongside the actual
prompt used. Reading a briefing does not change the stored assignment or
progress; version provenance is returned and submitted with a result.

The first version exposes descriptive counts and rates with their denominators,
observation window and change flags. It does not automatically declare a
winner, stop early based on the current lead or switch allocation toward a
variant. Statistical winner claims need a prespecified analysis and sufficient
sample size; adding A/B/n also requires accounting for multiple comparisons.
See [Statsig experiment configuration](https://docs.statsig.com/statsig-warehouse-native/features/configure-an-experiment)
for primary metrics, observation periods and analysis settings. A separate
experiment service or analytics model is outside this initial module.

### 3. CampaignStepPrompt — specialization of Agent Prompt

This is a domain subtype of the existing fixed-Markdown Agent Prompt. It
inherits `uid`, `name`, `description`, `content_markdown`, version, authorship
and archive behavior. The underlying document remains in the existing Prompt
library; its text is not copied into a second document library.

| Additional field | Type / requirement | Meaning |
| --- | --- | --- |
| `inputs` | List of `{key, type, required, description}` | Named context values expected by this prompt. Keys are unique. |
| `result_fields` | List of `{key, type, required, description}` | Business fields expected in the task's structured result. Keys are unique. |

Initial value types are `string`, `boolean`, `number`, `datetime`, `object`
and `array`, with JSON-compatible, bounded values. No executable expressions
or general schema language is needed. The completion envelope always includes
`outcome_key`, `result` and `evidence`; these reserved fields are not repeated
in `result_fields`. Allowed outcomes come from the current Step.

Persist subtype fields as a one-to-one extension of the core Prompt, using the
same UID. Writes to the base document and subtype fields share the Prompt's
version fence and form one governed change. An existing Agent Prompt can be
specialized deliberately while retaining its UID. Ordinary Agent Prompts
remain usable without Campaigns enabled.

An assembled task briefing contains:

1. The current Campaign objective and shared context.
2. The current Step instructions, completion criteria and allowed outcomes.
3. The participant's assigned variant, selected Prompt's current Markdown and declared inputs.
4. Authorized Contact data, participant context and selected prior task results.
5. The actual CRM Task and the permitted outgoing transitions.

`input_bindings` select documented data paths rooted at `campaign`, `contact`,
`participant` or `previous.<step_uid>.result`. They do not execute code or
silently evaluate Jinja in an Agent Prompt. A required input that is absent
blocks preparation with a specific explanation. Optional inputs may be absent.
The service checks that bindings refer to reachable predecessor results and
that declared value types match at preparation time.

The existing Solution Selling Prompter is still a separate message-template
resource. A campaign may reference or use one when that module is available;
Campaigns does not require it for enrollment or graph progression.

### 4. CampaignTransition — an outcome connection

| Field | Type / requirement | Meaning |
| --- | --- | --- |
| `campaign_uid` | Required Campaign UID | Owning graph. |
| `from_step_uid` | Required Step UID | Task definition whose result is evaluated. |
| `outcome_key` | Required source Step outcome key | Exact completed outcome that selects this connection. |
| `to_step_uid` | Nullable Step UID | Next task definition; null explicitly finishes this participant's path. |
| `delay_seconds` | Nonnegative integer; default `0` | Delay after the source result before the next task becomes eligible. Must be zero for a finish connection. |

All endpoints belong to the same Campaign. There is exactly one connection
per declared outcome before activation, including explicit finish connections.
This makes routing deterministic without priorities, arbitrary predicates or
an expression interpreter. Business conditions are assessed by the source
task under its prompt and completion criteria. The engine validates the chosen
outcome and follows its connection; an agent cannot invent a destination UID.

### 5. CampaignParticipant — enrollment and task progress

| Field | Type / requirement | Meaning |
| --- | --- | --- |
| `campaign_uid` | Required Campaign UID | Campaign being followed. |
| `contact_uid` | Required existing Contact UID | Person enrolled; immutable after creation. |
| `status` | `active`, `paused`, `completed`, `withdrawn` | Participant lifecycle, independent of other campaigns for the same person. |
| `context` | Object; default `{}` | Participant-specific campaign values; does not copy the Contact record. |
| `progress` | List of embedded task progress records; default `[]` | The mapping from definitions to actual Tasks and their recorded outcomes. |
| `next_step_uid` | Nullable Step UID; service-owned | The next eligible definition, including the entry step before the first Task exists. |
| `eligible_at` | Nullable offset-aware datetime; service-owned | Earliest time the next task may be created after a delay. |
| `finished_at` | Nullable offset-aware datetime; service-owned | Time of completion or withdrawal. |

There is one enrollment per `(campaign_uid, contact_uid)` in the initial
design. Repeated batches and automatic re-enrollment are outside scope.
Campaign-specific progress does not overwrite the Contact's Solution Selling
Lead state or create a Deal implicitly.

Each embedded progress record has the following fields:

| Field | Type / requirement | Meaning |
| --- | --- | --- |
| `step_uid` | Required Step UID | Stable definition identity, unique within this participant. |
| `task_uid` | Required existing CRM Task UID | Concrete task instance; belongs to this participant's Contact and cannot be shared with another progress record. |
| `prompt_assignment` | Required embedded `{variant_key, prompt_uid, assigned_prompt_version, assigned_at, comparison?, comparison_changed}` | Selection made at Task creation, including for a single prompt. Optional `comparison` retains the PromptComparison fields and variant allocation at assignment. Assignment facts are immutable; the service marks changed comparisons. Actual preparation follows the current mapping for the same variant key. |
| `state` | `open`, `waiting`, `blocked`, `completed`, `cancelled` | Campaign progression state. Task text, owner, due date and completion metadata remain on the core Task. |
| `outcome_key` | Nullable string | Validated business outcome once completed. |
| `result` | Object; default `{}` | Actual business outputs conforming to the prepared prompt's result fields. |
| `evidence` | List of `{summary, resource_type?, resource_uid?}` | Observed or user-reported facts, optionally referencing an authorized CRM record. No private model reasoning. |
| `wake_at` | Nullable offset-aware datetime | When a waiting task should next be considered. |
| `blocked_reason` | Nullable string | Actionable missing input, stale briefing, permission or external-operation failure. |
| `prepared_with` | Nullable `{campaign_version, step_version, prompt_uid, prompt_version}` | Provenance submitted with the latest accepted result or reconciliation. Preparation returns this value without writing it; it never selects an old graph or prompt for future work. |
| `completed_at` | Nullable offset-aware datetime | Time the module accepted the outcome and settled progression. |

This value object supplies the association and result needed for the existing
Task. It is not a new task system, an agent transcript or a separately managed
CampaignStepExecution. Participant version checks protect progress updates.

## Execution and completion

1. Enroll an existing Contact. Activation requires a valid graph and schedules
   its entry step for that participant. Reading a campaign never enrolls anyone.
2. When eligible, assign the prompt variant, then create the existing CRM Task
   and its progress entry together through one governed command. Enforce one
   instance and one assignment per participant/step, including concurrent calls.
3. Prepare the task briefing from current definitions and authorized data.
   Preparation is read-only. Execution may be manual or delegated to an agent
   using the existing platform runtime; this ADR adds no agent harness.
4. A task may wait, become blocked or produce its result. A real external event
   or an explicit human report supplies facts such as connection acceptance.
   The initial module does not include a LinkedIn delivery or event connector.
5. Complete through a Campaigns command that validates input versions, evidence
   requirements, result types and the allowed outcome. Atomically complete the
   CRM Task, record progress and select the next step/delay or finish.
6. A worker or authorized assistant can advance eligible participants through
   the same command boundary. Delay/wait state survives a process restart.
   Task creation or preparation alone never sends a message.

Core Task completion without a Campaign result must not advance the graph. The
participant remains blocked with `outcome_required` until a valid result is
recorded. Reopening a completed Task does not replay downstream tasks; expose
the inconsistency for reconciliation. Failures resume the existing instance.
After an uncertain external write, read and reconcile the actual outcome
before considering another attempt. There is no claim of exactly-once delivery.

## Live editing and graph invariants

- Save graph edits as one change against the expected Campaign version;
  changes to its Steps and Transitions also advance that version. Prompt edits
  use the Prompt version. No revision entity or historical graph selector is introduced.
- Validate same-campaign references, required prompt variants and their compatible
  contracts, comparison metrics, allocation totals, unique outcome routes,
  one entry, reachability and acyclicity. An incomplete draft may be saved with
  diagnostics, but it cannot run; active edits must leave a runnable graph.
- Stable Step UIDs survive title, prompt and layout edits. Retire referenced
  steps with an archive marker rather than removing identity/history.
- Future preparation and routing use the current graph and prompt. Open work
  affected by edits must refresh its briefing. Completed work and actual
  external effects remain facts; editing never resends them or erases results.
  Removing or archiving an assigned variant/Prompt blocks affected open work
  for explicit reconciliation; it must not silently switch a Contact from A to B.
- Structural edits return affected open Tasks and scheduled next steps. Apply
  the chosen reassignment/cancellation in the same authorized graph-change
  operation, or leave affected participants blocked pending reconciliation.
  Because core Tasks have no cancellation state, cancellation archives the
  open Task and marks its progress cancelled; it never falsely completes it.
- Existing Task text, owner and due time are instance values. Editing their
  defaults affects newly created Tasks. Updating open instances is an explicit
  part of the edit's impact selection, with their existing version checks.
- If a definition changes during agent work, preserve any reported real effects
  and block automatic advancement for reconciliation against the current
  graph. Never discard an actual send or replay it to match a changed prompt.
- Completed participants remain completed until an explicit future design for
  resumption is approved. Editing a campaign does not restart them.

## Example and visual designer

All boxes below are task definitions with a prompt. Edge labels are outcomes.
"Finish" is a participant lifecycle result, not an extra task model.

```text
[Prepare and send connection request]
                  | sent
                  v
       [Await connection acceptance]
           | accepted          | expired -> Finish
           v
 [Prepare and send pricing + GPU offer]
                  | sent
                  v
        [Await and assess response]
           | interested -> [Arrange demo] ---------> Finish
           | question   -> [Prepare and send answer] -> Finish
           | no_reply   -> [Send one follow-up] ----> Finish
           | declined -----------------------------> Finish
```

The designer reads and writes these same models. A task card exposes its title,
one prompt or A/B alternatives with allocation weights, inputs, task defaults,
completion criteria and outcomes. A/B configuration also selects a success
outcome and observation window. Connections
expose outcome and delay. Layout coordinates are presentation data. A selected
Contact overlays actual Tasks, results, the current position and blocking
reasons without changing the underlying graph. A follow-up sequence is made
of explicit additional task definitions; retrying a failed operation does not
add a cycle to the business graph.

## Module, HTTP and MCP requirements

**Everything in this section is required implementation work, not an existing
capability.** Follow the repository's extension convention:
`extensions.campaigns.active` in `config/crm.yaml`, routes below
`/extensions/campaigns/`, and feature discovery controlling navigation and
the advertised MCP catalogue. Disabled modules retain their data.

REST, MCP and the visual designer must call the same shared services, with
verified effective-person authorization and ordinary CRM version fences.
Prompts and task results never grant capabilities. Use existing `crm.read`,
`crm.create`, `crm.update` and `crm.archive` checks as applicable, including
the capabilities needed for related Task/Prompt changes. No manual grants,
new identity store or workload-permission fallback is introduced.

The following is the proposed minimum MCP surface. Names are design targets
until implemented and advertised with exact schemas:

| Tools | Required behavior |
| --- | --- |
| `crm_campaigns_list`, `crm_campaigns_get` | Search campaign summaries; read the complete current graph, validation status and per-step variant counts/rates with their denominators and change flags. |
| `crm_campaigns_create`, `crm_campaigns_update` | Create a draft; edit campaign fields or explicitly change lifecycle with fresh versions. Activation validates the graph. |
| `crm_campaigns_graph_validate` | Read-only validation of a candidate graph, including the impact on current participants and Tasks. |
| `crm_campaigns_graph_update` | Atomically add/edit/retire Steps and Transitions with the expected Campaign version and explicit handling of affected work. |
| `crm_campaign_prompts_list`, `crm_campaign_prompts_get`, `crm_campaign_prompts_create`, `crm_campaign_prompts_update` | Discover, read, create/specialize and edit CampaignStepPrompts using the shared base Prompt identity and version. |
| `crm_campaign_participants_list`, `crm_campaign_participants_get`, `crm_campaign_participants_create`, `crm_campaign_participants_update` | Read per-contact progress; enroll a Contact; update context, pause/resume or withdraw. Progress fields are service-owned. |
| `crm_campaign_tasks_prepare` | Read-only current briefing for an existing participant Task, including its already-assigned prompt variant, context, allowed outcomes and version provenance. Never rerandomizes. |
| `crm_campaign_tasks_advance` | Create the eligible Task and its association once, or return the existing instance; does not execute its work. |
| `crm_campaign_tasks_complete` | Validate a result, settle the existing Task and choose the next step atomically. |

Graph editing covers node and edge CRUD without adding separate tool families
for every embedded value. Read operations need read-only annotations; writes
must expose expected versions and actual business results. A timeout remains
an uncertain write until state is read, including for an advance operation
whose uniqueness guard prevents creating a second Task. Lifecycle rules must
be identical across MCP and the visual designer.

## Required documentation and agent skills

The module is not complete until it includes all of the following in the same
delivery:

1. **User documentation:** campaign meaning, task definition versus instance,
   prompt mapping, creating and editing a DAG, enrolling Contacts, reading
   progress, interpreting waits/decisions, configuring A/B variants and handling
   live edits and their effect on comparisons. Include the
   Dubai example and a visual-design walkthrough in the paired frontend guide.
2. **API and MCP documentation:** mounted routes and exact schemas, model
   fields, feature availability, permissions, version conflicts, validation
   errors, lifecycle commands, outcome submission and uncertain-write recovery.
   Keep proposed behavior clearly separate until its routes/tools are mounted.
3. **A published `crm-campaigns` usage skill:** installed in the API-owned
   `.agents/skills/mainsequence_crm/` usage pack, published by authenticated
   MCP `skills_extension`, and kept identical in the paired frontend pack.
   Update shared guidance and tool allocation so agents discover it.
4. **Skill workflows for create, edit and read:** resolve existing Contacts and
   Prompts; create/specialize a step prompt; construct and validate task nodes
   and outcome connections; configure one prompt or A/B allocation and the
   success metric; save and inspect successful results; edit with
   current versions and explain affected work; read a graph and a Contact's
   actual Tasks/results without causing progression as a side effect.
5. **Skill workflows for execution:** enroll only when requested; prepare the
   current task; use its assigned prompt variant and input contract; distinguish drafts,
   actual events and Task completion; submit an allowed outcome with evidence;
   read back progression; reconcile stale briefings and uncertain writes.
   Read variant counts and rates with observation windows; never pick variants
   manually or announce an unsupported winner from a small or changed sample.
6. **Delivery documentation:** migrations, module enablement, durable wake-up
   behavior and verification results. Hosted schema changes use the existing
   automatic migration Job and workflow.

The Campaigns skill must explain how it composes with `crm-core` and optional
Solution Selling skills. Its instructions cannot invent tools, send permission,
successful delivery or a new route. Do not publish an operational Campaigns
skill while its advertised tools are absent.

## Acceptance criteria for implementation

- The graph and all five model contracts can be created, edited and read via
  both the UI and the documented MCP/shared service boundary.
- Every instantiated step has one existing Contact Task and a required prompt;
  duplicate enrollment or concurrent advance cannot create duplicate instances.
- Single-prompt and A/B assignment work through the same model. Concurrent
  creation, preparation and restart preserve a Contact's assigned variant.
  Invalid allocations or incompatible prompt contracts fail validation.
- Comparison results retain every assignment, use the declared metric and equal
  observation windows, flag changed exposures/configuration, and never pool
  different comparison keys or claim an automatic statistical winner.
- A real two-contact example follows different outcome paths without mixing
  context, results or Task references. Waiting work survives a restart.
- Invalid cycles, missing outcomes, cross-campaign edges, missing required
  inputs and unsupported result types fail with useful validation errors.
- Live graph/prompt edits affect subsequent preparation, preserve completed
  results and expose affected active work. No frozen campaign plan is used.
- Task/result/next-step changes and association creation pass governed atomic
  command tests and fresh-process catalog binding checks.
- Core completion without an outcome, task reopening, permission loss and an
  uncertain external action cannot silently advance or duplicate outreach.
- Module-off/on contracts, authenticated MCP tools, skill publication and the
  identical usage packs are verified. Strict MkDocs and documentation tests pass.
- Release gates include the repository's real-agent check. Any claimed hosted
  campaign execution is verified against persisted Task/result state; local or
  mocked checks alone are not deployment evidence.

## Review boundaries

This proposal deliberately starts with one live campaign graph, explicit
contact enrollment, one current task per participant and outcome-key routing.
It contains no campaign revisions, separate action/decision entities, separate
step-execution identity, generic workflow language, automatic channel delivery,
parallel joins, recurring campaigns or statistical decision engine. A/B uses
embedded variants, assignments and comparison metadata; A/B/n is deferred. Those can be
assessed separately when a concrete use case requires them.

This ADR changes documentation only. It does not enable Campaigns, add runtime
behavior, expose MCP tools, create agent skills or deploy a service.
