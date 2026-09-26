"""Tau's typed transport adapters for the shared CRM operation boundary.

The runtime supplier is host-owned. Tool arguments never contain an actor,
policy, directory, connection, or capability grant.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import anyio
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
from tau_agent.messages import TextContent
from tau_agent.tools import AgentTool, AgentToolResult, ToolCancellationToken
from tau_agent.types import JSONValue

from src.crm.contracts import DomainValidationError, model_for
from src.crm.models.affiliations import AffiliationCreate, AffiliationPatch, AffiliationTransition
from src.crm.models.bootstrap import SettingsPatch
from src.crm.models.deals import MoveDeal
from src.crm.models.merge import MergePreviewRequest
from src.crm.models.queries import FILTER_MODELS, QueryScope
from src.crm.platform.runtime import BootstrapPort
from src.crm.repositories.errors import ResourceConflict, ResourceNotFound
from src.crm.repositories.records import RECORDS, VersionedRecordStore
from src.crm.repositories.resources.store import GovernedResourceStore
from src.crm.services.operations import (
    RECORD_PATCHES,
    AccessDenied,
    CRMContext,
    CRMOperations,
    ServiceUnavailable,
)
from src.crm.solution_selling.config import solution_selling_enabled


@dataclass(frozen=True)
class CRMToolRuntime:
    """One trusted invocation's ports; never constructed from model input."""

    context: CRMContext
    resources: GovernedResourceStore | None = None
    records: VersionedRecordStore | None = None
    bootstrap: BootstrapPort | None = None

    def operations(self) -> CRMOperations:
        return CRMOperations(
            self.context,
            resources=self.resources,
            records=self.records,
            bootstrap=self.bootstrap,
        )


RuntimeProvider = Callable[[], CRMToolRuntime]
MAX_RESULT_CHARS = 128_000


def unavailable_runtime() -> CRMToolRuntime:
    """Default until the host supplies validated per-turn identity and ports."""
    raise ServiceUnavailable("Trusted CRM caller binding is unavailable")


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _UID(_Arguments):
    uid: UUID


class _ContactUID(_Arguments):
    contact_uid: UUID


class _AffiliationUID(_ContactUID):
    affiliation_uid: UUID


class _AffiliationList(_ContactUID):
    page_index: int = Field(default=0, ge=0)
    page_size: int = Field(default=25, ge=1, le=100)


class _RecordList(_Arguments):
    page_index: int = Field(default=0, ge=0)
    page_size: int = Field(default=25, ge=1, le=100)
    search: str | None = Field(default=None, max_length=255)
    filters: dict[str, str] = Field(default_factory=dict)


class _TaskVersion(_UID):
    expected_version: int = Field(ge=1)


class _Board(_UID):
    page_size: int = Field(default=25, ge=1, le=100)


class _NoArguments(_Arguments):
    pass


def _result(code: str, *, data: Any = None, message: str | None = None) -> AgentToolResult:
    details: dict[str, Any] = {"code": code}
    if data is not None:
        details["data"] = data
    if message is not None:
        details["message"] = message
    serialized = json.dumps(details, default=str, ensure_ascii=False)
    if len(serialized) > MAX_RESULT_CHARS:
        details = {
            "code": "result_too_large",
            "message": "Narrow the CRM query or read a specific record",
        }
        serialized = json.dumps(details)
    return AgentToolResult(
        content=[TextContent(text=serialized)],
        details=details,
    )


