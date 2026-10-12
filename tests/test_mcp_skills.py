"""Exercise the SDK skill publisher through the CRM's protected MCP endpoint."""

import hashlib
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import anyio
import httpx2
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from api.crm.main import create_app

try:
    from mcp.shared.skills import ListSkillsRequest, ListSkillsResult
except ImportError:
    # Main Sequence ships the official extension until MCP includes it natively.
    from mainsequence.server._mcp_skills_upstream.shared import ListSkillsRequest, ListSkillsResult

PACK = Path(__file__).resolve().parents[1] / ".agents/skills/mainsequence_crm"
ACTOR = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
EXTENSION = "io.modelcontextprotocol/skills"
RPC_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-11-25",
}


def request_body(method, params=None):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


def rpc(client, method, params=None):
    response = client.post("/mcp", headers=RPC_HEADERS, json=request_body(method, params))
    assert response.status_code == 200, response.text
    assert "mcp-session-id" not in response.headers
    return response.json()


@pytest.mark.parametrize("identity_fixture", ["local_backend", "signed_caller"])
@pytest.mark.parametrize("solution_selling", [True, False])
def test_published_pack_matches_files_and_all_links_are_served(
    request, config_file, identity_fixture, solution_selling
):
    identity = request.getfixturevalue(identity_fixture)
    headers = identity.sign_in(ACTOR) if identity_fixture == "local_backend" else identity(ACTOR)
    config_file(solution_selling=solution_selling)
    with TestClient(create_app(), headers=headers) as client:
        skills = rpc(client, "skills/list")["result"]["skills"]
        expected = {"skill://" + path.relative_to(PACK).as_posix() for path in PACK.rglob("SKILL.md")}
        assert {skill["uri"] for skill in skills} == expected
        assert len(skills) == 5
        served = {}
        for skill in skills:
            assert rpc(client, "skills/get", {"uri": skill["uri"]})["result"]["skill"] == skill
            for resource in skill["resources"]:
                uri = urlsplit(resource["uri"])
                source = PACK / uri.netloc / uri.path.lstrip("/")
                data = source.read_bytes()
                result = rpc(client, "resources/read", {"uri": resource["uri"]})["result"]
                actual = result["contents"][0]
                assert actual["uri"] == resource["uri"]
                assert actual["text"].encode() == data
                assert len(data) == resource["size"]
                assert "sha256:" + hashlib.sha256(data).hexdigest() == resource["digest"]
                assert resource["uri"] not in served
                served[resource["uri"]] = actual["text"]
        assert len(served) == 8
        for uri, text in served.items():
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if target.startswith("skill://"):
                    destination = target
                else:
                    # urljoin does not treat the custom skill scheme as relative.
                    destination = urljoin(uri.replace("skill://", "https://", 1), target)
                    destination = destination.replace("https://", "skill://", 1)
                assert destination.split("#", 1)[0] in served, (uri, target)
        tools = rpc(client, "tools/list")["result"]["tools"]
        assert len(tools) == (69 if solution_selling else 46)


def test_skill_methods_require_identity_and_approved_origin(local_backend):
    valid = local_backend.sign_in(ACTOR)
    operations = [
        ("skills/list", {}),
        ("skills/get", {"uri": "skill://crm-core/SKILL.md"}),
        ("resources/read", {"uri": "skill://crm-core/references/mcp-usage.md"}),
    ]
    with TestClient(create_app()) as client:
        for method, params in operations:
            for headers in ({}, {"Authorization": "Bearer invalid", "Mcp-Session-Id": "invalid"}):
                response = client.post("/mcp", headers=RPC_HEADERS | headers, json=request_body(method, params))
                assert response.status_code == 401
            response = client.post(
                "/mcp", headers=RPC_HEADERS | valid | {"Origin": "https://untrusted.example"},
                json=request_body(method, params),
            )
            assert response.status_code == 403


def test_only_files_in_published_skills_are_readable(local_backend):
    with TestClient(create_app(), headers=local_backend.sign_in(ACTOR)) as client:
        for uri in (
            "skill://build-mainsequence-crm-api/SKILL.md",
            "skill://crm-core/../mainsequence_crm_development/build-mainsequence-crm-api/SKILL.md",
            (PACK.parents[2] / "AGENTS.md").as_uri(),
        ):
            result = rpc(client, "resources/read", {"uri": uri})
            assert "error" in result and "result" not in result
        result = rpc(client, "skills/get", {"uri": "skill://unknown/SKILL.md"})
        assert "error" in result and "result" not in result


def test_modern_client_discovers_skill_extension_from_any_working_directory(
    local_backend, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    app = create_app()
    headers = local_backend.sign_in(ACTOR)

    async def scenario():
        async with app.router.lifespan_context(app), httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), headers=headers,
        ) as http:
            async with streamable_http_client("http://127.0.0.1:9999/mcp", http_client=http) as (read, write):
                async with ClientSession(read, write, extensions={EXTENSION: {}}) as session:
                    discovery = await session.discover()
                    assert EXTENSION in discovery.capabilities.extensions
                    skills = await session.send_request(ListSkillsRequest(), ListSkillsResult)
                    assert len(skills.skills) == 5
                    result = await session.read_resource("skill://crm-core/SKILL.md")
                    assert result.contents[0].text == (PACK / "crm-core/SKILL.md").read_text()
                    assert len((await session.list_tools()).tools) == 69

    anyio.run(scenario)
