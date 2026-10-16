"""Hosted adapters based on platform-verified identity and Team facts."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from mainsequence.client import User
from mainsequence.server.fastapi import reads_as_caller

from .runtime import CAPABILITIES


def effective_identity():
    caller = User.get_logged_user()
    return User.get_requester() or caller


def _team_uids(name: str) -> frozenset[str]:
    try:
        return frozenset(
            str(uuid.UUID(value.strip()))
            for value in os.environ.get(name, "").split(",")
            if value.strip()
        )
    except ValueError as exc:
        raise RuntimeError(f"{name} must contain platform Team UUIDs") from exc


@dataclass(frozen=True)
class PlatformPolicy:
    """Evaluate the effective person's identity and fresh Team memberships.

    Team configuration names existing platform Teams; it stores no people,
    memberships or credentials. Storage workload grants are independent.
    """

    reader_team_uids: frozenset[str]
    writer_team_uids: frozenset[str]

    @classmethod
    def from_environment(cls):
        return cls(_team_uids("CRM_READER_TEAM_UIDS"), _team_uids("CRM_WRITER_TEAM_UIDS"))

    def capabilities(self, actor_uid: uuid.UUID) -> set[str]:
        identity = effective_identity()
        if uuid.UUID(identity.uid) != actor_uid:
            return set()
        # Export is not available until its immutable-output live gate passes.
        if identity.is_organization_admin:
            return set(CAPABILITIES - {"crm.transfer.export"})
        teams = identity.in_teams(
            self.reader_team_uids | self.writer_team_uids, max_age_seconds=0
        )
        if teams & self.writer_team_uids:
            return set(CAPABILITIES - {"crm.transfer.export", "crm.configure"})
        if teams & self.reader_team_uids:
            return {"crm.read"}
        return set()


class PlatformDirectory:
    """Use signed self identity and the caller-scoped platform directory.

    The SDK cannot forward a requester-bearing assertion to directory APIs.
    Delegated calls can therefore select only their verified requester; they
    never borrow the workload's directory visibility for another owner.
    """

    @staticmethod
    def _user(actor_uid: uuid.UUID):
        identity = effective_identity()
        if uuid.UUID(identity.uid) == actor_uid:
            return identity
        if User.get_requester() is not None:
            raise PermissionError("Delegated owner lookup is unavailable")
        with reads_as_caller():
            user = User.get_by_uid(str(actor_uid))
        if user.is_active is not True or user.identity_type != "human":
            raise PermissionError("Owner is not an active platform person")
        return user

    def display_name(self, actor_uid: uuid.UUID) -> str:
        user = self._user(actor_uid)
        name = " ".join(
            str(getattr(user, field, "") or "").strip()
            for field in ("first_name", "last_name")
        ).strip()
        return name or user.username or str(actor_uid)

    def is_selectable(self, actor_uid: uuid.UUID) -> bool:
        try:
            self._user(actor_uid)
        except PermissionError:
            return False
        return True


def install_platform_services(application) -> None:
    # Import after runtime's protocols are initialized; BootstrapService uses them.
    from ..services.application import BootstrapService, CatalogSettingsStore

    policy = PlatformPolicy.from_environment()
    directory = PlatformDirectory()
    application.state.crm_policy = policy
    application.state.crm_directory = directory
    application.state.crm_bootstrap = BootstrapService(
        policy=policy, directory=directory, store=CatalogSettingsStore()
    )
