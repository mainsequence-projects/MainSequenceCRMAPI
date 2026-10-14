"""Prompt API and real governed SQL, confined to a disposable local PostgreSQL.

Only MetaTables' network transport and policy/directory ports are substituted.
The submitted compiled statements run on PostgreSQL, not a fake record store.
"""

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from test_resource_collections import SOURCE
from test_resource_collections import collection_postgres as _pg_fixture

from api.crm.main import create_app
from metatables import MetaTableCompiledSQLOperation
from src.crm.metatables import MODELS
from src.crm.models.prompts import PromptCreate, PromptPatch
from src.crm.repositories.resources.store import GovernedResourceStore

collection_postgres = _pg_fixture

MARKDOWN = "# Instructions\n\nHello **world**, {{ contact.first_name }}.\n\n```python\nprint('{literal}')\n```\n"


@pytest.fixture
def prompts_db(collection_postgres):
    with collection_postgres.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def prompts_api(prompts_db, monkeypatch, signed_caller, config_file):
    def no_network(*args, **kwargs):
        pytest.fail("Prompt route tests must never make platform or external HTTP requests")

    monkeypatch.setattr("requests.sessions.Session.request", no_network)
    config_file(solution_selling=False, google_workspace=False)
    calls = []

    def execute(payload):
        MetaTableCompiledSQLOperation.model_validate(payload)
        assert payload["data_source_uid"] == SOURCE
        calls.append(payload)
        rows = (
            prompts_db.exec_driver_sql(
                payload["statement"]["sql"], payload["statement"]["parameters"]
            )
            .mappings()
            .all()
        )
        return {"rows": [dict(row) for row in rows]}

    monkeypatch.setattr("src.crm.repositories.gateway.MetaTable.execute_operation", execute)
    actor = uuid.uuid4()
    grants = {"crm.read", "crm.create", "crm.edit", "crm.archive"}

    class Policy:
        def capabilities(self, user_uid):
            assert user_uid == actor
            return set(grants)

    store = GovernedResourceStore(SimpleNamespace(data_source_uid=SOURCE))
    app = create_app()
    app.state.crm_policy = Policy()
    app.state.crm_directory = object()
    app.state.crm_resources = store
    with TestClient(app, headers=signed_caller(actor)) as client:
        yield client, grants, calls, store, actor


def create(client, *, name="Local-only prompt", markdown=MARKDOWN):
    response = client.post(
        "/api/crm/v1/prompts/", json={"name": name, "content_markdown": markdown}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_fixed_markdown_crud_archive_and_metadata_only_collections(prompts_api, prompts_db):
    client, _grants, calls, _store, actor = prompts_api
    first = create(client)
    assert first["version"] == 1 and first["created_by_uid"] == str(actor)
    assert first["content_markdown"] == MARKDOWN
    path = f"/api/crm/v1/prompts/{first['uid']}/"
    assert client.get(path).json() == first
    discovery = client.get("/api/crm/v1/prompts/discovery/").json()
    assert discovery["contract"] == "command-center.resource_discovery@v1"
    assert discovery["resource"]["id"] == "prompts"
    listing = client.get("/api/crm/v1/prompts/", params={"page_size": 50}).json()
    assert listing["pageInfo"]["totalItems"] == 1
    assert "content_markdown" not in listing["items"][0]
    assert "content_markdown" not in calls[-1]["statement"]["sql"]
    changed = client.patch(
        path,
        json={
            "expected_version": 1,
            "changes": {
                "description": "Fixed content only",
                "content_markdown": MARKDOWN + "\nTail\n",
            },
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert (
        client.patch(path, json={"expected_version": 1, "changes": {"name": "Stale"}}).status_code
        == 409
    )
    assert client.get(path).json()["content_markdown"].endswith("\nTail\n")
    audit = prompts_db.exec_driver_sql(
        "SELECT changes FROM mainsequence_crm__activity_event WHERE entity_uid=%s::uuid AND kind='updated'",
        (first["uid"],),
    ).scalar_one()
    assert audit == {"description": "Fixed content only", "content_markdown_changed": True}
    assert client.post(path + "archive/", json={"expected_version": 2}).status_code == 200
    assert client.get("/api/crm/v1/prompts/").json()["items"] == []
    archived = client.get("/api/crm/v1/prompts/", params={"filters": '{"archived":true}'}).json()
    assert archived["items"][0]["uid"] == first["uid"]
    assert (
        client.patch(
            path, json={"expected_version": 3, "changes": {"name": "Archived edit"}}
        ).status_code
        == 409
    )
    assert client.post(path + "restore/", json={"expected_version": 3}).json()["version"] == 4
    assert client.get(path).json()["content_markdown"] == MARKDOWN + "\nTail\n"


def test_permission_revocation_is_checked_for_every_operation(prompts_api):
    client, grants, calls, _store, _actor = prompts_api
    item = create(client)
    path = f"/api/crm/v1/prompts/{item['uid']}/"
    grants.clear()
    before = len(calls)
    requests = [
        ("get", "/api/crm/v1/prompts/", None),
        ("get", "/api/crm/v1/prompts/discovery/", None),
        ("get", path, None),
        ("post", "/api/crm/v1/prompts/", {"name": "Denied", "content_markdown": MARKDOWN}),
        ("patch", path, {"expected_version": 1, "changes": {"name": "Denied"}}),
        ("post", path + "archive/", {"expected_version": 1}),
        ("post", path + "restore/", {"expected_version": 1}),
    ]
    for method, url, body in requests:
        assert client.request(method, url, json=body).status_code == 403
    assert len(calls) == before


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "content_markdown": "x"},
        {"name": "Valid", "content_markdown": " \n\t"},
        {"name": "Valid", "content_markdown": "😀" * 16385},
        {"name": "Valid", "content_markdown": "nul\x00"},
        {"name": "Valid", "content_markdown": "x", "description": "nul\x00"},
        {"name": "Valid", "content_markdown": "x", "created_by_uid": str(uuid.uuid4())},
        {"name": "Valid", "content_markdown": "x", "variables": {}},
    ],
)
def test_invalid_prompt_payload_is_rejected_before_sql(prompts_api, payload):
    client, _grants, calls, _store, _actor = prompts_api
    before = len(calls)
    assert client.post("/api/crm/v1/prompts/", json=payload).status_code == 422
    assert len(calls) == before


