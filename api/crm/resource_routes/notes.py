"""Note HTTP routes with concrete Pydantic request bodies."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from api.crm.route_support import _archive, _collection, _create, _detail, _discovery, _patch
from src.crm.models.common import VersionCommand
from src.crm.models.notes import NoteCreate, NotePatch

router = APIRouter(prefix="/api/crm/v1/notes")


@router.get("/discovery/", name="discover-notes")
def discovery(request: Request):
    return _discovery("notes", request)


@router.get("/", name="list-notes")
def collection(request: Request):
    return _collection("notes", request)


@router.get("/{uid}/", name="get-notes")
def detail(uid: uuid.UUID, request: Request):
    return _detail("notes", uid, request)


@router.post("/", status_code=201, name="create-notes")
def create(
    request: Request,
    payload: NoteCreate,
):
    return _create("notes", request, payload.model_dump(mode="json", exclude_unset=True))


@router.patch("/{uid}/", name="update-notes")
def patch(
    uid: uuid.UUID,
    request: Request,
    payload: NotePatch,
):
    return _patch("notes", uid, request, payload.model_dump(mode="json", exclude_unset=True))


@router.post("/{uid}/archive/", name="archive-notes")
def archive(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("notes", True, uid, request, payload.expected_version)


@router.post("/{uid}/restore/", name="restore-notes")
def restore(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("notes", False, uid, request, payload.expected_version)
