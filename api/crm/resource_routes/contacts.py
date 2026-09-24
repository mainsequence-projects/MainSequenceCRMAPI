"""Contact HTTP routes with concrete Pydantic request bodies."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from api.crm.route_support import _archive, _collection, _create, _detail, _discovery, _patch
from src.crm.models.common import VersionCommand
from src.crm.models.contacts import ContactCreate, ContactPatch

router = APIRouter(prefix="/api/crm/v1/contacts")


@router.get("/discovery/", name="discover-contacts")
def discovery(request: Request):
    return _discovery("contacts", request)


@router.get("/", name="list-contacts")
def collection(request: Request):
    return _collection("contacts", request)


@router.get("/{uid}/", name="get-contacts")
def detail(uid: uuid.UUID, request: Request):
    return _detail("contacts", uid, request)


@router.post("/", status_code=201, name="create-contacts")
def create(
    request: Request,
    payload: ContactCreate,
):
    return _create("contacts", request, payload.model_dump(mode="json", exclude_unset=True))


@router.patch("/{uid}/", name="update-contacts")
def patch(
    uid: uuid.UUID,
    request: Request,
    payload: ContactPatch,
):
    return _patch(
        "contacts",
        uid,
        request,
        payload.model_dump(mode="json", exclude_unset=True),
    )


@router.post("/{uid}/archive/", name="archive-contacts")
def archive(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("contacts", True, uid, request, payload.expected_version)


@router.post("/{uid}/restore/", name="restore-contacts")
def restore(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("contacts", False, uid, request, payload.expected_version)
