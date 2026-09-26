"""Read-only, bounded rendering of Solution Selling draft text."""

from __future__ import annotations

import uuid
from typing import Any

from jinja2 import StrictUndefined, nodes
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment

from src.crm.repositories.records import VersionedRecordStore
from src.crm.repositories.resources.store import GovernedResourceStore

from .models import PrompterRenderRequest

_ROOTS = {"contact", "company", "lead", "profile", "deal", "solution_selling", "sender", "inputs"}
_ALLOWED_NODES = (
    nodes.Template,
    nodes.Output,
    nodes.TemplateData,
    nodes.Name,
    nodes.Getattr,
    nodes.Getitem,
    nodes.Const,
    nodes.If,
    nodes.For,
    nodes.Not,
)


def _validate_template(source: str) -> SandboxedEnvironment:
    if len(source) > 16384:
        raise ValueError("Template is too long")
    environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
    environment.globals.clear()
    environment.filters.clear()
    environment.tests.clear()
    try:
        syntax = environment.parse(source)
    except TemplateError as exc:
        raise ValueError("Invalid template syntax") from exc

    def inspect(
        node: nodes.Node, *, loop_depth: int = 0, local: frozenset[str] = frozenset()
    ) -> None:
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"Unsupported template expression: {type(node).__name__}")
        if isinstance(node, nodes.Getattr) and node.attr.startswith("_"):
            raise ValueError("Private attributes are unavailable")
        if isinstance(node, nodes.Getitem) and (
            not isinstance(node.arg, nodes.Const) or not isinstance(node.arg.value, str)
        ):
            raise ValueError("Only literal string keys are available")
        if isinstance(node, nodes.Name) and node.name not in _ROOTS | local:
            raise ValueError(f"Unknown template name: {node.name}")
        if isinstance(node, nodes.For):
            if loop_depth or not isinstance(node.target, nodes.Name) or node.recursive or node.test:
                raise ValueError("Only one-level loops over supplied lists are supported")
            if not (
                isinstance(node.iter, nodes.Getattr)
                and isinstance(node.iter.node, nodes.Name)
                and node.iter.node.name == "profile"
                and node.iter.attr in {"likely_reasons", "likely_impacts"}
            ):
                raise ValueError("Loops may only use bounded profile guidance lists")
            inspect(node.iter, loop_depth=loop_depth, local=local)
            inner = local | {node.target.name}
            for child in (*node.body, *node.else_):
                inspect(child, loop_depth=1, local=inner)
            return
        for child in node.iter_child_nodes():
            inspect(child, loop_depth=loop_depth, local=local)

    inspect(syntax)
    return environment


def _projection(record: dict[str, Any] | None, *fields: str) -> dict[str, Any] | None:
    if record is None:
        return None
    result = {field: record.get(field) for field in fields}
    for key, value in result.items():
        if isinstance(value, str) and len(value) > 5000:
            raise ValueError(f"{key} exceeds rendering limit")
        if isinstance(value, list):
            if len(value) > 20:
                raise ValueError(f"{key} exceeds rendering limit")
            for item in value:
                if isinstance(item, str) and len(item) > 500:
                    raise ValueError(f"{key} exceeds rendering limit")
    return result


def render_prompter(
    *,
    prompter_uid: uuid.UUID,
    request: PrompterRenderRequest,
    actor_uid: uuid.UUID,
    sender_name: str,
    core: GovernedResourceStore,
    methodology: VersionedRecordStore,
) -> str:
    """Return a preview; never persist or dispatch generated text."""
    if len(request.inputs) > 50 or any(
        len(key) > 100 or len(value) > 500 for key, value in request.inputs.items()
    ):
        raise ValueError("Rendering inputs exceed the limit")
    template_record = methodology.detail("prompters", prompter_uid)
    contact = core.detail("contacts", request.contact_uid)
    company = core.detail("companies", request.company_uid)
    lead = methodology.detail("leads", request.lead_uid) if request.lead_uid else None
    profile = (
        methodology.detail("prospecting-profiles", request.profile_uid)
        if request.profile_uid
        else None
    )
    deal = core.detail("deals", request.deal_uid) if request.deal_uid else None
    assessment = (
        methodology.detail("assessments", request.solution_selling_uid)
        if request.solution_selling_uid
        else None
    )
    if lead and lead["contact_uid"] != str(request.contact_uid):
        raise ValueError("Lead does not belong to selected Contact")
    if lead and profile and lead["profile_uid"] != str(request.profile_uid):
        raise ValueError("Profile does not match selected Lead")
    if deal and deal["company_uid"] != str(request.company_uid):
        raise ValueError("Deal does not belong to selected Company")
    if assessment and (
        assessment["company_uid"] != str(request.company_uid)
        or (deal and assessment["deal_uid"] != str(request.deal_uid))
    ):
        raise ValueError("Assessment does not match selected Company or Deal")
    context = {
        "contact": _projection(contact, "uid", "first_name", "last_name", "title"),
        "company": _projection(company, "uid", "name", "website", "description"),
        "lead": _projection(lead, "uid", "status", "notes"),
        "profile": _projection(
            profile,
            "uid",
            "name",
            "role",
            "market_context",
            "potential_pain",
            "likely_reasons",
            "likely_impacts",
            "research_guidance",
            "opening_message",
        ),
        "deal": _projection(deal, "uid", "name", "description", "amount", "currency"),
        "solution_selling": _projection(
            assessment,
            "uid",
            "pain_summary",
            "power_summary",
            "vision_summary",
            "value_summary",
            "control_summary",
            "evaluation_plan",
        ),
        "sender": {"uid": str(actor_uid), "display_name": sender_name},
        "inputs": request.inputs,
    }
    environment = _validate_template(template_record["template"])
    try:
        stream = environment.from_string(template_record["template"]).generate(**context)
        output: list[str] = []
        length = 0
        for part in stream:
            length += len(part)
            if length > 32768:
                raise ValueError("Rendered draft exceeds 32 KiB")
            output.append(part)
    except TemplateError as exc:
        raise ValueError("Template references missing or unsupported data") from exc
    return "".join(output)
