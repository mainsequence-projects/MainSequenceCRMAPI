"""Stateless application MCP, inside the API's verified identity boundary."""

import contextvars
import logging

from fastapi import FastAPI, HTTPException, Request
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, Tool

from api.crm.mcp_tools import CRMToolRuntime, build_crm_tools, tool_result
from api.crm.service_adapter import context_for
from mainsequence.client import User
from mainsequence.server.fastapi import install_mcp, reads_as_caller
from mainsequence.server.mcp_skills import skills_extension
from src.crm.platform.diagnostics import observe_stage, request_diagnostics
from src.crm.platform.runtime import CAPABILITIES, request_port
from src.crm.services.operations import AccessDenied, ServiceUnavailable

logger = logging.getLogger(__name__)
_active_tool_name: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "crm_mcp_tool_name", default=None
)


def _required_capability(error: AccessDenied) -> str | None:
    message = str(error)
    suffix = " access denied"
    capability = message.removesuffix(suffix) if message.endswith(suffix) else None
    return capability if capability in CAPABILITIES else None


def _log_denial(
    request,
    *,
    identity_mode: str,
    reason: str,
    required_capability: str | None = None,
) -> None:
    fields = {
        "crm_mcp_tool": _active_tool_name.get(),
        "crm_request_uid": str(getattr(request.state, "crm_request_uid", "unknown")),
        "crm_mcp_identity_mode": identity_mode,
        "crm_mcp_denial_reason": reason,
        "crm_required_capability": required_capability,
    }
    logger.warning(
        "crm_mcp_access_denied tool=%(crm_mcp_tool)s request_uid=%(crm_request_uid)s "
        "identity_mode=%(crm_mcp_identity_mode)s reason=%(crm_mcp_denial_reason)s "
        "required_capability=%(crm_required_capability)s",
        fields,
        extra=fields,
    )


def _require_hosted_person(request) -> str:
    """Return the trusted effective-person mode or fail closed.

    Delegation is already verified by request identity. Without it, use the
    caller-scoped directory to distinguish a direct human from an unbound
    workload; request identities deliberately do not project identity type.
    """
    if User.get_requester() is not None:
        return "delegated_requester"
    caller = User.get_logged_user()
    try:
        with reads_as_caller():
            caller_record = User.get_by_uid(caller.uid)
            # Human directory projections omit identity_type. Prove the type
            # with the platform's exact filter instead of treating None as human.
            if caller_record.identity_type is None:
                humans = User.filter(uid=caller.uid, identity_type="human")
                if len(humans) != 1 or humans[0].uid != caller.uid:
                    _log_denial(request, identity_mode="direct_caller", reason="human_not_verified")
                    raise AccessDenied("Direct caller is not a verified person")
                caller_record = humans[0]
                if caller_record.is_active is not True:
                    _log_denial(request, identity_mode="direct_caller", reason="inactive_direct_caller")
                    raise AccessDenied("Direct caller is not an active person")
                return "direct_human"
    except AccessDenied:
        raise
    except Exception as exc:
        _log_denial(request, identity_mode="direct_caller", reason="caller_type_unavailable")
        raise ServiceUnavailable("Direct caller type could not be verified") from exc
    if caller_record.is_active is not True:
        _log_denial(request, identity_mode="direct_caller", reason="inactive_direct_caller")
        raise AccessDenied("Direct caller is not an active person")
    if caller_record.identity_type != "human":
        reason = "unbound_workload" if caller_record.identity_type == "workload" else "nonhuman_caller"
        _log_denial(request, identity_mode="direct_caller", reason=reason)
        raise AccessDenied("Direct caller is not a person")
    return "direct_human"


def install_crm_mcp(application: FastAPI) -> None:
    active_request: contextvars.ContextVar[Request | None] = contextvars.ContextVar(
        "crm_mcp_request", default=None
    )

    def runtime() -> CRMToolRuntime:
        request = active_request.get()
        if request is None:
            raise ServiceUnavailable("Missing HTTP request context")
        with observe_stage("identity"):
            identity_mode = "local"
            if application.state.mainsequence_request_identity["mode"] != "local":
                identity_mode = _require_hosted_person(request)
            try:
                context = context_for(request)
            except HTTPException as exc:
                if exc.status_code in {401, 403}:
                    _log_denial(request, identity_mode=identity_mode, reason="crm_identity_rejected")
                    raise AccessDenied("CRM identity required") from exc
                raise ServiceUnavailable("CRM policy or directory unavailable") from exc

        def report_denial(error: AccessDenied) -> None:
            required_capability = _required_capability(error)
            _log_denial(
                request,
                identity_mode=identity_mode,
                reason="missing_capability" if required_capability else "access_denied",
                required_capability=required_capability,
            )

        return CRMToolRuntime(
            context,
            resources=request_port(request, "crm_resources"),
            records=request_port(request, "crm_record_store"),
            bootstrap=request_port(request, "crm_bootstrap"),
            denial_reporter=report_denial,
        )

    catalogue = {tool.definition.name: tool for tool in build_crm_tools(runtime)}

    class CRMMCPServer(MCPServer):
        # Preserve the authored schemas and strict, redacted CRM validation
        # through MCPServer's public tool methods. The SDK owns skill resources.
        async def list_tools(self) -> list[Tool]:
            return [tool.definition for tool in catalogue.values()]

        async def call_tool(
            self, name: str, arguments: dict, context: Context | None = None
        ) -> CallToolResult:
            if context is None:
                return tool_result("unavailable", message="Missing HTTP request context")
            token = _active_tool_name.set(name)
            try:
                tool = catalogue.get(name)
                if tool is None:
                    return tool_result("not_found", message="CRM tool not found")
                return await tool.invoke(arguments)
            finally:
                _active_tool_name.reset(token)

    server = CRMMCPServer(
        "crm", version="1",
        extensions=[skills_extension(".agents/skills/mainsequence_crm")],
    )
    # install_mcp owns authentication and browser Origin admission for both
    # platform release hosts and local URLs, as with the previous transport.
    transport = server.streamable_http_app(
        stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    async def crm_transport(scope, receive, send):
        # Capture the owning FastAPI request before the SDK's nested Starlette
        # app replaces scope["app"]. CRM ports live on this FastAPI application;
        # caller identity still comes exclusively from SDK-verified getters.
        request_token = active_request.set(Request(dict(scope), receive))
        try:
            request = active_request.get()
            with request_diagnostics(getattr(request.state, "crm_request_uid", None)):
                await transport(scope, receive, send)
        finally:
            active_request.reset(request_token)

    install_mcp(application, crm_transport, lifespan=server.session_manager.run)
