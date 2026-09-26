"""Transport-independent CRM operations shared by HTTP and Tau tool adapters.

Callers supply a platform-authenticated actor and trusted policy/directory
ports. No model-provided actor or capability value is accepted here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..contracts import (
    DomainValidationError,
    model_for,
    normalized_create,
    normalized_patch,
    validate_payload,
)
from ..models.affiliations import AffiliationCreate, AffiliationPatch, AffiliationTransition
from ..models.bootstrap import SettingsPatch
from ..models.deals import MoveDeal
from ..models.interactions import InteractionPatch
from ..models.merge import MergeExecuteRequest, MergePreviewRequest
from ..models.queries import FILTER_MODELS, QueryScope
from ..models.record_filters import RecordFilters
from ..platform.runtime import CAPABILITIES, BootstrapPort, DirectoryPort, PolicyPort
from ..repositories.records import RECORDS, VersionedRecordStore
from ..repositories.resources.catalog import ORDER_COLUMNS, RESOURCE_SPECS
from ..repositories.resources.store import GovernedResourceStore
from ..solution_selling.config import solution_selling_enabled
from ..solution_selling.models import (
    AssessmentPatch,
    DiagnosisPatch,
    LeadPatch,
    PrompterPatch,
    PrompterRenderRequest,
    ProspectingProfilePatch,
)
from ..solution_selling.prompters import render_prompter


class ServiceUnavailable(RuntimeError):
    """A trusted platform port or valid policy verdict is unavailable."""


class AccessDenied(PermissionError):
    """The actor lacks a required CRM capability."""


RECORD_PATCHES: dict[str, type[BaseModel]] = {
    "interactions": InteractionPatch,
    "assessments": AssessmentPatch,
    "diagnoses": DiagnosisPatch,
    "prospecting-profiles": ProspectingProfilePatch,
    "leads": LeadPatch,
    "prompters": PrompterPatch,
}


ModelT = TypeVar("ModelT", bound=BaseModel)


def validated_model(model: type[ModelT], payload: BaseModel | dict[str, Any]) -> ModelT:
    """Validate again at the service boundary, including non-HTTP callers."""
    try:
        source = (
            payload.model_dump(mode="json", exclude_unset=True)
            if isinstance(payload, BaseModel)
            else payload
        )
        return model.model_validate(source)
    except (ValidationError, TypeError, ValueError) as exc:
        raise DomainValidationError(
            [{"path": "payload", "code": "invalid", "message": "Invalid value"}]
        ) from exc


def validate_scope(resource: str, scope: QueryScope) -> QueryScope:
    """Enforce semantic filters and ordering for every caller, not only HTTP."""
    if resource not in FILTER_MODELS:
        raise DomainValidationError(
            [{"path": "resource", "code": "invalid", "message": "Invalid value"}]
        )
    try:
        filters = (
            FILTER_MODELS[resource]
            .model_validate(scope.filters)
            .model_dump(mode="json", exclude_none=True)
        )
    except ValidationError as exc:
        raise DomainValidationError(
            [{"path": "filters", "code": "invalid", "message": "Invalid value"}]
        ) from exc
    if scope.ordering and scope.ordering.removeprefix("-") not in ORDER_COLUMNS[resource]:
        raise DomainValidationError(
            [{"path": "ordering", "code": "invalid", "message": "Invalid value"}]
        )
    return QueryScope.model_validate({**scope.model_dump(), "filters": filters})


@dataclass(frozen=True)
class CRMContext:
    actor_uid: uuid.UUID
    policy: PolicyPort
    directory: DirectoryPort

    def require(self, capability: str) -> None:
        try:
            capabilities = frozenset(self.policy.capabilities(self.actor_uid))
        except Exception as exc:
            raise ServiceUnavailable("CRM policy evaluation failed") from exc
        if not capabilities <= CAPABILITIES:
            raise ServiceUnavailable("CRM policy returned invalid capabilities")
        if capability not in capabilities:
            raise AccessDenied(f"{capability} access denied")


class CRMOperations:
    """One domain operation boundary for the current core and extension records."""

    def __init__(
        self,
        context: CRMContext,
        *,
        resources: GovernedResourceStore | None = None,
        records: VersionedRecordStore | None = None,
        bootstrap: BootstrapPort | None = None,
    ) -> None:
        self.context = context
        self.resources = resources if resources is not None else GovernedResourceStore()
        self.records = records if records is not None else VersionedRecordStore()
        self.bootstrap = bootstrap

    @staticmethod
    def _invalid(path: str) -> DomainValidationError:
        return DomainValidationError(
            [{"path": path, "code": "invalid", "message": "Invalid value"}]
        )

    @staticmethod
    def _record_enabled(resource: str) -> None:
        if resource not in RECORDS:
            raise CRMOperations._invalid("resource")
        if resource != "interactions" and not solution_selling_enabled():
            raise ServiceUnavailable("Solution Selling module is disabled")

    def _owner(self, data: dict[str, Any]) -> None:
        owner_uid = data.get("owner_uid")
        if owner_uid is None:
            return
        try:
            owner = uuid.UUID(str(owner_uid))
        except (TypeError, ValueError, AttributeError) as exc:
            raise self._invalid("owner_uid") from exc
        if not self.context.directory.is_selectable(owner):
            raise self._invalid("owner_uid")

    # Canonical core resource CRUD.
    def list_resources(self, resource: str, scope: QueryScope) -> dict[str, Any]:
        self.context.require("crm.read")
        return self.resources.collection(resource, validate_scope(resource, scope))

    def get_resource(self, resource: str, uid: uuid.UUID) -> dict[str, Any]:
        self.context.require("crm.read")
        return self.resources.detail(resource, uid)

    def create_resource(self, resource: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.context.require("crm.create")
        singular = RESOURCE_SPECS[resource].logical_table
        if resource in {"contacts", "companies"}:
            data = normalized_create(singular, payload)
        else:
            data = validate_payload(f"{singular.title()}Create", payload)
        self._owner(data)
        return self.resources.create(resource, self.context.actor_uid, data)

    def update_resource(
        self, resource: str, uid: uuid.UUID, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.context.require("crm.edit")
        existing = self.resources.detail(resource, uid)
        singular = RESOURCE_SPECS[resource].logical_table
        if resource in {"contacts", "companies"}:
            expected_version, data = normalized_patch(singular, existing, payload)
        else:
            patch = validate_payload(f"{singular.title()}Patch", payload)
            create_fields = model_for(f"{singular.title()}Create").model_fields
            candidate = {key: existing.get(key) for key in create_fields}
            candidate.update(patch["changes"])
            expected_version = patch["expected_version"]
            data = validate_payload(f"{singular.title()}Create", candidate)
        self._owner(data)
        return self.resources.update(resource, self.context.actor_uid, uid, expected_version, data)

    def archive_resource(
        self, resource: str, uid: uuid.UUID, expected_version: int, *, archived: bool
    ) -> dict[str, Any]:
        self.context.require("crm.archive")
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
        ):
            raise self._invalid("expected_version")
        return self.resources.archive(
            resource, self.context.actor_uid, uid, expected_version, archived
        )

    def complete_task(
        self, uid: uuid.UUID, expected_version: int, *, completed: bool
    ) -> dict[str, Any]:
        self.context.require("crm.edit")
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
        ):
            raise self._invalid("expected_version")
        return self.resources.task_completion(
            self.context.actor_uid, uid, expected_version, completed
        )

    # Core relationship and board commands.
    def transition_company(self, contact_uid: uuid.UUID, payload: BaseModel) -> dict[str, Any]:
        self.context.require("crm.edit")
        payload = validated_model(AffiliationTransition, payload)
        return self.resources.transition_company(
            self.context.actor_uid, contact_uid, payload.model_dump(mode="json")
        )

    def list_affiliations(
        self, contact_uid: uuid.UUID, page_index: int, page_size: int
    ) -> dict[str, Any]:
        self.context.require("crm.read")
        if page_index < 0 or not 1 <= page_size <= 100:
            raise self._invalid("page")
        self.resources.detail("contacts", contact_uid)
        return self.resources.affiliations(contact_uid, page_index, page_size)

    def get_affiliation(self, contact_uid: uuid.UUID, affiliation_uid: uuid.UUID) -> dict[str, Any]:
        self.context.require("crm.read")
        return self.resources.affiliation_detail(contact_uid, affiliation_uid)

    def create_affiliation(self, contact_uid: uuid.UUID, payload: BaseModel) -> dict[str, Any]:
        self.context.require("crm.edit")
        payload = validated_model(AffiliationCreate, payload)
        return self.resources.create_affiliation(
            self.context.actor_uid, contact_uid, payload.model_dump(mode="json")
        )

    def update_affiliation(
        self, contact_uid: uuid.UUID, affiliation_uid: uuid.UUID, payload: BaseModel
    ) -> dict[str, Any]:
        self.context.require("crm.edit")
        payload = validated_model(AffiliationPatch, payload)
        return self.resources.patch_affiliation(
            self.context.actor_uid,
            contact_uid,
            affiliation_uid,
            payload.model_dump(mode="json", exclude_unset=True),
        )

    def pipeline_stages(self, uid: uuid.UUID) -> dict[str, Any]:
        self.context.require("crm.read")
        return self.resources.pipeline_stages(uid)

    def pipeline_board(self, uid: uuid.UUID, page_size: int) -> dict[str, Any]:
        self.context.require("crm.read")
        if not 1 <= page_size <= 100:
            raise self._invalid("page_size")
        return self.resources.pipeline_board(uid, page_size)

    def board_column(
        self,
        uid: uuid.UUID,
        stage_uid: uuid.UUID,
        expected_board_version: int,
        page_size: int,
        cursor: int,
    ) -> dict[str, Any]:
        self.context.require("crm.read")
        if expected_board_version < 0 or not 1 <= page_size <= 100 or cursor < 0:
            raise self._invalid("board_query")
        return self.resources.board_column(
            uid, stage_uid, expected_board_version, page_size, cursor
        )

    def move_deal(self, uid: uuid.UUID, payload: MoveDeal) -> dict[str, Any]:
        self.context.require("crm.edit")
        payload = validated_model(MoveDeal, payload)
        return self.resources.move_deal(
            self.context.actor_uid, uid, payload.model_dump(mode="json", exclude_unset=True)
        )

    def merge_preview(self, uid: uuid.UUID, payload: MergePreviewRequest) -> dict[str, Any]:
        self.context.require("crm.merge")
        payload = validated_model(MergePreviewRequest, payload)
        command = payload.model_dump(mode="json", exclude_unset=True)
        return self.resources.merge_preview(
            uid, uuid.UUID(command["loser_uid"]), command["field_resolutions"]
        )

    def merge_contacts(self, uid: uuid.UUID, payload: MergeExecuteRequest) -> dict[str, Any]:
        self.context.require("crm.merge")
        payload = validated_model(MergeExecuteRequest, payload)
        return self.resources.merge_contacts(
            self.context.actor_uid, uid, payload.model_dump(mode="json", exclude_unset=True)
        )

    def principals(self) -> dict[str, Any]:
        self.context.require("crm.read")
        display_name = self.context.directory.display_name(self.context.actor_uid).strip()
        return {
            "items": [
                {
                    "uid": str(self.context.actor_uid),
                    "display_name": display_name,
                    "selectable": self.context.directory.is_selectable(self.context.actor_uid),
                }
            ],
            "pageInfo": {
                "pageIndex": 0,
                "pageSize": 25,
                "totalItems": 1,
                "hasNextPage": False,
                "hasPreviousPage": False,
            },
        }

    def settings(self) -> dict[str, Any]:
        self.context.require("crm.read")
        if self.bootstrap is None:
            raise ServiceUnavailable("CRM settings service is unavailable")
        return self.bootstrap.read(self.context.actor_uid)["settings"]

    def update_settings(self, payload: SettingsPatch) -> dict[str, Any]:
        self.context.require("crm.configure")
        payload = validated_model(SettingsPatch, payload)
        if self.bootstrap is None:
            raise ServiceUnavailable("CRM settings service is unavailable")
        patch = payload.model_dump(mode="json", exclude_unset=True)
        current = self.bootstrap.read(self.context.actor_uid)["settings"]
        candidate = {**current, **patch["changes"]}
        candidate["configuration_version"] = patch["expected_version"]
        candidate = validate_payload("Settings", candidate)
        self.resources.update_settings(self.context.actor_uid, patch["expected_version"], candidate)
        return self.bootstrap.read(self.context.actor_uid)["settings"]

    # Interaction and optional methodology records.
    def list_records(
        self,
        resource: str,
        *,
        page_index: int,
        page_size: int,
        search: str | None,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        self.context.require("crm.read")
        self._record_enabled(resource)
        if page_index < 0 or not 1 <= page_size <= 100:
            raise self._invalid("page")
        if search is not None and len(search) > 255:
            raise self._invalid("search")
        permitted = set(RECORDS[resource].filters)
        unexpected = set(filters) - permitted
        if unexpected:
            raise self._invalid(sorted(unexpected)[0])
        try:
            validated_filters = RecordFilters.model_validate(filters).model_dump(
                mode="json", exclude_none=True
            )
        except ValidationError as exc:
            raise self._invalid("filters") from exc
        if resource == "interactions" and validated_filters.get("kind") not in (
            None,
            "call",
            "meeting",
            "workshop",
            "email",
        ):
            raise self._invalid("kind")
        statuses = {
            "interactions": {"planned", "completed", "cancelled"},
            "leads": {"to_contact", "contacted", "qualified", "nurture", "disqualified"},
        }
        if "status" in validated_filters and validated_filters["status"] not in statuses.get(
            resource, set()
        ):
            raise self._invalid("status")
        return self.records.collection(
            resource,
            page_index=page_index,
            page_size=page_size,
            search=search,
            filters=validated_filters,
        )

    def get_record(self, resource: str, uid: uuid.UUID) -> dict[str, Any]:
        self.context.require("crm.read")
        self._record_enabled(resource)
        return self.records.detail(resource, uid)

    def create_record(self, resource: str, payload: BaseModel) -> dict[str, Any]:
        self.context.require("crm.create")
        self._record_enabled(resource)
        payload = validated_model(RECORDS[resource].create, payload)
        if resource == "leads" and payload.owner_uid is not None:
            if not self.context.directory.is_selectable(payload.owner_uid):
                raise self._invalid("owner_uid")
        return self.records.create(resource, self.context.actor_uid, payload)

    def update_record(self, resource: str, uid: uuid.UUID, payload: BaseModel) -> dict[str, Any]:
        self.context.require("crm.edit")
        self._record_enabled(resource)
        payload = validated_model(RECORD_PATCHES[resource], payload)
        existing = self.records.detail(resource, uid)
        changes = payload.changes.model_dump(mode="json", exclude_unset=True)
        candidate_data = {
            key: existing[key] for key in RECORDS[resource].create.model_fields
        } | changes
        try:
            candidate = RECORDS[resource].create.model_validate(candidate_data)
        except ValidationError as exc:
            raise self._invalid("changes") from exc
        if resource == "leads" and candidate.owner_uid is not None:
            if not self.context.directory.is_selectable(candidate.owner_uid):
                raise self._invalid("owner_uid")
        return self.records.update(
            resource,
            self.context.actor_uid,
            uid,
            payload.expected_version,
            changes,
            candidate,
        )

    def render_prompter(self, uid: uuid.UUID, payload: BaseModel) -> dict[str, str]:
        self.context.require("crm.read")
        self._record_enabled("prompters")
        payload = validated_model(PrompterRenderRequest, payload)
        return {
            "text": render_prompter(
                prompter_uid=uid,
                request=payload,
                actor_uid=self.context.actor_uid,
                sender_name=self.context.directory.display_name(self.context.actor_uid),
                core=self.resources,
                methodology=self.records,
            )
        }
