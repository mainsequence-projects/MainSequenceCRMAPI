"""Trusted runtime ports and fail-closed application readiness."""

from __future__ import annotations

import uuid
from typing import Protocol

from fastapi import HTTPException, Request

from .catalog import configured_registry

CAPABILITIES = frozenset(
    {
        "crm.read",
        "crm.create",
        "crm.edit",
        "crm.archive",
        "crm.merge",
        "crm.transfer.import",
        "crm.transfer.export",
        "crm.configure",
    }
)


class PolicyPort(Protocol):
    """Adapter to the existing platform policy, supplied by deployment wiring."""

    def capabilities(self, actor_uid: uuid.UUID) -> set[str]: ...


class DirectoryPort(Protocol):
    def display_name(self, actor_uid: uuid.UUID) -> str: ...

    def is_selectable(self, actor_uid: uuid.UUID) -> bool: ...


class RegistryPort(Protocol):
    """Active migration bindings, including a governed read proof."""

    def validate(self) -> None: ...

    def validate_settings(self) -> None: ...


class BootstrapPort(Protocol):
    def validate(self, actor_uid: uuid.UUID) -> None: ...

    def read(self, actor_uid: uuid.UUID) -> dict: ...


def authenticated_actor(request: Request) -> uuid.UUID:
    raw = getattr(request.state, "user_uid", None)
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=401, detail="Authenticated platform identity required"
        ) from exc


def request_port(request: Request, name: str):
    """Resolve explicit request wiring before deployment-wide application state."""

    request_value = getattr(request.state, name, None)
    if request_value is not None:
        return request_value
    return getattr(request.app.state, name, None)


def readiness(request: Request, actor_uid: uuid.UUID) -> dict:
    checks: list[dict[str, str]] = []
    policy: PolicyPort | None = request_port(request, "crm_policy")
    directory: DirectoryPort | None = request_port(request, "crm_directory")
    registry: RegistryPort | None = request_port(request, "crm_registry") or configured_registry()
    bootstrap_port: BootstrapPort | None = request_port(request, "crm_bootstrap")
    checks.append(
        {
            "id": "policy",
            "status": "ready" if policy else "failed",
            "message": "Connected" if policy else "Existing policy adapter is not connected",
        }
    )
    catalog_ready = False
    if registry is not None:
        try:
            registry.validate()
        except Exception:
            pass
        else:
            catalog_ready = True
    checks.append(
        {
            "id": "catalog",
            "status": "ready" if catalog_ready else "failed",
            "message": "Resolved" if catalog_ready else "Active MetaTable catalog is unavailable",
        }
    )
    settings_ready = False
    if catalog_ready:
        try:
            registry.validate_settings()
        except Exception:
            pass
        else:
            settings_ready = True
    checks.append(
        {
            "id": "crm-settings",
            "status": "ready" if settings_ready else "failed",
            "message": "Resolved" if settings_ready else "CRM settings are unavailable",
        }
    )
    if directory:
        try:
            if not directory.display_name(actor_uid).strip():
                raise ValueError("Missing display name")
            if not directory.is_selectable(actor_uid):
                raise ValueError("Actor is not selectable")
        except Exception:
            checks.append(
                {
                    "id": "directory",
                    "status": "failed",
                    "message": "Existing directory lookup failed",
                }
            )
        else:
            checks.append({"id": "directory", "status": "ready", "message": "Connected"})
    else:
        checks.append(
            {
                "id": "directory",
                "status": "failed",
                "message": "Existing directory adapter is not connected",
            }
        )
    if bootstrap_port:
        try:
            bootstrap_port.validate(actor_uid)
        except Exception:
            checks.append(
                {
                    "id": "bootstrap",
                    "status": "failed",
                    "message": "CRM settings or default pipeline are unavailable",
                }
            )
        else:
            checks.append({"id": "bootstrap", "status": "ready", "message": "Validated"})
    else:
        checks.append(
            {
                "id": "bootstrap",
                "status": "failed",
                "message": "CRM settings read service is not connected",
            }
        )
    if settings_ready and policy:
        try:
            allowed = set(policy.capabilities(actor_uid))
            if not allowed <= CAPABILITIES:
                raise ValueError("Policy returned an unknown CRM capability")
            if "crm.read" not in allowed:
                raise HTTPException(status_code=403, detail="CRM read access denied")
        except HTTPException:
            raise
        except Exception:
            checks.append(
                {
                    "id": "authorization",
                    "status": "failed",
                    "message": "Existing policy could not authorize CRM read access",
                }
            )
        else:
            checks.append({"id": "authorization", "status": "ready", "message": "Authorized"})
    else:
        checks.append(
            {
                "id": "authorization",
                "status": "pending",
                "message": "Waiting for policy and settings",
            }
        )
    return {
        "status": "ready" if all(c["status"] == "ready" for c in checks) else "not_ready",
        "schema_version": "1",
        "application_version": "0.1.0",
        "checks": checks,
    }
