"""MCP typed transport adapters for the shared CRM operation boundary.

The runtime supplier is host-owned. Tool arguments never contain an actor,
policy, directory, connection, or capability grant.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import anyio
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from src.crm.campaigns.config import campaigns_enabled
from src.crm.campaigns.models import (
    AdvanceCommand,
    BlockCommand,
    CampaignCreate,
    CampaignFilters,
    CampaignPatch,
    CompleteCommand,
    GraphUpdate,
    GraphValidateRequest,
    ParticipantCreate,
    ParticipantFilters,
    ParticipantPatch,
    ProgressRef,
    ReconcileCommand,
    ReportCommand,
    StepPromptCreate,
    StepPromptFilters,
    StepPromptPatch,
    WaitCommand,
)
from src.crm.contracts import DomainValidationError, model_for
from src.crm.models.affiliations import AffiliationCreate, AffiliationPatch, AffiliationTransition
from src.crm.models.bootstrap import SettingsPatch
from src.crm.models.deals import MoveDeal
from src.crm.models.merge import MergePreviewRequest
from src.crm.models.queries import FILTER_MODELS, QueryScope
from src.crm.models.record_filters import RecordFilters
from src.crm.platform.diagnostics import observe_tool, record_exception
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
from src.crm.solution_selling.models import (
    DiagnosisPrepareRequest,
    PrompterRenderRequest,
    PrompterValidateRequest,
    SolutionSellingContextRequest,
)


@dataclass(frozen=True)
class CRMToolRuntime:
    """One trusted invocation's ports; never constructed from model input."""

    context: CRMContext
    resources: GovernedResourceStore | None = None
    records: VersionedRecordStore | None = None
    bootstrap: BootstrapPort | None = None
    denial_reporter: Callable[[AccessDenied], None] | None = None
    campaign_store: Any = None

    def operations(self) -> CRMOperations:
        return CRMOperations(
            self.context,
            resources=self.resources,
            records=self.records,
            bootstrap=self.bootstrap,
            campaign_store=self.campaign_store,
        )


RuntimeProvider = Callable[[], CRMToolRuntime]
MAX_RESULT_CHARS = 128_000


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


def tool_result(
    code: str, *, data: Any = None, message: str | None = None,
    diagnostics: dict[str, str] | None = None,
) -> CallToolResult:
    details: dict[str, Any] = {"code": code}
    if data is not None:
        details["data"] = data
    if message is not None:
        details["message"] = message
    if diagnostics is not None:
        details["diagnostics"] = diagnostics
    serialized = json.dumps(details, default=str, ensure_ascii=False)
    if len(serialized) > MAX_RESULT_CHARS:
        details = {
            "code": "result_too_large",
            "message": "Narrow the CRM query or read a specific record",
        }
        serialized = json.dumps(details)
    return CallToolResult(
        content=[TextContent(type="text", text=serialized)],
        structuredContent=json.loads(serialized),
        isError=details["code"] != "ok",
    )


@dataclass(frozen=True)
class CRMTool:
    definition: Tool
    invoke: Callable[[Mapping[str, Any]], Awaitable[CallToolResult]]


