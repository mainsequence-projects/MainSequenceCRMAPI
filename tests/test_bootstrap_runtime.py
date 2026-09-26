"""One-request bootstrap and assistant runtime selection contract."""

import uuid

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient

from api.crm.main import create_app
from src.crm.assistant_runtime import resolve_assistant
from src.crm.config import crm_config
from src.crm.models.bootstrap import Bootstrap

ACTOR = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
PIPELINE = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


class ReadyRegistry:
    def validate(self):
        pass

    def validate_settings(self):
        pass


class ReadyPolicy:
    def capabilities(self, actor_uid):
        return {"crm.read"}


class ReadyDirectory:
    def display_name(self, actor_uid):
        return "Test user"

    def is_selectable(self, actor_uid):
        return True


class ReadyBootstrap:
    def validate(self, actor_uid):
        pass

    def read(self, actor_uid):
        return {
            "application_version": "0.1.0",
            "current_user": {"uid": str(actor_uid), "display_name": "Test user", "selectable": True},
            "capabilities": ["crm.read"],
            "settings": {
                "configuration_version": 1, "default_currency": "USD", "timezone": "UTC",
                "company_sectors": [], "contact_statuses": [], "deal_categories": [], "task_types": [],
            },
            "default_pipeline_uid": str(PIPELINE),
            "limits": {
                "list_page_max": 100, "bulk_explicit_max": 200,
                "upload_bytes_max": 20971520, "transfer_rows_max": 20000,
            },
            "modules": {"solution_selling": True, "google_workspace": True},
        }


def ready_app():
    app = create_app()
    app.state.crm_registry = ReadyRegistry()
    app.state.crm_policy = ReadyPolicy()
    app.state.crm_directory = ReadyDirectory()
    app.state.crm_bootstrap = ReadyBootstrap()

    @app.middleware("http")
    async def actor(request, call_next):
        request.state.user_uid = str(ACTOR)
        return await call_next(request)

    return app


def test_persisted_extension_configuration_ignores_old_environment_switches(config_file, monkeypatch):
    monkeypatch.setenv("INCLUDE_SOLUTION_SELLING", "false")
    monkeypatch.setenv("INCLUDE_GOOGLE_WORKSPACE_EXTENSION", "false")
    paths = create_app().openapi()["paths"]
    assert "/extensions/solution-selling/leads/" in paths
    assert "/extensions/google/oauth/callback/" in paths


def test_invalid_persisted_configuration_fails_at_app_boot(config_file):
    config_file(google_workspace=False)
    from src.crm.config import CONFIG_PATH

    CONFIG_PATH.write_text("extensions:\n  solution_selling:\n    active: true\n", encoding="utf-8")
    crm_config.cache_clear()
    with pytest.raises(RuntimeError, match="config/crm.yaml"):
        create_app()


def test_bootstrap_serializes_readiness_and_unavailable_assistant(monkeypatch):
    monkeypatch.setattr("api.crm.main.resolve_assistant", lambda origin: _unavailable())
    response = TestClient(ready_app()).get("/api/crm/v1/bootstrap/")
    assert response.status_code == 200
    payload = Bootstrap.model_validate(response.json())
    assert payload.readiness.status.value == "ready"
    assert payload.assistant.enabled is False


async def _unavailable():
    return {"enabled": False, "runtime": None, "agent_uid": None,
            "environment_uid": None, "display_name": "CRM assistant"}


def test_local_tau_precedes_platform_and_unready_tau_falls_back(monkeypatch):
    import src.crm.assistant_runtime as runtime

    platform = {"enabled": True, "runtime": {"mode": "platform"},
                "agent_uid": str(uuid.uuid4()), "environment_uid": str(uuid.uuid4()),
                "display_name": "CRM assistant"}
    calls = []
    monkeypatch.setattr(runtime, "_platform_agent", lambda name: calls.append(name) or platform)

    class TauClient:
        ready = True

        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            assert url == "http://127.0.0.1:38642/ready"
            return httpx.Response(200 if self.ready else 503, json={"ok": self.ready, "mode": "local"})

    monkeypatch.setattr(runtime.httpx, "AsyncClient", TauClient)
    local = anyio.run(resolve_assistant, "http://127.0.0.1:38642")
    assert local["runtime"] == {"mode": "local", "base_path": "/tau"}
    assert local["agent_uid"] is None and calls == []
    TauClient.ready = False
    fallback = anyio.run(resolve_assistant, "http://127.0.0.1:38642")
    assert fallback == platform and calls == ["CRM assistant"]
    assert anyio.run(resolve_assistant, None) == platform


def test_invalid_card_disables_both_transports(monkeypatch, tmp_path):
    import src.crm.assistant_runtime as runtime

    card = tmp_path / "agent_card.json"
    card.write_text('{"name": "", "description": "No name"}', encoding="utf-8")
    monkeypatch.setattr(runtime, "CARD_PATH", card)
    monkeypatch.setattr(runtime, "_platform_agent", lambda name: pytest.fail("Platform lookup must not run"))
    result = anyio.run(resolve_assistant, None)
    assert result["enabled"] is False and result["display_name"] is None
