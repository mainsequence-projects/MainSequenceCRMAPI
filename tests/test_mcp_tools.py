"""Actual MCP protocol shares the REST service and verified caller boundary."""

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import anyio
import httpx2
import pytest
from fastapi.testclient import TestClient
from tau_coding.extensions.loader import load_extensions
from tau_coding.resources import TauResourcePaths

from api.crm.main import create_app
from api.crm.mcp_tools import CRMToolRuntime, build_crm_tools
from api.tau.local_mcp import local_mcp_tools
from src.crm.services.operations import CRMContext
from src.crm.solution_selling.models import ProspectingProfileCreate

ACTOR = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CONTACT = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
AGENT = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


class WorkflowReads:
    """Read ports deliberately have no mutation method."""

    def __init__(self):
        self.deal, self.company, self.interaction, self.profile, self.prompter, self.assessment = (
            str(uuid.uuid4()) for _ in range(6)
        )
        def record(uid, **fields):
            return {"uid": uid, "version": 7, **fields}
        self.data = {
            "deals": record(self.deal, company_uid=self.company),
            "companies": record(self.company, name="Example Company"),
            "contacts": record(str(CONTACT), first_name="Ada"),
            "interactions": record(self.interaction, company_uid=self.company, deal_uid=self.deal),
            "assessments": record(self.assessment, company_uid=self.company, deal_uid=self.deal,
                                  key_players=[{"contact_uid": str(CONTACT), "pain": "Delay",
                                                "status": "reported", "reasons": []}], pain_chain=[]),
            "prospecting-profiles": record(self.profile, **ProspectingProfileCreate(
                name="Research", market_context="Funds", role="Researcher", potential_pain="Delay",
                diagnosis_template={"open": {"reasons": [{"question": "What causes the delay?"}]}},
            ).model_dump(mode="json")),
            "prompters": record(self.prompter, template="Hi {{ contact.first_name }} at {{ company.name }}"),
        }
        self.calls = []
        self.no_assessment = False

    def detail(self, resource, uid):
        self.calls.append((resource, str(uid)))
        assert str(uid) == self.data[resource]["uid"]
        return self.data[resource]

    def collection(self, resource, **scope):
        self.calls.append((resource, scope))
        assert scope["filters"] == {"deal_uid": self.deal}
        items = [] if resource == "assessments" and self.no_assessment else [self.data[resource]]
        return {"items": items, "pageInfo": {"pageIndex": scope["page_index"],
                "pageSize": scope["page_size"], "totalItems": len(items),
                "hasNextPage": False, "hasPreviousPage": scope["page_index"] > 0}}

    def scenarios(self):
        return [
            ("crm_prompters_render", {"uid": self.prompter, "payload": {
                "contact_uid": str(CONTACT), "company_uid": self.company}},
             f"/extensions/solution-selling/prompters/{self.prompter}/render/", True),
            ("crm_solution_selling_context_get", {"deal_uid": self.deal,
                "interaction_page_size": 2}, "/extensions/solution-selling/context/", False),
            ("crm_diagnoses_prepare", {"interaction_uid": self.interaction, "contact_uid": str(CONTACT),
                "profile_uid": self.profile, "solution_selling_uid": self.assessment},
             "/extensions/solution-selling/diagnoses/prepare/", False),
        ]