def _tool(
    name: str,
    description: str,
    arguments_model: type[BaseModel],
    operation: Callable[[CRMOperations, BaseModel], Any],
    runtime_provider: RuntimeProvider,
    *,
    mutation: bool = False,
) -> AgentTool:
    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
        on_update: Any = None,
    ) -> AgentToolResult:
        del tool_call_id, on_update
        if signal is not None and signal.is_cancelled():
            return _result("cancelled", message="The command was not started")
        try:
            parsed = arguments_model.model_validate(dict(arguments))
        except (ValidationError, TypeError, ValueError):
            return _result("invalid_arguments", message="Invalid tool arguments")

        def call() -> Any:
            service = runtime_provider().operations()
            return operation(service, parsed)

        try:
            data = await anyio.to_thread.run_sync(call, abandon_on_cancel=False)
        except AccessDenied:
            return _result("forbidden", message="CRM access denied")
        except ServiceUnavailable:
            return _result("unavailable", message="CRM runtime is unavailable")
        except DomainValidationError as exc:
            return _result(
                "validation_error",
                data={
                    "fields": [
                        {"path": field.get("path", "payload"), "code": field.get("code", "invalid")}
                        for field in exc.fields
                    ]
                },
            )
        except ResourceNotFound:
            return _result("not_found", message="CRM record not found")
        except ResourceConflict:
            return _result("conflict", message="CRM state changed; reread before retrying")
        except Exception:
            return _result("internal_error", message="CRM operation failed")
        if signal is not None and signal.is_cancelled():
            return _result(
                "outcome_unknown" if mutation else "cancelled",
                message=(
                    "Read the current CRM record before any retry"
                    if mutation
                    else "The read was cancelled"
                ),
            )
        return _result("ok", data=data)

    return AgentTool(
        name=name,
        label=name.replace("_", " "),
        description=description,
        parameters=arguments_model.model_json_schema(),
        execute_fn=execute,
        execution_mode="sequential" if mutation else "parallel",
    )


