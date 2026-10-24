"""Campaign operations shared by REST, MCP and the designer.

Every method rechecks the effective person's capability, validates the
command again, reads current state and then issues one governed write.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from random import Random, SystemRandom
from typing import Any

from pydantic import BaseModel, ValidationError

from ..contracts import DomainValidationError
from ..repositories.campaigns import CampaignStore
from ..repositories.errors import ResourceConflict, ResourceNotFound
from ..repositories.resources.store import GovernedResourceStore
from .briefing import CONTACT_FIELDS, choose_variant, resolve_inputs, validate_result
from .config import campaigns_enabled
from .graph import comparison_changed, layout_only_change, validate_graph
from .models import (
    AdvanceCommand,
    BlockCommand,
    Campaign,
    CampaignCreate,
    CampaignFilters,
    CampaignGraph,
    CampaignPatch,
    CampaignSummary,
    CompleteCommand,
    GraphUpdate,
    GraphValidateRequest,
    GraphValidation,
    Participant,
    ParticipantCreate,
    ParticipantFilters,
    ParticipantPatch,
    PreparedWith,
    ProgressRef,
    ReconcileCommand,
    ReportCommand,
    Step,
    StepFields,
    StepPrompt,
    StepPromptCreate,
    StepPromptFilters,
    StepPromptPatch,
    StepPromptSummary,
    WaitCommand,
)

STEP_FIELDS = tuple(StepFields.model_fields)
ALLOWED_STATUS = {
    "draft": {"active"},
    "active": {"paused", "completed"},
    "paused": {"active", "completed"},
    "completed": set(),
}


def _invalid(path: str, code: str = "invalid", message: str = "Invalid value") -> DomainValidationError:
    return DomainValidationError([{"path": path, "code": code, "message": message}])


def _validated(model: type[BaseModel], payload: BaseModel | dict[str, Any]):
    try:
        source = payload.model_dump(mode="json", exclude_unset=True) if isinstance(payload, BaseModel) else payload
        return model.model_validate(source)
    except (ValidationError, TypeError, ValueError) as exc:
        raise DomainValidationError([{"path": "payload", "code": "invalid", "message": "Invalid value"}]) from exc


class CampaignOperations:
    def __init__(self, context, *, store: CampaignStore | None = None,
                 resources: GovernedResourceStore | None = None, rng: Random | None = None,
                 clock=None) -> None:
        self.context = context
        self.store = store if store is not None else CampaignStore()
        self.resources = resources if resources is not None else GovernedResourceStore()
        self.rng = rng or SystemRandom()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ----- helpers ---------------------------------------------------------

    def _require(self, *capabilities: str) -> None:
        from ..services.operations import ServiceUnavailable

        if not campaigns_enabled():
            raise ServiceUnavailable("Campaigns module is disabled")
        for capability in capabilities:
            self.context.require(capability)

    def _owner(self, owner_uid: uuid.UUID | str | None) -> None:
        if owner_uid is None:
            return
        try:
            owner = uuid.UUID(str(owner_uid))
        except (TypeError, ValueError) as exc:
            raise _invalid("owner_uid") from exc
        if not self.context.directory.is_selectable(owner):
            raise _invalid("owner_uid")

    @staticmethod
    def _page(page_index: int, page_size: int, search: str | None) -> None:
        if page_index < 0 or not 1 <= page_size <= 100:
            raise _invalid("page")
        if search is not None and len(search) > 255:
            raise _invalid("search")

    def _graph_of(self, detail: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], CampaignGraph]:
        """Current graph as (step rows by uid, CampaignGraph of active steps)."""
        steps = {str(row["uid"]): row for row in detail["steps"]}
        graph = CampaignGraph.model_validate({
            "entry_step_uid": detail.get("entry_step_uid"),
            "steps": [
                {**{key: row[key] for key in STEP_FIELDS}, "uid": row["uid"], "archived": row["archived_at"] is not None}
                for row in detail["steps"] if row["archived_at"] is None
            ],
            "transitions": [
                {key: row[key] for key in ("uid", "from_step_uid", "outcome_key", "to_step_uid", "delay_seconds")}
                for row in detail["transitions"]
            ],
        })
        return steps, graph

    def _validation(self, graph: CampaignGraph) -> GraphValidation:
        uids = sorted({variant.prompt_uid for step in graph.steps if not step.archived for variant in step.prompt_variants}, key=str)
        prompts = self.store.step_prompts_by_uid(uids)
        return validate_graph(graph, {uuid.UUID(uid): data for uid, data in prompts.items()})

    def _campaign(self, uid: uuid.UUID) -> dict[str, Any]:
        detail = self.store.campaign_detail(uid)
        _, graph = self._graph_of(detail)
        detail["validation"] = self._validation(graph).model_dump(mode="json")
        detail["comparisons"] = self._comparisons(detail)
        return Campaign.model_validate(detail).model_dump(mode="json")

    def _comparisons(self, detail: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.store.comparisons(uuid.UUID(str(detail["uid"])))
        steps = {str(row["uid"]): row for row in detail["steps"]}
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            step = steps.get(str(row["step_uid"])) or {}
            current = step.get("prompt_comparison") or {}
            key = (str(row["step_uid"]), str(row["comparison_key"]))
            group = groups.setdefault(key, {
                "step_uid": str(row["step_uid"]),
                "comparison_key": str(row["comparison_key"]),
                "current": current.get("key") == row["comparison_key"],
                "control_variant_key": current.get("control_variant_key"),
                "metric_step_uid": current.get("metric_step_uid"),
                "success_outcome_keys": list(current.get("success_outcome_keys", [])),
                "observation_window_seconds": current.get("observation_window_seconds"),
                "variants": [],
            })
            matured, successes = int(row["matured"]), int(row["successes"])
            group["variants"].append({
                "variant_key": str(row["variant_key"]), "assigned": int(row["assigned"]),
                "completed": int(row["completed"]), "cancelled": int(row["cancelled"]), "matured": matured,
                "successes": successes, "success_rate": None if matured == 0 else successes / matured,
                "changed_exposures": int(row["changed_exposures"]),
            })
        return list(groups.values())

    # ----- campaigns -------------------------------------------------------

    def list_campaigns(self, *, page_index: int, page_size: int, search: str | None, filters: dict[str, Any]) -> dict[str, Any]:
        self._require("crm.read")
        self._page(page_index, page_size, search)
        validated = _validated(CampaignFilters, filters).model_dump(mode="json", exclude_none=True)
        result = self.store.campaign_collection(page_index=page_index, page_size=page_size, search=search, filters=validated)
        result["items"] = [CampaignSummary.model_validate(item).model_dump(mode="json") for item in result["items"]]
        return result

    def get_campaign(self, uid: uuid.UUID) -> dict[str, Any]:
        self._require("crm.read")
        return self._campaign(uid)

    def create_campaign(self, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        self._require("crm.create")
        data = _validated(CampaignCreate, payload)
        self._owner(data.owner_uid)
        created = self.store.create_campaign(self.context.actor_uid, data.model_dump(mode="json"))
        return self._campaign(uuid.UUID(str(created["uid"])))

    def update_campaign(self, uid: uuid.UUID, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        self._require("crm.edit")
        patch = _validated(CampaignPatch, payload)
        changes = patch.changes.model_dump(mode="json", exclude_unset=True)
        self._owner(changes.get("owner_uid"))
        current = self.store.campaign_detail(uid)
        if current["version"] != patch.expected_version:
            raise ResourceConflict("Campaign version precondition failed")
        if "status" in changes:
            target = changes["status"]
            if target not in ALLOWED_STATUS[current["status"]]:
                raise _invalid("changes.status", "lifecycle", "Invalid value")
            if target == "active":
                _, graph = self._graph_of(current)
                validation = self._validation(graph)
                if not validation.runnable:
                    raise DomainValidationError([
                        {"path": "graph", "code": item.code, "message": item.message}
                        for item in validation.diagnostics
                    ])
        self.store.update_campaign(self.context.actor_uid, uid, patch.expected_version, changes)
        return self._campaign(uid)

    def archive_campaign(self, uid: uuid.UUID, expected_version: int, *, archived: bool) -> dict[str, Any]:
        self._require("crm.archive")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            raise _invalid("expected_version")
        self.store.archive_campaign(self.context.actor_uid, uid, expected_version, archived)
        return self._campaign(uid)

    # ----- graph -----------------------------------------------------------

    def _graph_change(self, current: dict[str, Any], graph: CampaignGraph) -> dict[str, Any]:
        """Compare the candidate with the stored graph; returns the write plan."""
        current_steps = {str(row["uid"]): row for row in current["steps"]}
        current_transitions = {str(row["uid"]): row for row in current["transitions"]}
        upserts, layout, changed, retired, compared = [], [], [], [], []
        seen = set()
        for step in graph.steps:
            key = str(step.uid)
            seen.add(key)
            after = step.model_dump(mode="json", exclude={"uid", "archived"})
            before_row = current_steps.get(key)
            payload = {**after, "uid": key, "archived": step.archived}
            if before_row is None:
                if step.archived:
                    raise _invalid("graph.steps", "retire_unknown", "Invalid value")
                upserts.append(payload)
                continue
            before = Step.model_validate(before_row).model_dump(mode="json", include=set(STEP_FIELDS))
            was_archived = before_row["archived_at"] is not None
            if step.archived:
                if not was_archived:
                    retired.append(step.uid)
                    upserts.append(payload)
                continue
            if was_archived:
                raise _invalid("graph.steps", "retired_step_restore", "Invalid value")
            if before == after:
                continue
            if layout_only_change(before, after):
                layout.append({"uid": key, "position": after["position"]})
                continue
            upserts.append(payload)
            changed.append(step.uid)
            if comparison_changed(before, after):
                compared.append(step.uid)
        missing = [uid for uid, row in current_steps.items() if row["archived_at"] is None and uid not in seen]
        if missing:
            raise DomainValidationError([
                {"path": "graph.steps", "code": "step_missing", "message": "Invalid value"} for _ in missing
            ])
        transition_upserts = []
        for transition in graph.transitions:
            after = transition.model_dump(mode="json")
            before_row = current_transitions.get(str(transition.uid))
            if before_row is not None and all(str(before_row[k]) == str(after[k]) if after[k] is not None else before_row[k] is None
                                              for k in ("from_step_uid", "outcome_key", "to_step_uid", "delay_seconds")):
                continue
            transition_upserts.append(after)
        return {
            "steps": upserts, "layout_steps": layout, "transitions": transition_upserts,
            "kept_transition_uids": [t.uid for t in graph.transitions],
            "changed_step_uids": changed, "retired_step_uids": retired, "comparison_changed_step_uids": compared,
        }

    def validate_candidate_graph(self, uid: uuid.UUID, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        """Read-only diagnostics plus the impact on current participants and Tasks."""
        self._require("crm.read")
        request = _validated(GraphValidateRequest, payload)
        current = self.store.campaign_detail(uid)
        validation = self._validation(request.graph)
        plan = self._graph_change(current, request.graph)
        affected = sorted({*plan["changed_step_uids"], *plan["retired_step_uids"]}, key=str)
        impact = self.store.graph_impact(uid, affected_step_uids=affected, retired_step_uids=plan["retired_step_uids"])
        return {
            "campaign_uid": str(uid), "campaign_version": current["version"],
            "validation": validation.model_dump(mode="json"),
            "changes": {
                "steps": len(plan["steps"]), "layout_steps": len(plan["layout_steps"]), "transitions": len(plan["transitions"]),
                "changed_step_uids": [str(u) for u in plan["changed_step_uids"]],
                "retired_step_uids": [str(u) for u in plan["retired_step_uids"]],
                "comparison_changed_step_uids": [str(u) for u in plan["comparison_changed_step_uids"]],
            },
            "impact": impact,
        }

    def update_graph(self, uid: uuid.UUID, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        self._require("crm.edit")
        command = _validated(GraphUpdate, payload)
        if command.affected_open_work == "cancel":
            self._require("crm.archive")
        current = self.store.campaign_detail(uid)
        if current["version"] != command.expected_version:
            raise ResourceConflict("Campaign version precondition failed")
        for step in command.graph.steps:
            self._owner(step.owner_uid)
        validation = self._validation(command.graph)
        if current["status"] in {"active", "paused"} and not validation.runnable:
            # Live campaigns must stay runnable; drafts may save diagnostics.
            raise DomainValidationError([
                {"path": "graph", "code": item.code, "message": item.message} for item in validation.diagnostics
            ])
        plan = self._graph_change(current, command.graph)
        self.store.save_graph(
            self.context.actor_uid, uid, command.expected_version,
            entry_step_uid=command.graph.entry_step_uid, steps=plan["steps"], layout_steps=plan["layout_steps"],
            transitions=plan["transitions"],
            kept_transition_uids=plan["kept_transition_uids"], changed_step_uids=plan["changed_step_uids"],
            retired_step_uids=plan["retired_step_uids"], comparison_changed_step_uids=plan["comparison_changed_step_uids"],
            cancel_retired_work=command.affected_open_work == "cancel",
        )
        return self._campaign(uid)

    # ----- step prompts ----------------------------------------------------

    def list_step_prompts(self, *, page_index: int, page_size: int, search: str | None, filters: dict[str, Any]) -> dict[str, Any]:
        self._require("crm.read")
        self._page(page_index, page_size, search)
        validated = _validated(StepPromptFilters, filters).model_dump(mode="json", exclude_none=True)
        result = self.store.step_prompt_collection(page_index=page_index, page_size=page_size, search=search, filters=validated)
        result["items"] = [StepPromptSummary.model_validate(item).model_dump(mode="json") for item in result["items"]]
        return result

    def get_step_prompt(self, uid: uuid.UUID) -> dict[str, Any]:
        self._require("crm.read")
        return StepPrompt.model_validate(self.store.step_prompt_detail(uid)).model_dump(mode="json")

    def create_step_prompt(self, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        command = _validated(StepPromptCreate, payload)
        data = command.model_dump(mode="json", exclude_unset=True)
        if command.prompt_uid is not None:
            self._require("crm.edit")
            item = self.store.specialize_prompt(self.context.actor_uid, command.prompt_uid, command.expected_version, data)
        else:
            self._require("crm.create")
            item = self.store.create_step_prompt(self.context.actor_uid, data)
        return StepPrompt.model_validate(item).model_dump(mode="json")

    def update_step_prompt(self, uid: uuid.UUID, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        self._require("crm.edit")
        patch = _validated(StepPromptPatch, payload)
        changes = patch.changes.model_dump(mode="json", exclude_unset=True)
        item = self.store.update_step_prompt(self.context.actor_uid, uid, patch.expected_version, changes)
        return StepPrompt.model_validate(item).model_dump(mode="json")

    # ----- participants ----------------------------------------------------

    def list_participants(self, *, page_index: int, page_size: int, search: str | None, filters: dict[str, Any]) -> dict[str, Any]:
        self._require("crm.read")
        self._page(page_index, page_size, search)
        validated = _validated(ParticipantFilters, filters).model_dump(mode="json", exclude_none=True)
        result = self.store.participant_collection(page_index=page_index, page_size=page_size, search=search, filters=validated)
        result["items"] = [Participant.model_validate(item).model_dump(mode="json") for item in result["items"]]
        return result

    def get_participant(self, uid: uuid.UUID) -> dict[str, Any]:
        self._require("crm.read")
        return Participant.model_validate(self.store.participant_detail(uid)).model_dump(mode="json")

    def create_participant(self, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        self._require("crm.create")
        data = _validated(ParticipantCreate, payload)
        campaign = self.store.campaign_detail(data.campaign_uid)
        if campaign["archived_at"] is not None or campaign["status"] == "completed":
            raise _invalid("campaign_uid", "lifecycle")
        item = self.store.create_participant(self.context.actor_uid, data.model_dump(mode="json"))
        return Participant.model_validate(item).model_dump(mode="json")

    def update_participant(self, uid: uuid.UUID, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        self._require("crm.edit")
        patch = _validated(ParticipantPatch, payload)
        changes = patch.changes.model_dump(mode="json", exclude_unset=True)
        if changes.get("status") == "withdrawn":
            self._require("crm.archive")
        current = self.store.participant_detail(uid)
        if current["status"] in {"completed", "withdrawn"}:
            raise _invalid("changes.status", "lifecycle")
        if "next_step_uid" in changes and changes["next_step_uid"] is None:
            raise _invalid("changes.next_step_uid")
        item = self.store.update_participant(self.context.actor_uid, uid, patch.expected_version, changes)
        return Participant.model_validate(item).model_dump(mode="json")

    # ----- progression -----------------------------------------------------

    @staticmethod
    def _progress(participant: dict[str, Any], step_uid: uuid.UUID) -> dict[str, Any] | None:
        return next((item for item in participant["progress"] if str(item["step_uid"]) == str(step_uid)), None)

    @staticmethod
    def _step(campaign: dict[str, Any], step_uid: uuid.UUID) -> dict[str, Any] | None:
        return next((row for row in campaign["steps"] if str(row["uid"]) == str(step_uid)), None)

    def advance(self, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        """Create the eligible Task once, or return the existing instance. Never executes work."""
        self._require("crm.create", "crm.edit")
        command = _validated(AdvanceCommand, payload)
        participant = self.store.participant_detail(command.participant_uid)
        if participant["version"] != command.expected_version:
            raise ResourceConflict("Participant version precondition failed")
        if participant["status"] != "active":
            raise _invalid("participant_uid", "lifecycle")
        step_uid = participant["next_step_uid"]
        if step_uid is None:
            raise _invalid("participant_uid", "nothing_scheduled")
        existing = self._progress(participant, step_uid)
        if existing is not None:
            if existing["state"] in {"completed", "cancelled"}:
                raise _invalid("next_step_uid", "step_already_visited")
            return {"created": False, "participant": Participant.model_validate(participant).model_dump(mode="json")}
        eligible_at = participant.get("eligible_at")
        if eligible_at and datetime.fromisoformat(str(eligible_at).replace("Z", "+00:00")) > self.clock():
            raise _invalid("participant_uid", "not_yet_eligible")
        campaign = self.store.campaign_detail(participant["campaign_uid"])
        if campaign["status"] != "active" or campaign["archived_at"] is not None:
            raise _invalid("campaign_uid", "lifecycle")
        row = self._step(campaign, step_uid)
        if row is None or row["archived_at"] is not None:
            raise _invalid("next_step_uid", "step_retired")
        step = Step.model_validate(row)
        variant = choose_variant(step.prompt_variants, self.rng)
        prompts = self.store.step_prompts_by_uid([variant.prompt_uid])
        prompt = prompts.get(str(variant.prompt_uid))
        if prompt is None or prompt["archived"]:
            raise _invalid("prompt_uid", "prompt_unavailable")
        assignment = {
            "variant_key": variant.key, "prompt_uid": str(variant.prompt_uid),
            "assigned_prompt_version": prompt["version"], "assigned_at": self.clock().isoformat(),
            "comparison": None if step.prompt_comparison is None else {
                **step.prompt_comparison.model_dump(mode="json"),
                "allocation": {v.key: v.allocation_percent for v in step.prompt_variants},
            },
            "comparison_changed": False,
        }
        try:
            updated = self.store.advance(
                self.context.actor_uid, command.participant_uid, command.expected_version,
                step_uid=step.uid, step_version=step.version, prompt_assignment=assignment,
            )
        except ResourceConflict:
            # A concurrent advance may have created the instance; the uniqueness
            # guard means at most one exists. Read before reporting.
            latest = self.store.participant_detail(command.participant_uid)
            if self._progress(latest, step_uid) is not None:
                return {"created": False, "participant": Participant.model_validate(latest).model_dump(mode="json")}
            raise
        return {"created": True, "participant": Participant.model_validate(updated).model_dump(mode="json")}

    def _context(self, ref: ProgressRef) -> dict[str, Any]:
        participant = self.store.participant_detail(ref.participant_uid)
        progress = self._progress(participant, ref.step_uid)
        if progress is None:
            raise ResourceNotFound("Campaign task not found for this participant and step")
        campaign = self.store.campaign_detail(participant["campaign_uid"])
        step_row = self._step(campaign, ref.step_uid)
        if step_row is None:
            raise ResourceNotFound("Campaign step not found")
        return {"participant": participant, "progress": progress, "campaign": campaign, "step_row": step_row}

    def _current_prompt(self, step_row: dict[str, Any], assignment: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
        """Resolve the assigned variant key through the step's current mapping."""
        variant = next((v for v in step_row["prompt_variants"] if v["key"] == assignment["variant_key"]), None)
        if variant is None:
            return None, [{"code": "variant_removed", "message": "The assigned variant no longer exists on this step"}]
        try:
            prompt = self.store.step_prompt_detail(uuid.UUID(str(variant["prompt_uid"])))
        except ResourceNotFound:
            return None, [{"code": "prompt_missing", "message": "The assigned variant's prompt is unavailable"}]
        if prompt.get("archived_at") is not None:
            return prompt, [{"code": "prompt_archived", "message": "The assigned variant's prompt is archived"}]
        return prompt, []

    def prepare(self, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        """Assemble the current briefing. Read-only: never rerandomizes or writes."""
        self._require("crm.read")
        ref = _validated(ProgressRef, payload)
        state = self._context(ref)
        participant, progress, campaign, step_row = state["participant"], state["progress"], state["campaign"], state["step_row"]
        diagnostics: list[dict[str, str]] = []
        if step_row["archived_at"] is not None:
            diagnostics.append({"code": "step_retired", "message": "This step was retired; reconcile the open task"})
        if campaign["status"] != "active":
            diagnostics.append({"code": "campaign_inactive", "message": f"The campaign is {campaign['status']}"})
        prompt, prompt_diagnostics = self._current_prompt(step_row, progress["prompt_assignment"])
        diagnostics.extend(prompt_diagnostics)
        contact = self.resources.detail("contacts", uuid.UUID(str(participant["contact_uid"])))
        previous = {
            str(item["step_uid"]): item["result"] for item in participant["progress"]
            if item["state"] == "completed" and str(item["step_uid"]) != str(ref.step_uid)
        }
        inputs, input_diagnostics = resolve_inputs(
            declared=prompt["inputs"] if prompt else [], bindings=step_row["input_bindings"], campaign=campaign,
            contact=contact, participant=participant, previous_results=previous,
        )
        diagnostics.extend(input_diagnostics)
        assignment = progress["prompt_assignment"]
        changed_exposure = bool(assignment.get("comparison_changed")) or (
            prompt is not None and (
                str(prompt["uid"]) != str(assignment["prompt_uid"])
                or int(prompt["version"]) != int(assignment["assigned_prompt_version"])
            )
        )
        task = self.store.task_version(uuid.UUID(str(progress["task_uid"])))
        prepared_with = None if prompt is None else {
            "campaign_version": campaign["version"], "step_version": step_row["version"],
            "prompt_uid": str(prompt["uid"]), "prompt_version": prompt["version"],
        }
        return {
            "campaign": {key: campaign[key] for key in ("uid", "name", "objective", "context", "status", "version")},
            "step": {key: step_row[key] for key in ("uid", "title", "task_text", "completion_criteria", "outcomes",
                                                    "completion_mode", "input_bindings", "version")},
            "prompt": None if prompt is None else {key: prompt[key] for key in ("uid", "name", "version", "content_markdown", "inputs", "result_fields")},
            "assignment": assignment,
            "changed_exposure": changed_exposure,
            "inputs": inputs,
            "contact": {key: contact.get(key) for key in CONTACT_FIELDS if key in contact},
            "participant": {key: participant[key] for key in ("uid", "version", "status", "context")},
            "previous_results": previous,
            "task": {key: task.get(key) for key in ("uid", "version", "completed_at", "archived_at")},
            "transitions": [
                {key: row[key] for key in ("outcome_key", "to_step_uid", "delay_seconds")}
                for row in campaign["transitions"] if str(row["from_step_uid"]) == str(ref.step_uid)
            ],
            "progress": progress,
            "prepared_with": prepared_with,
            "diagnostics": diagnostics,
            "ready": not diagnostics and progress["state"] in {"open", "waiting"},
        }

    def _validate_completion(self, state: dict[str, Any], *, outcome_key: str, result: dict[str, Any]) -> dict[str, Any]:
        campaign, step_row, progress = state["campaign"], state["step_row"], state["progress"]
        if campaign["status"] != "active" or campaign["archived_at"] is not None:
            raise _invalid("campaign_uid", "lifecycle")
        if step_row["archived_at"] is not None:
            raise _invalid("step_uid", "step_retired")
        if progress["state"] not in {"open", "waiting", "blocked"}:
            raise _invalid("step_uid", "not_open")
        if outcome_key not in {item["key"] for item in step_row["outcomes"]}:
            raise _invalid("outcome_key", "outcome_unknown")
        if not any(str(row["from_step_uid"]) == str(step_row["uid"]) and row["outcome_key"] == outcome_key
                   for row in campaign["transitions"]):
            raise _invalid("outcome_key", "route_missing")
        prompt, diagnostics = self._current_prompt(step_row, progress["prompt_assignment"])
        if prompt is None or diagnostics:
            raise DomainValidationError([{"path": "prompt", "code": d["code"], "message": d["message"]} for d in diagnostics])
        problems = validate_result(result, prompt["result_fields"])
        if problems:
            raise DomainValidationError(problems)
        return {"campaign_version": campaign["version"], "step_version": step_row["version"],
                "prompt_uid": str(prompt["uid"]), "prompt_version": prompt["version"]}

    def complete(self, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        """Accept a result and route, or preserve a stale result for reconciliation."""
        self._require("crm.edit")
        command = _validated(CompleteCommand, payload)
        state = self._context(command)
        if state["participant"]["version"] != command.expected_version:
            raise ResourceConflict("Participant version precondition failed")
        current = self._validate_completion(state, outcome_key=command.outcome_key, result=command.result)
        evidence = [item.model_dump(mode="json") for item in command.evidence]
        if command.prepared_with.model_dump(mode="json") != PreparedWith.model_validate(current).model_dump(mode="json"):
            participant = self.store.record(
                self.context.actor_uid, participant_uid=command.participant_uid, expected_version=command.expected_version,
                step_uid=command.step_uid, kind="stale_result", evidence=evidence, blocked_reason="stale_briefing",
                result=command.result, outcome_key=command.outcome_key,
                prepared_with=command.prepared_with.model_dump(mode="json"),
            )
            return {"accepted": False, "reason": "stale_briefing",
                    "participant": Participant.model_validate(participant).model_dump(mode="json")}
        participant = self.store.complete(
            self.context.actor_uid, participant_uid=command.participant_uid, expected_version=command.expected_version,
            step_uid=command.step_uid, task_uid=uuid.UUID(str(state["progress"]["task_uid"])),
            task_expected_version=command.task_expected_version, campaign_version=current["campaign_version"],
            step_version=current["step_version"], outcome_key=command.outcome_key, result=command.result,
            evidence=evidence, prepared_with=current,
        )
        return {"accepted": True, "participant": Participant.model_validate(participant).model_dump(mode="json")}

    def _record(self, command, *, kind: str, **extra) -> dict[str, Any]:
        state = self._context(command)
        if state["participant"]["version"] != command.expected_version:
            raise ResourceConflict("Participant version precondition failed")
        if state["progress"]["state"] not in {"open", "waiting", "blocked"}:
            raise _invalid("step_uid", "not_open")
        evidence = [item.model_dump(mode="json") for item in command.evidence]
        if len(state["progress"]["evidence"]) + len(evidence) > 50:
            raise _invalid("evidence", "too_many")
        participant = self.store.record(
            self.context.actor_uid, participant_uid=command.participant_uid, expected_version=command.expected_version,
            step_uid=command.step_uid, kind=kind, evidence=evidence, **extra,
        )
        return Participant.model_validate(participant).model_dump(mode="json")

    def wait(self, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        self._require("crm.edit")
        command = _validated(WaitCommand, payload)
        return self._record(command, kind="wait", wake_at=command.wake_at.isoformat())

    def block(self, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        self._require("crm.edit")
        command = _validated(BlockCommand, payload)
        return self._record(command, kind="block", blocked_reason=command.blocked_reason)

    def report(self, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        self._require("crm.edit")
        command = _validated(ReportCommand, payload)
        return self._record(command, kind="report", result=command.result)

    def reconcile(self, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        """Explicitly resolve blocked work against the current graph."""
        self._require("crm.edit")
        command = _validated(ReconcileCommand, payload)
        if command.action == "cancel":
            self._require("crm.archive")
        state = self._context(command)
        participant, progress = state["participant"], state["progress"]
        if participant["version"] != command.expected_version:
            raise ResourceConflict("Participant version precondition failed")
        if progress["state"] not in {"open", "waiting", "blocked"} and not (
            command.action == "reopen" and progress["state"] == "completed"
        ):
            raise _invalid("step_uid", "not_open")
        task = self.store.task_version(uuid.UUID(str(progress["task_uid"])))
        task_version = command.task_expected_version or int(task["version"])
        if command.action == "resume":
            if progress["state"] != "blocked" or not progress.get("outcome_key"):
                raise _invalid("action", "nothing_to_resume")
            if task.get("archived_at") is not None:
                raise _invalid("action", "task_archived")
            current = self._validate_completion(state, outcome_key=progress["outcome_key"], result=progress["result"])
            updated = self.store.complete(
                self.context.actor_uid, participant_uid=command.participant_uid, expected_version=command.expected_version,
                step_uid=command.step_uid, task_uid=uuid.UUID(str(task["uid"])), task_expected_version=task_version,
                campaign_version=current["campaign_version"], step_version=current["step_version"],
                outcome_key=progress["outcome_key"], result=progress["result"], evidence=[], prepared_with=current,
            )
        elif command.action == "reopen":
            updated = self.store.reconcile_reopen(
                self.context.actor_uid, participant_uid=command.participant_uid, expected_version=command.expected_version,
                step_uid=command.step_uid, task_uid=uuid.UUID(str(task["uid"])), task_expected_version=task_version,
            )
        else:
            updated = self.store.reconcile_cancel(
                self.context.actor_uid, participant_uid=command.participant_uid, expected_version=command.expected_version,
                step_uid=command.step_uid, task_uid=uuid.UUID(str(task["uid"])), task_expected_version=task_version,
                next_step_uid=command.next_step_uid, finish=command.finish,
            )
        return Participant.model_validate(updated).model_dump(mode="json")