def test_solution_selling_helpers_match_rest_and_preserve_evidence(signed_caller):
    store = WorkflowReads()
    app = app_for(Policy("crm.read"), store)
    app.state.crm_record_store = store
    with TestClient(app, headers=delegated(signed_caller)) as client:
        results = []
        for tool, args, route, wrapped in store.scenarios():
            result = call(client, tool, args)
            response = client.post(route, json=args["payload"] if wrapped else args)
            assert response.status_code == 200, response.text
            assert result["structuredContent"] == {"code": "ok", "data": response.json()}
            results.append(response.json())
    assert results[0]["text"] == "Hi Ada at Example Company"
    assert results[0]["subject"] is None and results[0]["is_valid"] is True
    context, prepared = results[1:]
    assert context["assessment"]["key_players"][0]["status"] == "reported"
    assert context["interactions"]["pageInfo"]["pageSize"] == 2
    assert all(s["version"] == 7 for s in context["sources"])
    assert prepared["saved"] is False and prepared["business_issue_status"] == "hypothesis"
    assert prepared["draft"]["matrix"]["open"]["reasons"] == [
        {"question": "What causes the delay?", "answer": None}]
    assert "uid" not in prepared["draft"] and prepared["draft"]["conclusion"] is None
    prepared["draft"]["matrix"]["open"]["reasons"][0]["question"] = "Edited"
    assert store.data["prospecting-profiles"]["diagnosis_template"]["open"]["reasons"][0]["question"] != "Edited"


def test_solution_selling_helpers_recheck_permissions_and_reject_spoofing(signed_caller):
    store = WorkflowReads()
    app = app_for(Policy(), store)
    app.state.crm_record_store = store
    with TestClient(app, headers=delegated(signed_caller)) as client:
        for tool, args, _route, _wrapped in store.scenarios():
            assert call(client, tool, args)["structuredContent"]["code"] == "forbidden"
            assert call(client, tool, args | {"actor_uid": str(AGENT)})["structuredContent"]["code"] == "invalid_arguments"
    assert store.calls == []


def test_solution_selling_helpers_validate_relations_and_bounds(signed_caller):
    store = WorkflowReads()
    app = app_for(Policy("crm.read"), store)
    app.state.crm_record_store = store
    with TestClient(app, headers=delegated(signed_caller)) as client:
        assert call(client, "crm_solution_selling_context_get", {
            "deal_uid": store.deal, "interaction_page_size": 21,
        })["structuredContent"]["code"] == "invalid_arguments"
        assert store.calls == []
        store.data["assessments"]["company_uid"] = str(uuid.uuid4())
        for tool, args, _route, _wrapped in store.scenarios()[1:]:
            assert call(client, tool, args)["structuredContent"]["code"] == "validation_error"
        store.data["prompters"]["template"] = "{{ inputs.secret_missing }}"
        result = call(client, *store.scenarios()[0][:2])
        assert result["structuredContent"]["code"] == "validation_error"
        assert "secret_missing" not in json.dumps(result)
        store.no_assessment = True
        context = call(client, "crm_solution_selling_context_get", {"deal_uid": store.deal})
        assert context["structuredContent"]["data"]["assessment"] is None
        store.data["prospecting-profiles"]["diagnosis_template"] = None
        prepared = call(client, "crm_diagnoses_prepare", {"interaction_uid": store.interaction,
            "contact_uid": str(CONTACT), "profile_uid": store.profile})["structuredContent"]["data"]
        assert all(cell == [] for row in prepared["draft"]["matrix"].values() for cell in row.values())


def test_record_list_filters_are_precise_and_helpers_follow_activation(config_file, signed_caller):
    with TestClient(app_for(Policy("crm.read")), headers=delegated(signed_caller)) as client:
        catalogue = {t["name"]: t for t in rpc(client, "tools/list")["tools"]}
        filters = catalogue["crm_diagnoses_list"]["inputSchema"]["$defs"]["DiagnosesToolFilters"]
        assert set(filters["properties"]) == {"interaction_uid", "contact_uid", "solution_selling_uid"}
        assert filters["additionalProperties"] is False
        assert call(client, "crm_diagnoses_list", {"filters": {"owner_uid": str(ACTOR)}})["structuredContent"]["code"] == "invalid_arguments"
        for name in ("crm_prompters_render", "crm_solution_selling_context_get", "crm_diagnoses_prepare"):
            assert catalogue[name]["annotations"]["readOnlyHint"] is True
    config_file(solution_selling=False)
    names = {t.definition.name for t in build_crm_tools(lambda: None)}
    assert not {"crm_prompters_render", "crm_solution_selling_context_get", "crm_diagnoses_prepare"} & names

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



