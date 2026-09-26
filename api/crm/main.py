"""FastAPI release entrypoint for CRM."""

import asyncio
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.crm.affiliation_routes import router as affiliation_router
from api.crm.google_routes import router as google_router
from api.crm.record_routes import core_router, module_router
from api.crm.resource_routes import router as resource_router
from api.crm.routes import router as crm_router
from api.crm.transfer_routes import router as transfer_router
from src.crm.assistant_runtime import resolve_assistant
from src.crm.config import crm_config
from src.crm.google_workspace.config import google_workspace_enabled
from src.crm.models.bootstrap import Bootstrap
from src.crm.platform.runtime import authenticated_actor, readiness, request_port
from src.crm.solution_selling.config import solution_selling_enabled

BOOTSTRAP_STAGE_TIMEOUT_SECONDS = 75


def create_app() -> FastAPI:
    crm_config()  # Fail before route mounting if the persisted configuration is invalid.
    application = FastAPI(title="Main Sequence CRM", version="0.1.0")
    application.state.crm_local_tau_origin = None

    @application.middleware("http")
    async def request_uid(request: Request, call_next):
        request.state.crm_request_uid = uuid.uuid4()
        return await call_next(request)

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {401: "IDENTITY_REQUIRED", 403: "PERMISSION_DENIED", 503: "CRM_NOT_READY"}.get(
            exc.status_code, "CRM_REQUEST_ERROR"
        )
        return JSONResponse(_error(request, code, str(exc.detail)), status_code=exc.status_code)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [
            {
                "path": ".".join(map(str, issue["loc"])),
                "code": issue["type"],
                "message": "Invalid value",
            }
            for issue in exc.errors()
        ]
        return JSONResponse(
            _error(request, "VALIDATION_ERROR", "Request validation failed", fields),
            status_code=422,
        )

    application.add_api_route("/healthz", healthz, methods=["GET"])
    application.add_api_route("/api/crm/v1/readiness/", crm_readiness, methods=["GET"])
    application.add_api_route("/api/crm/v1/bootstrap/", bootstrap, methods=["GET"])
    application.include_router(crm_router)
    application.include_router(resource_router)
    application.include_router(affiliation_router)
    application.include_router(transfer_router)
    if google_workspace_enabled():
        application.include_router(google_router)
    application.include_router(core_router)
    if solution_selling_enabled():
        application.include_router(module_router)
    return application


def _error(request: Request, code: str, message: str, fields: list[dict] | None = None) -> dict:
    value = {
        "code": code,
        "message": message,
        "request_uid": str(getattr(request.state, "crm_request_uid", uuid.uuid4())),
    }
    if fields is not None:
        value["fields"] = fields
    return {"error": value}


def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def _bounded_readiness(request: Request, actor_uid) -> dict:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(readiness, request, actor_uid),
            timeout=BOOTSTRAP_STAGE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        step = getattr(request.state, "crm_readiness_step", "platform-readiness")
        labels = {
            "policy": "CRM policy connection",
            "catalog": "Main Sequence MetaTable catalog",
            "crm-settings": "CRM settings",
            "directory": "Main Sequence user directory",
            "bootstrap": "CRM settings and default pipeline",
            "authorization": "CRM policy authorization",
        }
        label = labels.get(step, "CRM platform readiness")
        return {
            "status": "not_ready",
            "schema_version": "1",
            "application_version": "0.1.0",
            "checks": [{
                "id": step,
                "status": "failed",
                "message": f"{label} did not respond within {BOOTSTRAP_STAGE_TIMEOUT_SECONDS:g} seconds.",
            }],
        }


async def crm_readiness(request: Request, actor_uid=Depends(authenticated_actor)):
    result = await _bounded_readiness(request, actor_uid)
    return JSONResponse(result, status_code=200 if result["status"] == "ready" else 503)


async def bootstrap(request: Request, actor_uid=Depends(authenticated_actor)):
    result = await _bounded_readiness(request, actor_uid)
    if result["status"] != "ready":
        payload = _error(request, "CRM_NOT_READY", "CRM setup is incomplete.")
        payload["readiness"] = result
        return JSONResponse(
            payload,
            status_code=503,
        )
    bootstrap_port = request_port(request, "crm_bootstrap")
    if bootstrap_port is None:
        return JSONResponse(
            _error(request, "CRM_NOT_READY", "CRM bootstrap service is unavailable."),
            status_code=503,
        )
    try:
        document = getattr(request.state, "crm_bootstrap_document", None)
        if document is None:
            document = await asyncio.wait_for(
                asyncio.to_thread(bootstrap_port.read, actor_uid),
                timeout=BOOTSTRAP_STAGE_TIMEOUT_SECONDS,
            )
        document["readiness"] = result
        document["assistant"] = await resolve_assistant(
            request.app.state.crm_local_tau_origin
        )
        return Bootstrap.model_validate(document).model_dump(mode="json")
    except TimeoutError:
        return JSONResponse(
            _error(request, "CRM_NOT_READY", f"Main Sequence CRM settings or default pipeline did not respond within {BOOTSTRAP_STAGE_TIMEOUT_SECONDS:g} seconds."),
            status_code=503,
        )
    except Exception:
        return JSONResponse(
            _error(request, "CRM_NOT_READY", "CRM settings are unavailable."),
            status_code=503,
        )


app = create_app()
