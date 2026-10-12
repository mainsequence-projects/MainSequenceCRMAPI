"""Bounded collection SQL; PostgreSQL checks use only a private test cluster.

The MetaTables transport is captured, so these tests do not establish hosted
authorization or latency. PostgreSQL executes the actual submitted statement.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from api.crm.main import create_app
from metatables import MetaTableCompiledSQLOperation
from src.crm.metatables import MODELS, Base
from src.crm.models.queries import QueryScope
from src.crm.repositories.resources.catalog import ORDER_COLUMNS, RESOURCE_SPECS
from src.crm.repositories.resources.reads import ResourceReads

NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
SOURCE = str(uuid.UUID(int=90000))
COMPANY = uuid.UUID(int=20000)
TAG = uuid.UUID(int=30000)
TOTAL = 1000


def _postgres_command(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"PostgreSQL fixture command failed: {result.stderr or result.stdout}")


@pytest.mark.parametrize(
    "resource,ordering",
    [
        (resource, prefix + key)
        for resource in RESOURCE_SPECS
        for key in ORDER_COLUMNS[resource]
        for prefix in ("", "-")
    ],
)
def test_collection_sends_one_bounded_governed_statement(monkeypatch, resource, ordering):
    calls = []

    def execute(payload):
        MetaTableCompiledSQLOperation.model_validate(payload)
        calls.append(payload)
        return {"rows": [{"items": [], "total_items": 120}]}

    monkeypatch.setattr("src.crm.repositories.gateway.MetaTable.execute_operation", execute)
    result = ResourceReads(SimpleNamespace(data_source_uid=SOURCE)).collection(
        resource, QueryScope(page_index=1, page_size=50, ordering=ordering)
    )
    assert result["pageInfo"] == {
        "pageIndex": 1,
        "pageSize": 50,
        "totalItems": 120,
        "hasNextPage": True,
        "hasPreviousPage": True,
    }
    (call,) = calls
    assert call["operation"] == "select"
    assert call["data_source_uid"] == SOURCE
    assert call["limits"] == {"max_rows": 1, "statement_timeout_ms": 15000}
    assert call["statement"]["parameters"]["page_size"] == 50
    assert call["statement"]["parameters"]["page_offset"] == 50
    sql = call["statement"]["sql"]
    filtered, enrichment = sql.split("paged AS", 1)
    assert "t.*" not in filtered
    assert "jsonb_agg" not in filtered
    assert "count(*)" not in filtered
    assert "FROM filtered" in sql
    assert "row_number()" not in sql
    assert "CROSS JOIN LATERAL" in enrichment
    assert sql.index("LIMIT CAST") < sql.index("CROSS JOIN LATERAL")
    assert "WHERE t.uid=p.uid" in sql
    assert "ORDER BY p.__sort" in sql
    if resource == "deals" and ordering.removeprefix("-") == "amount":
        assert "t.amount AS __sort" in filtered
        assert "amount_numeric" not in filtered


@pytest.fixture(scope="module")
def collection_postgres():
    """Never connect to an existing database or listen on a TCP interface."""
    binaries = {name: shutil.which(name) for name in ("postgres", "initdb", "pg_ctl")}
    if os.name != "posix" or os.geteuid() == 0 or not all(binaries.values()):
        pytest.skip("PostgreSQL collection checks require local postgres/initdb/pg_ctl as non-root")
    pytest.importorskip("psycopg")
    with tempfile.TemporaryDirectory(prefix="crm-collection-pg-") as directory:
        root = Path(directory)
        data, socket = root / "data", root / "socket"
        socket.mkdir(mode=0o700)
        _postgres_command(
            [binaries["initdb"], "-D", str(data), "--auth=trust", "--no-locale", "--encoding=UTF8"],
        )
        # Trust is confined to the private Unix socket in this mode-0700 directory.
        _postgres_command(
            [
                binaries["pg_ctl"],
                "-D",
                str(data),
                "-l",
                str(root / "server.log"),
                "-o",
                f"-F -c listen_addresses='' -k {socket} -p 25432",
                "-w",
                "start",
            ],
        )
        engine = sa.create_engine(
            sa.URL.create(
                "postgresql+psycopg",
                username=getpass.getuser(),
                database="postgres",
                query={"host": str(socket), "port": "25432"},
            ),
            hide_parameters=True,
        )
        try:
            Base.metadata.create_all(engine)
            yield engine
        finally:
            engine.dispose()
            _postgres_command(
                [binaries["pg_ctl"], "-D", str(data), "-m", "fast", "-w", "stop"],
            )


def _record(number, **values):
    return {
        "uid": uuid.UUID(int=number),
        "created_at": NOW,
        "updated_at": NOW,
        "version": 1,
        **values,
    }


@pytest.fixture
def collection_db(collection_postgres):
    with collection_postgres.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                MODELS["company"].__table__.insert(),
                [
                    _record(COMPANY.int, name="Acme", context_links=[]),
                ],
            )
            connection.execute(
                MODELS["tag"].__table__.insert(),
                [
                    _record(TAG.int, name="Selected", normalized_name="selected", tone="neutral"),
                ],
            )
            # Reverse insertion order, repeated sort values and nulls expose
            # unstable pagination and accidental JSON aggregation reordering.
            contacts = [
                _record(
                    i,
                    first_name=f"Group {i // 3:04}",
                    last_name="Contact",
                    emails=[],
                    phones=[],
                    company_uid=COMPANY,
                    archived_at=None,
                    last_seen=None if i % 40 == 0 else NOW + timedelta(minutes=i // 3),
                )
                for i in range(TOTAL, 0, -1)
            ]
            contacts.append(
                _record(
                    TOTAL + 1,
                    first_name="Archived",
                    last_name="Contact",
                    emails=[],
                    phones=[],
                    company_uid=COMPANY,
                    archived_at=NOW,
                    last_seen=None,
                )
            )
            connection.execute(MODELS["contact"].__table__.insert(), contacts)
            connection.execute(
                MODELS["contact_tag"].__table__.insert(),
                [
                    {
                        "uid": uuid.UUID(int=40000 + i),
                        "contact_uid": uuid.UUID(int=i),
                        "tag_uid": TAG,
                        "created_at": NOW,
                    }
                    for i in range(2, TOTAL + 1, 2)
                ],
            )
            connection.execute(
                MODELS["task"].__table__.insert(),
                [
                    _record(50000 + i, contact_uid=uuid.UUID(int=i), text="Open", type_key="none")
                    for i in range(2, TOTAL + 1, 2)
                ],
            )
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def collection_store(collection_db, monkeypatch):
    calls = []

    def execute(payload):
        MetaTableCompiledSQLOperation.model_validate(payload)
        calls.append(payload)
        row = (
            collection_db.exec_driver_sql(
                payload["statement"]["sql"], payload["statement"]["parameters"]
            )
            .mappings()
            .one()
        )
        return {"rows": [dict(row)]}

    monkeypatch.setattr("src.crm.repositories.gateway.MetaTable.execute_operation", execute)
    return ResourceReads(SimpleNamespace(data_source_uid=SOURCE)), calls


def _nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


def test_postgres_enriches_only_fifty_of_one_thousand_contacts(collection_store, collection_db):
    store, calls = collection_store
    scope = QueryScope(page_index=1, page_size=50, ordering="first_name")
    result = store.collection("contacts", scope)
    assert [item["uid"] for item in result["items"]] == [
        str(uuid.UUID(int=i)) for i in range(51, 101)
    ]
    assert result["pageInfo"] == {
        "pageIndex": 1,
        "pageSize": 50,
        "totalItems": TOTAL,
        "hasNextPage": True,
        "hasPreviousPage": True,
    }
    assert all(item["company_name"] == "Acme" for item in result["items"])
    for i, item in enumerate(result["items"], start=51):
        assert item["open_task_count"] == (1 if i % 2 == 0 else 0)
        assert item["tag_uids"] == ([str(TAG)] if i % 2 == 0 else [])
        assert "__row" not in item and "__sort" not in item
    (call,) = calls
    plan = collection_db.exec_driver_sql(
        "EXPLAIN (ANALYZE, FORMAT JSON) " + call["statement"]["sql"],
        call["statement"]["parameters"],
    ).scalar_one()[0]["Plan"]
    # Company name, tag aggregation and task count run once per page contact,
    # not once per row in the complete matching set (or the offset prefix).
    enrichment = [node for node in _nodes(plan) if node.get("Parent Relationship") == "SubPlan"]
    assert len(enrichment) == 3
    assert [node["Actual Loops"] for node in enrichment] == [50, 50, 50]

    # The previous full-projection CTE was also consumed by the count. Its
    # display subqueries therefore ran across the complete matching set.
    legacy = (
        f"WITH q AS ({store._select_sql('contacts')} WHERE t.archived_at IS NULL), "
        "paged AS (SELECT q.*, row_number() OVER () AS __row FROM q "
        "ORDER BY q.first_name ASC NULLS LAST, q.uid ASC "
        "LIMIT %(page_size)s OFFSET %(page_offset)s) "
        "SELECT (SELECT jsonb_agg(to_jsonb(paged) ORDER BY __row) FROM paged) AS items, "
        "(SELECT count(*) FROM q) AS total_items"
    )
    legacy_plan = collection_db.exec_driver_sql(
        "EXPLAIN (ANALYZE, FORMAT JSON) " + legacy, call["statement"]["parameters"]
    ).scalar_one()[0]["Plan"]
    legacy_enrichment = [
        node for node in _nodes(legacy_plan) if node.get("Parent Relationship") == "SubPlan"
    ]
    assert [node["Actual Loops"] for node in legacy_enrichment] == [TOTAL, TOTAL, TOTAL]


@pytest.mark.parametrize("ordering", ["last_seen", "-last_seen"])
def test_postgres_pages_preserve_null_last_order_and_uid_ties(collection_store, ordering):
    store, _ = collection_store
    descending = ordering.startswith("-")
    nonnull = [i for i in range(1, TOTAL + 1) if i % 40]
    nonnull.sort(key=lambda i: (i // 3, i), reverse=descending)
    nulls = sorted(range(40, TOTAL + 1, 40), reverse=descending)
    expected = nonnull + nulls
    actual = []
    for index in range(TOTAL // 100):
        result = store.collection(
            "contacts",
            QueryScope(
                ordering=ordering,
                page_index=index,
                page_size=100,
            ),
        )
        assert result["pageInfo"]["totalItems"] == TOTAL
        actual.extend(uuid.UUID(item["uid"]).int for item in result["items"])
    assert actual == expected


@pytest.mark.parametrize(
    "scope,total,identifiers",
    [
        (QueryScope(search="Missing", page_size=50), 0, []),
        (QueryScope(page_index=20, page_size=50), TOTAL, []),
        (QueryScope(search="Archived", filters={"archived": True}), 1, [TOTAL + 1]),
        (
            QueryScope(
                filters={"tag_uid": str(TAG), "has_open_tasks": True},
                ordering="first_name",
                page_size=50,
            ),
            TOTAL // 2,
            list(range(2, 101, 2)),
        ),
        (
            QueryScope(
                filters={"company_uid": str(COMPANY), "archived": "all"},
                ordering="first_name",
                page_size=1,
            ),
            TOTAL + 1,
            [TOTAL + 1],
        ),
    ],
)
def test_postgres_filters_empty_pages_and_totals(collection_store, scope, total, identifiers):
    store, calls = collection_store
    result = store.collection("contacts", scope)
    assert result["pageInfo"]["totalItems"] == total
    assert [uuid.UUID(item["uid"]).int for item in result["items"]] == identifiers
    assert len(calls) == 1


def test_postgres_deal_amount_order_remains_numeric(collection_store, collection_db):
    store, _ = collection_store
    pipeline = _record(70000, name="Sales", is_default=True, board_version=1)
    stage = _record(
        70001,
        pipeline_uid=pipeline["uid"],
        key="open",
        label="Open",
        position=0,
        outcome="open",
        is_active=True,
    )
    collection_db.execute(MODELS["pipeline"].__table__.insert(), pipeline)
    collection_db.execute(MODELS["stage"].__table__.insert(), stage)
    collection_db.execute(
        MODELS["deal"].__table__.insert(),
        [
            _record(
                71000 + i,
                name=f"Deal {i}",
                pipeline_uid=pipeline["uid"],
                stage_uid=stage["uid"],
                amount=amount,
                currency="EUR",
                position=i,
            )
            for i, amount in enumerate(("100.0000", "9.0000", "20.0000"))
        ],
    )
    result = store.collection("deals", QueryScope(ordering="amount", page_size=2))
    assert [item["amount"] for item in result["items"]] == ["9.0000", "20.0000"]
    assert result["pageInfo"]["totalItems"] == 3
    assert all("amount_numeric" not in item for item in result["items"])


def test_postgres_company_projection_and_plain_collection(collection_store):
    store, _ = collection_store
    companies = store.collection("companies", QueryScope(page_size=1))
    assert companies["items"][0]["name"] == "Acme"
    assert companies["items"][0]["contact_count"] == 0  # No affiliation fixtures.
    assert companies["items"][0]["deal_count"] == 0
    tags = store.collection("tags", QueryScope(page_size=1))
    assert tags["items"][0]["uid"] == str(TAG)


def test_http_pagination_still_checks_fresh_permissions(collection_store, signed_caller):
    store, calls = collection_store
    actor = uuid.uuid4()
    grants = {"crm.read"}
    app = create_app()
    app.state.crm_policy = SimpleNamespace(capabilities=lambda _actor: grants)
    app.state.crm_directory = object()
    app.state.crm_resources = store
    with TestClient(app, headers=signed_caller(actor)) as client:
        response = client.get(
            "/api/crm/v1/contacts/",
            params={
                "page_size": "50",
                "page_index": "1",
                "ordering": "first_name",
            },
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 50
        assert response.json()["pageInfo"]["totalItems"] == TOTAL
        grants.clear()
        assert client.get("/api/crm/v1/contacts/", params={"page_size": "50"}).status_code == 403
    assert len(calls) == 1