def app_for(policy=None, store=None):
    app = create_app()
    app.state.crm_policy = policy
    app.state.crm_directory = Directory()
    app.state.crm_resources = store
    return app


def delegated(caller, person=ACTOR):
    return caller(AGENT, requester={
        "sub": str(person), "is_organization_admin": False,
    })


def rpc(client, method, params=None, *, headers=None):
    response = client.post("/mcp", headers={
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25", **(headers or {}),
    }, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    assert response.status_code == 200, response.text
    assert "mcp-session-id" not in response.headers
    return response.json()["result"]


def call(client, name, arguments=None, **kwargs):
    return rpc(client, "tools/call", {"name": name, "arguments": arguments or {}}, **kwargs)


def test_mcp_contact_create_update_match_http_shared_commands(signed_caller):
    policy = Policy("crm.create", "crm.edit")
    tool_store, http_store = Store(), Store()
    with TestClient(app_for(policy, tool_store), headers=delegated(signed_caller)) as mcp:
        http = TestClient(app_for(policy, http_store), headers=signed_caller(ACTOR))
        create = {"first_name": "  Ada  ", "emails": []}
        result = call(mcp, "crm_contacts_create", {"payload": create})
        response = http.post("/api/crm/v1/contacts/", json=create)
        assert response.status_code == 201
        assert result["structuredContent"] == {"code": "ok", "data": response.json()}
        assert result["isError"] is False
        assert tool_store.calls == http_store.calls
        patch = {"expected_version": 1, "changes": {"first_name": "Grace"}}
        result = call(mcp, "crm_contacts_update", {"uid": str(CONTACT), "payload": patch})
        response = http.patch(f"/api/crm/v1/contacts/{CONTACT}/", json=patch)
        assert response.status_code == 200
        assert result["structuredContent"] == {"code": "ok", "data": response.json()}
        assert tool_store.calls == http_store.calls


def test_protocol_initialize_catalogue_and_strict_validation(signed_caller):
    store = Store()
    with TestClient(app_for(Policy(), store), headers=delegated(signed_caller)) as client:
        init = rpc(client, "initialize", {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "crm-test", "version": "1"},
        })
        assert init["serverInfo"]["name"] == "crm"
        catalogue = rpc(client, "tools/list")["tools"]
        assert len(catalogue) == 70
        names = {tool["name"] for tool in catalogue}
        assert "crm_contacts_archive" not in names
        assert "crm_contacts_merge_execute" not in names
        assert sum(t["annotations"]["readOnlyHint"] for t in catalogue) == 39
        result = call(client, "crm_contacts_create", {"payload": {"first_name": "Ada"}})
        assert result["structuredContent"]["code"] == "forbidden"
        result = call(client, "crm_contacts_create", {
            "payload": {"first_name": "Ada"}, "actor_uid": "secret-spoofed-identity",
        })
        assert result["structuredContent"]["code"] == "invalid_arguments"
        assert "secret-spoofed-identity" not in json.dumps(result)
        assert result["isError"] is True
        result = call(client, "crm_contacts_list", {"filters": {"has_open_tasks": 1}})
        assert result["structuredContent"]["code"] == "invalid_arguments"
        assert store.calls == []


