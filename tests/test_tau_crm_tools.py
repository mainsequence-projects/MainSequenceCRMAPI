"""Tau tools are typed adapters over the same CRM service as HTTP."""

from __future__ import annotations

import uuid
from pathlib import Path

import anyio
from fastapi.testclient import TestClient
from tau_coding.extensions.loader import load_extensions
from tau_coding.resources import TauResourcePaths

from api.crm.main import create_app
from api.tau.crm_tools import CRMToolRuntime, build_crm_tools, unavailable_runtime
from src.crm.services.operations import CRMContext

ACTOR = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CONTACT = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


class Policy:
    def __init__(self, *allowed: str):
        self.allowed = set(allowed)

    def capabilities(self, actor_uid):
        assert actor_uid == ACTOR
        return self.allowed


class Directory:
    def is_selectable(self, uid):
        return True

    def display_name(self, uid):
        return "Test actor"


class Store:
    def __init__(self):
        self.calls = []
        self.record = None

    def create(self, resource, actor_uid, data):
        self.calls.append(("create", resource, actor_uid, data))
        self.record = {"uid": str(CONTACT), "version": 1, **data}
        return self.record

    def detail(self, resource, uid):
        self.calls.append(("detail", resource, uid))
        return self.record

    def update(self, resource, actor_uid, uid, expected_version, data):
        self.calls.append(("update", resource, actor_uid, uid, expected_version, data))
        self.record = {"uid": str(uid), "version": expected_version + 1, **data}
        return self.record

    def collection(self, resource, scope):
        self.calls.append(("collection", resource, scope))
        return {"items": [], "pageInfo": {}}


def tools_for(policy, store):
    return {
        tool.name: tool
        for tool in build_crm_tools(
            lambda: CRMToolRuntime(CRMContext(ACTOR, policy, Directory()), resources=store)
        )
    }


def client_for(policy, store):
    app = create_app()
    app.state.crm_policy = policy
    app.state.crm_directory = Directory()
    app.state.crm_resources = store

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user_uid = ACTOR
        return await call_next(request)

    return TestClient(app)


def run(tool, arguments):
    return anyio.run(tool.execute, "call-1", arguments)


def test_tau_contact_create_update_match_http_shared_commands():
    policy = Policy("crm.create", "crm.edit")
    tool_store, http_store = Store(), Store()
    tools = tools_for(policy, tool_store)
    client = client_for(policy, http_store)
    create = {"first_name": "  Ada  ", "emails": []}
    result = run(tools["crm_contacts_create"], {"payload": create})
    http = client.post("/api/crm/v1/contacts/", json=create)
    assert result.details == {"code": "ok", "data": http.json()}
    assert http.status_code == 201
    assert tool_store.calls == http_store.calls

    patch = {"expected_version": 1, "changes": {"first_name": "Grace"}}
    result = run(tools["crm_contacts_update"], {"uid": str(CONTACT), "payload": patch})
    http = client.patch(f"/api/crm/v1/contacts/{CONTACT}/", json=patch)
    assert result.details == {"code": "ok", "data": http.json()}
    assert http.status_code == 200
    assert tool_store.calls == http_store.calls


def test_tool_denies_without_capability_and_never_accepts_actor_argument():
    store = Store()
    tool = tools_for(Policy(), store)["crm_contacts_create"]
    result = run(tool, {"payload": {"first_name": "Ada"}})
    assert result.details["code"] == "forbidden"
    assert store.calls == []
    result = run(
        tool,
        {
            "payload": {"first_name": "Ada"},
            "actor_uid": str(ACTOR),
        },
    )
    assert result.details["code"] == "invalid_arguments"
    assert store.calls == []


def test_unbound_project_extension_registers_declared_tools_but_fails_closed(tmp_path):
    class Tau:
        def __init__(self):
            self.tools = []

        def register_tool(self, tool):
            self.tools.append(tool)

    tau = Tau()
    extensions = load_extensions(
        TauResourcePaths(root=tmp_path, cwd=Path(__file__).parents[1]),
        include_project_dir=True,
        include_user_dir=False,
    )
    assert not extensions.diagnostics
    assert [(extension.name, extension.source) for extension in extensions.extensions] == [
        ("crm", "project")
    ]
    extensions.extensions[0].setup(tau)
    assert {tool.name for tool in tau.tools} == {
        tool.name for tool in build_crm_tools(unavailable_runtime)
    }
    assert "crm_contacts_create" in {tool.name for tool in tau.tools}
    assert "crm_contacts_archive" not in {tool.name for tool in tau.tools}
    result = run(
        next(tool for tool in tau.tools if tool.name == "crm_contacts_get"), {"uid": str(CONTACT)}
    )
    assert result.details["code"] == "unavailable"


def test_semantic_query_validation_and_disabled_module(config_file):
    store = Store()
    tools = tools_for(Policy("crm.read"), store)
    result = run(tools["crm_contacts_list"], {"filters": {"has_open_tasks": 1}})
    assert result.details["code"] == "invalid_arguments"
    assert store.calls == []
    config_file(solution_selling=False)
    names = {tool.name for tool in build_crm_tools(unavailable_runtime)}
    assert "crm_interactions_list" in names
    assert "crm_leads_list" not in names


def test_cancellation_after_write_reports_unknown_outcome_without_replaying():
    store = Store()
    tool = tools_for(Policy("crm.create"), store)["crm_contacts_create"]

    class Signal:
        def is_cancelled(self):
            return bool(store.calls)

    result = anyio.run(tool.execute, "call-1", {"payload": {"first_name": "Ada"}}, Signal())
    assert result.details["code"] == "outcome_unknown"
    assert len(store.calls) == 1


def test_large_collection_result_is_bounded():
    class LargeStore(Store):
        def collection(self, resource, scope):
            return {"items": [{"text": "x" * 129_000}], "pageInfo": {}}

    tool = tools_for(Policy("crm.read"), LargeStore())["crm_contacts_list"]
    result = run(tool, {})
    assert result.details["code"] == "result_too_large"
    assert len(result.text) < 200
