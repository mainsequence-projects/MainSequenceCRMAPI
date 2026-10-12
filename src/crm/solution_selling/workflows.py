"""Read-only Solution Selling compositions over the governed CRM stores."""

from __future__ import annotations

from typing import Any

from .models import (
    DiagnosisCreate,
    DiagnosisPrepareRequest,
    ProspectingProfileCreate,
    SolutionSellingContextRequest,
)


def source(resource: str, record: dict[str, Any]) -> dict[str, Any]:
    return {"resource": resource, "uid": str(record["uid"]), "version": record["version"]}


def solution_selling_context(request: SolutionSellingContextRequest, *, core, methodology):
    deal = core.detail("deals", request.deal_uid)
    company = core.detail("companies", deal["company_uid"]) if deal["company_uid"] else None
    assessments = methodology.collection(
        "assessments",
        page_index=0,
        page_size=1,
        search=None,
        filters={"deal_uid": str(request.deal_uid)},
    )
    if assessments["pageInfo"]["totalItems"] > 1:
        raise RuntimeError("The Deal assessment uniqueness invariant failed")
    assessment = next(iter(assessments["items"]), None)
    if assessment is not None and (
        str(assessment["deal_uid"]) != str(deal["uid"])
        or str(assessment["company_uid"]) != str(deal["company_uid"])
    ):
        raise ValueError("The assessment does not belong to this Deal and Company")
    interactions = methodology.collection(
        "interactions",
        page_index=request.interaction_page_index,
        page_size=request.interaction_page_size,
        search=None,
        filters={"deal_uid": str(request.deal_uid)},
    )
    sources = [source("deals", deal)]
    if company is not None:
        sources.append(source("companies", company))
    if assessment is not None:
        sources.append(source("assessments", assessment))
    sources.extend(source("interactions", item) for item in interactions["items"])
    return {
        "deal": deal,
        "company": company,
        "assessment": assessment,
        "interactions": interactions,
        "sources": sources,
    }


def prepare_diagnosis(request: DiagnosisPrepareRequest, *, core, methodology):
    interaction = methodology.detail("interactions", request.interaction_uid)
    contact = core.detail("contacts", request.contact_uid)
    profile_record = methodology.detail("prospecting-profiles", request.profile_uid)
    profile = ProspectingProfileCreate.model_validate(
        {key: profile_record[key] for key in ProspectingProfileCreate.model_fields}
    )
    sources = [
        source("interactions", interaction),
        source("contacts", contact),
        source("prospecting-profiles", profile_record),
    ]
    if request.solution_selling_uid is not None:
        assessment = methodology.detail("assessments", request.solution_selling_uid)
        if str(assessment["company_uid"]) != str(interaction["company_uid"]) or (
            interaction["deal_uid"] is not None
            and str(assessment["deal_uid"]) != str(interaction["deal_uid"])
        ):
            raise ValueError("The assessment does not belong to the Interaction's Company and Deal")
        sources.append(source("assessments", assessment))
    draft = DiagnosisCreate(
        interaction_uid=request.interaction_uid,
        contact_uid=request.contact_uid,
        solution_selling_uid=request.solution_selling_uid,
        business_issue=profile.potential_pain,
        **(
            {"matrix": profile.diagnosis_template.model_copy(deep=True)}
            if profile.diagnosis_template is not None
            else {}
        ),
    )
    return {
        "draft": draft.model_dump(mode="json"),
        "saved": False,
        "business_issue_status": "hypothesis",
        "sources": sources,
    }
