"""The one deployment workflow migrates the CRM tables before anything rolls out."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest
import yaml

import metatables

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".mainsequence" / "workflows"
EVERY_PUSH = {"enabled": True, "tag_regex": None}


def _workflow() -> dict:
    return yaml.safe_load((WORKFLOWS / "crm-api.yaml").read_text(encoding="utf-8"))


def _ancestors(steps: dict, key: str) -> set[str]:
    seen: set[str] = set()
    pending = list(steps[key].get("needs", []))
    while pending:
        step = pending.pop()
        if step not in seen:
            seen.add(step)
            pending.extend(steps[step].get("needs", []))
    return seen


@pytest.mark.parametrize("migrated,state", [(False, "already current"), (True, "migrated")])
def test_migration_job_upgrades_only_the_crm_provider(monkeypatch, capsys, migrated, state):
    calls = []

    def upgrade_application(provider):
        calls.append(provider)
        return {"migrated": migrated, "revision": "0009", "data_source_uid": "source-uid"}

    monkeypatch.setattr(metatables, "upgrade_application", upgrade_application)
    runpy.run_path(str(ROOT / "jobs" / "migrate_crm.py"), run_name="__main__")
    assert calls == ["src.crm.migrations:migration"]
    assert capsys.readouterr().out == (
        f"src.crm.migrations:migration: 0009 ({state}; catalog reconciled) on source-uid\n"
    )


def test_migration_job_propagates_finalization_failure(monkeypatch, capsys):
    def upgrade_application(provider):
        raise RuntimeError("physical_table_missing")

    monkeypatch.setattr(metatables, "upgrade_application", upgrade_application)
    with pytest.raises(RuntimeError, match="physical_table_missing"):
        runpy.run_path(str(ROOT / "jobs" / "migrate_crm.py"), run_name="__main__")
    assert capsys.readouterr().out == ""


def test_the_repository_has_one_workflow_file():
    assert sorted(path.name for path in WORKFLOWS.iterdir()) == ["crm-api.yaml"]


def test_api_and_assistant_deploy_only_after_the_migration_job():
    workflow = _workflow()
    assert workflow["api_version"] == "3.0.0"
    resources = {item["key"]: item for item in workflow["resources"]}
    assert {key: item["kind"] for key, item in resources.items()} == {
        "crm": "fastapi",
        "migrate-crm": "job",
        "crm-assistant": "harness_agent",
    }
    job = resources["migrate-crm"]["spec"]
    assert (ROOT / job["execution_path"]).is_file()
    # Every connected step must be admitted by the same promotion policy.
    for item in resources.values():
        assert item["spec"]["automatic_redeployment"] == EVERY_PUSH
    assert resources["migrate-crm"]["access"] == {
        "branches": [{"repository": "MetaTables", "policy": "reader"}]
    }
    # Workflow-owned user policies support Agent discovery and application MCP.
    # Requester authorization and storage access remain independent checks.
    assert resources["crm"]["access"] == {
        "branches": [{"repository": "MetaTables", "policy": "reader"}],
        "resources": [{"key": "crm-assistant", "policy": "user"}],
    }
    assert resources["crm"]["spec"]["mcp_enabled"] is True
    assert resources["crm-assistant"]["acts_for_requester"] is True
    assert resources["crm-assistant"]["access"] == {
        "resources": [{"key": "crm", "policy": "user"}]
    }
    assert workflow["execution"] == {
        "steps": {
            "image": {"prepare_image": "crm"},
            "migrate": {"run_job": "migrate-crm", "image_from": "image", "needs": ["image"]},
            "deploy_api": {"deploy": "crm", "image_from": "image", "needs": ["migrate"]},
            "image_assistant": {"prepare_image": "crm-assistant"},
            "deploy_assistant": {
                "deploy": "crm-assistant",
                "image_from": "image_assistant",
                "needs": ["deploy_api", "image_assistant"],
            },
        }
    }


def test_every_runtime_waits_for_the_migration_and_scheduled_jobs_stay_out():
    workflow = _workflow()
    steps = workflow["execution"]["steps"]
    runtimes = {
        item["key"]
        for item in workflow["resources"]
        if item["kind"] in {"fastapi", "harness_agent"}
    }
    deployed = {step["deploy"]: key for key, step in steps.items() if "deploy" in step}
    assert set(deployed) == runtimes
    for target, key in deployed.items():
        assert "migrate" in _ancestors(steps, key)
        assert steps[steps[key]["image_from"]] == {"prepare_image": target}
    # A step-referenced Job gets its new image when the run is admitted, before
    # the migration, so a scheduled Job never appears in the graph.
    referenced = {
        value
        for step in steps.values()
        for operation, value in step.items()
        if operation in {"prepare_image", "run_job", "deploy"}
    }
    for item in workflow["resources"]:
        if item["kind"] == "job" and item["spec"].get("task_schedule"):
            assert item["key"] not in referenced


def test_the_assistant_kept_its_declaration_when_it_moved_into_this_file():
    resources = {item["key"]: item for item in _workflow()["resources"]}
    assert resources["crm-assistant"]["spec"] == {
        "source_path": "api/tau/main.py",
        "mcp_applications": [{"resource": "crm"}],
        "llm_provider": "openai-codex",
        "llm_model": "gpt-5.6-luna",
        "llm_thinking": "medium",
        "command_center_icon": {
            "path": "assets/agents/rolo/idle.png",
            "rendering": "color",
            "image_rendering": "pixelated",
        },
        "command_center_animations": {
            "poses": {
                "thinking": {"path": "assets/agents/rolo/thinking.png"},
                "working": {"path": "assets/agents/rolo/working.png"},
                "outreach": {"path": "assets/agents/rolo/outreach.png"},
                "error": {"path": "assets/agents/rolo/error.png"},
            },
            "tools": [{"application": "crm", "pose": "outreach"}],
        },
        "automatic_deployment": True,
        "automatic_redeployment": EVERY_PUSH,
        "revision_retention_count": 3,
        "env_vars": [
            {"name": "TAU_EXCLUDE_BASE_TOOLS", "value": "true"},
            {"name": "TAU_EXCLUDE_MAINSEQUENCE_MCP", "value": "true"},
        ],
    }
