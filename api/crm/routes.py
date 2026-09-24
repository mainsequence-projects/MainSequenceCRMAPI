"""Cross-resource CRM endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from api.crm.query import QueryError, parse_board_query
from src.crm.contracts import validate_payload
from src.crm.models.bootstrap import SettingsPatch
from src.crm.models.deals import MoveDeal
from src.crm.models.merge import MergeExecuteRequest, MergePreviewRequest
from src.crm.platform.runtime import request_port
from src.crm.repositories.resources.store import ResourceConflict, ResourceNotFound

from .route_support import _authorized, _domain, _store

router = APIRouter(prefix="/api/crm/v1")


@router.get("/principals/", name="list-principals")
def principals(request: Request):
    context = _authorized(request, "crm.read")
    display_name = context.directory.display_name(context.actor_uid).strip()
    return {
        "items": [
            {
                "uid": str(context.actor_uid),
                "display_name": display_name,
                "selectable": context.directory.is_selectable(context.actor_uid),
            }
        ],
        "pageInfo": {
            "pageIndex": 0,
            "pageSize": 25,
            "totalItems": 1,
            "hasNextPage": False,
            "hasPreviousPage": False,
        },
    }


@router.get("/settings/", name="get-settings")
def settings(request: Request):
    context = _authorized(request, "crm.read")
    bootstrap = request_port(request, "crm_bootstrap")
    if bootstrap is None:
        raise HTTPException(status_code=503, detail="CRM settings service is unavailable")
    return bootstrap.read(context.actor_uid)["settings"]


@router.patch("/settings/", name="update-settings")
def update_settings(
    request: Request,
    payload: SettingsPatch,
):
    context = _authorized(request, "crm.configure")
    patch = payload.model_dump(mode="json", exclude_unset=True)
    bootstrap = request_port(request, "crm_bootstrap")
    if bootstrap is None:
        raise HTTPException(status_code=503, detail="CRM settings service is unavailable")
    current = bootstrap.read(context.actor_uid)["settings"]
    candidate = {**current, **patch["changes"]}
    candidate["configuration_version"] = patch["expected_version"]
    candidate = _domain(validate_payload, "Settings", candidate)
    try:
        _store(request).update_settings(
            context.actor_uid,
            patch["expected_version"],
            candidate,
        )
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return bootstrap.read(context.actor_uid)["settings"]


@router.get("/pipelines/{uid}/board/", name="get-pipeline-board")
def pipeline_board(uid: uuid.UUID, request: Request):
    _authorized(request, "crm.read")
    try:
        query = parse_board_query(dict(request.query_params))
        return _store(request).pipeline_board(uid, query.page_size)
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {exc.field}: {exc}") from exc
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/pipelines/{uid}/stages/{stage_uid}/cards/", name="get-pipeline-stage-cards")
def pipeline_stage_cards(uid: uuid.UUID, stage_uid: uuid.UUID, request: Request):
    _authorized(request, "crm.read")
    try:
        query = parse_board_query(dict(request.query_params), stage_cards=True)
        return _store(request).board_column(
            uid,
            stage_uid,
            query.expected_board_version,
            query.page_size,
            query.cursor,
        )
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {exc.field}: {exc}") from exc
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/deals/{uid}/move/", name="move-deal")
def move_deal(
    uid: uuid.UUID,
    request: Request,
    payload: MoveDeal,
):
    context = _authorized(request, "crm.edit")
    command = payload.model_dump(mode="json", exclude_unset=True)
    try:
        return _store(request).move_deal(
            context.actor_uid,
            uid,
            command,
        )
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/contacts/{uid}/merge/preview/", name="preview-contact-merge")
def preview_contact_merge(uid: uuid.UUID, request: Request, payload: MergePreviewRequest):
    _authorized(request, "crm.merge")
    command = payload.model_dump(mode="json", exclude_unset=True)
    try:
        return _store(request).merge_preview(
            uid,
            uuid.UUID(command["loser_uid"]),
            command["field_resolutions"],
        )
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ResourceConflict, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/contacts/{uid}/merge/", name="merge-contacts")
def merge_contacts(
    uid: uuid.UUID,
    request: Request,
    payload: MergeExecuteRequest,
):
    context = _authorized(request, "crm.merge")
    command = payload.model_dump(mode="json", exclude_unset=True)
    try:
        return _store(request).merge_contacts(
            context.actor_uid,
            uid,
            command,
        )
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ResourceConflict, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
