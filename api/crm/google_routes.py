"""Google Workspace connection routes; Google callback has no CRM bearer dependency."""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from src.crm.google_workspace.imports import GoogleImports, ImportDecision, PreviewQuery
from src.crm.google_workspace.service import GoogleWorkspaceService

from .service_adapter import context_for, invoke

router = APIRouter(prefix="/extensions/google")


class OAuthStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["contacts", "gmail", "calendar"]


class OAuthComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completion_handle: str = Field(min_length=32, max_length=512)


def _actor(request: Request) -> uuid.UUID:
    context = context_for(request)
    invoke(lambda: context.require("crm.transfer.import"))
    return context.actor_uid


def _service(request: Request) -> GoogleWorkspaceService:
    supplied = getattr(request.app.state, "crm_google_service", None)
    if supplied is not None:
        return supplied
    try:
        return _configured_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Google integration is not configured") from exc


@lru_cache(maxsize=1)
def _configured_service() -> GoogleWorkspaceService:
    return GoogleWorkspaceService()


@router.post("/oauth/start/")
def oauth_start(request: Request, payload: OAuthStart):
    actor = _actor(request)
    return invoke(lambda: _service(request).start(actor, payload.source))


@router.get("/oauth/callback/", include_in_schema=True)
def oauth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    # Google redirects here outside the delegated Command Center transport.
    destination = _service(request).callback(code=code, state=state, error=error)
    return RedirectResponse(destination, status_code=303, headers={"Cache-Control": "no-store"})


@router.get("/oauth/done/", response_class=HTMLResponse)
def oauth_done(google_status: str = "failed"):
    message = "Google authorization finished. Return to the CRM window and close this tab." if google_status == "ready" else "Google authorization did not finish. Return to the CRM window and try again."
    return HTMLResponse(
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Google connection</title>"
        f"<main><h1>Google connection</h1><p>{message}</p></main></html>",
        headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; style-src 'none'; frame-ancestors 'none'"},
    )


@router.get("/oauth/attempts/{uid}/")
def oauth_attempt_status(uid: uuid.UUID, request: Request, response: Response):
    actor = _actor(request)
    response.headers["Cache-Control"] = "no-store"
    return invoke(lambda: _service(request).attempt_status(actor, uid))


@router.post("/oauth/complete/")
def oauth_complete(request: Request, payload: OAuthComplete):
    actor = _actor(request)
    return invoke(lambda: _service(request).complete(actor, payload.completion_handle))


@router.get("/connections/")
def google_connections(request: Request):
    actor = _actor(request)
    supplied = getattr(request.app.state, "crm_google_service", None)
    connection = invoke(lambda: supplied.connection(actor) if supplied is not None else GoogleWorkspaceService.connection_without_google_config(actor))
    return {"items": [connection] if connection else []}


@router.post("/connections/{uid}/disconnect/")
def google_disconnect(uid: uuid.UUID, request: Request):
    actor = _actor(request)
    return invoke(lambda: _service(request).disconnect(actor, uid))


@router.get("/calendars/")
def google_calendars(request: Request):
    actor = _actor(request)
    return invoke(lambda: GoogleImports(_service(request)).calendars(actor))


@router.post("/preview/")
def google_preview(request: Request, payload: PreviewQuery):
    actor = _actor(request)
    return invoke(lambda: GoogleImports(_service(request)).preview(actor, payload))


@router.post("/imports/")
def google_import(request: Request, payload: ImportDecision):
    context = context_for(request)
    invoke(lambda: context.require("crm.transfer.import"))
    if payload.action == "create":
        invoke(lambda: context.require("crm.create"))
    if payload.action == "update":
        invoke(lambda: context.require("crm.edit"))
    return invoke(lambda: GoogleImports(_service(request)).commit(context.actor_uid, payload))
