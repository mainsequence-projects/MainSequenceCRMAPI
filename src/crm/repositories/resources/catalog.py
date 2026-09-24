"""Allowlisted CRM storage projections and ordering expressions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ResourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    logical_table: str
    contract: str
    item_label: str
    search_fields: tuple[str, ...]
    default_ordering: str


RESOURCE_SPECS: dict[str, ResourceSpec] = {
    "companies": ResourceSpec(
        logical_table="company",
        contract="Company",
        item_label="Company",
        search_fields=("name", "website", "city"),
        default_ordering="name",
    ),
    "contacts": ResourceSpec(
        logical_table="contact",
        contract="Contact",
        item_label="Contact",
        search_fields=("first_name", "last_name", "title"),
        default_ordering="-last_seen",
    ),
    "deals": ResourceSpec(
        logical_table="deal",
        contract="Deal",
        item_label="Deal",
        search_fields=("name", "description"),
        default_ordering="-updated_at",
    ),
    "tasks": ResourceSpec(
        logical_table="task",
        contract="Task",
        item_label="Task",
        search_fields=("text",),
        default_ordering="due_at",
    ),
    "notes": ResourceSpec(
        logical_table="note",
        contract="Note",
        item_label="Note",
        search_fields=("text",),
        default_ordering="-occurred_at",
    ),
    "tags": ResourceSpec(
        logical_table="tag",
        contract="Tag",
        item_label="Tag",
        search_fields=("name",),
        default_ordering="name",
    ),
    "activity": ResourceSpec(
        logical_table="activity_event",
        contract="Activity",
        item_label="Activity",
        search_fields=("summary", "kind"),
        default_ordering="-occurred_at",
    ),
    "pipelines": ResourceSpec(
        logical_table="pipeline",
        contract="Pipeline",
        item_label="Pipeline",
        search_fields=("name",),
        default_ordering="name",
    ),
}


ORDER_COLUMNS: dict[str, dict[str, str]] = {
    "companies": {"name": "q.name", "created_at": "q.created_at", "updated_at": "q.updated_at"},
    "contacts": {
        "first_name": "q.first_name",
        "last_name": "q.last_name",
        "last_seen": "q.last_seen",
        "created_at": "q.created_at",
        "updated_at": "q.updated_at",
    },
    "deals": {
        "name": "q.name",
        "amount": "q.amount_numeric",
        "expected_closing_date": "q.expected_closing_date",
        "updated_at": "q.updated_at",
    },
    "tasks": {"due_at": "q.due_at", "created_at": "q.created_at", "updated_at": "q.updated_at"},
    "notes": {"occurred_at": "q.occurred_at", "created_at": "q.created_at"},
    "tags": {"name": "q.name", "created_at": "q.created_at"},
    "activity": {"occurred_at": "q.occurred_at"},
    "pipelines": {"name": "q.name", "created_at": "q.created_at", "updated_at": "q.updated_at"},
    "transfers": {"created_at": "q.created_at", "updated_at": "q.updated_at"},
}
