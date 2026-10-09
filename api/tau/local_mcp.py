"""Local-only MCP transport; CRM schemas and business rules live in the API."""

import json
import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tau_agent.messages import TextContent
from tau_agent.tools import AgentTool, AgentToolResult

MAX_RESULT_CHARS = 1_000_000


class _List(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Call(_List):
    tool: str = Field(min_length=1, max_length=128)
    arguments: dict = Field(default_factory=dict)


def _endpoint() -> str:
    origin = os.environ.get("CRM_LOCAL_API_ORIGIN", "http://127.0.0.1:38641")
    url = urlsplit(origin)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "::1", "localhost"}
        or url.username is not None
        or url.password is not None
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
        or url.port is None
    ):
        raise ValueError("CRM_LOCAL_API_ORIGIN must be an HTTP loopback origin with a port")
    return origin.rstrip("/") + "/mcp"


def _http_client():
    return httpx.AsyncClient(timeout=60, trust_env=False)


@asynccontextmanager
async def _session(endpoint):
    # No credentials, identities or sessions are cached. The loopback CRM
    # launcher supplies and verifies its own saved local SDK sign-in.
    async with _http_client() as http:
        async with streamable_http_client(endpoint, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def _result(data):
    text = json.dumps(data, ensure_ascii=False)
    if len(text) > MAX_RESULT_CHARS:
        data = {"code": "result_too_large", "message": "Narrow the CRM query"}
        text = json.dumps(data)
    return AgentToolResult(content=[TextContent(text=text)], details=data)


def local_mcp_tools() -> tuple[AgentTool, ...]:
    if os.environ.get("TAU_LOCAL_MODE", "").lower() not in {"true", "1", "yes", "on"}:
        return ()
    if os.environ.get("APP_NAME") or os.environ.get("MAINSEQUENCE_CALLER_AUTH_MODE") == "assertion":
        raise ValueError("The local CRM bridge cannot run in a hosted runtime")
    endpoint = _endpoint()

    def tool(name, model, *, call):
        async def execute(tool_call_id, arguments, signal=None, on_update=None):
            del tool_call_id, on_update
            try:
                parsed = model.model_validate(dict(arguments))
            except (ValidationError, TypeError, ValueError):
                return _result({"code": "invalid_arguments"})
            if signal is not None and signal.is_cancelled():
                return _result({"code": "cancelled", "message": "The call was not started"})
            sent = False
            try:
                with anyio.fail_after(60):
                    async with _session(endpoint) as session:
                        if signal is not None and signal.is_cancelled():
                            return _result({"code": "cancelled"})
                        if call:
                            sent = True
                            result = await session.call_tool(parsed.tool, parsed.arguments)
                            data = result.model_dump(mode="json", exclude_none=True)
                        else:
                            result = await session.list_tools()
                            data = result.model_dump(mode="json", exclude_none=True)
            except Exception:
                # No retry: a failed response may follow a committed write.
                return _result({
                    "code": "outcome_unknown" if sent else "unavailable",
                    "message": (
                        "Read current CRM state before retrying; the call may have completed"
                        if sent else "The local CRM MCP endpoint is unavailable"
                    ),
                })
            if signal is not None and signal.is_cancelled():
                return _result({
                    "code": "outcome_unknown" if sent else "cancelled",
                    "message": "Read current CRM state before any retry",
                })
            return _result(data)

        return AgentTool(
            name=name,
            label=name,
            description=(
                "Call a CRM MCP tool by name; use crm__list_tools for its input schema."
                if call else "List the CRM application's MCP tools and input schemas."
            ),
            parameters=model.model_json_schema(),
            execute_fn=execute,
            execution_mode="sequential" if call else "parallel",
        )

    return (
        tool("crm__list_tools", _List, call=False),
        tool("crm__call_tool", _Call, call=True),
    )
