"""Pydantic CRM transfers models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    conint,
    constr,
)


class ImportCommitMode(Enum):
    strict = "strict"
    valid_rows_only = "valid_rows_only"


class ImportCommitRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    plan_hash: constr(pattern=r"^[a-f0-9]{64}$")
    mapping_revision: conint(strict=True, ge=1)
    accept_warnings: StrictBool
    mode: ImportCommitMode


class ImportAdapterId(Enum):
    generic_csv_v1 = "generic-csv-v1"
    atomic_csv_v1 = "atomic-csv-v1"
    atomic_legacy_json_v1 = "atomic-legacy-json-v1"
    atomic_raw_json_v1 = "atomic-raw-json-v1"
    mainsequence_portable_v1 = "mainsequence-portable-v1"


class ImportEntityType(Enum):
    company = "company"
    contact = "contact"
    deal = "deal"
    task = "task"
    note = "note"
    tag = "tag"


class CreateImport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    adapter_id: ImportAdapterId
    source_connection_uid: UUID
    entity_type: ImportEntityType | None
    display_name: constr(min_length=1, max_length=255)


class TransferDirection(Enum):
    import_ = "import"
    export = "export"


class TransferStatus(Enum):
    uploading = "uploading"
    staged = "staged"
    validating = "validating"
    needs_mapping = "needs_mapping"
    validated = "validated"
    queued = "queued"
    running = "running"
    partial = "partial"
    failed = "failed"
    succeeded = "succeeded"
    cancelled = "cancelled"
    expired = "expired"


class TransferCounts(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    total: conint(strict=True, ge=0)
    valid: conint(strict=True, ge=0)
    blocked: conint(strict=True, ge=0)
    committed: conint(strict=True, ge=0)
    skipped: conint(strict=True, ge=0)
    failed: conint(strict=True, ge=0)


class TransferSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    uid: UUID
    direction: TransferDirection
    status: TransferStatus
    mapping_revision: conint(strict=True, ge=1)
    plan_hash: constr(pattern=r"^[a-f0-9]{64}$") | None
    counts: TransferCounts
    cancel_requested: StrictBool
    created_at: AwareDatetime
    updated_at: AwareDatetime


class SourceConnectionCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: constr(min_length=1, max_length=255)
    adapter_id: ImportAdapterId
    source_account_key: constr(min_length=1, max_length=255)


class SourceConnection(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    uid: UUID
    name: constr(min_length=1, max_length=255)
    adapter_id: ImportAdapterId
    source_account_key: constr(min_length=1, max_length=255)
    version: conint(strict=True, ge=1)


class ValidationSeverity(Enum):
    warning = "warning"
    error = "error"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    row_uid: UUID
    entity_type: str
    ordinal: conint(strict=True, ge=0)
    field: str | None
    code: str
    message: str
    severity: ValidationSeverity


class TransferPlan(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    job_uid: UUID
    plan_hash: constr(pattern=r"^[a-f0-9]{64}$")
    mapping_revision: conint(strict=True, ge=1)
    can_commit: StrictBool
    counts: TransferCounts
    issues: list[ValidationIssue] = Field(..., max_length=200)
    has_more_issues: StrictBool


class ExportFormat(Enum):
    portable_json = "portable-json"
    csv = "csv"


class ExportEntityType(Enum):
    companies = "companies"
    contacts = "contacts"
    deals = "deals"
    tasks = "tasks"
    notes = "notes"
    tags = "tags"


class CreateExport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    format: ExportFormat
    entity_type: ExportEntityType | None
    filters: dict[str, Any]
    search: str
    consistency: Literal["best_effort"]
    include_archived: StrictBool
