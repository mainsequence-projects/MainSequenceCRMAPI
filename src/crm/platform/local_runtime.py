"""Adapters used only by the explicit loopback development entrypoint."""

from __future__ import annotations

import uuid
from typing import Any

from ..services.application import BootstrapService, CatalogSettingsStore
from .catalog import CatalogRegistry, configured_registry
from .runtime import CAPABILITIES

LOCAL_CAPABILITIES = CAPABILITIES - {"crm.transfer.export"}


class LocalSdkUserPolicy:
    """Bind CRM capabilities to one SDK-authenticated local human."""

    def __init__(self, actor_uid: uuid.UUID):
        self.actor_uid = actor_uid

    def capabilities(self, actor_uid: uuid.UUID) -> set[str]:
        if actor_uid != self.actor_uid:
            return set()
        # Export remains hidden until its immutable output path passes a live gate.
        return set(LOCAL_CAPABILITIES)


class LocalSdkUserDirectory:
    """Expose only the SDK-authenticated user in local single-user mode."""

    def __init__(self, signed_user: Any):
        try:
            self.actor_uid = uuid.UUID(str(signed_user.uid))
        except (AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError("The signed-in SDK user has no valid UID") from exc
        full_name = " ".join(
            part.strip()
            for part in (
                str(getattr(signed_user, "first_name", "") or ""),
                str(getattr(signed_user, "last_name", "") or ""),
            )
            if part.strip()
        )
        self._display_name = (
            full_name
            or str(getattr(signed_user, "username", "") or "").strip()
            or str(getattr(signed_user, "email", "") or "").strip()
            or str(self.actor_uid)
        )

    def display_name(self, actor_uid: uuid.UUID) -> str:
        if actor_uid != self.actor_uid:
            raise PermissionError("Actor is not the locally authenticated SDK user")
        return self._display_name

    def is_selectable(self, actor_uid: uuid.UUID) -> bool:
        return actor_uid == self.actor_uid


def build_local_services(
    *, signed_user: Any, registry: CatalogRegistry | None = None
) -> tuple[
    LocalSdkUserPolicy,
    LocalSdkUserDirectory,
    BootstrapService,
]:
    """Build request-scoped adapters for one verified loopback SDK session."""

    actor_uid = uuid.UUID(str(signed_user.uid))
    registry = registry or configured_registry()
    policy = LocalSdkUserPolicy(actor_uid)
    directory = LocalSdkUserDirectory(signed_user)
    bootstrap = BootstrapService(
        policy=policy,
        directory=directory,
        store=CatalogSettingsStore(registry),
    )
    return policy, directory, bootstrap
