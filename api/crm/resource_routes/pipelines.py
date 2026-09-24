"""Pipeline HTTP routes with concrete Pydantic request bodies."""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.crm.route_support import _collection

router = APIRouter(prefix="/api/crm/v1/pipelines")


@router.get("/", name="list-pipelines")
def collection(request: Request):
    return _collection("pipelines", request)
