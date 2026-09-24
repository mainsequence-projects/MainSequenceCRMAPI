"""Company HTTP routes with concrete Pydantic request bodies."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from api.crm.route_support import _archive, _collection, _create, _detail, _discovery, _patch
from src.crm.models.common import VersionCommand
from src.crm.models.companies import CompanyCreate, CompanyPatch

router = APIRouter(prefix="/api/crm/v1/companies")


@router.get("/discovery/", name="discover-companies")
def discovery(request: Request):
    return _discovery("companies", request)


@router.get("/", name="list-companies")
def collection(request: Request):
    return _collection("companies", request)


@router.get("/{uid}/", name="get-companies")
def detail(uid: uuid.UUID, request: Request):
    return _detail("companies", uid, request)


@router.post("/", status_code=201, name="create-companies")
def create(
    request: Request,
    payload: CompanyCreate,
):
    return _create("companies", request, payload.model_dump(mode="json", exclude_unset=True))


@router.patch("/{uid}/", name="update-companies")
def patch(
    uid: uuid.UUID,
    request: Request,
    payload: CompanyPatch,
):
    return _patch(
        "companies",
        uid,
        request,
        payload.model_dump(mode="json", exclude_unset=True),
    )


@router.post("/{uid}/archive/", name="archive-companies")
def archive(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("companies", True, uid, request, payload.expected_version)


@router.post("/{uid}/restore/", name="restore-companies")
def restore(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("companies", False, uid, request, payload.expected_version)
