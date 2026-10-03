"""The deployment workflow migrates the CRM tables before the API rolls out."""

from __future__ import annotations

import runpy
from pathlib import Path

import yaml

import metatables

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".mainsequence" / "workflows"


def test_migration_job_upgrades_only_the_crm_provider(monkeypatch, capsys):
    calls = []

    def upgrade_application(provider):
        calls.append(provider)
        return {"migrated": False, "revision": "0009", "data_source_uid": "source-uid"}

    monkeypatch.setattr(metatables, "upgrade_application", upgrade_application)
    runpy.run_path(str(ROOT / "jobs" / "migrate_crm.py"), run_name="__main__")
    assert calls == ["src.crm.migrations:migration"]
    assert capsys.readouterr().out == (
        "src.crm.migrations:migration: 0009 (already current) on source-uid\n"
    )


def test_crm_api_deploys_only_after_the_migration_job():
    workflow = yaml.safe_load((WORKFLOWS / "crm-api.yaml").read_text(encoding="utf-8"))
    assert workflow["api_version"] == "2.3.0"
    resources = {item["key"]: item for item in workflow["resources"]}
    assert {key: item["kind"] for key, item in resources.items()} == {
        "crm-api": "fastapi",
        "migrate-crm": "job",
    }
    job = resources["migrate-crm"]["spec"]
    assert (ROOT / job["execution_path"]).is_file()
    # Every connected step must be admitted by the same promotion policy.
    assert job["automatic_redeployment"] == {"enabled": True, "tag_regex": None}
    assert resources["crm-api"]["spec"]["automatic_redeployment"] == job["automatic_redeployment"]
    assert workflow["execution"] == {
        "steps": {
            "image": {"prepare_image": "crm-api"},
            "migrate": {"run_job": "migrate-crm", "image_from": "image", "needs": ["image"]},
            "deploy_api": {"deploy": "crm-api", "image_from": "image", "needs": ["migrate"]},
        }
    }


def test_assistant_workflow_stays_a_separate_file():
    workflow = yaml.safe_load((WORKFLOWS / "crm-assistant.yaml").read_text(encoding="utf-8"))
    assert [(item["key"], item["kind"]) for item in workflow["resources"]] == [
        ("crm-assistant", "harness_agent")
    ]
    assert "execution" not in workflow
