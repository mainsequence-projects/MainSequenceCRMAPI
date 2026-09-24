"""Pydantic validation of collection and discovery URL parameters."""

from __future__ import annotations

import json
from typing import Mapping

from pydantic import ValidationError

from src.crm.models.queries import FILTER_MODELS, QueryScope
from src.crm.repositories.resources.catalog import ORDER_COLUMNS

from .query_models import BoardQuery, CollectionQuery, DiscoveryQuery, PageQuery, StageCardsQuery


class QueryError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


def _invalid(exc: ValidationError) -> QueryError:
    first = exc.errors(include_url=False, include_context=False)[0]
    field = ".".join(str(part) for part in first["loc"]) or "filters"
    return QueryError(field, first["msg"])


def parse_query(resource: str, params: Mapping[str, str], *, discovery: bool = False) -> QueryScope:
    if resource not in FILTER_MODELS:
        raise ValueError("Unknown CRM resource")
    try:
        http = (DiscoveryQuery if discovery else CollectionQuery).model_validate(params)
    except ValidationError as exc:
        raise _invalid(exc) from exc
    try:
        raw_filters = json.loads(http.filters)
    except json.JSONDecodeError as exc:
        raise QueryError("filters", "Filters must be a JSON object") from exc
    try:
        filters = (
            FILTER_MODELS[resource]
            .model_validate(raw_filters)
            .model_dump(mode="json", exclude_none=True)
        )
    except ValidationError as exc:
        error = _invalid(exc)
        field = "filters" if error.field == "filters" else f"filters.{error.field}"
        raise QueryError(field, str(error)) from exc
    if discovery:
        return QueryScope(search=http.search, filters=filters)
    ordering = http.ordering or None
    if ordering and ordering.removeprefix("-") not in ORDER_COLUMNS[resource]:
        raise QueryError("ordering", "Unsupported ordering key")
    return QueryScope(
        search=http.search,
        filters=filters,
        ordering=ordering,
        page_index=http.page_index,
        page_size=http.page_size,
    )


def parse_page(params: Mapping[str, str]) -> PageQuery:
    try:
        return PageQuery.model_validate(params)
    except ValidationError as exc:
        raise _invalid(exc) from exc


def parse_board_query(
    params: Mapping[str, str], *, stage_cards: bool = False
) -> BoardQuery | StageCardsQuery:
    try:
        query = (StageCardsQuery if stage_cards else BoardQuery).model_validate(params)
    except ValidationError as exc:
        raise _invalid(exc) from exc
    parse_query(
        "deals",
        query.model_dump(include={"search", "filters"}, exclude_none=True),
        discovery=True,
    )
    return query
