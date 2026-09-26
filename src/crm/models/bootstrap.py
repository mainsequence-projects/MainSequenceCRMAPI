"""Pydantic CRM bootstrap models."""

from __future__ import annotations

from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    conint,
    constr,
)

from .common import NonEmptyChanges


class ReadinessStatus(Enum):
    ready = "ready"
    not_ready = "not_ready"


class CheckStatus(Enum):
    ready = "ready"
    failed = "failed"
    pending = "pending"


class Check(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    status: CheckStatus
    message: str


class Readiness(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    status: ReadinessStatus
    schema_version: str
    application_version: str
    checks: list[Check]


class Principal(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    uid: UUID
    display_name: str
    selectable: StrictBool


class Option(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: constr(min_length=1)
    label: constr(min_length=1)


class Settings(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    configuration_version: conint(strict=True, ge=1)
    default_currency: constr(pattern=r"^[A-Z]{3}$")
    timezone: str
    company_sectors: list[Option] = Field(..., max_length=100)
    contact_statuses: list[Option] = Field(..., max_length=100)
    deal_categories: list[Option] = Field(..., max_length=100)
    task_types: list[Option] = Field(..., max_length=100)


class SettingsChanges(NonEmptyChanges):
    model_config = ConfigDict(
        extra="forbid",
    )
    default_currency: constr(pattern=r"^[A-Z]{3}$") | None = None
    timezone: str | None = None
    company_sectors: list[Option] | None = Field(None, max_length=100)
    contact_statuses: list[Option] | None = Field(None, max_length=100)
    deal_categories: list[Option] | None = Field(None, max_length=100)
    task_types: list[Option] | None = Field(None, max_length=100)


class SettingsPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: conint(strict=True, ge=1)
    changes: SettingsChanges


class CrmCapability(Enum):
    crm_read = "crm.read"
    crm_create = "crm.create"
    crm_edit = "crm.edit"
    crm_archive = "crm.archive"
    crm_merge = "crm.merge"
    crm_transfer_import = "crm.transfer.import"
    crm_transfer_export = "crm.transfer.export"
    crm_configure = "crm.configure"


class Limits(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    list_page_max: conint(strict=True, ge=1)
    bulk_explicit_max: conint(strict=True, ge=1)
    upload_bytes_max: conint(strict=True, ge=1)
    transfer_rows_max: conint(strict=True, ge=1)


class LocalRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["local"]
    base_path: Literal["/tau"]


class PlatformRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["platform"]


class AssistantUnavailable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: Literal[False]
    runtime: None
    agent_uid: None
    environment_uid: None
    display_name: str | None


class AssistantLocal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: Literal[True]
    runtime: LocalRuntime
    agent_uid: None
    environment_uid: None
    display_name: constr(min_length=1)


class AssistantPlatform(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: Literal[True]
    runtime: PlatformRuntime
    agent_uid: UUID
    environment_uid: UUID
    display_name: constr(min_length=1)


class Bootstrap(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    application_version: str
    current_user: Principal
    capabilities: list[CrmCapability]
    settings: Settings
    default_pipeline_uid: UUID
    limits: Limits
    modules: dict[str, bool]
    readiness: Readiness
    assistant: AssistantUnavailable | AssistantLocal | AssistantPlatform
