"""Authorized, deterministic transfer operations shared by callers."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from typing import Any

from pydantic import BaseModel

from ..models.import_mapping import ImportMapping
from ..models.queries import QueryScope
from ..models.transfers import (
    CreateExport,
    CreateImport,
    ImportCommitRequest,
    SourceConnectionCreate,
)
from ..repositories.transfers.store import GovernedTransferStore
from .operations import CRMContext, validate_scope, validated_model

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_ROWS = 20_000


class ImportInputError(ValueError):
    def __init__(self, message: str, *, too_large: bool = False) -> None:
        super().__init__(message)
        self.too_large = too_large


def parse_import_rows(
    adapter: str, entity_type: str | None, content: bytes
) -> tuple[list[dict[str, Any]], str]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportInputError("Upload must be UTF-8") from exc
    if adapter.endswith("csv-v1"):
        if not entity_type:
            raise ImportInputError("CSV imports require an entity type")
        try:
            rows = [dict(row) for row in csv.DictReader(io.StringIO(text, newline=""))]
        except csv.Error as exc:
            raise ImportInputError("Invalid CSV input") from exc
        return rows, entity_type
    try:
        document = json.loads(text, parse_int=str, parse_float=str)
    except json.JSONDecodeError as exc:
        raise ImportInputError("Invalid JSON input") from exc
    if not isinstance(document, dict):
        raise ImportInputError("JSON import must be an object")
    rows: list[dict[str, Any]] = []
    if adapter == "mainsequence-portable-v1":
        records = document.get("entities")
        if document.get("format") != "mainsequence.crm.portable@v1" or not isinstance(
            records, dict
        ):
            raise ImportInputError("Invalid portable CRM envelope")
        supported = {
            "companies": "company",
            "contacts": "contact",
            "tags": "tag",
            "pipelines": "pipeline",
            "stages": "stage",
            "deals": "deal",
            "notes": "note",
            "tasks": "task",
            "contact_company_affiliations": "contact_company_affiliation",
        }
        for group, values in records.items():
            if group not in supported:
                raise ImportInputError(f"Unsupported portable group: {group}")
            if not isinstance(values, list):
                raise ImportInputError(f"Portable {group} must be an array")
            for value in values:
                if not isinstance(value, dict):
                    raise ImportInputError(f"Portable {group} row must be an object")
                rows.append({**value, "__entity_type": supported[group]})
        return rows, "bundle"
    tables = document.get("tables", document)
    if not isinstance(tables, dict):
        raise ImportInputError("JSON table bundle must be an object")
    for group, values in tables.items():
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                rows.append({"__entity_type": group.removesuffix("s"), **value})
    return rows, "bundle"


class TransferOperations:
    def __init__(self, context: CRMContext, store: GovernedTransferStore | None = None) -> None:
        self.context = context
        self.store = store if store is not None else GovernedTransferStore()

    def source_connections(self, page_index: int, page_size: int) -> dict[str, Any]:
        self.context.require("crm.transfer.import")
        if page_index < 0 or not 1 <= page_size <= 100:
            raise ImportInputError("Invalid pagination")
        return self.store.source_connections(page_index, page_size)

    def create_source_connection(self, payload: BaseModel) -> dict[str, Any]:
        self.context.require("crm.transfer.import")
        payload = validated_model(SourceConnectionCreate, payload)
        return self.store.create_source_connection(
            self.context.actor_uid, payload.model_dump(mode="json")
        )

    def list_transfers(self, scope: QueryScope) -> dict[str, Any]:
        self.context.require("crm.read")
        return self.store.transfers(self.context.actor_uid, validate_scope("transfers", scope))

    def create_import(self, payload: BaseModel) -> dict[str, Any]:
        self.context.require("crm.transfer.import")
        payload = validated_model(CreateImport, payload)
        return self.store.create_import(self.context.actor_uid, payload.model_dump(mode="json"))

    def upload_import(
        self, uid: uuid.UUID, filename: str, content_type: str, content: bytes
    ) -> dict[str, Any]:
        self.context.require("crm.transfer.import")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ImportInputError("Import file exceeds 20 MiB", too_large=True)
        job = self.store._job_row(uid, self.context.actor_uid)
        manifest = job.get("input_manifest")
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        rows, fallback_type = parse_import_rows(
            job["adapter_id"], (manifest or {}).get("entity_type"), content
        )
        if len(rows) > MAX_ROWS:
            raise ImportInputError("Import exceeds 20,000 rows", too_large=True)
        return self.store.stage_upload(
            self.context.actor_uid,
            uid,
            filename,
            content_type,
            hashlib.sha256(content).hexdigest(),
            rows,
            fallback_type,
        )

    def save_mapping(self, uid: uuid.UUID, payload: BaseModel) -> dict[str, Any]:
        self.context.require("crm.transfer.import")
        payload = validated_model(ImportMapping, payload)
        return self.store.save_mapping(self.context.actor_uid, uid, payload.model_dump(mode="json"))

    def validate_import(self, uid: uuid.UUID) -> dict[str, Any]:
        self.context.require("crm.transfer.import")
        return self.store.validate_import(self.context.actor_uid, uid)

    def import_plan(self, uid: uuid.UUID) -> dict[str, Any]:
        self.context.require("crm.transfer.import")
        return self.store.plan(self.context.actor_uid, uid)

    def commit_import(self, uid: uuid.UUID, payload: BaseModel) -> dict[str, Any]:
        self.context.require("crm.transfer.import")
        payload = validated_model(ImportCommitRequest, payload)
        return self.store.commit_import(
            self.context.actor_uid, uid, payload.model_dump(mode="json")
        )

    def transfer_detail(self, uid: uuid.UUID) -> dict[str, Any]:
        self.context.require("crm.read")
        return self.store.transfer_detail(uid, self.context.actor_uid)

    def transfer_issues(self, uid: uuid.UUID, page_index: int, page_size: int) -> dict[str, Any]:
        self.context.require("crm.read")
        if page_index < 0 or not 1 <= page_size <= 100:
            raise ImportInputError("Invalid pagination")
        return self.store.issues(self.context.actor_uid, uid, page_index, page_size)

    def transfer_errors(self, uid: uuid.UUID) -> str:
        self.context.require("crm.read")
        return self.store.errors_csv(self.context.actor_uid, uid)

    def transfer_action(self, uid: uuid.UUID, action: str) -> dict[str, Any]:
        if action not in {"cancel", "retry"}:
            raise ValueError("Unknown transfer action")
        self.context.require("crm.read")
        job = self.store._job_row(uid, self.context.actor_uid)
        required = "crm.transfer.import" if job["direction"] == "import" else "crm.transfer.export"
        self.context.require(required)
        return getattr(self.store, action)(self.context.actor_uid, uid)

    def create_export(self, payload: BaseModel) -> dict[str, Any]:
        self.context.require("crm.transfer.export")
        payload = validated_model(CreateExport, payload)
        return self.store.create_export(self.context.actor_uid, payload.model_dump(mode="json"))

    def download_export(self, uid: uuid.UUID) -> tuple[str, str, str]:
        self.context.require("crm.transfer.export")
        return self.store.download_export(self.context.actor_uid, uid)