def build_crm_tools(runtime_provider: RuntimeProvider) -> tuple[AgentTool, ...]:
    """Build tools for operations already implemented in ``src/crm``.

    Destructive commands are omitted until trusted confirmation evidence can
    be checked by the shared service. Unimplemented CRM operations are omitted.
    """
    tools: list[AgentTool] = []

    def add(
        name: str,
        description: str,
        model: type[BaseModel],
        call: Callable[[CRMOperations, BaseModel], Any],
        *,
        mutation: bool = False,
    ) -> None:
        tools.append(_tool(name, description, model, call, runtime_provider, mutation=mutation))

    for resource in (
        "contacts",
        "companies",
        "deals",
        "tasks",
        "notes",
        "tags",
        "activity",
        "pipelines",
    ):
        filter_model = FILTER_MODELS[resource]
        list_model = create_model(
            f"{resource.title()}ListToolArguments",
            __base__=QueryScope,
            filters=(filter_model, Field(default_factory=filter_model)),
        )
        add(
            f"crm_{resource}_list",
            f"List CRM {resource} with bounded paging and filters.",
            list_model,
            lambda service, args, resource=resource: service.list_resources(resource, args),
        )
        add(
            f"crm_{resource}_get",
            f"Get one CRM {resource} record by UID.",
            _UID,
            lambda service, args, resource=resource: service.get_resource(resource, args.uid),
        )
        if resource in {"activity", "pipelines"}:
            continue
        singular = resource[:-1] if resource != "companies" else "company"
        create_model_type = model_for(f"{singular.title()}Create")
        patch_model_type = model_for(f"{singular.title()}Patch")
        create_args = create_model(
            f"{singular.title()}CreateToolArguments",
            __base__=_Arguments,
            payload=(create_model_type, ...),
        )
        update_args = create_model(
            f"{singular.title()}UpdateToolArguments",
            __base__=_UID,
            payload=(patch_model_type, ...),
        )
        add(
            f"crm_{resource}_create",
            f"Create a CRM {singular}.",
            create_args,
            lambda service, args, resource=resource: service.create_resource(
                resource, args.payload.model_dump(mode="json", exclude_unset=True)
            ),
            mutation=True,
        )
        add(
            f"crm_{resource}_update",
            f"Update a CRM {singular} using its expected version.",
            update_args,
            lambda service, args, resource=resource: service.update_resource(
                resource, args.uid, args.payload.model_dump(mode="json", exclude_unset=True)
            ),
            mutation=True,
        )

    for resource in RECORDS:
        if resource != "interactions" and not solution_selling_enabled():
            continue
        slug = resource.replace("-", "_")
        create_type = RECORDS[resource].create
        patch_type = RECORD_PATCHES[resource]
        create_args = create_model(
            f"{slug.title()}CreateToolArguments",
            __base__=_Arguments,
            payload=(create_type, ...),
        )
        update_args = create_model(
            f"{slug.title()}UpdateToolArguments",
            __base__=_UID,
            payload=(patch_type, ...),
        )
        add(
            f"crm_{slug}_list",
            f"List CRM {resource}.",
            _RecordList,
            lambda service, args, resource=resource: service.list_records(
                resource, **args.model_dump(mode="python")
            ),
        )
        add(
            f"crm_{slug}_get",
            f"Get one CRM {resource} record.",
            _UID,
            lambda service, args, resource=resource: service.get_record(resource, args.uid),
        )
        add(
            f"crm_{slug}_create",
            f"Create a CRM {resource} record.",
            create_args,
            lambda service, args, resource=resource: service.create_record(resource, args.payload),
            mutation=True,
        )
        add(
            f"crm_{slug}_update",
            f"Update a CRM {resource} record using its version.",
            update_args,
            lambda service, args, resource=resource: service.update_record(
                resource, args.uid, args.payload
            ),
            mutation=True,
        )

    add(
        "crm_affiliations_list",
        "List a contact's company affiliations.",
        _AffiliationList,
        lambda service, args: service.list_affiliations(
            args.contact_uid, args.page_index, args.page_size
        ),
    )
    add(
        "crm_affiliations_get",
        "Get one contact affiliation.",
        _AffiliationUID,
        lambda service, args: service.get_affiliation(args.contact_uid, args.affiliation_uid),
    )
    affiliation_create = create_model(
        "AffiliationCreateToolArguments",
        __base__=_ContactUID,
        payload=(AffiliationCreate, ...),
    )
    affiliation_update = create_model(
        "AffiliationUpdateToolArguments",
        __base__=_AffiliationUID,
        payload=(AffiliationPatch, ...),
    )
    affiliation_transition = create_model(
        "AffiliationTransitionToolArguments",
        __base__=_ContactUID,
        payload=(AffiliationTransition, ...),
    )
    add(
        "crm_affiliations_create",
        "Create a contact affiliation.",
        affiliation_create,
        lambda service, args: service.create_affiliation(args.contact_uid, args.payload),
        mutation=True,
    )
    add(
        "crm_affiliations_update",
        "Update a contact affiliation.",
        affiliation_update,
        lambda service, args: service.update_affiliation(
            args.contact_uid, args.affiliation_uid, args.payload
        ),
        mutation=True,
    )
    add(
        "crm_contacts_transition_company",
        "Change a contact's primary company.",
        affiliation_transition,
        lambda service, args: service.transition_company(args.contact_uid, args.payload),
        mutation=True,
    )

    add(
        "crm_principals_list",
        "List selectable CRM principals visible to the caller.",
        _NoArguments,
        lambda service, args: service.principals(),
    )
    add(
        "crm_settings_get",
        "Get CRM singleton settings.",
        _NoArguments,
        lambda service, args: service.settings(),
    )
    settings_update = create_model(
        "SettingsUpdateToolArguments", __base__=_Arguments, payload=(SettingsPatch, ...)
    )
    add(
        "crm_settings_update",
        "Update CRM settings using their expected version.",
        settings_update,
        lambda service, args: service.update_settings(args.payload),
        mutation=True,
    )

    for action, completed in (("complete", True), ("reopen", False)):
        add(
            f"crm_tasks_{action}",
            f"{action.title()} a CRM task using its version.",
            _TaskVersion,
            lambda service, args, completed=completed: service.complete_task(
                args.uid, args.expected_version, completed=completed
            ),
            mutation=True,
        )
    move_args = create_model("DealMoveToolArguments", __base__=_UID, payload=(MoveDeal, ...))
    add(
        "crm_deals_move",
        "Move a deal with deal and board version fences.",
        move_args,
        lambda service, args: service.move_deal(args.uid, args.payload),
        mutation=True,
    )
    add(
        "crm_pipelines_stages",
        "List stages in a pipeline.",
        _UID,
        lambda service, args: service.pipeline_stages(args.uid),
    )
    add(
        "crm_pipelines_board",
        "Read a pipeline board.",
        _Board,
        lambda service, args: service.pipeline_board(args.uid, args.page_size),
    )
    preview_args = create_model(
        "ContactMergePreviewToolArguments",
        __base__=_UID,
        payload=(MergePreviewRequest, ...),
    )
    add(
        "crm_contacts_merge_preview",
        "Preview a contact merge without writing.",
        preview_args,
        lambda service, args: service.merge_preview(args.uid, args.payload),
    )
    return tuple(tools)
