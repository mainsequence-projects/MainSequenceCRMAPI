"""Deal HTTP routes with concrete Pydantic request bodies."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from api.crm.route_support import _archive, _collection, _create, _detail, _discovery, _patch
from src.crm.models.common import VersionCommand
from src.crm.models.deals import DealCreate, DealPatch

router = APIRouter(prefix="/api/crm/v1/deals")


@router.get("/discovery/", name="discover-deals")
def discovery(request: Request):
    return _discovery("deals", request)


@router.get("/", name="list-deals")
def collection(request: Request):
    return _collection("deals", request)


@router.get("/{uid}/", name="get-deals")
def detail(uid: uuid.UUID, request: Request):
    return _detail("deals", uid, request)


@router.post("/", status_code=201, name="create-deals")
def create(
    request: Request,
    payload: DealCreate,
):
    return _create("deals", request, payload.model_dump(mode="json", exclude_unset=True))


@router.patch("/{uid}/", name="update-deals")
def patch(
    uid: uuid.UUID,
    request: Request,
    payload: DealPatch,
):
    return _patch("deals", uid, request, payload.model_dump(mode="json", exclude_unset=True))


@router.post("/{uid}/archive/", name="archive-deals")
def archive(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("deals", True, uid, request, payload.expected_version)


@router.post("/{uid}/restore/", name="restore-deals")
def restore(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("deals", False, uid, request, payload.expected_version)
