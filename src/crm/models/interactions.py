"""Core CRM conversation contracts; independent of sales methodology."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    conint,
    constr,
    model_validator,
)

from .common import NonEmptyChanges


class InteractionParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_uid: UUID | None = None
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=255)
    role: Literal["organizer", "attendee"] = "attendee"

    @model_validator(mode="after")
    def identifies_person(self) -> InteractionParticipant:
        self.email = (self.email.strip() or None) if self.email is not None else None
        self.display_name = (self.display_name.strip() or None) if self.display_name is not None else None
        if not (self.contact_uid or self.email or self.display_name):
            raise ValueError("A participant needs a Contact, email, or name")
        return self


class InteractionFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_uid: UUID | None = None
    deal_uid: UUID | None = None
    participants: list[InteractionParticipant] = Field(default_factory=list, max_length=100)
    subject: constr(min_length=1, max_length=255)
    kind: Literal["call", "meeting", "workshop", "email"]
    status: Literal["planned", "completed", "cancelled"]
    scheduled_at: AwareDatetime | None = None
    occurred_at: AwareDatetime | None = None
    objective: str | None = None
    research_notes: str | None = None
    discussion_plan: str | None = None
    outcome_notes: str | None = None
    next_steps: str | None = None

    @model_validator(mode="after")
    def deal_has_company(self) -> InteractionFields:
        if self.deal_uid and not self.company_uid:
            raise ValueError("A Deal context requires its Company")
        contacts: set[UUID] = set()
        emails: set[str] = set()
        names_without_other_identity: set[str] = set()
        for person in self.participants:
            contact = person.contact_uid
            email = person.email.casefold() if person.email else None
            name = person.display_name.casefold() if person.display_name and not (contact or email) else None
            if (contact and contact in contacts) or (email and email in emails) or (name and name in names_without_other_identity):
                raise ValueError("Participants must be unique")
            if contact:
                contacts.add(contact)
            if email:
                emails.add(email)
            if name:
                names_without_other_identity.add(name)
        return self


class InteractionCreate(InteractionFields):
    @model_validator(mode="after")
    def has_participants(self) -> InteractionCreate:
        if not self.participants:
            raise ValueError("Select at least one person in this Interaction")
        return self


class Interaction(InteractionFields):
    uid: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_uid: UUID | None
    updated_by_uid: UUID | None
    version: StrictInt
    archived_at: AwareDatetime | None


class InteractionChanges(NonEmptyChanges):
    model_config = ConfigDict(extra="forbid")

    company_uid: UUID | None = None
    deal_uid: UUID | None = None
    participants: list[InteractionParticipant] | None = None
    subject: constr(min_length=1, max_length=255) | None = None
    kind: Literal["call", "meeting", "workshop", "email"] | None = None
    status: Literal["planned", "completed", "cancelled"] | None = None
    scheduled_at: AwareDatetime | None = None
    occurred_at: AwareDatetime | None = None
    objective: str | None = None
    research_notes: str | None = None
    discussion_plan: str | None = None
    outcome_notes: str | None = None
    next_steps: str | None = None

    @model_validator(mode="after")
    def cannot_clear_people(self) -> InteractionChanges:
        if self.participants is not None and not self.participants:
            raise ValueError("An Interaction needs at least one person")
        return self


class InteractionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: conint(strict=True, ge=1)
    changes: InteractionChanges
