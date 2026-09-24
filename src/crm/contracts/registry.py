"""Explicit mapping from CRM contract names to authored Pydantic classes."""

from __future__ import annotations

from pydantic import BaseModel

from ..models import (
    activity,
    affiliations,
    bootstrap,
    bulk,
    common,
    companies,
    contacts,
    deals,
    errors,
    merge,
    notes,
    pipelines,
    socials,
    tags,
    tasks,
    transfers,
)
from ..models.import_mapping import ImportMapping

CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "Affiliation": affiliations.Affiliation,
    "AffiliationCreate": affiliations.AffiliationCreate,
    "AffiliationPatch": affiliations.AffiliationPatch,
    "AffiliationTransition": affiliations.AffiliationTransition,
    "Activity": activity.Activity,
    "Readiness": bootstrap.Readiness,
    "Principal": bootstrap.Principal,
    "Settings": bootstrap.Settings,
    "SettingsPatch": bootstrap.SettingsPatch,
    "Bootstrap": bootstrap.Bootstrap,
    "BulkResult": bulk.BulkResult,
    "AssetRef": common.AssetRef,
    "Email": common.Email,
    "Phone": common.Phone,
    "SocialLinks": socials.SocialLinks,
    "SocialLinksPatch": socials.SocialLinksPatch,
    "VersionCommand": common.VersionCommand,
    "Company": companies.Company,
    "CompanyCreate": companies.CompanyCreate,
    "CompanyPatch": companies.CompanyPatch,
    "Contact": contacts.Contact,
    "ContactCreate": contacts.ContactCreate,
    "ContactPatch": contacts.ContactPatch,
    "Deal": deals.Deal,
    "DealCreate": deals.DealCreate,
    "DealPatch": deals.DealPatch,
    "MoveDeal": deals.MoveDeal,
    "MoveResult": deals.MoveResult,
    "Error": errors.Error,
    "MergePreviewRequest": merge.MergePreviewRequest,
    "MergeExecuteRequest": merge.MergeExecuteRequest,
    "MergePreview": merge.MergePreview,
    "MergeResult": merge.MergeResult,
    "Note": notes.Note,
    "NoteCreate": notes.NoteCreate,
    "NotePatch": notes.NotePatch,
    "Pipeline": pipelines.Pipeline,
    "PipelineCreate": pipelines.PipelineCreate,
    "PipelinePatch": pipelines.PipelinePatch,
    "Stage": pipelines.Stage,
    "StageCreate": pipelines.StageCreate,
    "StagePatch": pipelines.StagePatch,
    "StageCreateCommand": pipelines.StageCreateCommand,
    "StagePatchCommand": pipelines.StagePatchCommand,
    "ReorderStages": pipelines.ReorderStages,
    "BoardColumn": pipelines.BoardColumn,
    "Board": pipelines.Board,
    "Tag": tags.Tag,
    "TagCreate": tags.TagCreate,
    "TagPatch": tags.TagPatch,
    "Task": tasks.Task,
    "TaskCreate": tasks.TaskCreate,
    "TaskPatch": tasks.TaskPatch,
    "ImportCommitRequest": transfers.ImportCommitRequest,
    "CreateImport": transfers.CreateImport,
    "TransferSummary": transfers.TransferSummary,
    "SourceConnectionCreate": transfers.SourceConnectionCreate,
    "SourceConnection": transfers.SourceConnection,
    "ValidationIssue": transfers.ValidationIssue,
    "TransferPlan": transfers.TransferPlan,
    "CreateExport": transfers.CreateExport,
    "ImportMapping": ImportMapping,
}


def model_for(definition: str) -> type[BaseModel]:
    try:
        return CONTRACT_MODELS[definition]
    except KeyError as exc:
        raise ValueError(f"Unknown CRM contract definition: {definition}") from exc
