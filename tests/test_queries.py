import pytest
from pydantic import BaseModel

from api.crm.discovery import resource_discovery
from api.crm.query import QueryError, parse_board_query, parse_page, parse_query
from api.crm.query_models import CollectionQuery, DiscoveryQuery
from src.crm.models.queries import QueryScope
from src.crm.portability.exporting import (
    csv_safe,
    export_entity_names,
    export_record_key,
    package_export,
    render_export,
)


def test_page_defaults_and_discovery_is_separate():
    scope = parse_query("contacts", {})
    assert (scope.page_index, scope.page_size, scope.search) == (0, 25, None)
    with pytest.raises(QueryError):
        parse_query("contacts", {"page_size": "25"}, discovery=True)


def test_invalid_order_filter_and_nested_shape_are_rejected():
    for parameters in (
        {"ordering": "workspace_uid"},
        {"filters": '{"workspace_uid":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}'},
        {"filters": '{"company_uid":{"$ne":null}}'},
        {"page_size": "101"},
    ):
        with pytest.raises(QueryError):
            parse_query("contacts", parameters)


def test_valid_semantic_scope():
    scope = parse_query(
        "contacts",
        {
            "search": "  Alex  ",
            "ordering": "-last_seen",
            "filters": '{"archived":false,"has_open_tasks":true}',
        },
    )
    assert scope.search == "Alex"
    assert scope.ordering == "-last_seen"
    assert scope.filters == {"archived": False, "has_open_tasks": True}


def test_pydantic_filters_reject_coercion_and_unknown_fields():
    for parameters in (
        {"filters": '{"has_open_tasks":1}'},
        {"filters": '{"archived":"false"}'},
        {"filters": '{"company_uid":null}'},
        {"filters": '{"company_uid":123}'},
        {"filters": '{"status_key":"  "}'},
        {"filters": "[]"},
        {"page_index": "-1"},
        {"page_size": "1.5"},
    ):
        with pytest.raises(QueryError):
            parse_query("contacts", parameters)


def test_transfer_ordering_is_allowlisted_at_http_boundary():
    assert parse_query("transfers", {"ordering": "-updated_at"}).ordering == "-updated_at"
    with pytest.raises(QueryError):
        parse_query("transfers", {"ordering": "uid; DROP TABLE transfer_job"})


def test_board_and_transfer_pagination_have_closed_http_models():
    assert parse_page({"page_index": "2", "page_size": "10"}).page_index == 2
    assert parse_board_query({"page_size": "12"}).page_size == 12
    assert (
        parse_board_query({"expected_board_version": "0", "cursor": "4"}, stage_cards=True).cursor
        == 4
    )
    for parameters in ({"page_size": "101"}, {"search": "unexpected"}):
        with pytest.raises(QueryError):
            parse_page(parameters)
    for parameters in ({"cursor": "-1"}, {"expected_board_version": "1.5"}, {}):
        with pytest.raises(QueryError):
            parse_board_query(parameters, stage_cards=True)
    with pytest.raises(QueryError):
        parse_board_query({"ordering": "name"})
    with pytest.raises(QueryError):
        parse_board_query({"filters": '{"workspace_uid":"x"}'})


def test_query_scopes_are_pydantic_and_discovery_stays_in_api():
    assert issubclass(QueryScope, BaseModel)
    assert issubclass(CollectionQuery, BaseModel)
    assert CollectionQuery.__module__ == "api.crm.query_models"
    assert DiscoveryQuery.__module__ == "api.crm.query_models"
    discovery = resource_discovery("contacts")
    assert discovery["resource"]["item_label"] == "Contact"
    assert discovery["list"]["columns"][0]["value_path"] == "display_name"


def test_export_mapping_and_rendering_are_pure_portability_logic():
    assert export_entity_names("companies") == ["company"]
    assert export_record_key("company") == "companies"
    assert csv_safe("=1+1") == "'=1+1"
    manifest, counts = package_export(
        {"format": "portable-json", "entity_type": "companies"},
        {"companies": [{"uid": "example"}]},
    )
    assert counts["total"] == 1
    content, mime_type, filename = render_export(manifest)
    assert "example" in content
    assert mime_type == "application/json"
    assert filename == "crm-export.json"
    csv_manifest, _ = package_export(
        {"format": "csv", "entity_type": "companies"},
        {"companies": [{"uid": "example"}]},
    )
    assert csv_manifest["output"]["records"] == [{"uid": "example"}]
