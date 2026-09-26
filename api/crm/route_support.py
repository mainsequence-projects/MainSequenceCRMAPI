"""Thin HTTP wrappers around the shared CRM operation service."""

from __future__ import annotations

import uuid

from fastapi import Request

from api.crm.discovery import resource_discovery
from api.crm.query import parse_query

from .service_adapter import invoke, service_for


def _authorized(request: Request, capability: str):
    """Compatibility helper while cross-resource routes move to CRMOperations."""
    service = service_for(request)
    invoke(lambda: service.context.require(capability))
    return service.context


def _query(request: Request, resource: str, *, discovery: bool = False):
    return invoke(lambda: parse_query(resource, dict(request.query_params), discovery=discovery))


def _collection(resource: str, request: Request):
    service = service_for(request)
    invoke(lambda: service.context.require("crm.read"))
    return invoke(lambda: service.list_resources(resource, _query(request, resource)))


def _discovery(resource: str, request: Request):
    service = service_for(request)
    invoke(lambda: service.context.require("crm.read"))
    _query(request, resource, discovery=True)
    return resource_discovery(resource)


def _detail(resource: str, uid: uuid.UUID, request: Request):
    return invoke(lambda: service_for(request).get_resource(resource, uid))


def _create(resource: str, request: Request, payload: dict):
    return invoke(lambda: service_for(request).create_resource(resource, payload))


def _patch(resource: str, uid: uuid.UUID, request: Request, payload: dict):
    return invoke(lambda: service_for(request).update_resource(resource, uid, payload))


def _archive(
    resource: str,
    archived: bool,
    uid: uuid.UUID,
    request: Request,
    expected_version: int,
):
    return invoke(
        lambda: service_for(request).archive_resource(
            resource, uid, expected_version, archived=archived
        )
    )


def _task_completion(completed: bool, uid: uuid.UUID, request: Request, expected_version: int):
    return invoke(
        lambda: service_for(request).complete_task(uid, expected_version, completed=completed)
    )
