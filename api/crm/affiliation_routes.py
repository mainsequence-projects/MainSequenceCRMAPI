"""HTTP adapters for contact-company history operations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request

from src.crm.models.affiliations import (
    Affiliation,
    AffiliationCreate,
    AffiliationList,
    AffiliationPatch,
    AffiliationTransition,
)
from src.crm.models.contacts import Contact

from .service_adapter import invoke, service_for

router = APIRouter(prefix="/api/crm/v1/contacts", tags=["contact affiliations"])


@router.post("/{uid}/company-transition/", response_model=Contact)
def transition_company(uid: uuid.UUID, request: Request, payload: AffiliationTransition):
    return invoke(lambda: service_for(request).transition_company(uid, payload))


@router.get("/{uid}/affiliations/", response_model=AffiliationList)
def list_affiliations(
    uid: uuid.UUID,
    request: Request,
    page_index: int = Query(default=0, ge=0),
    page_size: int = Query(default=25, ge=1, le=100),
):
    return invoke(lambda: service_for(request).list_affiliations(uid, page_index, page_size))


@router.get("/{uid}/affiliations/{affiliation_uid}/", response_model=Affiliation)
def get_affiliation(uid: uuid.UUID, affiliation_uid: uuid.UUID, request: Request):
    return invoke(lambda: service_for(request).get_affiliation(uid, affiliation_uid))


@router.post("/{uid}/affiliations/", status_code=201, response_model=Affiliation)
def create_affiliation(uid: uuid.UUID, request: Request, payload: AffiliationCreate):
    return invoke(lambda: service_for(request).create_affiliation(uid, payload))


@router.patch("/{uid}/affiliations/{affiliation_uid}/", response_model=Affiliation)
def patch_affiliation(
    uid: uuid.UUID,
    affiliation_uid: uuid.UUID,
    request: Request,
    payload: AffiliationPatch,
):
    return invoke(lambda: service_for(request).update_affiliation(uid, affiliation_uid, payload))
