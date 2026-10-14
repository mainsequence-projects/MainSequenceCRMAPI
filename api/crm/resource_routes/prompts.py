"""Core fixed Markdown prompt routes with existing CRM authorization."""

import uuid

from fastapi import APIRouter, Request

from api.crm.route_support import _archive, _collection, _create, _detail, _discovery, _patch
from src.crm.models.common import VersionCommand
from src.crm.models.prompts import PromptCreate, PromptPatch

router = APIRouter(prefix="/api/crm/v1/prompts")


@router.get("/discovery/", name="discover-prompts")
def discovery(request: Request):
    return _discovery("prompts", request)


@router.get("/", name="list-prompts")
def collection(request: Request):
    return _collection("prompts", request)


@router.get("/{uid}/", name="get-prompts")
def detail(uid: uuid.UUID, request: Request):
    return _detail("prompts", uid, request)


@router.post("/", status_code=201, name="create-prompts")
def create(request: Request, payload: PromptCreate):
    return _create("prompts", request, payload.model_dump(mode="json", exclude_unset=True))


@router.patch("/{uid}/", name="update-prompts")
def patch(uid: uuid.UUID, request: Request, payload: PromptPatch):
    return _patch("prompts", uid, request, payload.model_dump(mode="json", exclude_unset=True))


@router.post("/{uid}/archive/", name="archive-prompts")
def archive(uid: uuid.UUID, request: Request, payload: VersionCommand):
    return _archive("prompts", True, uid, request, payload.expected_version)


@router.post("/{uid}/restore/", name="restore-prompts")
def restore(uid: uuid.UUID, request: Request, payload: VersionCommand):
    return _archive("prompts", False, uid, request, payload.expected_version)
