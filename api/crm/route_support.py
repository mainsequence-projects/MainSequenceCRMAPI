"""Authorization and shared resource handlers for typed CRM routes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, Request

from api.crm.discovery import resource_discovery
from api.crm.query import QueryError, parse_query
from src.crm.contracts import (
    DomainValidationError,
    model_for,
    normalized_create,
    normalized_patch,
    validate_payload,
)
from src.crm.platform.runtime import (
    CAPABILITIES,
    DirectoryPort,
    PolicyPort,
    authenticated_actor,
    request_port,
)
from src.crm.repositories.resources.catalog import RESOURCE_SPECS
from src.crm.repositories.resources.store import (
    GovernedResourceStore,
    ResourceConflict,
    ResourceNotFound,
)


@dataclass(frozen=True)
class AuthorizedRequest:
    actor_uid: uuid.UUID
    capabilities: frozenset[str]
    policy: PolicyPort
    directory: DirectoryPort


def _authorized(request: Request, capability: str) -> AuthorizedRequest:
    actor_uid = authenticated_actor(request)
    policy: PolicyPort | None = request_port(request, "crm_policy")
    directory: DirectoryPort | None = request_port(request, "crm_directory")
    if policy is None or directory is None:
        raise HTTPException(status_code=503, detail="CRM policy or directory is unavailable")
    try:
        capabilities = frozenset(policy.capabilities(actor_uid))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="CRM policy evaluation failed") from exc
    if not capabilities <= CAPABILITIES:
        raise HTTPException(status_code=503, detail="CRM policy returned invalid capabilities")
    if capability not in capabilities:
        raise HTTPException(status_code=403, detail=f"{capability} access denied")
    return AuthorizedRequest(actor_uid, capabilities, policy, directory)


def _store(request: Request) -> GovernedResourceStore:
    return request_port(request, "crm_resources") or GovernedResourceStore()


def _domain(callable_, *args):
    try:
        return callable_(*args)
    except DomainValidationError as exc:
        field = exc.fields[0]["path"] if exc.fields else "payload"
        raise HTTPException(status_code=422, detail=f"Invalid {field or 'payload'}") from exc


def _create_data(resource: str, payload: dict) -> dict:
    singular = RESOURCE_SPECS[resource].logical_table
    if resource in {"contacts", "companies"}:
        return _domain(normalized_create, singular, payload)
    return _domain(validate_payload, f"{singular.title()}Create", payload)


def _patch_data(resource: str, existing: dict, payload: dict) -> tuple[int, dict]:
    singular = RESOURCE_SPECS[resource].logical_table
    if resource in {"contacts", "companies"}:
        return _domain(normalized_patch, singular, existing, payload)
    patch = _domain(validate_payload, f"{singular.title()}Patch", payload)
    create_fields = model_for(f"{singular.title()}Create").model_fields
    candidate = {key: existing.get(key) for key in create_fields}
    candidate.update(patch["changes"])
    return patch["expected_version"], _domain(
        validate_payload, f"{singular.title()}Create", candidate
    )


def _check_owner(context: AuthorizedRequest, data: dict) -> None:
    owner_uid = data.get("owner_uid")
    if owner_uid is None:
        return
    try:
        owner = uuid.UUID(str(owner_uid))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid owner_uid") from exc
    if not context.directory.is_selectable(owner):
        raise HTTPException(status_code=422, detail="Owner is not selectable")


def _query(request: Request, resource: str, *, discovery: bool = False):
    try:
        return parse_query(resource, dict(request.query_params), discovery=discovery)
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {exc.field}: {exc}") from exc


def _collection(resource: str, request: Request):
    _authorized(request, "crm.read")
    try:
        return _store(request).collection(resource, _query(request, resource))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _discovery(resource: str, request: Request):
    _authorized(request, "crm.read")
    _query(request, resource, discovery=True)
    return resource_discovery(resource)


def _detail(resource: str, uid: uuid.UUID, request: Request):
    _authorized(request, "crm.read")
    try:
        return _store(request).detail(resource, uid)
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _create(resource: str, request: Request, payload: dict):
    context = _authorized(request, "crm.create")
    data = _create_data(resource, payload)
    _check_owner(context, data)
    try:
        return _store(request).create(resource, context.actor_uid, data)
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _patch(resource: str, uid: uuid.UUID, request: Request, payload: dict):
    context = _authorized(request, "crm.edit")
    store = _store(request)
    try:
        existing = store.detail(resource, uid)
        expected_version, data = _patch_data(resource, existing, payload)
        _check_owner(context, data)
        return store.update(
            resource,
            context.actor_uid,
            uid,
            expected_version,
            data,
        )
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _archive(
    resource: str,
    archived: bool,
    uid: uuid.UUID,
    request: Request,
    expected_version: int,
):
    context = _authorized(request, "crm.archive")
    try:
        return _store(request).archive(
            resource,
            context.actor_uid,
            uid,
            expected_version,
            archived,
        )
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _task_completion(completed: bool, uid: uuid.UUID, request: Request, expected_version: int):
    context = _authorized(request, "crm.edit")
    try:
        return _store(request).task_completion(
            context.actor_uid,
            uid,
            expected_version,
            completed,
        )
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