def _tool(
    name: str,
    description: str,
    arguments_model: type[BaseModel],
    operation: Callable[[CRMOperations, BaseModel], Any],
    runtime_provider: RuntimeProvider,
    *,
    mutation: bool = False,
) -> CRMTool:
    async def dispatch(arguments: Mapping[str, Any]) -> CallToolResult:
        try:
            parsed = arguments_model.model_validate(dict(arguments))
        except (ValidationError, TypeError, ValueError):
            return tool_result("invalid_arguments", message="Invalid tool arguments")

        runtime: CRMToolRuntime | None = None

        def call() -> Any:
            nonlocal runtime
            runtime = runtime_provider()
            service = runtime.operations()
            return operation(service, parsed)

        # Cancellation before dispatch starts no work. Once a synchronous write
        # starts, wait for it; a lost/cancelled response never proves rollback.
        await anyio.lowlevel.checkpoint()
        try:
            data = await anyio.to_thread.run_sync(call, abandon_on_cancel=False)
        except AccessDenied as exc:
            if runtime is not None and runtime.denial_reporter is not None:
                runtime.denial_reporter(exc)
            return tool_result("forbidden", message="CRM access denied")
        except ServiceUnavailable as exc:
            record_exception(exc)
            return tool_result("unavailable", message="CRM runtime is unavailable")
        except DomainValidationError as exc:
            return tool_result(
                "validation_error",
                data={
                    "fields": [
                        {"path": field.get("path", "payload"), "code": field.get("code", "invalid")}
                        for field in exc.fields
                    ]
                },
            )
        except ResourceNotFound:
            return tool_result("not_found", message="CRM record not found")
        except ResourceConflict:
            return tool_result("conflict", message="CRM state changed; reread before retrying")
        except Exception as exc:
            record_exception(exc)
            return tool_result("internal_error", message="CRM operation failed")
        return tool_result("ok", data=data)

    async def execute(arguments: Mapping[str, Any]) -> CallToolResult:
        with observe_tool(name) as observation:
            result = await dispatch(arguments)
            details = result.structured_content
            observation.code = details["code"]
            if result.is_error and observation.code != "result_too_large":
                return tool_result(**details, diagnostics=observation.public_details())
            return result

    return CRMTool(
        definition=Tool(
            name=name,
            description=description,
            inputSchema=arguments_model.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=not mutation,
                destructiveHint=mutation,
                idempotentHint=not mutation,
                openWorldHint=False,
            ),
            _meta={"mainsequence.ai/timeout-seconds/v1": 60},
        ),
        invoke=execute,
    )


