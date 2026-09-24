"""Task HTTP routes with concrete Pydantic request bodies."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from api.crm.route_support import (
    _archive,
    _collection,
    _create,
    _detail,
    _discovery,
    _patch,
    _task_completion,
)
from src.crm.models.common import VersionCommand
from src.crm.models.tasks import TaskCreate, TaskPatch

router = APIRouter(prefix="/api/crm/v1/tasks")


@router.get("/discovery/", name="discover-tasks")
def discovery(request: Request):
    return _discovery("tasks", request)


@router.get("/", name="list-tasks")
def collection(request: Request):
    return _collection("tasks", request)


@router.get("/{uid}/", name="get-tasks")
def detail(uid: uuid.UUID, request: Request):
    return _detail("tasks", uid, request)


@router.post("/", status_code=201, name="create-tasks")
def create(
    request: Request,
    payload: TaskCreate,
):
    return _create("tasks", request, payload.model_dump(mode="json", exclude_unset=True))


@router.patch("/{uid}/", name="update-tasks")
def patch(
    uid: uuid.UUID,
    request: Request,
    payload: TaskPatch,
):
    return _patch("tasks", uid, request, payload.model_dump(mode="json", exclude_unset=True))


@router.post("/{uid}/archive/", name="archive-tasks")
def archive(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _archive("tasks", True, uid, request, payload.expected_version)


@router.post("/{uid}/complete/", name="complete-task")
def complete(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _task_completion(True, uid, request, payload.expected_version)


@router.post("/{uid}/reopen/", name="reopen-task")
def reopen(
    uid: uuid.UUID,
    request: Request,
    payload: VersionCommand,
):
    return _task_completion(False, uid, request, payload.expected_version)
