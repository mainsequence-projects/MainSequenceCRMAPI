"""Activity HTTP routes with concrete Pydantic request bodies."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from api.crm.route_support import _collection, _detail, _discovery

router = APIRouter(prefix="/api/crm/v1/activity")


@router.get("/discovery/", name="discover-activity")
def discovery(request: Request):
    return _discovery("activity", request)


@router.get("/", name="list-activity")
def collection(request: Request):
    return _collection("activity", request)


@router.get("/{uid}/", name="get-activity")
def detail(uid: uuid.UUID, request: Request):
    return _detail("activity", uid, request)
