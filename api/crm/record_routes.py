"""Thin HTTP adapters for core Interactions and optional extension records."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from src.crm.models.interactions import InteractionCreate, InteractionPatch
from src.crm.solution_selling.models import (
    AssessmentCreate,
    AssessmentPatch,
    DiagnosisCreate,
    DiagnosisPatch,
    LeadCreate,
    LeadPatch,
    PrompterCreate,
    PrompterPatch,
    PrompterRenderRequest,
    ProspectingProfileCreate,
    ProspectingProfilePatch,
)

from .service_adapter import invoke, service_for

core_router = APIRouter(prefix="/api/crm/v1/interactions")
module_router = APIRouter(prefix="/extensions/solution-selling")


def _list(resource: str, request: Request, page_index: int, page_size: int, search: str | None):
    filters = {
        key: value for key, value in request.query_params.items()
        if key not in {"page_index", "page_size", "search"}
    }
    return invoke(
        lambda: service_for(request).list_records(
            resource, page_index=page_index, page_size=page_size,
            search=search, filters=filters,
        )
    )


def _detail(resource: str, request: Request, uid: uuid.UUID):
    return invoke(lambda: service_for(request).get_record(resource, uid))


def _create(resource: str, request: Request, payload: BaseModel):
    return invoke(lambda: service_for(request).create_record(resource, payload))


def _patch(resource: str, request: Request, uid: uuid.UUID, payload: BaseModel):
    return invoke(lambda: service_for(request).update_record(resource, uid, payload))


@core_router.get("/")
def list_interactions(
    request: Request,
    page_index: int = Query(0, ge=0),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=255),
):
    return _list("interactions", request, page_index, page_size, search)


@core_router.get("/{uid}/")
def get_interaction(uid: uuid.UUID, request: Request):
    return _detail("interactions", request, uid)


@core_router.post("/", status_code=201)
def create_interaction(request: Request, payload: InteractionCreate):
    return _create("interactions", request, payload)


@core_router.patch("/{uid}/")
def update_interaction(uid: uuid.UUID, request: Request, payload: InteractionPatch):
    return _patch("interactions", request, uid, payload)


@module_router.get("/assessments/")
def list_assessments(
    request: Request,
    page_index: int = Query(0, ge=0),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=255),
):
    return _list("assessments", request, page_index, page_size, search)


@module_router.get("/assessments/{uid}/")
def get_assessment(uid: uuid.UUID, request: Request):
    return _detail("assessments", request, uid)


@module_router.post("/assessments/", status_code=201)
def create_assessment(request: Request, payload: AssessmentCreate):
    return _create("assessments", request, payload)


@module_router.patch("/assessments/{uid}/")
def update_assessment(uid: uuid.UUID, request: Request, payload: AssessmentPatch):
    return _patch("assessments", request, uid, payload)


@module_router.get("/diagnoses/")
def list_diagnoses(
    request: Request,
    page_index: int = Query(0, ge=0),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=255),
):
    return _list("diagnoses", request, page_index, page_size, search)


@module_router.get("/diagnoses/{uid}/")
def get_diagnosis(uid: uuid.UUID, request: Request):
    return _detail("diagnoses", request, uid)


@module_router.post("/diagnoses/", status_code=201)
def create_diagnosis(request: Request, payload: DiagnosisCreate):
    return _create("diagnoses", request, payload)


@module_router.patch("/diagnoses/{uid}/")
def update_diagnosis(uid: uuid.UUID, request: Request, payload: DiagnosisPatch):
    return _patch("diagnoses", request, uid, payload)


@module_router.get("/prospecting-profiles/")
def list_profiles(
    request: Request,
    page_index: int = Query(0, ge=0),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=255),
):
    return _list("prospecting-profiles", request, page_index, page_size, search)


@module_router.get("/prospecting-profiles/{uid}/")
def get_profile(uid: uuid.UUID, request: Request):
    return _detail("prospecting-profiles", request, uid)


@module_router.post("/prospecting-profiles/", status_code=201)
def create_profile(request: Request, payload: ProspectingProfileCreate):
    return _create("prospecting-profiles", request, payload)


@module_router.patch("/prospecting-profiles/{uid}/")
def update_profile(uid: uuid.UUID, request: Request, payload: ProspectingProfilePatch):
    return _patch("prospecting-profiles", request, uid, payload)


@module_router.get("/leads/")
def list_leads(
    request: Request,
    page_index: int = Query(0, ge=0),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=255),
):
    return _list("leads", request, page_index, page_size, search)


@module_router.get("/leads/{uid}/")
def get_lead(uid: uuid.UUID, request: Request):
    return _detail("leads", request, uid)


@module_router.post("/leads/", status_code=201)
def create_lead(request: Request, payload: LeadCreate):
    return _create("leads", request, payload)


@module_router.patch("/leads/{uid}/")
def update_lead(uid: uuid.UUID, request: Request, payload: LeadPatch):
    return _patch("leads", request, uid, payload)


@module_router.get("/prompters/")
def list_prompters(
    request: Request,
    page_index: int = Query(0, ge=0),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=255),
):
    return _list("prompters", request, page_index, page_size, search)


@module_router.get("/prompters/{uid}/")
def get_prompter(uid: uuid.UUID, request: Request):
    return _detail("prompters", request, uid)


@module_router.post("/prompters/", status_code=201)
def create_prompter(request: Request, payload: PrompterCreate):
    return _create("prompters", request, payload)


@module_router.patch("/prompters/{uid}/")
def update_prompter(uid: uuid.UUID, request: Request, payload: PrompterPatch):
    return _patch("prompters", request, uid, payload)


@module_router.post("/prompters/{uid}/render/")
def render_prompter_preview(uid: uuid.UUID, request: Request, payload: PrompterRenderRequest):
    return invoke(lambda: service_for(request).render_prompter(uid, payload))
