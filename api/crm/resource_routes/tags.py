"""Tag HTTP routes with concrete Pydantic request bodies."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from api.crm.route_support import _archive, _collection, _create, _detail, _discovery, _patch
from src.crm.models.common import VersionCommand
from src.crm.models.tags import TagCreate, TagPatch

router = APIRouter(prefix="/api/crm/v1/tags")


@router.get("/discovery/", name="discover-tags")
def discovery(request: Request):
    return _discovery("tags", request)


@router.get("/", name="list-tags")
def collection(request: Request):
    return _collection("tags", request)


@router.get("/{uid}/", name="get-tags")
def detail(uid: uuid.UUID, request: Request):
    return _detail("tags", uid, request)


@router.post("/", status_code=201, name="create-tags")
def create(
    request: Request,
    payload: TagCreate,
):
    return _create("tags", request, payload.model_dump(mode="json", exclude_unset=True))


@router.patch("/{uid}/", name="update-tags")
def patch(
    uid: uuid.UUID,
    request: Request,
    payload: TagPatch,
):
    return _patch("tags", uid, request, payload.model_dump(mode="json", exclude_unset=True))


@router.post("/{uid}/archive/", name="archive-tags")
def archive(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("tags", True, uid, request, payload.expected_version)


@router.post("/{uid}/restore/", name="restore-tags")
def restore(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("tags", False, uid, request, payload.expected_version)