def test_strict_patch_and_utf8_boundary():
    assert PromptCreate(name="Name", content_markdown="😀" * 16384).content_markdown == "😀" * 16384
    for payload in [
        {"expected_version": True, "changes": {"name": "Valid"}},
        {"expected_version": 1, "changes": {}},
        {"expected_version": 1, "changes": {"content_markdown": None}},
        {"expected_version": 1, "changes": {"name": None}},
    ]:
        with pytest.raises(ValidationError):
            PromptPatch.model_validate(payload)


def test_atomic_audit_failure_rolls_back_prompt_update(prompts_api, prompts_db):
    client, _grants, _calls, store, actor = prompts_api
    item = create(client)
    prompts_db.exec_driver_sql(
        "ALTER TABLE mainsequence_crm__activity_event ADD CONSTRAINT test_prompt_audit CHECK (kind <> 'updated')"
    )
    with pytest.raises(sa.exc.IntegrityError), prompts_db.begin_nested():
        store.update("prompts", actor, uuid.UUID(item["uid"]), 1, {"name": "Must roll back"})
    assert store.detail("prompts", uuid.UUID(item["uid"])) == item


def test_postgres_reader_cannot_write_and_failed_write_keeps_state(prompts_api, prompts_db):
    client, _grants, _calls, store, actor = prompts_api
    item = create(client)
    role = "prompt_reader_" + uuid.uuid4().hex
    prompts_db.exec_driver_sql(f'CREATE ROLE "{role}"')
    prompts_db.exec_driver_sql(f'GRANT SELECT ON mainsequence_crm__prompt TO "{role}"')
    with prompts_db.begin_nested() as savepoint:
        prompts_db.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
        assert store.detail("prompts", uuid.UUID(item["uid"])) == item
        with pytest.raises(sa.exc.ProgrammingError):
            store.update("prompts", actor, uuid.UUID(item["uid"]), 1, {"name": "Denied"})
        savepoint.rollback()
    assert store.detail("prompts", uuid.UUID(item["uid"])) == item


def test_prompt_pagination_search_and_published_sdk_schemas(prompts_api, prompts_db):
    client, _grants, _calls, _store, actor = prompts_api
    from test_resource_collections import NOW

    prompts_db.execute(
        MODELS["prompt"].__table__.insert(),
        [
            {
                "uid": uuid.UUID(int=100000 + number),
                "name": f"Prompt {number:03}",
                "description": "searchable metadata",
                "content_markdown": "Large hidden body. " * 2000,
                "version": 1,
                "created_at": NOW,
                "updated_at": NOW,
                "created_by_uid": actor,
                "updated_by_uid": actor,
            }
            for number in range(71)
        ],
    )
    pages = [
        client.get(
            "/api/crm/v1/prompts/",
            params={"page_index": index, "page_size": 50, "ordering": "name"},
        ).json()
        for index in (0, 1)
    ]
    assert [len(page["items"]) for page in pages] == [50, 21]
    assert pages[0]["pageInfo"]["totalItems"] == 71
    assert pages[0]["pageInfo"]["hasNextPage"] is True
    assert pages[1]["pageInfo"]["hasNextPage"] is False
    assert len({item["uid"] for page in pages for item in page["items"]}) == 71
    assert all("content_markdown" not in item for page in pages for item in page["items"])
    assert len(json.dumps(pages[0])) < 30000
    assert (
        client.get("/api/crm/v1/prompts/", params={"search": "hidden body"}).json()["items"] == []
    )
    assert (
        client.get("/api/crm/v1/prompts/", params={"search": "Prompt 070"}).json()["pageInfo"][
            "totalItems"
        ]
        == 1
    )
    for query in (
        {"page_size": 101},
        {"ordering": "content_markdown"},
        {"filters": '{"unknown":true}'},
    ):
        assert client.get("/api/crm/v1/prompts/", params=query).status_code == 422

    static = (
        Path(__file__).resolve().parents[2]
        / "main-sequence-crm-5f1b0619-9997-449c-b986-36990ae49e14"
    )
    root = static / "node_modules/@dev-mainsequence/command-center-sdk/contracts"
    manifest = json.loads((root / "manifest.json").read_text())
    schemas = [json.loads((root / item["file"]).read_text()) for item in manifest["schemas"]]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    tested = set()
    for item, schema in zip(manifest["schemas"], schemas):
        contract = item["contract"]
        if contract not in {
            "command-center.resource_collection@v1",
            "command-center.resource_discovery@v1",
        }:
            continue
        validator = Draft202012Validator(schema, registry=registry)
        for file in item["fixtures"]["valid"]:
            validator.validate(json.loads((root / file).read_text()))
        for file in item["fixtures"]["invalid"]:
            assert list(validator.iter_errors(json.loads((root / file).read_text())))
        actual = (
            pages[0]
            if "resource_collection" in contract
            else client.get("/api/crm/v1/prompts/discovery/").json()
        )
        validator.validate(actual)
        tested.add(contract)
    assert len(tested) == 2
