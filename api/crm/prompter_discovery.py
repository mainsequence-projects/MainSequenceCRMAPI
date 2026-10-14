"""Canonical list metadata and caller-authorized prompter bulk action."""

BASE = "/extensions/solution-selling/prompters/"


def prompter_discovery(*, can_delete: bool) -> dict:
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {"id": "prompters", "label": "Prompters", "item_label": "Prompter",
                     "identity": {"fields": ["uid"]}},
        "list": {
            "controls": {"search": {"placeholder": "Search prompters",
                                    "fields": ["name", "kind", "description"]},
                         "filters": [], "ordering": []},
            "columns": [
                {"id": key, "header": label, "value_path": field, "data_type": kind,
                 "default_visible": True, "hideable": importance != "primary",
                 "importance": importance}
                for key, label, field, kind, importance in (
                    ("identity", "Prompter", "name", "text", "primary"),
                    ("kind", "Kind", "kind", "text", "secondary"),
                    ("updated", "Updated", "updated_at", "datetime", "tertiary"),
                )
            ],
        },
        "bulk_actions": [{
            "id": "delete", "label": "Delete prompters", "tone": "danger",
            "endpoint": BASE + "bulk-delete/", "method": "POST",
            "selection_modes": ["explicit"], "options": [],
            "preflight_endpoint": BASE + "bulk-delete/preflight/",
            "confirmation": {
                "title": "Delete selected prompters?", "word": "DELETE",
                "button_label": "Delete prompters",
                "warning": "Selected templates will be removed from the active list and can no longer be rendered. Their audit history is retained.",
            },
        }] if can_delete else [],
    }