def build_crm_tools(runtime_provider: RuntimeProvider) -> tuple[CRMTool, ...]:
    """Build tools for operations already implemented in ``src/crm``.

    Destructive commands are omitted until trusted confirmation evidence can
    be checked by the shared service. Unimplemented CRM operations are omitted.
    """
    tools: list[CRMTool] = []

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
        "prompts",
    ):
        filter_model = FILTER_MODELS[resource]
        list_model = create_model(
            f"{resource.title()}ListToolArguments",
            __base__=QueryScope,
            filters=(filter_model, Field(default_factory=filter_model)),
        )
        add(
            f"crm_{resource}_list",
            ("Find saved Agent Prompts by name or description with bounded paging and "
             "archive filters. Returns metadata only; read the selected UID with "
             "crm_prompts_get for its full Markdown instructions. Agent Prompts are "
             "separate from Solution Selling message templates (Prompters)."
             if resource == "prompts" else f"List CRM {resource} with bounded paging and filters."),
            list_model,
            lambda service, args, resource=resource: service.list_resources(resource, args),
        )
        add(
            f"crm_{resource}_get",
            ("Read one saved Agent Prompt by UID, including its exact content_markdown. "
             "Returns a stored document without rendering, executing or sending it."
             if resource == "prompts" else f"Get one CRM {resource} record by UID."),
            _UID,
            lambda service, args, resource=resource: service.get_resource(resource, args.uid),
        )
        if resource in {"activity", "pipelines", "prompts"}:
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
            ("Attach a free-form Markdown note to an existing contact or deal. Provide "
             "contact_uid or deal_uid (exactly one), text (body), and occurred_at "
             "(date/time with timezone). An optional plain-text title can name the note; "
             "no category is required."
             if resource == "notes" else f"Create a CRM {singular}."),
            create_args,
            lambda service, args, resource=resource: service.create_resource(
                resource, args.payload.model_dump(mode="json", exclude_unset=True)
            ),
            mutation=True,
        )
        add(
            f"crm_{resource}_update",
            ("Edit a CRM note using its expected version. Changes may include title, "
             "text (Markdown body), or occurred_at. Omit title to keep it, or set it "
             "to null to clear it."
             if resource == "notes" else f"Update a CRM {singular} using its expected version."),
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
        filter_type = create_model(
            f"{slug.title()}ToolFilters", __base__=_Arguments,
            **{name: (RecordFilters.model_fields[name].annotation,
                      deepcopy(RecordFilters.model_fields[name]))
               for name in RECORDS[resource].filters},
        )
        list_args = create_model(
            f"{slug.title()}ListToolArguments", __base__=_RecordList,
            filters=(filter_type, Field(default_factory=filter_type)),
        )
        add(
            f"crm_{slug}_list",
            f"List active CRM {resource} with bounded paging and resource-specific filters.",
            list_args,
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

    if solution_selling_enabled():
        render_args = create_model(
            "PrompterRenderToolArguments", __base__=_UID, payload=(PrompterRenderRequest, ...),
        )
        add(
            "crm_prompters_render",
            "Render a stored prompter with explicit Contact and Company references. "
            "Returns body text, optional subject, character counts and constraint violations. "
            "Overlong drafts are returned intact with is_valid=false; never saves or sends a message.",
            render_args,
            lambda service, args: service.render_prompter(args.uid, args.payload),
        )
        validate_args = create_model(
            "PrompterValidateToolArguments", __base__=_UID, payload=(PrompterValidateRequest, ...),
        )
        add(
            "crm_prompters_validate",
            "Validate edited body text and optional subject against a saved prompter's current "
            "constraints. Returns counts and violations without rendering, saving or sending.",
            validate_args,
            lambda service, args: service.validate_prompter(args.uid, args.payload),
        )
        add(
            "crm_solution_selling_context_get",
            "Read a Deal, its Company and optional assessment (including key players and pain chain), "
            "plus a bounded page of Interactions and source UIDs/versions. "
            "Evidence statuses are preserved; individual reads are not an atomic snapshot.",
            SolutionSellingContextRequest,
            lambda service, args: service.solution_selling_context(args),
        )
        add(
            "crm_diagnoses_prepare",
            "Prepare an unsaved diagnosis for an explicit Interaction and Contact from a prospecting "
            "profile. Copies questions with empty answers; potential pain is a hypothesis. "
            "A missing template yields nine empty matrix cells. Never creates or updates a record.",
            DiagnosisPrepareRequest,
            lambda service, args: service.prepare_diagnosis(args),
        )

    if campaigns_enabled():
        _add_campaign_tools(add)

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


def _add_campaign_tools(add) -> None:
    """Campaigns module tools: definitions, step prompts, enrollment and progression."""

    def resource_tools(slug, label, filters_model, create_model_type, patch_model_type, *, methods, create_description, update_description):
        list_args = create_model(
            f"{slug.title()}ListToolArguments", __base__=_RecordList,
            filters=(filters_model, Field(default_factory=filters_model)),
        )
        create_args = create_model(f"{slug.title()}CreateToolArguments", __base__=_Arguments, payload=(create_model_type, ...))
        update_args = create_model(f"{slug.title()}UpdateToolArguments", __base__=_UID, payload=(patch_model_type, ...))
        prefix = f"crm_{slug}"
        list_method, get_method, create_method, update_method = methods
        add(f"{prefix}_list", f"List {label} with bounded paging, search and filters.", list_args,
            lambda service, args, m=list_method: getattr(service.campaigns, m)(**args.model_dump(mode="python")))
        add(f"{prefix}_get", f"Read one {label[:-1]} by UID.", _UID,
            lambda service, args, m=get_method: getattr(service.campaigns, m)(args.uid))
        add(f"{prefix}_create", create_description, create_args,
            lambda service, args, m=create_method: getattr(service.campaigns, m)(args.payload), mutation=True)
        add(f"{prefix}_update", update_description, update_args,
            lambda service, args, m=update_method: getattr(service.campaigns, m)(args.uid, args.payload), mutation=True)

    resource_tools(
        "campaigns", "campaigns", CampaignFilters, CampaignCreate, CampaignPatch,
        methods=("list_campaigns", "get_campaign", "create_campaign", "update_campaign"),
        create_description="Create a draft campaign with a name, Markdown objective, owner and bounded context. "
                           "Steps and connections are added with crm_campaigns_graph_update.",
        update_description="Edit campaign fields or change its lifecycle (draft→active, active↔paused, →completed) "
                           "using the expected version. Activation validates the live graph.",
    )
    resource_tools(
        "campaign_prompts", "campaign step prompts", StepPromptFilters, StepPromptCreate, StepPromptPatch,
        methods=("list_step_prompts", "get_step_prompt", "create_step_prompt", "update_step_prompt"),
        create_description="Create a campaign step prompt (an Agent Prompt with declared inputs and result fields), "
                           "or specialize an existing Agent Prompt by prompt_uid and expected_version.",
        update_description="Edit a step prompt's document, inputs or result fields using the shared Prompt version. "
                           "Changed content blocks open work and flags compared assignments.",
    )
    resource_tools(
        "campaign_participants", "campaign participants", ParticipantFilters, ParticipantCreate, ParticipantPatch,
        methods=("list_participants", "get_participant", "create_participant", "update_participant"),
        create_description="Enroll an existing Contact in a campaign once. Enrollment schedules the entry step; "
                           "it never creates or sends anything by itself.",
        update_description="Change participant context, pause/resume, withdraw, or explicitly reroute next_step_uid "
                           "after a live edit, using the expected version. Progress fields are service-owned.",
    )
    validate_args = create_model("CampaignGraphValidateToolArguments", __base__=_UID, payload=(GraphValidateRequest, ...))
    add("crm_campaigns_graph_validate",
        "Read-only validation of a complete candidate graph (steps, connections, entry) with the impact on "
        "current participants and open Tasks. Nothing is saved.",
        validate_args, lambda service, args: service.campaigns.validate_candidate_graph(args.uid, args.payload))
    graph_args = create_model("CampaignGraphUpdateToolArguments", __base__=_UID, payload=(GraphUpdate, ...))
    add("crm_campaigns_graph_update",
        "Atomically save the complete graph against the campaign version: add/edit/retire steps and replace "
        "connections. affected_open_work chooses block (default) or cancel for retired steps' open Tasks.",
        graph_args, lambda service, args: service.campaigns.update_graph(args.uid, args.payload), mutation=True)
    add("crm_campaign_tasks_prepare",
        "Read-only briefing for an existing participant Task: current objective, step, assigned prompt variant, "
        "resolved inputs, allowed outcomes, transitions and version provenance. Never rerandomizes or writes.",
        ProgressRef, lambda service, args: service.campaigns.prepare(args))
    add("crm_campaign_tasks_advance",
        "Create the eligible next Task and its prompt assignment once, or return the existing instance. "
        "Does not execute the work or send anything.",
        AdvanceCommand, lambda service, args: service.campaigns.advance(args), mutation=True)
    add("crm_campaign_tasks_complete",
        "Submit an allowed outcome, typed result and evidence with the briefing's prepared_with provenance. "
        "Completes the Task and routes atomically; a stale briefing records the facts and blocks instead.",
        CompleteCommand, lambda service, args: service.campaigns.complete(args), mutation=True)
    add("crm_campaign_tasks_wait",
        "Mark an open campaign Task as waiting until wake_at, optionally recording evidence.",
        WaitCommand, lambda service, args: service.campaigns.wait(args), mutation=True)
    add("crm_campaign_tasks_block",
        "Mark an open campaign Task as blocked with an actionable reason, optionally recording evidence.",
        BlockCommand, lambda service, args: service.campaigns.block(args), mutation=True)
    add("crm_campaign_tasks_report",
        "Record observed facts or partial results on an open campaign Task without completing or routing it.",
        ReportCommand, lambda service, args: service.campaigns.report(args), mutation=True)
    add("crm_campaign_tasks_reconcile",
        "Resolve blocked work explicitly: resume (accept the stored result against the current graph), "
        "reopen (refresh the briefing), or cancel (archive the Task and reroute or finish the participant).",
        ReconcileCommand, lambda service, args: service.campaigns.reconcile(args), mutation=True)
