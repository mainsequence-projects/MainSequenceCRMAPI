"""Application-owned contact-company history endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request

from src.crm.models.affiliations import (
    Affiliation,
    AffiliationCreate,
    AffiliationList,
    AffiliationPatch,
    AffiliationTransition,
)
from src.crm.models.contacts import Contact
from src.crm.repositories.resources.store import ResourceConflict, ResourceNotFound

from .route_support import _authorized, _store

router = APIRouter(prefix="/api/crm/v1/contacts", tags=["contact affiliations"])


@router.post("/{uid}/company-transition/", response_model=Contact)
def transition_company(
    uid: uuid.UUID,
    request: Request,
    payload: AffiliationTransition,
):
    context = _authorized(request, "crm.edit")
    try:
        return _store(request).transition_company(
            context.actor_uid,
            uid,
            payload.model_dump(mode="json"),
        )
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{uid}/affiliations/", response_model=AffiliationList)
def list_affiliations(
    uid: uuid.UUID,
    request: Request,
    page_index: int = Query(default=0, ge=0),
    page_size: int = Query(default=25, ge=1, le=100),
):
    _authorized(request, "crm.read")
    store = _store(request)
    try:
        store.detail("contacts", uid)
        return store.affiliations(uid, page_index, page_size)
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{uid}/affiliations/{affiliation_uid}/", response_model=Affiliation)
def get_affiliation(uid: uuid.UUID, affiliation_uid: uuid.UUID, request: Request):
    _authorized(request, "crm.read")
    try:
        return _store(request).affiliation_detail(uid, affiliation_uid)
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{uid}/affiliations/", status_code=201, response_model=Affiliation)
def create_affiliation(
    uid: uuid.UUID,
    request: Request,
    payload: AffiliationCreate,
):
    context = _authorized(request, "crm.edit")
    try:
        return _store(request).create_affiliation(
            context.actor_uid,
            uid,
            payload.model_dump(mode="json"),
        )
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{uid}/affiliations/{affiliation_uid}/", response_model=Affiliation)
def patch_affiliation(
    uid: uuid.UUID,
    affiliation_uid: uuid.UUID,
    request: Request,
    payload: AffiliationPatch,
):
    context = _authorized(request, "crm.edit")
    try:
        return _store(request).patch_affiliation(
            context.actor_uid,
            uid,
            affiliation_uid,
            payload.model_dump(mode="json", exclude_unset=True),
        )
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
