"""Command Center presentation metadata for CRM resource discovery."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.crm.repositories.resources.catalog import ORDER_COLUMNS, RESOURCE_SPECS


class DiscoveryColumn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    header: str
    importance: str


class DiscoverySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    columns: tuple[DiscoveryColumn, ...]


def _spec(label: str, *columns: tuple[str, str, str]) -> DiscoverySpec:
    return DiscoverySpec(
        label=label,
        columns=tuple(
            DiscoveryColumn(key=key, header=header, importance=importance)
            for key, header, importance in columns
        ),
    )


DISCOVERY: dict[str, DiscoverySpec] = {
    "companies": _spec(
        "Companies",
        ("name", "Company", "primary"),
        ("sector_key", "Sector", "secondary"),
        ("contact_count", "Contacts", "secondary"),
        ("deal_count", "Deals", "tertiary"),
    ),
    "contacts": _spec(
        "Contacts",
        ("display_name", "Contact", "primary"),
        ("company_name", "Company", "secondary"),
        ("status_key", "Status", "secondary"),
        ("last_seen", "Last interaction", "tertiary"),
    ),
    "deals": _spec(
        "Deals",
        ("name", "Deal", "primary"),
        ("stage_uid", "Stage", "secondary"),
        ("amount", "Amount", "secondary"),
        ("expected_closing_date", "Expected close", "tertiary"),
    ),
    "tasks": _spec(
        "Tasks",
        ("text", "Task", "primary"),
        ("due_at", "Due", "secondary"),
        ("type_key", "Type", "tertiary"),
        ("completed_at", "Completed", "secondary"),
    ),
    "notes": _spec(
        "Notes",
        ("text", "Note", "primary"),
        ("occurred_at", "Occurred", "secondary"),
        ("author_uid", "Author", "tertiary"),
    ),
    "tags": _spec("Tags", ("name", "Tag", "primary"), ("tone", "Tone", "secondary")),
    "activity": _spec(
        "Activity",
        ("summary", "Activity", "primary"),
        ("occurred_at", "When", "secondary"),
        ("origin", "Origin", "tertiary"),
    ),
    "pipelines": _spec(
        "Pipelines", ("name", "Pipeline", "primary"), ("board_version", "Board version", "tertiary")
    ),
}


def resource_discovery(resource: str) -> dict:
    spec = DISCOVERY[resource]
    storage = RESOURCE_SPECS[resource]
    ordering = list(ORDER_COLUMNS[resource])
    columns = []
    for item in spec.columns:
        column = {
            "id": item.key.replace("_", "-"),
            "header": item.header,
            "value_path": item.key,
            "data_type": "text",
            "default_visible": True,
            "hideable": item.importance != "primary",
            "importance": item.importance,
        }
        if item.key in ordering:
            column["sortable_key"] = item.key
        columns.append(column)
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {
            "id": resource,
            "label": spec.label,
            "item_label": storage.item_label,
            "identity": {"fields": ["uid"]},
        },
        "list": {
            "controls": {
                "search": {
                    "placeholder": f"Search {spec.label.lower()}",
                    "fields": list(storage.search_fields),
                },
                "filters": [],
                "ordering": ordering,
            },
            "columns": columns,
        },
        "bulk_actions": [],
    }
