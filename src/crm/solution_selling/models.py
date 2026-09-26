"""Typed contracts for the optional Solution Selling module."""

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

from src.crm.models.common import NonEmptyChanges

AssessmentStatus = Literal["hypothesis", "reported", "confirmed"]
LeadStatus = Literal["to_contact", "contacted", "qualified", "nurture", "disqualified"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_uid: UUID | None
    updated_by_uid: UUID | None
    version: StrictInt
    archived_at: AwareDatetime | None


class KeyPlayerPain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_uid: UUID
    pain: str | None
    reasons: list[str] = Field(default_factory=list)
    status: AssessmentStatus


class PainChainLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_contact_uid: UUID
    to_contact_uid: UUID
    explanation: constr(min_length=1)
    status: AssessmentStatus


def validate_pain_chain(
    key_players: list[KeyPlayerPain], pain_chain: list[PainChainLink]
) -> None:
    players = {item.contact_uid: item for item in key_players}
    if len(players) != len(key_players):
        raise ValueError("key_players contains a duplicate Contact")
    links: set[tuple[UUID, UUID]] = set()
    for link in pain_chain:
        pair = (link.from_contact_uid, link.to_contact_uid)
        if link.from_contact_uid == link.to_contact_uid or pair in links:
            raise ValueError("pain_chain contains a self-link or duplicate directed link")
        if any(uid not in players or not players[uid].pain for uid in pair):
            raise ValueError("pain_chain endpoints must have recorded key-player pains")
        links.add(pair)


class AssessmentFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deal_uid: UUID
    company_uid: UUID
    pain_summary: str | None = None
    pain_contact_uid: UUID | None = None
    power_summary: str | None = None
    power_contact_uid: UUID | None = None
    sponsor_contact_uid: UUID | None = None
    vision_summary: str | None = None
    value_summary: str | None = None
    control_summary: str | None = None
    key_players: list[KeyPlayerPain] = Field(default_factory=list)
    pain_chain: list[PainChainLink] = Field(default_factory=list)
    evaluation_plan: str | None = None

    @model_validator(mode="after")
    def valid_chain(self):
        validate_pain_chain(self.key_players, self.pain_chain)
        return self


class AssessmentCreate(AssessmentFields):
    pass


class SolutionSelling(AssessmentFields, Record):
    pass


class AssessmentChanges(NonEmptyChanges):
    model_config = ConfigDict(extra="forbid")

    pain_summary: str | None = None
    pain_contact_uid: UUID | None = None
    power_summary: str | None = None
    power_contact_uid: UUID | None = None
    sponsor_contact_uid: UUID | None = None
    vision_summary: str | None = None
    value_summary: str | None = None
    control_summary: str | None = None
    key_players: list[KeyPlayerPain] | None = None
    pain_chain: list[PainChainLink] | None = None
    evaluation_plan: str | None = None


class DiagnosisEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: constr(min_length=1)
    answer: str | None = None


class DiagnosisRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasons: list[DiagnosisEntry] = Field(default_factory=list)
    impact: list[DiagnosisEntry] = Field(default_factory=list)
    capabilities: list[DiagnosisEntry] = Field(default_factory=list)


class DiagnosisMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open: DiagnosisRow = Field(default_factory=DiagnosisRow)
    control: DiagnosisRow = Field(default_factory=DiagnosisRow)
    confirming: DiagnosisRow = Field(default_factory=DiagnosisRow)


class DiagnosisFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_uid: UUID
    contact_uid: UUID
    solution_selling_uid: UUID | None = None
    business_issue: constr(min_length=1)
    matrix: DiagnosisMatrix = Field(default_factory=DiagnosisMatrix)
    conclusion: str | None = None


class DiagnosisCreate(DiagnosisFields):
    pass


class SolutionSellingDiagnosis(DiagnosisFields, Record):
    pass


class DiagnosisChanges(NonEmptyChanges):
    model_config = ConfigDict(extra="forbid")

    solution_selling_uid: UUID | None = None
    business_issue: constr(min_length=1) | None = None
    matrix: DiagnosisMatrix | None = None
    conclusion: str | None = None


class ProspectingProfileFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: constr(min_length=1, max_length=255)
    market_context: constr(min_length=1, max_length=255)
    role: constr(min_length=1, max_length=255)
    potential_pain: constr(min_length=1)
    likely_reasons: list[str] = Field(default_factory=list)
    likely_impacts: list[str] = Field(default_factory=list)
    research_guidance: str | None = None
    opening_message: str | None = None
    suggested_next_commitment: str | None = None
    diagnosis_template: DiagnosisMatrix | None = None

    @model_validator(mode="after")
    def unanswered_template(self):
        if self.diagnosis_template is not None:
            for approach in ("open", "control", "confirming"):
                row = getattr(self.diagnosis_template, approach)
                for subject in ("reasons", "impact", "capabilities"):
                    if any(entry.answer is not None for entry in getattr(row, subject)):
                        raise ValueError("diagnosis_template cannot contain answers")
        return self


class ProspectingProfileCreate(ProspectingProfileFields):
    pass


class SolutionSellingProspectingProfile(ProspectingProfileFields, Record):
    pass


class ProspectingProfileChanges(NonEmptyChanges):
    model_config = ConfigDict(extra="forbid")

    name: constr(min_length=1, max_length=255) | None = None
    market_context: constr(min_length=1, max_length=255) | None = None
    role: constr(min_length=1, max_length=255) | None = None
    potential_pain: constr(min_length=1) | None = None
    likely_reasons: list[str] | None = None
    likely_impacts: list[str] | None = None
    research_guidance: str | None = None
    opening_message: str | None = None
    suggested_next_commitment: str | None = None
    diagnosis_template: DiagnosisMatrix | None = None


class LeadFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_uid: UUID
    profile_uid: UUID | None = None
    owner_uid: UUID | None = None
    status: LeadStatus
    next_task_uid: UUID | None = None
    notes: str | None = None


class LeadCreate(LeadFields):
    pass


class SolutionSellingLead(LeadFields, Record):
    pass


class LeadChanges(NonEmptyChanges):
    model_config = ConfigDict(extra="forbid")

    profile_uid: UUID | None = None
    owner_uid: UUID | None = None
    status: LeadStatus | None = None
    next_task_uid: UUID | None = None
    notes: str | None = None


class PrompterFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: constr(min_length=1, max_length=255)
    kind: constr(min_length=1, max_length=100)
    description: str | None = None
    template: constr(min_length=1, max_length=16384)


class PrompterCreate(PrompterFields):
    pass


class SolutionSellingPrompter(PrompterFields, Record):
    pass


class PrompterChanges(NonEmptyChanges):
    model_config = ConfigDict(extra="forbid")

    name: constr(min_length=1, max_length=255) | None = None
    kind: constr(min_length=1, max_length=100) | None = None
    description: str | None = None
    template: constr(min_length=1, max_length=16384) | None = None


class VersionedPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: conint(strict=True, ge=1)


class AssessmentPatch(VersionedPatch):
    changes: AssessmentChanges


class DiagnosisPatch(VersionedPatch):
    changes: DiagnosisChanges


class ProspectingProfilePatch(VersionedPatch):
    changes: ProspectingProfileChanges


class LeadPatch(VersionedPatch):
    changes: LeadChanges


class PrompterPatch(VersionedPatch):
    changes: PrompterChanges


class PrompterRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_uid: UUID
    company_uid: UUID
    lead_uid: UUID | None = None
    profile_uid: UUID | None = None
    deal_uid: UUID | None = None
    solution_selling_uid: UUID | None = None
    inputs: dict[str, str] = Field(default_factory=dict)


class PrompterRenderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
