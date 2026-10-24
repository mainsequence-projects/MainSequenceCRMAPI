"""Campaign governed SQL on a disposable private PostgreSQL.

Only MetaTables' network transport and the policy/directory ports are
substituted; the submitted statements run on PostgreSQL. The cluster comes
from local ``initdb``/``pg_ctl`` binaries or, when ``CRM_TEST_POSTGRES_DOCKER``
is set, from a throwaway Docker container bound to the loopback interface.
Neither path touches an existing database or hosted data.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic import command
from test_campaigns import ACTOR, AWAIT, DEMO, OFFER, PROMPT_A, PROMPT_B, SEND, dubai_graph
from test_resource_collections import SOURCE
from test_resource_collections import collection_postgres as _local_postgres

from metatables import MetaTableCompiledSQLOperation
from metatables.migrations import alembic_config_for_provider
from src.crm.campaigns.service import CampaignOperations
from src.crm.contracts import DomainValidationError, normalized_create
from src.crm.metatables import MODELS, Base
from src.crm.migrations import migration
from src.crm.repositories.campaigns import CampaignStore
from src.crm.repositories.errors import ResourceConflict
from src.crm.repositories.resources.store import GovernedResourceStore
from src.crm.services.operations import CRMContext

collection_postgres = _local_postgres


@pytest.fixture(scope="module")
def campaign_postgres(request):
    """Prefer local binaries; otherwise an opt-in disposable Docker container."""
    if shutil.which("postgres") and shutil.which("initdb") and shutil.which("pg_ctl"):
        yield request.getfixturevalue("collection_postgres")
        return
    if not os.environ.get("CRM_TEST_POSTGRES_DOCKER") or not shutil.which("docker"):
        pytest.skip("Campaign PostgreSQL checks need local postgres binaries or CRM_TEST_POSTGRES_DOCKER=1")
    pytest.importorskip("psycopg")
    image = os.environ.get("CRM_TEST_POSTGRES_IMAGE", "postgres:17")
    container = subprocess.run(
        ["docker", "run", "-d", "--rm", "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", "POSTGRES_DB=crm",
         "-p", "127.0.0.1::5432", image], check=True, capture_output=True, text=True,
    ).stdout.strip()
    try:
        port = subprocess.run(["docker", "port", container, "5432/tcp"], check=True, capture_output=True,
                              text=True).stdout.strip().rsplit(":", 1)[1]
        engine = sa.create_engine(f"postgresql+psycopg://postgres@127.0.0.1:{port}/crm", hide_parameters=True)
        for _ in range(120):
            try:
                with engine.connect() as probe:
                    probe.execute(sa.text("SELECT 1"))
                break
            except Exception:  # noqa: BLE001 - the container is still starting
                time.sleep(0.5)
        else:
            raise RuntimeError("Disposable PostgreSQL container did not become ready")
        Base.metadata.create_all(engine)
        yield engine
        engine.dispose()
    finally:
        subprocess.run(["docker", "rm", "-f", container], check=False, capture_output=True)


@pytest.fixture
def db(campaign_postgres):
    with campaign_postgres.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def world(db, monkeypatch, config_file):
    """Service, stores and two disposable Contacts bound to the private database."""
    calls = []

    def execute(payload):
        MetaTableCompiledSQLOperation.model_validate(payload)
        assert payload["data_source_uid"] == SOURCE
        calls.append(payload)
        rows = db.exec_driver_sql(payload["statement"]["sql"], payload["statement"]["parameters"]).mappings().all()
        return {"rows": [dict(row) for row in rows]}

    monkeypatch.setattr("src.crm.repositories.gateway.MetaTable.execute_operation", execute)
    registry = SimpleNamespace(data_source_uid=SOURCE)
    resources = GovernedResourceStore(registry)
    store = CampaignStore(registry)

    class Directory:
        def is_selectable(self, uid):
            return uid == ACTOR

        def display_name(self, uid):
            return "Owner"

    grants = {"crm.read", "crm.create", "crm.edit", "crm.archive"}
    context = CRMContext(actor_uid=ACTOR, policy=SimpleNamespace(capabilities=lambda uid: set(grants)), directory=Directory())
    ops = CampaignOperations(context, store=store, resources=resources, rng=random.Random(11),
                             clock=lambda: datetime.now(timezone.utc))
    contacts = [
        resources.create("contacts", ACTOR, normalized_create("contact", {"first_name": name, "last_name": "Prospect"}))
        for name in ("Sarah", "Omar", "Lina")
    ]
    return SimpleNamespace(db=db, ops=ops, store=store, resources=resources, contacts=contacts, calls=calls, grants=grants)


def build_campaign(world, *, delay=0, window=7 * 86400):
    """Create step prompts and the Dubai graph with real UIDs; returns the active campaign."""
    inputs = [{"key": "first_name", "type": "string", "required": False}, {"key": "offer", "type": "object", "required": False},
              {"key": "previous_offer", "type": "string", "required": False}]
    results = [{"key": "message", "type": "string", "required": True}]
    prompt_a = world.ops.create_step_prompt({"name": "GPU first", "content_markdown": "# Lead with GPU hours", "inputs": inputs, "result_fields": results})
    base = world.resources.create("prompts", ACTOR, {"name": "Pricing first", "description": None, "content_markdown": "# Lead with pricing"})
    prompt_b = world.ops.create_step_prompt({"prompt_uid": base["uid"], "expected_version": 1, "inputs": inputs, "result_fields": results})
    assert prompt_b["version"] == 2 and prompt_b["content_markdown"] == "# Lead with pricing"
    campaign = world.ops.create_campaign({
        "name": "Dubai LinkedIn outreach", "objective": "# Pilots with preferred pricing", "owner_uid": str(ACTOR),
        "context": {"offer": {"gpu_hours": 100, "discount": "20%"}},
    })
    graph = dubai_graph().model_dump(mode="json")
    mapping = {str(PROMPT_A): prompt_a["uid"], str(PROMPT_B): prompt_b["uid"]}
    for step in graph["steps"]:
        for variant in step["prompt_variants"]:
            variant["prompt_uid"] = mapping[variant["prompt_uid"]]
        if step["prompt_comparison"]:
            step["prompt_comparison"]["observation_window_seconds"] = window
    for transition in graph["transitions"]:
        if transition["delay_seconds"]:
            transition["delay_seconds"] = delay
    saved = world.ops.update_graph(uuid.UUID(campaign["uid"]), {"expected_version": 1, "graph": graph})
    assert saved["version"] == 2 and saved["validation"]["runnable"] is True
    assert {s["uid"] for s in saved["steps"]} == {str(SEND), str(AWAIT), str(OFFER), str(DEMO)}
    active = world.ops.update_campaign(uuid.UUID(campaign["uid"]), {"expected_version": 2, "changes": {"status": "active"}})
    assert active["status"] == "active" and active["version"] == 3
    return active, {"a": prompt_a, "b": prompt_b}


def progress_of(participant, step_uid):
    return next(item for item in participant["progress"] if item["step_uid"] == str(step_uid))


def run_step(world, participant, step_uid, outcome, result=None):
    """Advance, prepare and complete one step through the service; returns the participant."""
    advanced = world.ops.advance({"participant_uid": participant["uid"], "expected_version": participant["version"]})
    assert advanced["created"] is True
    participant = advanced["participant"]
    briefing = world.ops.prepare({"participant_uid": participant["uid"], "step_uid": str(step_uid)})
    assert briefing["ready"] is True, briefing["diagnostics"]
    task = progress_of(participant, step_uid)["task_uid"]
    completed = world.ops.complete({
        "participant_uid": participant["uid"], "step_uid": str(step_uid), "expected_version": participant["version"],
        "task_expected_version": briefing["task"]["version"], "outcome_key": outcome,
        "result": result or {"message": f"{outcome} for {participant['contact_display_name']}"},
        "evidence": [{"summary": f"Observed {outcome}", "resource_type": "task", "resource_uid": task}],
        "prepared_with": briefing["prepared_with"],
    })
    assert completed["accepted"] is True
    return completed["participant"], briefing


def test_two_contacts_follow_different_paths_with_persisted_ab_assignment(world):
    campaign, prompts = build_campaign(world)
    sarah = world.ops.create_participant({"campaign_uid": campaign["uid"], "contact_uid": world.contacts[0]["uid"], "context": {"city": "Dubai"}})
    omar = world.ops.create_participant({"campaign_uid": campaign["uid"], "contact_uid": world.contacts[1]["uid"]})
    assert sarah["next_step_uid"] == str(SEND) and sarah["status"] == "active"
    with pytest.raises(ResourceConflict):  # one enrollment per Contact and campaign
        world.ops.create_participant({"campaign_uid": campaign["uid"], "contact_uid": world.contacts[0]["uid"]})

    sarah, briefing = run_step(world, sarah, SEND, "sent")
    assert briefing["inputs"] == {} and briefing["campaign"]["context"]["offer"]["gpu_hours"] == 100
    omar, _ = run_step(world, omar, SEND, "sent")
    sarah, _ = run_step(world, sarah, AWAIT, "accepted")
    omar, _ = run_step(world, omar, AWAIT, "expired")
    assert omar["status"] == "completed" and omar["finished_at"] and omar["next_step_uid"] is None
    assert sarah["next_step_uid"] == str(OFFER) and sarah["status"] == "active"

    sarah, briefing = run_step(world, sarah, OFFER, "sent", {"message": "Hello Sarah, 100 GPU hours..."})
    assignment = progress_of(sarah, OFFER)["prompt_assignment"]
    assert assignment["variant_key"] in {"A", "B"} and assignment["comparison"]["key"] == "dubai-offer-copy-1"
    assert briefing["inputs"] == {"first_name": "Sarah", "offer": {"gpu_hours": 100, "discount": "20%"}}
    assert briefing["prompt"]["uid"] == assignment["prompt_uid"]
    sarah, briefing = run_step(world, sarah, DEMO, "interested")
    assert briefing["inputs"] == {"previous_offer": "Hello Sarah, 100 GPU hours..."}
    assert sarah["status"] == "completed"
    assert [item["state"] for item in sarah["progress"]] == ["completed"] * 4
    assert len({item["task_uid"] for item in sarah["progress"]} | {item["task_uid"] for item in omar["progress"]}) == 6

    tasks = world.db.exec_driver_sql(
        "SELECT contact_uid, completed_at IS NOT NULL AS done, text FROM mainsequence_crm__task ORDER BY created_at"
    ).mappings().all()
    assert len(tasks) == 6 and all(row["done"] for row in tasks)
    assert tasks[0]["text"].startswith("Send connection request\n\n")
    assert {str(row["contact_uid"]) for row in tasks} == {world.contacts[0]["uid"], world.contacts[1]["uid"]}

    # Comparison accounting: the only assignment is immature until its window passes.
    detail = world.ops.get_campaign(uuid.UUID(campaign["uid"]))
    assert len(detail["comparisons"]) == 1, detail["comparisons"]
    (report,) = detail["comparisons"]
    variant = report["variants"][0]
    assert report["current"] is True and variant == {
        "variant_key": assignment["variant_key"], "assigned": 1, "completed": 1, "cancelled": 0, "matured": 0,
        "successes": 0, "success_rate": None, "changed_exposures": 0,
    }
    # Age the assignment past its 7-day window with the success inside the window...
    world.db.exec_driver_sql(
        "UPDATE mainsequence_crm__campaign_progress SET prompt_assignment=jsonb_set(prompt_assignment, '{assigned_at}', "
        "to_jsonb(to_char(NOW() - interval '8 days', 'YYYY-MM-DD\"T\"HH24:MI:SS.USTZH:TZM'))) WHERE step_uid=%s::uuid", (str(OFFER),),
    )
    world.db.exec_driver_sql(
        "UPDATE mainsequence_crm__campaign_progress SET completed_at=NOW() - interval '3 days' WHERE step_uid=%s::uuid", (str(DEMO),),
    )
    matured = world.ops.get_campaign(uuid.UUID(campaign["uid"]))["comparisons"][0]["variants"][0]
    assert matured["matured"] == 1 and matured["successes"] == 1 and matured["success_rate"] == 1.0
    # ...and then so far back that the same success arrived after the window closed.
    world.db.exec_driver_sql(
        "UPDATE mainsequence_crm__campaign_progress SET prompt_assignment=jsonb_set(prompt_assignment, '{assigned_at}', "
        "to_jsonb(to_char(NOW() - interval '12 days', 'YYYY-MM-DD\"T\"HH24:MI:SS.USTZH:TZM'))) WHERE step_uid=%s::uuid", (str(OFFER),),
    )
    late = world.ops.get_campaign(uuid.UUID(campaign["uid"]))["comparisons"][0]["variants"][0]
    assert late["matured"] == 1 and late["successes"] == 0, "a success after the window never counts"
    assert detail["participant_counts"] == {"completed": 2}
    listing = world.ops.list_participants(page_index=0, page_size=10, search="sar", filters={"campaign_uid": campaign["uid"]})
    assert [item["contact_display_name"] for item in listing["items"]] == ["Sarah Prospect"]


def test_duplicate_advance_delay_and_uncertain_write_recovery(world):
    campaign, _ = build_campaign(world, delay=3600)
    sarah = world.ops.create_participant({"campaign_uid": campaign["uid"], "contact_uid": world.contacts[0]["uid"]})
    step = next(s for s in campaign["steps"] if s["uid"] == str(SEND))
    assignment = {"variant_key": "A", "prompt_uid": step["prompt_variants"][0]["prompt_uid"], "assigned_prompt_version": 1,
                  "assigned_at": datetime.now(timezone.utc).isoformat(), "comparison": None, "comparison_changed": False}
    first = world.store.advance(ACTOR, uuid.UUID(sarah["uid"]), 1, step_uid=SEND, step_version=step["version"], prompt_assignment=assignment)
    assert len(first["progress"]) == 1
    with pytest.raises(ResourceConflict):  # the same command again cannot create a second instance
        world.store.advance(ACTOR, uuid.UUID(sarah["uid"]), 1, step_uid=SEND, step_version=step["version"], prompt_assignment=assignment)
    with pytest.raises(ResourceConflict):  # nor with the fresh version: the step already has an instance
        world.store.advance(ACTOR, uuid.UUID(sarah["uid"]), 2, step_uid=SEND, step_version=step["version"], prompt_assignment=assignment)
    assert world.db.exec_driver_sql("SELECT count(*) FROM mainsequence_crm__task").scalar_one() == 1
    # The service treats a lost response the same way: read, then return the existing instance.
    again = world.ops.advance({"participant_uid": sarah["uid"], "expected_version": 2})
    assert again["created"] is False and len(again["participant"]["progress"]) == 1
    sarah = again["participant"]
    briefing = world.ops.prepare({"participant_uid": sarah["uid"], "step_uid": str(SEND)})
    done = world.ops.complete({
        "participant_uid": sarah["uid"], "step_uid": str(SEND), "expected_version": sarah["version"], "task_expected_version": 1,
        "outcome_key": "sent", "result": {"message": "x"}, "evidence": [{"summary": "sent"}], "prepared_with": briefing["prepared_with"],
    })
    sarah = done["participant"]
    sarah, _ = run_step(world, sarah, AWAIT, "accepted")
    eligible = datetime.fromisoformat(sarah["eligible_at"].replace("Z", "+00:00"))
    assert eligible > datetime.now(timezone.utc) + timedelta(minutes=55), "the connection's delay is persisted"
    with pytest.raises(DomainValidationError) as early:
        world.ops.advance({"participant_uid": sarah["uid"], "expected_version": sarah["version"]})
    assert early.value.fields[0]["code"] == "not_yet_eligible"
    with pytest.raises(ResourceConflict):  # the database refuses it too, independently of the clock
        world.store.advance(ACTOR, uuid.UUID(sarah["uid"]), sarah["version"], step_uid=OFFER, step_version=1, prompt_assignment=assignment)
    # Nothing needs attention while the delay runs; a blocked task shows up immediately.
    attention = world.ops.list_participants(page_index=0, page_size=10, search=None, filters={"attention": True})
    assert attention["pageInfo"]["totalItems"] == 0
    world.db.exec_driver_sql("UPDATE mainsequence_crm__campaign_participant SET eligible_at=NOW() - interval '1 minute'")
    attention = world.ops.list_participants(page_index=0, page_size=10, search=None, filters={"attention": True})
    assert attention["pageInfo"]["totalItems"] == 1
    sarah = world.ops.advance({"participant_uid": sarah["uid"], "expected_version": sarah["version"]})["participant"]
    waited = world.ops.wait({"participant_uid": sarah["uid"], "step_uid": str(OFFER), "expected_version": sarah["version"],
                             "wake_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                             "evidence": [{"summary": "Offer drafted, awaiting approval"}]})
    record = progress_of(waited, OFFER)
    assert record["state"] == "waiting" and record["wake_at"] and record["evidence"][0]["summary"].startswith("Offer drafted")
    # The wait is data on the progress row: a fresh read (a restart) sees it.
    fresh = world.store.participant_detail(uuid.UUID(sarah["uid"]))
    assert progress_of(fresh, OFFER)["state"] == "waiting"
    assert world.ops.list_participants(page_index=0, page_size=10, search=None, filters={"attention": True})["pageInfo"]["totalItems"] == 0


def test_core_task_changes_prompt_archive_and_merge_are_guarded(world):
    campaign, prompts = build_campaign(world)
    lina = world.ops.create_participant({"campaign_uid": campaign["uid"], "contact_uid": world.contacts[2]["uid"]})
    lina = world.ops.advance({"participant_uid": lina["uid"], "expected_version": 1})["participant"]
    task_uid = uuid.UUID(progress_of(lina, SEND)["task_uid"])
    # Core completion without an outcome blocks the graph instead of advancing it.
    world.resources.task_completion(ACTOR, task_uid, 1, True)
    lina = world.ops.get_participant(uuid.UUID(lina["uid"]))
    assert progress_of(lina, SEND)["state"] == "blocked" and progress_of(lina, SEND)["blocked_reason"] == "outcome_required"
    assert lina["next_step_uid"] == str(SEND), "the graph did not advance"
    # Core reopen exposes the inconsistency and never replays downstream Tasks.
    briefing = world.ops.prepare({"participant_uid": lina["uid"], "step_uid": str(SEND)})
    done = world.ops.complete({
        "participant_uid": lina["uid"], "step_uid": str(SEND), "expected_version": lina["version"], "task_expected_version": 2,
        "outcome_key": "sent", "result": {"message": "ok"}, "evidence": [{"summary": "sent"}], "prepared_with": briefing["prepared_with"],
    })
    assert done["accepted"] is True and done["participant"]["next_step_uid"] == str(AWAIT)
    world.resources.task_completion(ACTOR, task_uid, 3, False)
    lina = world.ops.get_participant(uuid.UUID(lina["uid"]))
    assert progress_of(lina, SEND)["state"] == "blocked" and progress_of(lina, SEND)["blocked_reason"] == "task_reopened"
    assert lina["next_step_uid"] == str(AWAIT) and world.db.exec_driver_sql("SELECT count(*) FROM mainsequence_crm__task").scalar_one() == 1
    # Reassigning a campaign Task to another Contact is rejected; other edits work.
    with pytest.raises(ResourceConflict):
        world.resources.update("tasks", ACTOR, task_uid, 4, {"contact_uid": world.contacts[0]["uid"]})
    assert world.resources.update("tasks", ACTOR, task_uid, 4, {"text": "Edited text"})["version"] == 5
    # Archiving the assigned prompt blocks open work; the assignment is preserved.
    lina = world.ops.advance({"participant_uid": lina["uid"], "expected_version": lina["version"]})["participant"]
    prompt_a = prompts["a"]
    world.resources.archive("prompts", ACTOR, uuid.UUID(prompt_a["uid"]), prompt_a["version"], True)
    lina = world.ops.get_participant(uuid.UUID(lina["uid"]))
    assert progress_of(lina, AWAIT)["state"] == "blocked" and progress_of(lina, AWAIT)["blocked_reason"] == "prompt_archived"
    assert progress_of(lina, AWAIT)["prompt_assignment"]["prompt_uid"] == prompt_a["uid"]
    prepared = world.ops.prepare({"participant_uid": lina["uid"], "step_uid": str(AWAIT)})
    assert "prompt_archived" in {d["code"] for d in prepared["diagnostics"]} and prepared["ready"] is False
    world.resources.archive("prompts", ACTOR, uuid.UUID(prompt_a["uid"]), prompt_a["version"] + 1, False)
    reopened = world.ops.reconcile({"participant_uid": lina["uid"], "step_uid": str(AWAIT), "expected_version": lina["version"], "action": "reopen"})
    assert progress_of(reopened, AWAIT)["state"] == "open"
    # Enrolled Contacts cannot be merged until an explicit policy exists.
    with pytest.raises(ResourceConflict, match="Campaign"):
        world.resources.merge_preview(uuid.UUID(world.contacts[0]["uid"]), uuid.UUID(world.contacts[2]["uid"]), {})
    # Withdrawal archives open Tasks and cancels progress without completing anything.
    withdrawn = world.ops.update_participant(uuid.UUID(lina["uid"]), {"expected_version": reopened["version"], "changes": {"status": "withdrawn"}})
    assert withdrawn["status"] == "withdrawn" and progress_of(withdrawn, AWAIT)["state"] == "cancelled"
    archived = world.db.exec_driver_sql(
        "SELECT archived_at IS NOT NULL, completed_at IS NOT NULL FROM mainsequence_crm__task WHERE uid=%s::uuid",
        (progress_of(withdrawn, AWAIT)["task_uid"],),
    ).one()
    assert tuple(archived) == (True, False)


def test_live_graph_edits_block_or_cancel_open_work_and_stale_saves_roll_back(world):
    campaign, prompts = build_campaign(world)
    sarah = world.ops.create_participant({"campaign_uid": campaign["uid"], "contact_uid": world.contacts[0]["uid"]})
    sarah = world.ops.advance({"participant_uid": sarah["uid"], "expected_version": 1})["participant"]
    briefing = world.ops.prepare({"participant_uid": sarah["uid"], "step_uid": str(SEND)})
    graph = {
        "entry_step_uid": str(SEND),
        "steps": [{k: v for k, v in step.items() if k in {"uid", *briefing["step"].keys(), "prompt_variants", "prompt_comparison",
                                                            "owner_uid", "task_type_key", "due_after_seconds", "position"}} | {"archived": False}
                  for step in campaign["steps"]],
        "transitions": [{k: t[k] for k in ("uid", "from_step_uid", "outcome_key", "to_step_uid", "delay_seconds")} for t in campaign["transitions"]],
    }
    for step in graph["steps"]:
        step.pop("version", None)
    layout_only = json.loads(json.dumps(graph))
    layout_only["steps"][0]["position"] = {"x": 40, "y": 80}
    preview = world.ops.validate_candidate_graph(uuid.UUID(campaign["uid"]), {"graph": layout_only})
    assert preview["changes"]["changed_step_uids"] == [] and preview["impact"]["open_work_count"] == 0
    saved = world.ops.update_graph(uuid.UUID(campaign["uid"]), {"expected_version": campaign["version"], "graph": layout_only})
    assert saved["version"] == campaign["version"] + 1
    assert next(s for s in saved["steps"] if s["uid"] == str(SEND))["version"] == 1, "layout edits keep step versions"
    assert world.ops.prepare({"participant_uid": sarah["uid"], "step_uid": str(SEND)})["ready"] is True

    # A stale save is rejected whole: no step, transition or activity row changes.
    before = world.db.exec_driver_sql("SELECT count(*) FROM mainsequence_crm__activity_event").scalar_one()
    with pytest.raises(ResourceConflict):
        world.ops.update_graph(uuid.UUID(campaign["uid"]), {"expected_version": campaign["version"], "graph": layout_only})
    # A save referencing an unknown prompt fails inside the statement after dependent writes were planned.
    broken = json.loads(json.dumps(layout_only))
    broken["steps"][1]["prompt_variants"][0]["prompt_uid"] = str(uuid.uuid4())
    broken["steps"][1]["title"] = "Changed title"
    with pytest.raises(DomainValidationError):
        world.ops.update_graph(uuid.UUID(campaign["uid"]), {"expected_version": saved["version"], "graph": broken})
    world.db.exec_driver_sql("UPDATE mainsequence_crm__campaign_step_prompt SET uid=uid")  # keep the transaction live
    assert world.db.exec_driver_sql("SELECT count(*) FROM mainsequence_crm__activity_event").scalar_one() == before
    assert world.db.exec_driver_sql("SELECT title FROM mainsequence_crm__campaign_step WHERE uid=%s::uuid", (str(AWAIT),)).scalar_one() == "Await acceptance"

    # A material edit of the open step blocks its work; the campaign version advances.
    edited = json.loads(json.dumps(layout_only))
    edited["steps"][0]["task_text"] = "Send the request with the Dubai pilot mention."
    preview = world.ops.validate_candidate_graph(uuid.UUID(campaign["uid"]), {"graph": edited})
    assert preview["changes"]["changed_step_uids"] == [str(SEND)] and preview["impact"]["open_work_count"] == 1
    saved = world.ops.update_graph(uuid.UUID(campaign["uid"]), {"expected_version": saved["version"], "graph": edited})
    sarah = world.ops.get_participant(uuid.UUID(sarah["uid"]))
    assert progress_of(sarah, SEND)["state"] == "blocked" and progress_of(sarah, SEND)["blocked_reason"] == "step_changed"
    stale = world.ops.complete({
        "participant_uid": sarah["uid"], "step_uid": str(SEND), "expected_version": sarah["version"], "task_expected_version": 1,
        "outcome_key": "sent", "result": {"message": "already sent"}, "evidence": [{"summary": "Actually sent before the edit"}],
        "prepared_with": briefing["prepared_with"],
    })
    assert stale["accepted"] is False and stale["reason"] == "stale_briefing"
    record = progress_of(stale["participant"], SEND)
    assert record["result"] == {"message": "already sent"} and record["outcome_key"] == "sent" and record["state"] == "blocked"
    resumed = world.ops.reconcile({"participant_uid": sarah["uid"], "step_uid": str(SEND), "expected_version": stale["participant"]["version"], "action": "resume"})
    assert progress_of(resumed, SEND)["state"] == "completed" and resumed["next_step_uid"] == str(AWAIT)
    assert progress_of(resumed, SEND)["prepared_with"]["step_version"] == 2

    # Retiring the scheduled step with the cancel policy archives its Task; reroute afterwards.
    sarah = world.ops.advance({"participant_uid": sarah["uid"], "expected_version": resumed["version"]})["participant"]
    retired = json.loads(json.dumps(edited))
    retired["steps"][1]["archived"] = True
    retired["transitions"] = [t for t in retired["transitions"] if str(AWAIT) not in (t["from_step_uid"], str(t["to_step_uid"]))]
    retired["transitions"].append({"uid": str(uuid.uuid4()), "from_step_uid": str(SEND), "outcome_key": "sent", "to_step_uid": str(OFFER), "delay_seconds": 0})
    preview = world.ops.validate_candidate_graph(uuid.UUID(campaign["uid"]), {"graph": retired})
    assert preview["validation"]["runnable"] is True and preview["changes"]["retired_step_uids"] == [str(AWAIT)]
    assert preview["impact"]["open_work_count"] == 1
    saved = world.ops.update_graph(uuid.UUID(campaign["uid"]), {"expected_version": saved["version"], "graph": retired, "affected_open_work": "cancel"})
    assert {s["uid"] for s in saved["steps"] if s["archived_at"]} == {str(AWAIT)}
    assert len(saved["transitions"]) == 4
    sarah = world.ops.get_participant(uuid.UUID(sarah["uid"]))
    assert progress_of(sarah, AWAIT)["state"] == "cancelled"
    assert world.db.exec_driver_sql("SELECT archived_at IS NOT NULL FROM mainsequence_crm__task WHERE uid=%s::uuid",
                                    (progress_of(sarah, AWAIT)["task_uid"],)).scalar_one() is True
    rerouted = world.ops.update_participant(uuid.UUID(sarah["uid"]), {"expected_version": sarah["version"], "changes": {"next_step_uid": str(OFFER)}})
    assert rerouted["next_step_uid"] == str(OFFER)
    with pytest.raises(ResourceConflict):  # a visited step cannot receive a second instance by reroute
        world.ops.update_participant(uuid.UUID(sarah["uid"]), {"expected_version": rerouted["version"], "changes": {"next_step_uid": str(SEND)}})
    # Editing the compared step flags existing assignments as changed exposure.
    sarah = world.ops.advance({"participant_uid": sarah["uid"], "expected_version": rerouted["version"]})["participant"]
    changed = json.loads(json.dumps(retired))
    changed["steps"][2]["prompt_variants"][0]["allocation_percent"] = 70
    changed["steps"][2]["prompt_variants"][1]["allocation_percent"] = 30
    saved = world.ops.update_graph(uuid.UUID(campaign["uid"]), {"expected_version": saved["version"], "graph": changed})
    sarah = world.ops.get_participant(uuid.UUID(sarah["uid"]))
    assert progress_of(sarah, OFFER)["prompt_assignment"]["comparison_changed"] is True
    assert progress_of(sarah, OFFER)["prompt_assignment"]["comparison"]["allocation"] == {"A": 50, "B": 50}
    assert saved["comparisons"][0]["variants"][0]["changed_exposures"] == 1
    # Editing the prompt's content blocks open work and bumps the shared Prompt version.
    updated = world.ops.update_step_prompt(uuid.UUID(prompts["a"]["uid"]), {"expected_version": prompts["a"]["version"], "changes": {"content_markdown": "# New wording"}})
    assert updated["version"] == prompts["a"]["version"] + 1
    assert world.ops.get_step_prompt(uuid.UUID(prompts["a"]["uid"]))["content_markdown"] == "# New wording"


def test_campaign_revision_applies_on_postgresql_and_matches_models(campaign_postgres):
    """Run the authored history on the real dialect, including the circular entry-step key."""
    url = campaign_postgres.url.set(database="postgres") if campaign_postgres.url.database != "postgres" else campaign_postgres.url
    admin = sa.create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(sa.text("DROP DATABASE IF EXISTS crm_migration_check"))
        connection.execute(sa.text("CREATE DATABASE crm_migration_check"))
    engine = sa.create_engine(url.set(database="crm_migration_check"))
    try:
        config = alembic_config_for_provider(migration, sqlalchemy_url=engine.url.render_as_string(hide_password=False))
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()
            inspector = sa.inspect(connection)
            tables = set(inspector.get_table_names())
            assert {MODELS[name].__tablename__ for name in MODELS} <= tables
            foreign = {fk["name"] for fk in inspector.get_foreign_keys("mainsequence_crm__campaign")}
            assert "fk_mainsequence_crm__campaign_entry_step" in foreign
            uniques = {u["name"] for u in inspector.get_unique_constraints("mainsequence_crm__campaign_progress")}
            assert {"uq_mainsequence_crm__campaign_progress_step", "uq_mainsequence_crm__campaign_progress_task"} <= uniques
            command.downgrade(config, "0012")
            connection.commit()
            assert not any("campaign" in name for name in sa.inspect(connection).get_table_names())
            command.upgrade(config, "head")
            connection.commit()
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(sa.text("DROP DATABASE IF EXISTS crm_migration_check"))
        admin.dispose()