def test_requester_and_unbound_workload_have_no_identity_or_permission_cache(signed_caller, monkeypatch):
    class PerPersonPolicy:
        def __init__(self):
            self.people = []

        def capabilities(self, actor_uid):
            self.people.append(actor_uid)
            return {"crm.create"} if actor_uid in {ACTOR, AGENT} else set()

    policy, store = PerPersonPolicy(), Store()
    monkeypatch.setattr(
        "api.crm.mcp_server.User.get_by_uid",
        lambda uid: SimpleNamespace(is_active=True, identity_type="workload"),
    )
    with TestClient(app_for(policy, store)) as client:
        args = {"payload": {"first_name": "Ada"}}
        assert call(client, "crm_contacts_create", args,
                    headers=delegated(signed_caller))["structuredContent"]["code"] == "ok"
        assert call(client, "crm_contacts_create", args,
                    headers=delegated(signed_caller, CONTACT))["structuredContent"]["code"] == "forbidden"
        assert call(client, "crm_contacts_create", args,
                    headers=signed_caller(AGENT))["structuredContent"]["code"] == "forbidden"
        assert policy.people == [ACTOR, CONTACT]
        assert len(store.calls) == 1
        for headers in ({}, {"X-User-UID": str(ACTOR)}, signed_caller(AGENT, requester={"sub": str(ACTOR)})):
            assert client.post("/mcp", headers=headers, json={}).status_code == 401
        assert len(store.calls) == 1


def test_concurrent_mcp_calls_keep_each_requester(signed_caller):
    rendezvous = threading.Barrier(2)

    class ConcurrentStore(Store):
        def create(self, *args):
            rendezvous.wait(timeout=5)
            return super().create(*args)

    policy = SimpleNamespace(capabilities=lambda actor: {"crm.create"})
    store = ConcurrentStore()
    with TestClient(app_for(policy, store)) as client:
        def create(person):
            return call(client, "crm_contacts_create", {
                "payload": {"first_name": str(person)},
            }, headers=delegated(signed_caller, person))

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, [ACTOR, CONTACT]))
        assert all(r["structuredContent"]["code"] == "ok" for r in results)
        assert {(str(c[2]), c[3]["first_name"]) for c in store.calls} == {
            (str(ACTOR), str(ACTOR)), (str(CONTACT), str(CONTACT)),
        }


def test_disabled_module_runtime_unavailable_and_transport_guard(signed_caller, config_file):
    config_file(solution_selling=False)
    with TestClient(app_for(), headers=delegated(signed_caller)) as client:
        tools = rpc(client, "tools/list")["tools"]
        assert len(tools) == 46
        assert "crm_leads_list" not in {t["name"] for t in tools}
        assert call(client, "crm_leads_list")["structuredContent"]["code"] == "not_found"
        assert call(client, "crm_contacts_list")["structuredContent"]["code"] == "unavailable"
        assert client.get("/mcp").status_code == 405
        assert client.post("/mcp", headers={"Origin": "https://untrusted.example"}, json={}).status_code == 403
        assert client.get("/healthz").status_code == 200


def test_large_result_and_safe_failure(signed_caller):
    class LargeStore(Store):
        def collection(self, resource, scope):
            return {"items": [{"text": "x" * 129_000}], "pageInfo": {}}

        def create(self, *args):
            raise RuntimeError("secret-token")

    with TestClient(app_for(Policy("crm.read", "crm.create"), LargeStore()),
                    headers=delegated(signed_caller)) as client:
        result = call(client, "crm_contacts_list")
        assert result["structuredContent"]["code"] == "result_too_large"
        assert len(json.dumps(result)) < 400
        result = call(client, "crm_contacts_create", {"payload": {"first_name": "Ada"}})
        assert result["structuredContent"]["code"] == "internal_error"
        assert "secret-token" not in json.dumps(result)


def test_cancellation_never_replays_a_started_write():
    started, release = threading.Event(), threading.Event()

    class SlowStore(Store):
        def create(self, *args):
            started.set()
            release.wait(5)
            return super().create(*args)

    store = SlowStore()
    tool = next(t for t in build_crm_tools(lambda: CRMToolRuntime(
        CRMContext(ACTOR, Policy("crm.create"), Directory()), resources=store,
    )) if t.definition.name == "crm_contacts_create")

    async def scenario():
        async with anyio.create_task_group() as group:
            group.start_soon(tool.invoke, {"payload": {"first_name": "Ada"}})
            await anyio.to_thread.run_sync(started.wait, 5)
            assert started.is_set()
            group.cancel_scope.cancel()
            release.set()

    anyio.run(scenario)
    assert len(store.calls) == 1


