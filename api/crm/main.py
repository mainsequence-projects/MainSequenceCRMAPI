"""FastAPI release entrypoint for CRM."""

import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.crm.platform.runtime import authenticated_actor, readiness, request_port

from .affiliation_routes import router as affiliation_router
from .resource_routes import router as resource_router
from .routes import router as crm_router
from .transfer_routes import router as transfer_router


def create_app() -> FastAPI:
    application = FastAPI(title="Main Sequence CRM", version="0.1.0")

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


def crm_readiness(request: Request, actor_uid=Depends(authenticated_actor)):
    result = readiness(request, actor_uid)
    return JSONResponse(result, status_code=200 if result["status"] == "ready" else 503)


def bootstrap(request: Request, actor_uid=Depends(authenticated_actor)):
    result = readiness(request, actor_uid)
    if result["status"] != "ready":
        return JSONResponse(
            _error(request, "CRM_NOT_READY", "CRM setup is incomplete."),
            status_code=503,
        )
    bootstrap_port = request_port(request, "crm_bootstrap")
    if bootstrap_port is None:
        return JSONResponse(
            _error(request, "CRM_NOT_READY", "CRM bootstrap service is unavailable."),
            status_code=503,
        )
    try:
        return bootstrap_port.read(actor_uid)
    except Exception:
        return JSONResponse(
            _error(request, "CRM_NOT_READY", "CRM settings are unavailable."),
            status_code=503,
        )


app = create_app()
