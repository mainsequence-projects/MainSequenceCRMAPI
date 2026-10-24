"""Typed contracts for the optional Campaigns module (ADR 0001).

Definitions (Campaign, Step, Transition, step Prompt) are live records. The
participant's progress records are embedded values owned by the service.
"""

from __future__ import annotations

import json
import math
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    conint,
    field_validator,
    model_validator,
)

from src.crm.models.common import NonEmptyChanges, VersionCommand
from src.crm.models.prompts import MARKDOWN_BYTES_MAX, validate_markdown

CampaignStatus = Literal["draft", "active", "paused", "completed"]
ParticipantStatus = Literal["active", "paused", "completed", "withdrawn"]
ProgressState = Literal["open", "waiting", "blocked", "completed", "cancelled"]
CompletionMode = Literal["human", "agent"]
ValueType = Literal["string", "boolean", "number", "datetime", "object", "array"]

# Finite bounds (ADR 0001 "documented finite bounds").
STEPS_MAX = 50
TRANSITIONS_MAX = 200
OUTCOMES_MAX = 20
VARIANTS_MAX = 2
FIELDS_MAX = 30
EVIDENCE_MAX = 50
JSON_BYTES_MAX = 16_384
SECONDS_MAX = 366 * 24 * 3600

Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
VariantKey = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")]
ComparisonKey = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ShortText = Annotated[str, StringConstraints(max_length=2000)]
BindingPath = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


def bounded_json(value: Any, *, label: str) -> Any:
    """Reject unbounded or non-JSON values before they reach governed SQL."""
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be JSON-compatible") from exc
    if len(encoded.encode("utf-8")) > JSON_BYTES_MAX:
        raise ValueError(f"{label} exceeds {JSON_BYTES_MAX} bytes")
    if "\x00" in encoded:
        raise ValueError(f"{label} cannot contain NUL characters")

    def depth(item: Any, level: int = 0) -> int:
        if level > 8:
            raise ValueError(f"{label} is nested too deeply")
        if isinstance(item, dict):
            return max((depth(child, level + 1) for child in item.values()), default=level)
        if isinstance(item, list):
            return max((depth(child, level + 1) for child in item), default=level)
        return level

    depth(value)
    return value


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_uid: UUID | None
    updated_by_uid: UUID | None
    version: StrictInt = Field(ge=1)
    archived_at: AwareDatetime | None


# --- Step definition values -------------------------------------------------


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Key
    label: Label
    description: ShortText | None = None


class PromptVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: VariantKey
    label: Label
    prompt_uid: UUID
    allocation_percent: conint(strict=True, ge=1, le=100)


class PromptComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: ComparisonKey
    control_variant_key: VariantKey
    metric_step_uid: UUID
    success_outcome_keys: list[Key] = Field(min_length=1, max_length=OUTCOMES_MAX)
    observation_window_seconds: conint(strict=True, ge=1, le=SECONDS_MAX)

    @field_validator("success_outcome_keys")
    @classmethod
    def unique_keys(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("success_outcome_keys must be unique")
        return value


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float

    @field_validator("x", "y")
    @classmethod
    def finite(cls, value: float) -> float:
        if not math.isfinite(value) or abs(value) > 1_000_000:
            raise ValueError("Layout coordinates must be finite and bounded")
        return value


class StepFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Label
    task_text: str = Field(min_length=1, max_length=MARKDOWN_BYTES_MAX)
    prompt_variants: list[PromptVariant] = Field(min_length=1, max_length=VARIANTS_MAX)
    prompt_comparison: PromptComparison | None = None
    completion_mode: CompletionMode = "human"
    owner_uid: UUID | None = None
    task_type_key: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    due_after_seconds: conint(strict=True, ge=0, le=SECONDS_MAX) | None = None
    input_bindings: dict[Key, BindingPath] = Field(default_factory=dict)
    completion_criteria: str = Field(min_length=1, max_length=MARKDOWN_BYTES_MAX)
    outcomes: list[Outcome] = Field(min_length=1, max_length=OUTCOMES_MAX)
    position: Position | None = None

    _task_text = field_validator("task_text")(validate_markdown)
    _criteria = field_validator("completion_criteria")(validate_markdown)

    @field_validator("input_bindings")
    @classmethod
    def bounded_bindings(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > FIELDS_MAX:
            raise ValueError("Too many input bindings")
        return value

    @model_validator(mode="after")
    def consistent_definition(self):
        keys = [variant.key for variant in self.prompt_variants]
        if len(set(keys)) != len(keys):
            raise ValueError("Prompt variant keys must be unique within a step")
        if sum(variant.allocation_percent for variant in self.prompt_variants) != 100:
            raise ValueError("Prompt variant allocations must sum to 100")
        if len(self.prompt_variants) == 2 and self.prompt_comparison is None:
            raise ValueError("Two prompt variants require a prompt comparison")
        if len(self.prompt_variants) == 1 and self.prompt_comparison is not None:
            raise ValueError("A single prompt variant cannot define a comparison")
        if self.prompt_comparison and self.prompt_comparison.control_variant_key not in keys:
            raise ValueError("The comparison control variant must be one of the step variants")
        outcome_keys = [outcome.key for outcome in self.outcomes]
        if len(set(outcome_keys)) != len(outcome_keys):
            raise ValueError("Outcome keys must be unique within a step")
        return self


class GraphStep(StepFields):
    """A step inside a candidate graph. New steps carry a client-generated UUID."""

    uid: UUID
    archived: bool = False


class Step(StepFields, Record):
    campaign_uid: UUID


class GraphTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    from_step_uid: UUID
    outcome_key: Key
    to_step_uid: UUID | None = None
    delay_seconds: conint(strict=True, ge=0, le=SECONDS_MAX) = 0

    @model_validator(mode="after")
    def finish_has_no_delay(self):
        if self.to_step_uid is None and self.delay_seconds:
            raise ValueError("A finish connection cannot define a delay")
        return self


class Transition(Record):
    campaign_uid: UUID
    from_step_uid: UUID
    outcome_key: Key
    to_step_uid: UUID | None
    delay_seconds: StrictInt


class CampaignGraph(BaseModel):
    """The complete candidate graph: every active step and every connection."""

    model_config = ConfigDict(extra="forbid")

    entry_step_uid: UUID | None = None
    steps: list[GraphStep] = Field(default_factory=list, max_length=STEPS_MAX)
    transitions: list[GraphTransition] = Field(default_factory=list, max_length=TRANSITIONS_MAX)

    @model_validator(mode="after")
    def unique_identities(self):
        step_uids = [step.uid for step in self.steps]
        if len(set(step_uids)) != len(step_uids):
            raise ValueError("Step UIDs must be unique")
        transition_uids = [item.uid for item in self.transitions]
        if len(set(transition_uids)) != len(transition_uids):
            raise ValueError("Transition UIDs must be unique")
        return self


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    step_uid: UUID | None = None
    transition_uid: UUID | None = None


class GraphValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runnable: bool
    diagnostics: list[Diagnostic]


AffectedWorkPolicy = Literal["block", "cancel"]


class GraphUpdate(VersionCommand):
    graph: CampaignGraph
    affected_open_work: AffectedWorkPolicy = "block"


class GraphValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph: CampaignGraph


# --- Campaign ---------------------------------------------------------------


class CampaignFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Label
    objective: str = Field(min_length=1, max_length=MARKDOWN_BYTES_MAX)
    owner_uid: UUID
    context: dict[str, Any] = Field(default_factory=dict)

    _objective = field_validator("objective")(validate_markdown)

    @field_validator("context")
    @classmethod
    def bounded_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        return bounded_json(value, label="context")


class CampaignCreate(CampaignFields):
    pass


class CampaignChanges(NonEmptyChanges):
    name: Label | None = None
    objective: str | None = Field(default=None, min_length=1, max_length=MARKDOWN_BYTES_MAX)
    owner_uid: UUID | None = None
    context: dict[str, Any] | None = None
    status: CampaignStatus | None = None

    @field_validator("name", "objective", "owner_uid", "context", "status")
    @classmethod
    def required_fields(cls, value, info):
        if value is None:
            raise ValueError("Campaign fields cannot be null")
        if info.field_name == "objective":
            return validate_markdown(value)
        if info.field_name == "context":
            return bounded_json(value, label="context")
        return value


class CampaignPatch(VersionCommand):
    changes: CampaignChanges


class CampaignSummary(CampaignFields, Record):
    status: CampaignStatus
    entry_step_uid: UUID | None
    participant_counts: dict[str, int] = Field(default_factory=dict)


class VariantReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_key: str
    assigned: int
    completed: int
    cancelled: int
    matured: int
    successes: int
    success_rate: float | None
    changed_exposures: int


class ComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_uid: UUID
    comparison_key: str
    current: bool
    control_variant_key: str | None
    metric_step_uid: UUID | None
    success_outcome_keys: list[str]
    observation_window_seconds: int | None
    variants: list[VariantReport]


class Campaign(CampaignSummary):
    steps: list[Step]
    transitions: list[Transition]
    validation: GraphValidation
    comparisons: list[ComparisonReport]


# --- Step prompt (Agent Prompt specialization) -------------------------------


class ValueField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Key
    type: ValueType
    required: bool = True
    description: ShortText | None = None


def unique_field_keys(value: list[ValueField]) -> list[ValueField]:
    keys = [item.key for item in value]
    if len(set(keys)) != len(keys):
        raise ValueError("Field keys must be unique")
    reserved = {"outcome_key", "result", "evidence"} & set(keys)
    if reserved:
        raise ValueError(f"Reserved completion fields cannot be declared: {sorted(reserved)}")
    return value


class StepPromptCreate(BaseModel):
    """Create a new specialized prompt, or specialize an existing Agent Prompt by UID."""

    model_config = ConfigDict(extra="forbid")

    prompt_uid: UUID | None = None
    expected_version: conint(strict=True, ge=1) | None = None
    name: Label | None = None
    description: ShortText | None = None
    content_markdown: str | None = Field(default=None, min_length=1, max_length=MARKDOWN_BYTES_MAX)
    inputs: list[ValueField] = Field(default_factory=list, max_length=FIELDS_MAX)
    result_fields: list[ValueField] = Field(default_factory=list, max_length=FIELDS_MAX)

    _inputs = field_validator("inputs")(unique_field_keys)
    _results = field_validator("result_fields")(unique_field_keys)

    @model_validator(mode="after")
    def one_shape(self):
        specializing = self.prompt_uid is not None
        if specializing:
            if self.expected_version is None:
                raise ValueError("Specializing an existing prompt requires expected_version")
            if self.name is not None or self.content_markdown is not None:
                raise ValueError("Specialization keeps the existing prompt document")
        else:
            if self.expected_version is not None:
                raise ValueError("expected_version only applies to specialization")
            if not self.name or not self.content_markdown:
                raise ValueError("A new step prompt needs a name and content_markdown")
            validate_markdown(self.content_markdown)
        return self


class StepPromptChanges(NonEmptyChanges):
    name: Label | None = None
    description: ShortText | None = None
    content_markdown: str | None = Field(default=None, min_length=1, max_length=MARKDOWN_BYTES_MAX)
    inputs: list[ValueField] | None = Field(default=None, max_length=FIELDS_MAX)
    result_fields: list[ValueField] | None = Field(default=None, max_length=FIELDS_MAX)

    @field_validator("name", "content_markdown", "inputs", "result_fields")
    @classmethod
    def required_fields(cls, value, info):
        if value is None:
            raise ValueError("Required step prompt fields cannot be null")
        if info.field_name == "content_markdown":
            return validate_markdown(value)
        if info.field_name in {"inputs", "result_fields"}:
            return unique_field_keys(value)
        return value


class StepPromptPatch(VersionCommand):
    changes: StepPromptChanges


class StepPromptSummary(Record):
    name: str
    description: str | None
    inputs: list[ValueField]
    result_fields: list[ValueField]


class StepPrompt(StepPromptSummary):
    content_markdown: str


# --- Participant and progress ---------------------------------------------


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    resource_type: Annotated[str, StringConstraints(min_length=1, max_length=50)] | None = None
    resource_uid: UUID | None = None


class AssignedComparison(PromptComparison):
    allocation: dict[VariantKey, conint(strict=True, ge=1, le=100)]


class PromptAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_key: VariantKey
    prompt_uid: UUID
    assigned_prompt_version: StrictInt
    assigned_at: AwareDatetime
    comparison: AssignedComparison | None = None
    comparison_changed: bool = False


class PreparedWith(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_version: conint(strict=True, ge=1)
    step_version: conint(strict=True, ge=1)
    prompt_uid: UUID
    prompt_version: conint(strict=True, ge=1)


class ProgressRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_uid: UUID
    task_uid: UUID
    prompt_assignment: PromptAssignment
    state: ProgressState
    outcome_key: str | None
    result: dict[str, Any]
    evidence: list[Evidence]
    wake_at: AwareDatetime | None
    blocked_reason: str | None
    prepared_with: PreparedWith | None
    completed_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ParticipantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_uid: UUID
    contact_uid: UUID
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("context")
    @classmethod
    def bounded_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        return bounded_json(value, label="context")


class ParticipantChanges(NonEmptyChanges):
    context: dict[str, Any] | None = None
    status: Literal["active", "paused", "withdrawn"] | None = None
    # Explicit reroute after a live edit; the target must have no instance yet.
    next_step_uid: UUID | None = None

    @field_validator("context", "status")
    @classmethod
    def required_fields(cls, value, info):
        if value is None:
            raise ValueError("Participant fields cannot be null")
        if info.field_name == "context":
            return bounded_json(value, label="context")
        return value


class ParticipantPatch(VersionCommand):
    changes: ParticipantChanges


class Participant(Record):
    campaign_uid: UUID
    contact_uid: UUID
    contact_display_name: str
    status: ParticipantStatus
    context: dict[str, Any]
    progress: list[ProgressRecord]
    next_step_uid: UUID | None
    eligible_at: AwareDatetime | None
    finished_at: AwareDatetime | None


# --- Task commands -----------------------------------------------------------


class ProgressRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_uid: UUID
    step_uid: UUID


class AdvanceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_uid: UUID
    expected_version: conint(strict=True, ge=1)


class CompleteCommand(ProgressRef):
    expected_version: conint(strict=True, ge=1)
    task_expected_version: conint(strict=True, ge=1)
    outcome_key: Key
    result: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(min_length=1, max_length=EVIDENCE_MAX)
    prepared_with: PreparedWith

    @field_validator("result")
    @classmethod
    def bounded_result(cls, value: dict[str, Any]) -> dict[str, Any]:
        return bounded_json(value, label="result")


class WaitCommand(ProgressRef):
    expected_version: conint(strict=True, ge=1)
    wake_at: AwareDatetime
    evidence: list[Evidence] = Field(default_factory=list, max_length=EVIDENCE_MAX)


class BlockCommand(ProgressRef):
    expected_version: conint(strict=True, ge=1)
    blocked_reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    evidence: list[Evidence] = Field(default_factory=list, max_length=EVIDENCE_MAX)


class ReportCommand(ProgressRef):
    """Record observed facts or partial results without completing or routing."""

    expected_version: conint(strict=True, ge=1)
    evidence: list[Evidence] = Field(min_length=1, max_length=EVIDENCE_MAX)
    result: dict[str, Any] | None = None

    @field_validator("result")
    @classmethod
    def bounded_result(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else bounded_json(value, label="result")


ReconcileAction = Literal["resume", "reopen", "cancel"]


class ReconcileCommand(ProgressRef):
    expected_version: conint(strict=True, ge=1)
    action: ReconcileAction
    task_expected_version: conint(strict=True, ge=1) | None = None
    next_step_uid: UUID | None = None
    finish: bool = False

    @model_validator(mode="after")
    def coherent(self):
        if self.action == "cancel" and (self.next_step_uid is None) == (not self.finish):
            raise ValueError("Cancelling requires exactly one of next_step_uid or finish")
        if self.action != "cancel" and (self.next_step_uid is not None or self.finish):
            raise ValueError("next_step_uid and finish only apply to cancel")
        return self


# --- Collection filters ----------------------------------------------------


class CampaignFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CampaignStatus | None = None
    owner_uid: UUID | None = None
    archived: bool | Literal["all"] | None = None


class StepPromptFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archived: bool | Literal["all"] | None = None


class ParticipantFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_uid: UUID | None = None
    contact_uid: UUID | None = None
    status: ParticipantStatus | None = None
    attention: bool | None = None
