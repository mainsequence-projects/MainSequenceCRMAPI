"""Stateless application MCP, inside the API's verified identity boundary."""

from fastapi import FastAPI, HTTPException
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from api.crm.mcp_tools import CRMToolRuntime, build_crm_tools, tool_result
from api.crm.service_adapter import context_for
from mainsequence.client import User
from mainsequence.server.fastapi import install_mcp
from src.crm.platform.runtime import request_port
from src.crm.services.operations import AccessDenied, ServiceUnavailable


def install_crm_mcp(application: FastAPI) -> None:
    server = Server("crm", version="1")

    def runtime() -> CRMToolRuntime:
        request = server.request_context.request
        if request is None:
            raise ServiceUnavailable("Missing HTTP request context")
        # Hosted CRM tools serve a person. A verified workload alone is not a
        # substitute when delegation is absent, expired, or refused.
        if application.state.mainsequence_request_identity["mode"] != "local":
            if User.get_requester() is None:
                raise AccessDenied("A verified requester is required")
        try:
            context = context_for(request)
        except HTTPException as exc:
            if exc.status_code in {401, 403}:
                raise AccessDenied("CRM identity required") from exc
            raise ServiceUnavailable("CRM policy or directory unavailable") from exc
        return CRMToolRuntime(
            context,
            resources=request_port(request, "crm_resources"),
            records=request_port(request, "crm_record_store"),
            bootstrap=request_port(request, "crm_bootstrap"),
        )

    catalogue = {tool.definition.name: tool for tool in build_crm_tools(runtime)}

    @server.list_tools()
    async def list_tools():
        return [tool.definition for tool in catalogue.values()]

    # Our Pydantic boundary validates strictly and redacts invalid inputs. The
    # SDK's default schema error includes the supplied value in its message.
    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        tool = catalogue.get(name)
        if tool is None:
            return tool_result("not_found", message="CRM tool not found")
        return await tool.invoke(arguments)

    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True)
    install_mcp(application, manager.handle_request, lifespan=manager.run)