def test_local_bridge_uses_real_mcp_protocol_and_no_duplicate_tools(monkeypatch, local_sign_in):
    from api.crm.local import create_app as local_app

    monkeypatch.setenv("TAU_LOCAL_MODE", "true")
    local_sign_in.as_user(SimpleNamespace(uid=ACTOR, username="local"))
    app = local_app()
    store = Store()
    app.state.crm_resources = store
    monkeypatch.setattr("api.tau.local_mcp._http_client", lambda: httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app, client=("127.0.0.1", 1234)),
    ))
    tools = {t.name: t for t in local_mcp_tools()}
    assert set(tools) == {"crm__list_tools", "crm__call_tool"}

    async def scenario():
        async with app.router.lifespan_context(app):
            catalogue = await tools["crm__list_tools"].execute("list", {})
            assert len(catalogue.details["tools"]) == 70
            result = await tools["crm__call_tool"].execute("create", {
                "tool": "crm_contacts_create", "arguments": {"payload": {"first_name": "Ada"}},
            })
            assert result.details["structuredContent"]["code"] == "ok"

    anyio.run(scenario)
    assert len(store.calls) == 1


@pytest.mark.parametrize("origin", ["https://example.test", "http://127.0.0.1:8000/evil", "http://user:secret@127.0.0.1:8000"])
def test_local_bridge_rejects_remote_or_credentialed_endpoints(monkeypatch, origin):
    monkeypatch.setenv("TAU_LOCAL_MODE", "true")
    monkeypatch.setenv("CRM_LOCAL_API_ORIGIN", origin)
    with pytest.raises(ValueError):
        local_mcp_tools()


def test_hosted_extension_registers_no_native_business_tools(monkeypatch):
    monkeypatch.setenv("TAU_LOCAL_MODE", "false")
    assert local_mcp_tools() == ()


@pytest.mark.parametrize("local", [False, True])
def test_effective_project_extension_catalogue(monkeypatch, tmp_path, local):
    monkeypatch.setenv("TAU_LOCAL_MODE", str(local).lower())
    loaded = load_extensions(
        TauResourcePaths(root=tmp_path, cwd=Path(__file__).parents[1]),
        include_project_dir=True, include_user_dir=False,
    )
    assert not loaded.diagnostics
    tools = []
    for extension in loaded.extensions:
        extension.setup(SimpleNamespace(register_tool=tools.append))
    assert {t.name for t in tools} == (
        {"crm__list_tools", "crm__call_tool"} if local else set()
    )


def test_local_bridge_lost_write_response_is_redacted_and_never_retried(monkeypatch):
    monkeypatch.setenv("TAU_LOCAL_MODE", "true")
    calls = []

    class Session:
        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            raise RuntimeError("private-token-in-transport-error")

    @asynccontextmanager
    async def session(endpoint):
        yield Session()

    monkeypatch.setattr("api.tau.local_mcp._session", session)
    tool = local_mcp_tools()[1]
    result = anyio.run(tool.execute, "write", {"tool": "crm_contacts_create"})
    assert result.details["code"] == "outcome_unknown"
    assert len(calls) == 1
    assert "private-token" not in result.text
    assert "Read current CRM state" in result.text


def test_local_bridge_cancel_before_dispatch_does_not_connect(monkeypatch):
    monkeypatch.setenv("TAU_LOCAL_MODE", "true")

    def unexpected(endpoint):
        pytest.fail("A cancelled call must not connect")

    monkeypatch.setattr("api.tau.local_mcp._session", unexpected)
    result = anyio.run(
        local_mcp_tools()[1].execute, "write", {"tool": "crm_contacts_create"},
        SimpleNamespace(is_cancelled=lambda: True),
    )
    assert result.details["code"] == "cancelled"
