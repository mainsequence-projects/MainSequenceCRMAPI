"""HTTP transport adapter for the shared CRM operation boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import HTTPException, Request

from api.crm.query import QueryError
from src.crm.contracts import DomainValidationError
from src.crm.platform.runtime import authenticated_actor, request_port
from src.crm.repositories.errors import ResourceConflict, ResourceNotFound
from src.crm.services.operations import (
    AccessDenied,
    CRMContext,
    CRMOperations,
    ServiceUnavailable,
)
from src.crm.services.transfers import ImportInputError

T = TypeVar("T")


def context_for(request: Request) -> CRMContext:
    actor_uid = authenticated_actor(request)
    policy = request_port(request, "crm_policy")
    directory = request_port(request, "crm_directory")
    if policy is None or directory is None:
        raise HTTPException(status_code=503, detail="CRM policy or directory is unavailable")
    return CRMContext(actor_uid=actor_uid, policy=policy, directory=directory)


def service_for(request: Request) -> CRMOperations:
    return CRMOperations(
        context_for(request),
        resources=request_port(request, "crm_resources"),
        records=request_port(request, "crm_record_store"),
        bootstrap=request_port(request, "crm_bootstrap"),
    )


def invoke(call: Callable[[], T], *, value_status: int = 422) -> T:
    try:
        return call()
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DomainValidationError as exc:
        field = exc.fields[0]["path"] if exc.fields else "payload"
        raise HTTPException(status_code=422, detail=f"Invalid {field or 'payload'}") from exc
    except ImportInputError as exc:
        raise HTTPException(status_code=413 if exc.too_large else 422, detail=str(exc)) from exc
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {exc.field}: {exc}") from exc
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=value_status, detail=str(exc)) from exc
