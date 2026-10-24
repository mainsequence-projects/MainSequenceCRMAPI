"""Pure validation of a candidate campaign graph. No persistence, no I/O."""

from __future__ import annotations

from collections import deque
from typing import Any
from uuid import UUID

from .models import CampaignGraph, Diagnostic, GraphStep, GraphValidation


def _diag(code: str, message: str, **where: UUID | None) -> Diagnostic:
    return Diagnostic(code=code, message=message, **where)


def active_steps(graph: CampaignGraph) -> dict[UUID, GraphStep]:
    return {step.uid: step for step in graph.steps if not step.archived}


def validate_graph(
    graph: CampaignGraph, prompts: dict[UUID, dict[str, Any]] | None = None
) -> GraphValidation:
    """Return diagnostics; ``runnable`` is True only when nothing blocks activation.

    ``prompts`` maps step-prompt UIDs to ``{"archived": bool, "inputs": [...],
    "result_fields": [...]}`` when the caller resolved them. Unresolved prompts
    are reported as missing.
    """
    diagnostics: list[Diagnostic] = []
    steps = active_steps(graph)
    archived = {step.uid for step in graph.steps if step.archived}

    if graph.entry_step_uid is None:
        diagnostics.append(_diag("entry_missing", "Choose the entry step before activation"))
    elif graph.entry_step_uid not in steps:
        diagnostics.append(
            _diag("entry_invalid", "The entry step must be an active step of this campaign",
                  step_uid=graph.entry_step_uid)
        )

    routes: dict[tuple[UUID, str], int] = {}
    adjacency: dict[UUID, set[UUID]] = {uid: set() for uid in steps}
    for transition in graph.transitions:
        if transition.from_step_uid not in steps:
            diagnostics.append(
                _diag("transition_source_invalid", "Connection starts at a missing or retired step",
                      transition_uid=transition.uid, step_uid=transition.from_step_uid)
            )
            continue
        source = steps[transition.from_step_uid]
        if transition.outcome_key not in {outcome.key for outcome in source.outcomes}:
            diagnostics.append(
                _diag("transition_outcome_unknown",
                      f"Outcome '{transition.outcome_key}' is not declared by the source step",
                      transition_uid=transition.uid, step_uid=source.uid)
            )
        if transition.to_step_uid is not None:
            if transition.to_step_uid in archived:
                diagnostics.append(
                    _diag("transition_target_retired", "Connection targets a retired step",
                          transition_uid=transition.uid, step_uid=transition.to_step_uid)
                )
            elif transition.to_step_uid not in steps:
                diagnostics.append(
                    _diag("transition_target_invalid", "Connection targets a step outside this graph",
                          transition_uid=transition.uid, step_uid=transition.to_step_uid)
                )
            else:
                adjacency[source.uid].add(transition.to_step_uid)
        route = (transition.from_step_uid, transition.outcome_key)
        routes[route] = routes.get(route, 0) + 1
    for (step_uid, outcome_key), count in routes.items():
        if count > 1:
            diagnostics.append(
                _diag("route_duplicate", f"Outcome '{outcome_key}' has more than one connection",
                      step_uid=step_uid)
            )
    for step in steps.values():
        for outcome in step.outcomes:
            if (step.uid, outcome.key) not in routes:
                diagnostics.append(
                    _diag("route_missing",
                          f"Outcome '{outcome.key}' needs a connection to a next step or finish",
                          step_uid=step.uid)
                )
        for variant in step.prompt_variants:
            resolved = None if prompts is None else prompts.get(variant.prompt_uid)
            if resolved is None:
                diagnostics.append(
                    _diag("prompt_missing", f"Variant '{variant.key}' references an unknown step prompt",
                          step_uid=step.uid)
                )
            elif resolved.get("archived"):
                diagnostics.append(
                    _diag("prompt_archived", f"Variant '{variant.key}' references an archived prompt",
                          step_uid=step.uid)
                )
        if prompts is not None and len(step.prompt_variants) == 2:
            contracts = []
            for variant in step.prompt_variants:
                resolved = prompts.get(variant.prompt_uid)
                if resolved is not None:
                    contracts.append((
                        frozenset((f["key"], f["type"], f.get("required", True)) for f in resolved.get("inputs", [])),
                        frozenset((f["key"], f["type"], f.get("required", True)) for f in resolved.get("result_fields", [])),
                    ))
            if len(contracts) == 2 and contracts[0] != contracts[1]:
                diagnostics.append(
                    _diag("variant_contract_mismatch",
                          "A/B variants must declare the same inputs and result fields",
                          step_uid=step.uid)
                )
        comparison = step.prompt_comparison
        if comparison is not None:
            metric = steps.get(comparison.metric_step_uid)
            if metric is None:
                diagnostics.append(
                    _diag("comparison_metric_invalid", "The comparison metric step is not an active step",
                          step_uid=step.uid)
                )
            else:
                declared = {outcome.key for outcome in metric.outcomes}
                unknown = set(comparison.success_outcome_keys) - declared
                if unknown:
                    diagnostics.append(
                        _diag("comparison_outcome_unknown",
                              f"Success outcomes {sorted(unknown)} are not declared by the metric step",
                              step_uid=step.uid)
                    )
                if metric.uid != step.uid and not _reaches(adjacency, step.uid, metric.uid):
                    diagnostics.append(
                        _diag("comparison_metric_unreachable",
                              "The metric step is not reachable from the compared step",
                              step_uid=step.uid)
                    )
        declared_inputs = None
        if prompts is not None:
            resolved = [prompts.get(v.prompt_uid) for v in step.prompt_variants]
            if all(item is not None for item in resolved):
                declared_inputs = set.union(*(
                    {field["key"] for field in item.get("inputs", [])} for item in resolved
                )) if resolved else set()
        for key, path in step.input_bindings.items():
            if declared_inputs is not None and key not in declared_inputs:
                diagnostics.append(
                    _diag("binding_undeclared", f"Binding '{key}' is not an input of the step's prompt",
                          step_uid=step.uid)
                )
            parts = path.split(".")
            if parts[0] == "previous":
                if len(parts) < 3 or parts[2] != "result":
                    diagnostics.append(
                        _diag("binding_invalid", f"Binding '{key}' must use previous.<step_uid>.result.<field>",
                              step_uid=step.uid)
                    )
                    continue
                try:
                    predecessor = UUID(parts[1])
                except ValueError:
                    diagnostics.append(
                        _diag("binding_invalid", f"Binding '{key}' names an invalid step UID",
                              step_uid=step.uid)
                    )
                    continue
                if predecessor not in steps or not _reaches(adjacency, predecessor, step.uid):
                    diagnostics.append(
                        _diag("binding_predecessor_unreachable",
                              f"Binding '{key}' must reference a step that can precede this one",
                              step_uid=step.uid)
                    )
            elif parts[0] not in {"campaign", "contact", "participant"}:
                diagnostics.append(
                    _diag("binding_invalid",
                          f"Binding '{key}' must be rooted at campaign, contact, participant or previous",
                          step_uid=step.uid)
                )

    if graph.entry_step_uid in steps:
        reachable = _closure(adjacency, graph.entry_step_uid)
        for uid in steps:
            if uid not in reachable:
                diagnostics.append(
                    _diag("step_unreachable", "Step cannot be reached from the entry step", step_uid=uid)
                )
    for uid in _cycle_members(adjacency):
        diagnostics.append(_diag("cycle", "Step participates in a cycle", step_uid=uid))
    if not steps:
        diagnostics.append(_diag("graph_empty", "Add at least one step"))
    return GraphValidation(runnable=not diagnostics, diagnostics=diagnostics)


