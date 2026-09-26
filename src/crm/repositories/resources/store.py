"""Explicit composition boundary for CRM resource persistence."""

from __future__ import annotations

import uuid
from typing import Any

from ...models.queries import QueryScope
from ...platform.catalog import CatalogRegistry, configured_registry
from ..contacts.affiliations import ContactAffiliations
from ..contacts.merge import ContactMerge
from ..deals.board import DealBoard
from ..errors import ResourceConflict, ResourceNotFound
from ..settings import SettingsRepository
from ..tasks import TaskRepository
from .reads import ResourceReads
from .writes import ResourceMutations


class GovernedResourceStore:
    """Service-facing persistence facade; no SQL or mixin inheritance lives here."""

    def __init__(self, registry: CatalogRegistry | None = None):
        binding_registry = registry or configured_registry()
        self.reads = ResourceReads(binding_registry)
        self.mutations = ResourceMutations(binding_registry, self.reads)
        self.affiliations_repo = ContactAffiliations(binding_registry, self.reads)
        self.merge_repo = ContactMerge(binding_registry, self.reads, self.affiliations_repo)
        self.board_repo = DealBoard(binding_registry, self.reads)
        self.tasks = TaskRepository(binding_registry, self.reads)
        self.settings = SettingsRepository(binding_registry)

    def collection(self, resource: str, scope: QueryScope) -> dict[str, Any]:
        return self.reads.collection(resource, scope)

    def detail(self, resource: str, uid: uuid.UUID) -> dict[str, Any]:
        return self.reads.detail(resource, uid)

    def create(self, resource: str, actor_uid: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
        return self.mutations.create(resource, actor_uid, data)

    def update(
        self,
        resource: str,
        actor_uid: uuid.UUID,
        uid: uuid.UUID,
        expected_version: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        return self.mutations.update(resource, actor_uid, uid, expected_version, data)

    def archive(
        self,
        resource: str,
        actor_uid: uuid.UUID,
        uid: uuid.UUID,
        expected_version: int,
        archived: bool,
    ) -> dict[str, Any]:
        return self.mutations.archive(resource, actor_uid, uid, expected_version, archived)

    def transition_company(
        self, actor_uid: uuid.UUID, contact_uid: uuid.UUID, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self.affiliations_repo.transition_company(actor_uid, contact_uid, payload)

    def create_affiliation(
        self, actor_uid: uuid.UUID, contact_uid: uuid.UUID, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self.affiliations_repo.create_affiliation(actor_uid, contact_uid, payload)

    def patch_affiliation(
        self,
        actor_uid: uuid.UUID,
        contact_uid: uuid.UUID,
        affiliation_uid: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.affiliations_repo.patch_affiliation(
            actor_uid, contact_uid, affiliation_uid, payload
        )

    def affiliations(
        self, contact_uid: uuid.UUID, page_index: int = 0, page_size: int = 25
    ) -> dict[str, Any]:
        return self.affiliations_repo.affiliations(contact_uid, page_index, page_size)

    def affiliation_detail(
        self, contact_uid: uuid.UUID, affiliation_uid: uuid.UUID
    ) -> dict[str, Any]:
        return self.affiliations_repo.affiliation_detail(contact_uid, affiliation_uid)

    def merge_preview(
        self, survivor_uid: uuid.UUID, loser_uid: uuid.UUID, field_resolutions: dict[str, str]
    ) -> dict[str, Any]:
        return self.merge_repo.merge_preview(survivor_uid, loser_uid, field_resolutions)

    def merge_contacts(
        self, actor_uid: uuid.UUID, survivor_uid: uuid.UUID, command: dict[str, Any]
    ) -> dict[str, Any]:
        return self.merge_repo.merge_contacts(actor_uid, survivor_uid, command)

    def pipeline_board(self, pipeline_uid: uuid.UUID, page_size: int) -> dict[str, Any]:
        return self.board_repo.pipeline_board(pipeline_uid, page_size)

    def pipeline_stages(self, pipeline_uid: uuid.UUID) -> dict[str, Any]:
        return self.board_repo.pipeline_stages(pipeline_uid)

    def board_column(
        self,
        pipeline_uid: uuid.UUID,
        stage_uid: uuid.UUID,
        expected_board_version: int,
        page_size: int,
        offset: int,
    ) -> dict[str, Any]:
        return self.board_repo.board_column(
            pipeline_uid, stage_uid, expected_board_version, page_size, offset
        )

    def move_deal(
        self, actor_uid: uuid.UUID, deal_uid: uuid.UUID, command: dict[str, Any]
    ) -> dict[str, Any]:
        return self.board_repo.move_deal(actor_uid, deal_uid, command)

    def task_completion(
        self, actor_uid: uuid.UUID, uid: uuid.UUID, expected_version: int, completed: bool
    ) -> dict[str, Any]:
        return self.tasks.task_completion(actor_uid, uid, expected_version, completed)

    def update_settings(
        self, actor_uid: uuid.UUID, expected_version: int, settings: dict[str, Any]
    ) -> None:
        return self.settings.update_settings(actor_uid, expected_version, settings)


__all__ = ["GovernedResourceStore", "ResourceConflict", "ResourceNotFound"]
