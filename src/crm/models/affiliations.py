"""Typed contact-company employment history; dates retain source precision."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

AffiliationStatus = Literal["current", "former", "unknown"]


def period_bounds(value: str) -> tuple[date, date]:
    """Validate YYYY, YYYY-MM or YYYY-MM-DD without inventing stored days."""
    parts = value.split("-")
    if len(parts) not in (1, 2, 3) or len(parts[0]) != 4:
        raise ValueError("Expected YYYY, YYYY-MM or YYYY-MM-DD")
    if any(len(part) != 2 for part in parts[1:]) or not all(
        part.isascii() and part.isdigit() for part in parts
    ):
        raise ValueError("Expected YYYY, YYYY-MM or YYYY-MM-DD")
    year = int(parts[0])
    if not 1 <= year <= 9999:
        raise ValueError("Year is outside the supported range")
    month = int(parts[1]) if len(parts) >= 2 else None
    day = int(parts[2]) if len(parts) == 3 else None
    if month is not None and not 1 <= month <= 12:
        raise ValueError("Month is outside the supported range")
    if day is not None:
        exact = date(year, month, day)  # type: ignore[arg-type]
        return exact, exact
    if month is not None:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    return date(year, 1, 1), date(year, 12, 31)


class AffiliationFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_uid: UUID
    status: AffiliationStatus
    is_primary: StrictBool = False
    started_period: str | None = Field(default=None, max_length=10)
    ended_period: str | None = Field(default=None, max_length=10)
    job_title: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def valid_period_and_primary(self):
        if self.is_primary and self.status != "current":
            raise ValueError("Only a current affiliation may be primary")
        if self.status == "current" and self.ended_period is not None:
            raise ValueError("A current affiliation cannot have an end period")
        if self.status == "unknown" and self.ended_period is not None:
            raise ValueError("An affiliation with an end period is former")
        start = period_bounds(self.started_period) if self.started_period is not None else None
        end = period_bounds(self.ended_period) if self.ended_period is not None else None
        if start and end and start[0] > end[1]:
            raise ValueError("End period precedes start period")
        if self.job_title is not None and not self.job_title.strip():
            raise ValueError("Job title must not be blank")
        return self


class AffiliationCreate(AffiliationFields):
    expected_contact_version: StrictInt = Field(ge=1)


class AffiliationChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AffiliationStatus | None = None
    started_period: str | None = Field(default=None, max_length=10)
    ended_period: str | None = Field(default=None, max_length=10)
    job_title: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def not_empty(self):
        if not self.model_fields_set:
            raise ValueError("At least one affiliation field must change")
        return self


class AffiliationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: StrictInt = Field(ge=1)
    expected_contact_version: StrictInt = Field(ge=1)
    changes: AffiliationChanges


class AffiliationTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_contact_version: StrictInt = Field(ge=1)
    previous_status: Literal["current", "former"] | None
    new_company_uid: UUID | None
    new_started_period: str | None = Field(default=None, max_length=10)
    previous_ended_period: str | None = Field(default=None, max_length=10)
    new_job_title: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def valid_transition(self):
        if self.previous_status != "former" and self.previous_ended_period is not None:
            raise ValueError("An end period requires a former previous affiliation")
        if self.new_company_uid is None and (self.new_started_period or self.new_job_title):
            raise ValueError("A new period or title requires a new company")
        if self.new_started_period is not None:
            period_bounds(self.new_started_period)
        if self.previous_ended_period is not None:
            period_bounds(self.previous_ended_period)
        if self.new_job_title is not None and not self.new_job_title.strip():
            raise ValueError("Job title must not be blank")
        return self


class Affiliation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    contact_uid: UUID
    company_uid: UUID
    company_name: str
    version: StrictInt = Field(ge=1)
    status: AffiliationStatus
    is_primary: StrictBool
    started_period: str | None
    ended_period: str | None
    job_title: str | None


class AffiliationList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Affiliation]
    next_page_index: StrictInt | None