def _closure(adjacency: dict[UUID, set[UUID]], start: UUID) -> set[UUID]:
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in adjacency.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def _reaches(adjacency: dict[UUID, set[UUID]], source: UUID, target: UUID) -> bool:
    return target in _closure(adjacency, source)


def _cycle_members(adjacency: dict[UUID, set[UUID]]) -> list[UUID]:
    """Kahn's algorithm: whatever cannot be topologically ordered lies on a cycle."""
    indegree = {uid: 0 for uid in adjacency}
    for targets in adjacency.values():
        for target in targets:
            if target in indegree:
                indegree[target] += 1
    queue = deque(uid for uid, degree in indegree.items() if degree == 0)
    ordered = 0
    while queue:
        current = queue.popleft()
        ordered += 1
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return sorted((uid for uid, degree in indegree.items() if degree > 0), key=str)


def layout_only_change(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Position edits never invalidate briefings, assignments or comparisons."""
    return {k: v for k, v in before.items() if k != "position"} == {
        k: v for k, v in after.items() if k != "position"
    }


def comparison_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Prompt mapping, allocation, comparison, task rules or criteria changed."""
    keys = ("prompt_variants", "prompt_comparison", "task_text", "completion_criteria",
            "outcomes", "input_bindings", "completion_mode", "due_after_seconds")
    return any(before.get(key) != after.get(key) for key in keys)
