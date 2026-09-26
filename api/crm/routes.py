"""Cross-resource HTTP adapters for the shared CRM service."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from api.crm.query import parse_board_query
from src.crm.models.bootstrap import SettingsPatch
from src.crm.models.deals import MoveDeal
from src.crm.models.merge import MergeExecuteRequest, MergePreviewRequest
from src.crm.models.pipelines import PipelineStages

from .service_adapter import invoke, service_for

router = APIRouter(prefix="/api/crm/v1")


@router.get("/principals/", name="list-principals")
def principals(request: Request):
    return invoke(lambda: service_for(request).principals())


@router.get("/settings/", name="get-settings")
def settings(request: Request):
    return invoke(lambda: service_for(request).settings())


@router.patch("/settings/", name="update-settings")
def update_settings(request: Request, payload: SettingsPatch):
    return invoke(lambda: service_for(request).update_settings(payload))


@router.get("/pipelines/{uid}/stages/", name="get-pipeline-stages", response_model=PipelineStages)
def pipeline_stages(uid: uuid.UUID, request: Request):
    service = service_for(request)
    invoke(lambda: service.context.require("crm.read"))
    if request.query_params:
        raise HTTPException(status_code=422, detail="Pipeline stages do not accept query parameters")
    return invoke(lambda: service.pipeline_stages(uid))


@router.get("/pipelines/{uid}/board/", name="get-pipeline-board")
def pipeline_board(uid: uuid.UUID, request: Request):
    service = service_for(request)
    invoke(lambda: service.context.require("crm.read"))
    query = invoke(lambda: parse_board_query(dict(request.query_params)))
    return invoke(lambda: service.pipeline_board(uid, query.page_size))


@router.get("/pipelines/{uid}/stages/{stage_uid}/cards/", name="get-pipeline-stage-cards")
def pipeline_stage_cards(uid: uuid.UUID, stage_uid: uuid.UUID, request: Request):
    service = service_for(request)
    invoke(lambda: service.context.require("crm.read"))
    query = invoke(lambda: parse_board_query(dict(request.query_params), stage_cards=True))
    return invoke(
        lambda: service.board_column(
            uid, stage_uid, query.expected_board_version, query.page_size, query.cursor
        )
    )


@router.post("/deals/{uid}/move/", name="move-deal")
def move_deal(uid: uuid.UUID, request: Request, payload: MoveDeal):
    return invoke(lambda: service_for(request).move_deal(uid, payload))


@router.post("/contacts/{uid}/merge/preview/", name="preview-contact-merge")
def preview_contact_merge(uid: uuid.UUID, request: Request, payload: MergePreviewRequest):
    return invoke(lambda: service_for(request).merge_preview(uid, payload), value_status=409)


@router.post("/contacts/{uid}/merge/", name="merge-contacts")
def merge_contacts(uid: uuid.UUID, request: Request, payload: MergeExecuteRequest):
    return invoke(lambda: service_for(request).merge_contacts(uid, payload), value_status=409)
