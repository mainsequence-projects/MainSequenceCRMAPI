"""Explicit composition boundary for governed CRM transfer persistence."""

from __future__ import annotations

import uuid
from typing import Any

from ...models.queries import QueryScope
from ...platform.catalog import CatalogRegistry, configured_registry
from .connections import SourceConnections
from .exports import TransferExports
from .jobs import TransferJobs
from .planning import ImportPlanning
from .reports import TransferReports


class GovernedTransferStore:
    def __init__(self, registry: CatalogRegistry | None = None):
        binding_registry = registry or configured_registry()
        self.connections = SourceConnections(binding_registry)
        self.jobs = TransferJobs(binding_registry)
        self.planning = ImportPlanning(binding_registry)
        self.reports = TransferReports(binding_registry)
        self.exports = TransferExports(binding_registry)

    def source_connections(self, page_index: int, page_size: int) -> dict[str, Any]:
        return self.connections.source_connections(page_index, page_size)

    def create_source_connection(
        self, actor_uid: uuid.UUID, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self.connections.create_source_connection(actor_uid, payload)

    def transfers(self, actor_uid: uuid.UUID, scope: QueryScope) -> dict[str, Any]:
        return self.jobs.transfers(actor_uid, scope)

    def transfer_detail(self, job_uid: uuid.UUID, actor_uid: uuid.UUID) -> dict[str, Any]:
        return self.jobs.transfer_detail(job_uid, actor_uid)

    def create_import(self, actor_uid: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        return self.jobs.create_import(actor_uid, payload)

    def stage_upload(
        self,
        actor_uid: uuid.UUID,
        job_uid: uuid.UUID,
        filename: str,
        content_type: str,
        digest: str,
        rows: list[dict[str, Any]],
        entity_type: str,
    ) -> dict[str, Any]:
        return self.jobs.stage_upload(
            actor_uid, job_uid, filename, content_type, digest, rows, entity_type
        )

    def save_mapping(
        self, actor_uid: uuid.UUID, job_uid: uuid.UUID, mapping: dict[str, Any]
    ) -> dict[str, Any]:
        return self.jobs.save_mapping(actor_uid, job_uid, mapping)

    def validate_import(self, actor_uid: uuid.UUID, job_uid: uuid.UUID) -> dict[str, Any]:
        return self.planning.validate_import(actor_uid, job_uid)

    def plan(self, actor_uid: uuid.UUID, job_uid: uuid.UUID) -> dict[str, Any]:
        return self.planning.plan(actor_uid, job_uid)

    def commit_import(
        self, actor_uid: uuid.UUID, job_uid: uuid.UUID, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self.jobs.commit_import(actor_uid, job_uid, payload)

    def cancel(self, actor_uid: uuid.UUID, job_uid: uuid.UUID) -> dict[str, Any]:
        return self.jobs.cancel(actor_uid, job_uid)

    def retry(self, actor_uid: uuid.UUID, job_uid: uuid.UUID) -> dict[str, Any]:
        return self.jobs.retry(actor_uid, job_uid)

    def issues(
        self, actor_uid: uuid.UUID, job_uid: uuid.UUID, page_index: int, page_size: int
    ) -> dict[str, Any]:
        return self.reports.issues(actor_uid, job_uid, page_index, page_size)

    def errors_csv(self, actor_uid: uuid.UUID, job_uid: uuid.UUID) -> str:
        return self.reports.errors_csv(actor_uid, job_uid)

    def create_export(self, actor_uid: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        return self.exports.create_export(actor_uid, payload)

    def download_export(self, actor_uid: uuid.UUID, job_uid: uuid.UUID) -> tuple[str, str, str]:
        return self.reports.download_export(actor_uid, job_uid)
