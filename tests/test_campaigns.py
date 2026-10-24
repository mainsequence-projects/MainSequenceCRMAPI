"""Campaigns module contracts, graph validation, service rules and transport parity.

Persistence is replaced by an in-memory store here; the governed SQL runs
against a disposable PostgreSQL in ``test_campaign_postgres.py``.
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_mcp_tools import call, rpc

from api.crm.main import create_app
from api.crm.mcp_tools import build_crm_tools
from src.crm.campaigns.briefing import choose_variant, resolve_inputs, validate_result
from src.crm.campaigns.graph import validate_graph
from src.crm.campaigns.models import (
    CampaignGraph,
    GraphTransition,
    PromptVariant,
    ReconcileCommand,
    StepFields,
    StepPromptCreate,
)
from src.crm.campaigns.service import CampaignOperations
from src.crm.contracts import DomainValidationError
from src.crm.repositories.errors import ResourceConflict
from src.crm.services.operations import AccessDenied, CRMContext, ServiceUnavailable

ACTOR = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
AGENT = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
CONTACT = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
PROMPT_A, PROMPT_B = uuid.UUID(int=1), uuid.UUID(int=2)
SEND, AWAIT, OFFER, DEMO = (uuid.UUID(int=n) for n in (11, 12, 13, 14))
NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def step(uid, title, outcomes, *, variants=None, comparison=None, bindings=None, archived=False, position=None):
    return {
        "uid": str(uid), "title": title, "task_text": f"Do: {title}", "completion_criteria": "Evidence recorded",
        "prompt_variants": variants or [{"key": "A", "label": "Only", "prompt_uid": str(PROMPT_A), "allocation_percent": 100}],
        "prompt_comparison": comparison, "outcomes": [{"key": key, "label": key.title()} for key in outcomes],
        "input_bindings": bindings or {}, "archived": archived, "position": position,
    }


def edge(source, outcome, target, delay=0):
    return {"uid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}:{outcome}")), "from_step_uid": str(source),
            "outcome_key": outcome, "to_step_uid": None if target is None else str(target), "delay_seconds": delay}


def dubai_graph(**overrides):
    ab = [
        {"key": "A", "label": "GPU first", "prompt_uid": str(PROMPT_A), "allocation_percent": 50},
        {"key": "B", "label": "Pricing first", "prompt_uid": str(PROMPT_B), "allocation_percent": 50},
    ]
    comparison = {"key": "dubai-offer-copy-1", "control_variant_key": "A", "metric_step_uid": str(DEMO),
                  "success_outcome_keys": ["interested"], "observation_window_seconds": 7 * 86400}
    graph = {
        "entry_step_uid": str(SEND),
        "steps": [
            step(SEND, "Send connection request", ["sent"]),
            step(AWAIT, "Await acceptance", ["accepted", "expired"]),
            step(OFFER, "Send offer", ["sent"], variants=ab, comparison=comparison,
                 bindings={"first_name": "contact.first_name", "offer": "campaign.context.offer"}),
            step(DEMO, "Assess response", ["interested", "declined"],
                 bindings={"previous_offer": f"previous.{OFFER}.result.message"}),
        ],
        "transitions": [
            edge(SEND, "sent", AWAIT), edge(AWAIT, "accepted", OFFER, 3600), edge(AWAIT, "expired", None),
            edge(OFFER, "sent", DEMO), edge(DEMO, "interested", None), edge(DEMO, "declined", None),
        ],
    }
    graph.update(overrides)
    return CampaignGraph.model_validate(graph)


PROMPTS = {
    # One prompt serves several steps, so its inputs are optional where unbound.
    PROMPT_A: {"archived": False, "inputs": [{"key": "first_name", "type": "string", "required": False},
                                             {"key": "offer", "type": "object", "required": False},
                                             {"key": "previous_offer", "type": "string", "required": False}],
               "result_fields": [{"key": "message", "type": "string", "required": True}]},
    PROMPT_B: {"archived": False, "inputs": [{"key": "first_name", "type": "string", "required": False},
                                             {"key": "offer", "type": "object", "required": False},
                                             {"key": "previous_offer", "type": "string", "required": False}],
               "result_fields": [{"key": "message", "type": "string", "required": True}]},
}


def codes(validation):
    return sorted(item.code for item in validation.diagnostics)


def test_dubai_graph_is_runnable_and_edits_are_diagnosed():
    assert validate_graph(dubai_graph(), PROMPTS).runnable
    without_route = dubai_graph()
    without_route.transitions.pop()
    assert "route_missing" in codes(validate_graph(without_route, PROMPTS))
    cyclic = dubai_graph()
    cyclic.transitions[-1] = GraphTransition.model_validate(edge(DEMO, "declined", SEND))
    assert "cycle" in codes(validate_graph(cyclic, PROMPTS))
    duplicated = dubai_graph()
    duplicated.transitions.append(GraphTransition.model_validate({**edge(SEND, "sent", OFFER), "uid": str(uuid.uuid4())}))
    assert "route_duplicate" in codes(validate_graph(duplicated, PROMPTS))
    foreign = dubai_graph()
    foreign.transitions[0] = GraphTransition.model_validate(edge(SEND, "sent", uuid.uuid4()))
    found = codes(validate_graph(foreign, PROMPTS))
    assert "transition_target_invalid" in found and "step_unreachable" in found
    unknown_outcome = dubai_graph()
    unknown_outcome.transitions[0] = GraphTransition.model_validate(edge(SEND, "mailed", AWAIT))
    assert "transition_outcome_unknown" in codes(validate_graph(unknown_outcome, PROMPTS))
    no_entry = dubai_graph(entry_step_uid=None)
    assert "entry_missing" in codes(validate_graph(no_entry, PROMPTS))
    mismatched = {**PROMPTS, PROMPT_B: {**PROMPTS[PROMPT_B], "result_fields": []}}
    assert "variant_contract_mismatch" in codes(validate_graph(dubai_graph(), mismatched))
    archived_prompt = {**PROMPTS, PROMPT_A: {**PROMPTS[PROMPT_A], "archived": True}}
    assert "prompt_archived" in codes(validate_graph(dubai_graph(), archived_prompt))
    assert "prompt_missing" in codes(validate_graph(dubai_graph(), {}))
    bad_binding = dubai_graph()
    bad_binding.steps[0].input_bindings = {"x": f"previous.{DEMO}.result.message", "y": "secrets.token"}
    found = codes(validate_graph(bad_binding, PROMPTS))
    assert "binding_predecessor_unreachable" in found and "binding_invalid" in found
    assert "binding_undeclared" in found
    unreachable_metric = dubai_graph()
    unreachable_metric.steps[2].prompt_comparison.metric_step_uid = SEND
    assert "comparison_metric_unreachable" in codes(validate_graph(unreachable_metric, PROMPTS))


def test_step_contracts_bound_variants_allocations_and_finish_delays():
    base = step(SEND, "Send", ["sent"])
    StepFields.model_validate({k: v for k, v in base.items() if k not in {"uid", "archived"}})
    fields = lambda **changes: {k: v for k, v in {**base, **changes}.items() if k not in {"uid", "archived"}}  # noqa: E731
    with pytest.raises(ValidationError, match="sum to 100"):
        StepFields.model_validate(fields(prompt_variants=[{**base["prompt_variants"][0], "allocation_percent": 60}]))
    two = [{"key": "A", "label": "A", "prompt_uid": str(PROMPT_A), "allocation_percent": 50},
           {"key": "B", "label": "B", "prompt_uid": str(PROMPT_B), "allocation_percent": 50}]
    with pytest.raises(ValidationError, match="comparison"):
        StepFields.model_validate(fields(prompt_variants=two))
    with pytest.raises(ValidationError, match="unique"):
        StepFields.model_validate(fields(outcomes=[{"key": "sent", "label": "1"}, {"key": "sent", "label": "2"}]))
    with pytest.raises(ValidationError, match="finish"):
        GraphTransition.model_validate(edge(SEND, "sent", None, 60))
    with pytest.raises(ValidationError):
        CampaignGraph.model_validate({"steps": [step(SEND, "a", ["x"]), step(SEND, "b", ["y"])]})
    with pytest.raises(ValidationError, match="Reserved"):
        StepPromptCreate(name="p", content_markdown="# p", result_fields=[{"key": "outcome_key", "type": "string"}])
    with pytest.raises(ValidationError):
        StepPromptCreate(prompt_uid=PROMPT_A)  # specialization needs expected_version
    with pytest.raises(ValidationError):
        ReconcileCommand(participant_uid=CONTACT, step_uid=SEND, expected_version=1, action="cancel")


def test_variant_assignment_is_weighted_and_stable_for_a_single_prompt():
    variants = [PromptVariant(key="A", label="A", prompt_uid=PROMPT_A, allocation_percent=25),
                PromptVariant(key="B", label="B", prompt_uid=PROMPT_B, allocation_percent=75)]
    rng = random.Random(7)
    picks = [choose_variant(variants, rng).key for _ in range(2000)]
    assert 0.18 < picks.count("A") / len(picks) < 0.32
    assert choose_variant(variants[:1], random.Random(1)).key == "A"


def test_bindings_resolve_documented_paths_only_and_results_are_typed():
    inputs, diagnostics = resolve_inputs(
        declared=PROMPTS[PROMPT_A]["inputs"] + [{"key": "note", "type": "string", "required": False},
                                               {"key": "prior", "type": "string", "required": True}],
        bindings={"first_name": "contact.first_name", "offer": "campaign.context.offer",
                  "note": "participant.context.note", "prior": f"previous.{SEND}.result.message"},
        campaign={"context": {"offer": {"gpu_hours": 100}}}, contact={"first_name": "Sarah", "secret": "x"},
        participant={"context": {}}, previous_results={str(SEND): {"message": "Hi"}},
    )
    assert inputs == {"first_name": "Sarah", "offer": {"gpu_hours": 100}, "prior": "Hi"}
    assert diagnostics == []
    _, missing = resolve_inputs(declared=[{"key": "x", "type": "string"}], bindings={"x": "contact.secret"},
                                campaign={}, contact={"secret": "x"}, participant={}, previous_results={})
    assert [item["code"] for item in missing] == ["input_missing"]
    _, wrong = resolve_inputs(declared=[{"key": "x", "type": "number"}], bindings={"x": "contact.first_name"},
                              campaign={}, contact={"first_name": "Sarah"}, participant={}, previous_results={})
    assert [item["code"] for item in wrong] == ["input_type"]
    assert validate_result({"message": "ok"}, PROMPTS[PROMPT_A]["result_fields"]) == []
    problems = validate_result({"message": 3, "extra": 1}, PROMPTS[PROMPT_A]["result_fields"])
    assert {item["code"] for item in problems} == {"type", "unknown_field"}


# ----- service with an in-memory store ----------------------------------------


class Policy:
    def __init__(self, *allowed):
        self.allowed = set(allowed)

    def capabilities(self, actor_uid):
        assert actor_uid == ACTOR
        return self.allowed


class Directory:
    def is_selectable(self, uid):
        return uid == ACTOR

    def display_name(self, uid):
        return "Test actor"


class Resources:
    def detail(self, resource, uid):
        assert resource == "contacts"
        return {"uid": str(uid), "display_name": "Sarah Khan", "first_name": "Sarah", "last_name": "Khan",
                "emails": [{"email": "s@example.test", "type": "work"}], "version": 1}


def row(**fields):
    return {"created_at": NOW.isoformat(), "updated_at": NOW.isoformat(), "created_by_uid": str(ACTOR),
            "updated_by_uid": str(ACTOR), "version": 1, "archived_at": None, **fields}


class MemoryStore:
    """Records every write; detail reads return the authored state."""

    def __init__(self):
        self.calls = []
        graph = dubai_graph()
        self.campaign = row(uid=str(uuid.UUID(int=99)), name="Dubai LinkedIn outreach", objective="# Win pilots",
                            owner_uid=str(ACTOR), context={"offer": {"gpu_hours": 100, "discount": "20%"}},
                            status="active", entry_step_uid=str(SEND), participant_counts={"active": 1})
        self.steps = [row(**s.model_dump(mode="json", exclude={"archived"}), campaign_uid=self.campaign["uid"])
                      for s in graph.steps]
        self.transitions = [row(**t.model_dump(mode="json"), campaign_uid=self.campaign["uid"]) for t in graph.transitions]
        self.prompts = {str(uid): {**PROMPTS[uid], "version": 3} for uid in PROMPTS}
        self.participant = row(uid=str(uuid.UUID(int=77)), campaign_uid=self.campaign["uid"], contact_uid=str(CONTACT),
                               contact_display_name="Sarah Khan", status="active", context={"note": "VIP"}, progress=[],
                               next_step_uid=str(SEND), eligible_at=NOW.isoformat(), finished_at=None)
        self.task = {"uid": str(uuid.UUID(int=55)), "version": 1, "completed_at": None, "archived_at": None}

    def campaign_detail(self, uid):
        return {**self.campaign, "steps": [dict(s) for s in self.steps], "transitions": [dict(t) for t in self.transitions]}

    def comparisons(self, uid):
        return []

    def step_prompts_by_uid(self, uids):
        return {str(uid): self.prompts[str(uid)] for uid in uids if str(uid) in self.prompts}

    def step_prompt_detail(self, uid):
        data = self.prompts[str(uid)]
        return row(uid=str(uid), name="Prompt", description=None, content_markdown="# Prompt body", version=data["version"],
                   inputs=data["inputs"], result_fields=data["result_fields"])

    def participant_detail(self, uid):
        return json.loads(json.dumps(self.participant))

    def task_version(self, uid):
        return dict(self.task)

    def graph_impact(self, uid, **kwargs):
        self.calls.append(("graph_impact", kwargs))
        return {"open_work_count": 0, "open_work": [], "scheduled_to_retired_count": 0, "scheduled_to_retired": []}

    def __getattr__(self, name):
        def write(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "advance":
                self.participant["progress"].append({
                    "step_uid": kwargs["step_uid"] if isinstance(kwargs["step_uid"], str) else str(kwargs["step_uid"]),
                    "task_uid": self.task["uid"], "prompt_assignment": kwargs["prompt_assignment"], "state": "open",
                    "outcome_key": None, "result": {}, "evidence": [], "wake_at": None, "blocked_reason": None,
                    "prepared_with": None, "completed_at": None, "created_at": NOW.isoformat(), "updated_at": NOW.isoformat(),
                })
                self.participant["version"] += 1
            if name in {"record", "complete", "update_participant", "reconcile_reopen", "reconcile_cancel"}:
                self.participant["version"] += 1
            if name == "create_campaign":
                return {"uid": self.campaign["uid"]}
            if name in {"save_graph", "update_campaign", "archive_campaign"}:
                return self.campaign_detail(None)
            return self.participant_detail(None)
        return write


def operations(*capabilities, store=None, rng=None):
    context = CRMContext(actor_uid=ACTOR, policy=Policy(*capabilities), directory=Directory())
    return CampaignOperations(context, store=store or MemoryStore(), resources=Resources(),
                              rng=rng or random.Random(3), clock=lambda: NOW + timedelta(seconds=1))


def test_service_requires_capabilities_and_module_activation(config_file):
    ops = operations("crm.read")
    with pytest.raises(AccessDenied):
        ops.create_campaign({"name": "x", "objective": "# y", "owner_uid": str(ACTOR)})
    with pytest.raises(AccessDenied):
        ops.advance({"participant_uid": str(uuid.UUID(int=77)), "expected_version": 1})
    assert ops.get_campaign(uuid.UUID(int=99))["validation"]["runnable"] is True
    config_file(campaigns=False)
    with pytest.raises(ServiceUnavailable):
        ops.get_campaign(uuid.UUID(int=99))


def test_advance_assigns_once_prepares_read_only_and_completes_with_provenance():
    store = MemoryStore()
    ops = operations("crm.read", "crm.create", "crm.edit", store=store)
    first = ops.advance({"participant_uid": store.participant["uid"], "expected_version": 1})
    assert first["created"] is True
    (name, _args, kwargs), = [c for c in store.calls if c[0] == "advance"]
    assignment = kwargs["prompt_assignment"]
    assert assignment["variant_key"] == "A" and assignment["assigned_prompt_version"] == 3
    assert assignment["comparison"] is None and kwargs["step_version"] == 1
    # The same instance is returned without a second write.
    again = ops.advance({"participant_uid": store.participant["uid"], "expected_version": 2})
    assert again["created"] is False and len([c for c in store.calls if c[0] == "advance"]) == 1
    briefing = ops.prepare({"participant_uid": store.participant["uid"], "step_uid": str(SEND)})
    assert briefing["ready"] is True and briefing["prompt"]["content_markdown"] == "# Prompt body"
    assert briefing["prepared_with"] == {"campaign_version": 1, "step_version": 1, "prompt_uid": str(PROMPT_A), "prompt_version": 3}
    assert briefing["transitions"] == [{"outcome_key": "sent", "to_step_uid": str(AWAIT), "delay_seconds": 0}]
    assert "secret" not in briefing["contact"] and briefing["contact"]["first_name"] == "Sarah"
    assert not [c for c in store.calls if c[0] not in {"advance", "graph_impact"}], "preparation never writes"
    command = {
        "participant_uid": store.participant["uid"], "step_uid": str(SEND), "expected_version": 2,
        "task_expected_version": 1, "outcome_key": "sent", "result": {"message": "Sent on LinkedIn"},
        "evidence": [{"summary": "Connection request sent", "resource_type": "task", "resource_uid": store.task["uid"]}],
        "prepared_with": briefing["prepared_with"],
    }
    accepted = ops.complete(command)
    assert accepted["accepted"] is True
    complete_call = [c for c in store.calls if c[0] == "complete"][-1][2]
    assert complete_call["outcome_key"] == "sent" and complete_call["campaign_version"] == 1
    # A stale briefing preserves the reported effect but never routes.
    stale = ops.complete({**command, "expected_version": 3, "prepared_with": {**briefing["prepared_with"], "step_version": 9}})
    assert stale == {"accepted": False, "reason": "stale_briefing", "participant": stale["participant"]}
    recorded = [c for c in store.calls if c[0] == "record"][-1][2]
    assert recorded["kind"] == "stale_result" and recorded["blocked_reason"] == "stale_briefing"
    assert recorded["result"] == {"message": "Sent on LinkedIn"}
    with pytest.raises(DomainValidationError):
        ops.complete({**command, "expected_version": 4, "outcome_key": "accepted"})
    with pytest.raises(DomainValidationError):
        ops.complete({**command, "expected_version": 4, "result": {"message": 5}})
    with pytest.raises(ResourceConflict):
        ops.complete({**command, "expected_version": 1})


def test_ab_assignment_is_persisted_with_comparison_facts_and_preparation_follows_mapping():
    store = MemoryStore()
    store.participant["next_step_uid"] = str(OFFER)
    ops = operations("crm.read", "crm.create", "crm.edit", store=store, rng=random.Random(5))
    ops.advance({"participant_uid": store.participant["uid"], "expected_version": 1})
    assignment = store.participant["progress"][0]["prompt_assignment"]
    assert assignment["variant_key"] in {"A", "B"}
    assert assignment["comparison"]["key"] == "dubai-offer-copy-1"
    assert assignment["comparison"]["allocation"] == {"A": 50, "B": 50}
    # A later prompt edit shows as changed exposure without rewriting the assignment.
    store.prompts[assignment["prompt_uid"]]["version"] = 4
    briefing = ops.prepare({"participant_uid": store.participant["uid"], "step_uid": str(OFFER)})
    assert briefing["changed_exposure"] is True
    assert briefing["assignment"] == assignment
    assert briefing["inputs"] == {"first_name": "Sarah", "offer": {"gpu_hours": 100, "discount": "20%"}}
    # Removing the assigned variant blocks preparation with a specific explanation.
    store.steps[2]["prompt_variants"] = [v for v in store.steps[2]["prompt_variants"] if v["key"] != assignment["variant_key"]]
    blocked = ops.prepare({"participant_uid": store.participant["uid"], "step_uid": str(OFFER)})
    assert blocked["ready"] is False and "variant_removed" in {d["code"] for d in blocked["diagnostics"]}


def test_wait_block_report_and_reconcile_use_versioned_commands():
    store = MemoryStore()
    ops = operations("crm.read", "crm.create", "crm.edit", "crm.archive", store=store)
    ops.advance({"participant_uid": store.participant["uid"], "expected_version": 1})
    ref = {"participant_uid": store.participant["uid"], "step_uid": str(SEND)}
    ops.wait({**ref, "expected_version": 2, "wake_at": (NOW + timedelta(days=3)).isoformat()})
    ops.block({**ref, "expected_version": 3, "blocked_reason": "LinkedIn session expired"})
    ops.report({**ref, "expected_version": 4, "evidence": [{"summary": "Message delivered"}], "result": {"message": "sent"}})
    kinds = [c[2]["kind"] for c in store.calls if c[0] == "record"]
    assert kinds == ["wait", "block", "report"]
    with pytest.raises(DomainValidationError):
        ops.report({**ref, "expected_version": 5, "evidence": [{"summary": f"e{i}"} for i in range(51)]})
    store.participant["progress"][0].update(state="blocked", outcome_key="sent", result={"message": "sent"})
    ops.reconcile({**ref, "expected_version": 5, "action": "resume"})
    assert [c for c in store.calls if c[0] == "complete"][-1][2]["evidence"] == []
    ops.reconcile({**ref, "expected_version": 6, "action": "reopen"})
    assert store.calls[-1][0] == "reconcile_reopen" and store.calls[-1][2]["task_expected_version"] == 1
    ops.reconcile({**ref, "expected_version": 7, "action": "cancel", "finish": True})
    assert store.calls[-1][0] == "reconcile_cancel" and store.calls[-1][2]["finish"] is True
    reader = operations("crm.read", "crm.edit", store=store)
    with pytest.raises(AccessDenied):
        reader.reconcile({**ref, "expected_version": 8, "action": "cancel", "next_step_uid": str(AWAIT)})


def test_graph_update_plans_only_changed_records_and_live_campaigns_stay_runnable():
    store = MemoryStore()
    ops = operations("crm.read", "crm.edit", "crm.archive", store=store)
    graph = dubai_graph().model_dump(mode="json")
    graph["steps"][0]["position"] = {"x": 10, "y": 20}
    graph["steps"][1]["title"] = "Await LinkedIn acceptance"
    graph["steps"][3]["archived"] = True
    graph["transitions"] = [t for t in graph["transitions"] if str(DEMO) not in (t["from_step_uid"], str(t["to_step_uid"]))]
    with pytest.raises(DomainValidationError):  # retiring the metric/target step leaves routes dangling on a live campaign
        ops.update_graph(uuid.UUID(int=99), {"expected_version": 1, "graph": graph})
    graph["steps"][3]["archived"] = False
    graph["transitions"] = dubai_graph().model_dump(mode="json")["transitions"]
    preview = ops.validate_candidate_graph(uuid.UUID(int=99), {"graph": graph})
    assert preview["validation"]["runnable"] is True
    assert preview["changes"]["changed_step_uids"] == [str(AWAIT)]
    assert preview["changes"]["comparison_changed_step_uids"] == []
    assert preview["changes"]["steps"] == 1 and preview["changes"]["layout_steps"] == 1
    saved = ops.update_graph(uuid.UUID(int=99), {"expected_version": 1, "graph": graph, "affected_open_work": "cancel"})
    assert saved["uid"] == store.campaign["uid"]
    plan = [c for c in store.calls if c[0] == "save_graph"][-1][2]
    assert {s["uid"] for s in plan["steps"]} == {str(AWAIT)}
    assert plan["layout_steps"] == [{"uid": str(SEND), "position": {"x": 10.0, "y": 20.0}}]
    assert plan["changed_step_uids"] == [AWAIT] and plan["transitions"] == [] and plan["cancel_retired_work"] is True
    assert len(plan["kept_transition_uids"]) == 6
    with pytest.raises(ResourceConflict):
        ops.update_graph(uuid.UUID(int=99), {"expected_version": 2, "graph": graph})
    incomplete = {**graph, "steps": graph["steps"][:3]}
    with pytest.raises(DomainValidationError):  # every active step must be present
        ops.update_graph(uuid.UUID(int=99), {"expected_version": 1, "graph": incomplete})
    reader = operations("crm.read", "crm.edit", store=store)
    with pytest.raises(AccessDenied):  # cancelling open work archives Tasks
        reader.update_graph(uuid.UUID(int=99), {"expected_version": 1, "graph": graph, "affected_open_work": "cancel"})


def test_campaign_lifecycle_rules_and_owner_selection():
    store = MemoryStore()
    ops = operations("crm.read", "crm.create", "crm.edit", store=store)
    with pytest.raises(DomainValidationError):
        ops.create_campaign({"name": "x", "objective": "# y", "owner_uid": str(uuid.uuid4())})
    with pytest.raises(DomainValidationError):
        ops.update_campaign(uuid.UUID(int=99), {"expected_version": 1, "changes": {"status": "draft"}})
    store.campaign["status"] = "draft"
    store.transitions.pop()  # not runnable: a missing route blocks activation
    with pytest.raises(DomainValidationError) as failure:
        ops.update_campaign(uuid.UUID(int=99), {"expected_version": 1, "changes": {"status": "active"}})
    assert any(field["code"] == "route_missing" for field in failure.value.fields)
    store.participant["status"] = "completed"
    with pytest.raises(DomainValidationError):
        ops.update_participant(uuid.UUID(int=77), {"expected_version": 1, "changes": {"status": "active"}})


# ----- transport parity -------------------------------------------------------


def app_for(policy, store):
    app = create_app()
    app.state.crm_policy = policy
    app.state.crm_directory = Directory()
    app.state.crm_resources = Resources()
    app.state.crm_campaign_store = store
    return app


def test_module_routes_and_tools_follow_persisted_config(config_file):
    config_file(campaigns=False)
    disabled = create_app().openapi()["paths"]
    assert not any(path.startswith("/extensions/campaigns/") for path in disabled)
    assert not any("campaign" in tool.definition.name for tool in build_crm_tools(lambda: None))
    config_file(campaigns=True)
    enabled = create_app().openapi()["paths"]
    for resource in ("campaigns", "prompts", "participants"):
        assert {"get", "post"} <= set(enabled[f"/extensions/campaigns/{resource}/"])
        assert {"get", "patch"} <= set(enabled[f"/extensions/campaigns/{resource}/{{uid}}/"])
    for command in ("prepare", "advance", "complete", "wait", "block", "report", "reconcile"):
        assert "post" in enabled[f"/extensions/campaigns/tasks/{command}/"]
    tools = {tool.definition.name: tool.definition for tool in build_crm_tools(lambda: None)}
    assert len([name for name in tools if "campaign" in name]) == 21
    assert tools["crm_campaign_tasks_prepare"].annotations.read_only_hint is True
    assert tools["crm_campaigns_graph_validate"].annotations.read_only_hint is True
    assert tools["crm_campaign_tasks_advance"].annotations.read_only_hint is False


def test_mcp_and_http_share_the_campaign_service(signed_caller):
    policy = Policy("crm.read", "crm.create", "crm.edit")
    mcp_store, http_store = MemoryStore(), MemoryStore()
    delegated = signed_caller(AGENT, requester={"sub": str(ACTOR), "is_organization_admin": False})
    with TestClient(app_for(policy, mcp_store), headers=delegated) as mcp:
        http = TestClient(app_for(policy, http_store), headers=signed_caller(ACTOR))
        create = {"name": "Dubai", "objective": "# Win", "owner_uid": str(ACTOR), "context": {"offer": "GPU"}}
        result = call(mcp, "crm_campaigns_create", {"payload": create})
        response = http.post("/extensions/campaigns/campaigns/", json=create)
        assert response.status_code == 201, response.text
        assert result["structuredContent"] == {"code": "ok", "data": response.json()}
        assert mcp_store.calls[0][2] == http_store.calls[0][2] == {}
        assert mcp_store.calls[0][1][1]["context"] == {"offer": "GPU"}
        advance = {"participant_uid": str(uuid.UUID(int=77)), "expected_version": 1}
        result = call(mcp, "crm_campaign_tasks_advance", advance)
        response = http.post("/extensions/campaigns/tasks/advance/", json=advance)
        assert response.status_code == 200, response.text
        assert result["structuredContent"]["data"]["created"] is True and response.json()["created"] is True
        prepare = {"participant_uid": str(uuid.UUID(int=77)), "step_uid": str(SEND)}
        assert call(mcp, "crm_campaign_tasks_prepare", prepare)["structuredContent"]["data"]["ready"] is True
        assert http.post("/extensions/campaigns/tasks/prepare/", json=prepare).json()["ready"] is True
        assert call(mcp, "crm_campaigns_get", {"uid": str(uuid.UUID(int=99)), "actor_uid": "spoof"})["structuredContent"]["code"] == "invalid_arguments"
        assert http.get("/extensions/campaigns/participants/?status=bogus").status_code == 422
        catalogue = {t["name"]: t for t in rpc(mcp, "tools/list")["tools"]}
        assert catalogue["crm_campaign_tasks_complete"]["inputSchema"]["required"] == [
            "participant_uid", "step_uid", "expected_version", "task_expected_version", "outcome_key", "evidence", "prepared_with",
        ]


def test_reader_without_edit_is_denied_on_every_mutation(signed_caller):
    store = MemoryStore()
    with TestClient(app_for(Policy("crm.read"), store), headers=signed_caller(ACTOR)) as client:
        assert client.post("/extensions/campaigns/tasks/advance/", json={"participant_uid": str(uuid.UUID(int=77)), "expected_version": 1}).status_code == 403
        assert client.post("/extensions/campaigns/campaigns/", json={"name": "x", "objective": "# y", "owner_uid": str(ACTOR)}).status_code == 403
        assert client.get(f"/extensions/campaigns/campaigns/{uuid.UUID(int=99)}/").status_code == 200
    assert not [c for c in store.calls if c[0] != "graph_impact"]
