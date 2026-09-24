"""Shared governed collection and detail reads."""

from __future__ import annotations

import uuid
from typing import Any

from ...contracts import validate_payload
from ...metatables import MODELS
from ...models.queries import QueryScope
from ..companies.reads import company_projection
from ..contacts.reads import contact_projection
from ..deals.reads import deal_projection
from ..errors import ResourceNotFound
from ..gateway import GovernedGateway
from .catalog import ORDER_COLUMNS, RESOURCE_SPECS


class ResourceReads(GovernedGateway):
    def collection(self, resource: str, scope: QueryScope) -> dict[str, Any]:
        definition = RESOURCE_SPECS[resource]
        select_sql, referenced = self._select_sql(resource)
        where_sql, parameters, parameter_types, filter_tables = self._where_sql(resource, scope)
        ordering = scope.ordering or definition.default_ordering
        descending = ordering.startswith("-")
        order_key = ordering.removeprefix("-")
        order_expression = ORDER_COLUMNS[resource][order_key]
        direction = "DESC" if descending else "ASC"
        parameters.update(
            {"page_size": scope.page_size, "page_offset": scope.page_index * scope.page_size}
        )
        parameter_types.update({"page_size": "integer", "page_offset": "integer"})
        sql = (
            f"WITH q AS ({select_sql} WHERE {where_sql}), "
            "paged AS (SELECT q.*, row_number() OVER () AS __row FROM q "
            f"ORDER BY {order_expression} {direction} NULLS LAST, q.uid {direction} "
            "LIMIT CAST(%(page_size)s AS integer) OFFSET CAST(%(page_offset)s AS integer)) "
            "SELECT COALESCE((SELECT jsonb_agg(to_jsonb(paged) - '__row' - 'amount_numeric' "
            "ORDER BY __row) FROM paged), '[]'::jsonb) AS items, "
            "(SELECT count(*) FROM q) AS total_items"
        )
        tables = {definition.logical_table: "read", **referenced, **filter_tables}
        result = self._operation(
            operation="select",
            sql=sql,
            parameters=parameters,
            parameter_types=parameter_types,
            tables=tables,
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError("CRM collection query returned no envelope")
        items = self._json(rows[0].get("items"), expected=list, label="collection")
        total = int(rows[0].get("total_items", 0))
        page_index = int(scope.page_index)
        page_size = int(scope.page_size)
        for item in items:
            validate_payload(definition.contract, item)
        return {
            "items": items,
            "pageInfo": {
                "pageIndex": page_index,
                "pageSize": page_size,
                "totalItems": total,
                "hasNextPage": (page_index + 1) * page_size < total,
                "hasPreviousPage": page_index > 0,
            },
        }

    def detail(self, resource: str, uid: uuid.UUID) -> dict[str, Any]:
        definition = RESOURCE_SPECS[resource]
        select_sql, referenced = self._select_sql(resource)
        sql = (
            f"WITH q AS ({select_sql} WHERE t.uid = CAST(%(uid)s AS uuid)) "
            "SELECT to_jsonb(q) - 'amount_numeric' AS item FROM q"
        )
        result = self._operation(
            operation="select",
            sql=sql,
            parameters={"uid": str(uid)},
            parameter_types={"uid": "uuid"},
            tables={definition.logical_table: "read", **referenced},
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ResourceNotFound(f"{definition.item_label} not found")
        item = self._json(rows[0].get("item"), expected=dict, label="detail")
        return validate_payload(definition.contract, item)

    def _select_sql(self, resource: str) -> tuple[str, dict[str, str]]:
        table = MODELS[RESOURCE_SPECS[resource].logical_table].__tablename__
        if resource == "companies":
            return company_projection()
        if resource == "contacts":
            return contact_projection()
        if resource == "deals":
            return deal_projection()
        if resource == "activity":
            return (
                "SELECT t.uid, t.entity_type, t.entity_uid, t.kind, t.occurred_at, "
                "t.recorded_at, t.actor_uid, t.origin, t.summary, t.changes "
                f'FROM "{table}" t',
                {},
            )
        return (f'SELECT t.* FROM "{table}" t', {})

    def _where_sql(
        self, resource: str, scope: QueryScope
    ) -> tuple[str, dict[str, Any], dict[str, str], dict[str, str]]:
        clauses: list[str] = []
        parameters: dict[str, Any] = {}
        types: dict[str, str] = {}
        tables: dict[str, str] = {}
        definition = RESOURCE_SPECS[resource]
        if resource not in {"activity", "pipelines"}:
            archived = scope.filters.get("archived", False)
            if archived is True:
                clauses.append("t.archived_at IS NOT NULL")
            elif archived is False:
                clauses.append("t.archived_at IS NULL")
        if scope.search:
            escaped = scope.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters["search"] = f"%{escaped.casefold()}%"
            types["search"] = "string"
            clauses.append(
                "("
                + " OR ".join(
                    f"lower(coalesce(t.{field}::text, '')) LIKE %(search)s ESCAPE '\\'"
                    for field in definition.search_fields
                )
                + ")"
            )
        direct = {
            "companies": {"owner_uid", "sector", "country"},
            "contacts": {"company_uid", "owner_uid", "status_key"},
            "deals": {"pipeline_uid", "stage_uid", "company_uid", "owner_uid", "currency"},
            "tasks": {"contact_uid", "owner_uid", "type_key"},
            "notes": {"contact_uid", "deal_uid", "author_uid"},
            "activity": {"entity_type", "entity_uid", "actor_uid", "origin"},
        }.get(resource, set())
        column_alias = {"sector": "sector_key"}
        for key, value in scope.filters.items():
            if (
                key
                in {
                    "archived",
                    "tag_uid",
                    "has_open_tasks",
                    "contact_uid",
                    "completion",
                    "seen_window",
                    "due_window",
                    "occurred_window",
                }
                and key not in direct
            ):
                continue
            if key not in direct:
                continue
            column = column_alias.get(key, key)
            parameters[f"filter_{key}"] = str(value)
            types[f"filter_{key}"] = "uuid" if key.endswith("_uid") else "string"
            placeholder = f"%(filter_{key})s"
            if key.endswith("_uid"):
                placeholder = f"CAST({placeholder} AS uuid)"
            clauses.append(f"t.{column} = {placeholder}")
        if resource == "contacts" and "tag_uid" in scope.filters:
            link = MODELS["contact_tag"].__tablename__
            parameters["filter_tag_uid"] = scope.filters["tag_uid"]
            types["filter_tag_uid"] = "uuid"
            clauses.append(
                f'EXISTS (SELECT 1 FROM "{link}" ft WHERE ft.contact_uid=t.uid '
                "AND ft.tag_uid=CAST(%(filter_tag_uid)s AS uuid))"
            )
            tables["contact_tag"] = "read"
        if resource == "contacts" and "has_open_tasks" in scope.filters:
            task = MODELS["task"].__tablename__
            exists = "EXISTS" if scope.filters["has_open_tasks"] else "NOT EXISTS"
            clauses.append(
                f'{exists} (SELECT 1 FROM "{task}" ft WHERE ft.contact_uid=t.uid '
                "AND ft.completed_at IS NULL AND ft.archived_at IS NULL)"
            )
            tables["task"] = "read"
        if resource == "deals" and "contact_uid" in scope.filters:
            link = MODELS["deal_contact"].__tablename__
            parameters["filter_contact_uid"] = scope.filters["contact_uid"]
            types["filter_contact_uid"] = "uuid"
            clauses.append(
                f'EXISTS (SELECT 1 FROM "{link}" ft WHERE ft.deal_uid=t.uid '
                "AND ft.contact_uid=CAST(%(filter_contact_uid)s AS uuid))"
            )
            tables["deal_contact"] = "read"
        if resource == "tasks" and "completion" in scope.filters:
            value = scope.filters["completion"]
            if value not in {"open", "completed"}:
                raise ValueError("Unsupported task completion filter")
            clauses.append(
                "t.completed_at IS NULL" if value == "open" else "t.completed_at IS NOT NULL"
            )
        unsupported_windows = {
            "seen_window",
            "due_window",
            "occurred_window",
        } & scope.filters.keys()
        if unsupported_windows:
            raise ValueError(f"Unsupported filter: {sorted(unsupported_windows)[0]}")
        return " AND ".join(clauses) if clauses else "TRUE", parameters, types, tables
