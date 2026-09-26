"""HTTP and direct callers use the same authorized CRM command boundary."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.crm.main import create_app
from src.crm.contracts import DomainValidationError
from src.crm.models.queries import QueryScope
from src.crm.services.operations import (
    AccessDenied,
    CRMContext,
    CRMOperations,
    ServiceUnavailable,
)
from src.crm.services.transfers import TransferOperations

ACTOR = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CONTACT = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
TRANSFER = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


class Policy:
    def __init__(self, *capabilities: str):
        self.allowed = set(capabilities)

    def capabilities(self, actor_uid):
        assert actor_uid == ACTOR
        return self.allowed


class Directory:
    def is_selectable(self, _uid):
        return True

    def display_name(self, _uid):
        return "Test actor"


class ResourceStore:
    def __init__(self):
        self.record = None
        self.calls = []

    def create(self, resource, actor_uid, data):
        self.calls.append(("create", resource, actor_uid, data))
        self.record = {"uid": str(CONTACT), "version": 1, **data}
        return self.record

    def detail(self, resource, uid):
        self.calls.append(("detail", resource, uid))
        return self.record

    def update(self, resource, actor_uid, uid, expected_version, data):
        self.calls.append(("update", resource, actor_uid, uid, expected_version, data))
        self.record = {"uid": str(uid), "version": expected_version + 1, **data}
        return self.record

    def collection(self, resource, scope):
        self.calls.append(("collection", resource, scope))
        return {"items": [], "pageInfo": {}}


def client_for(policy, resources=None, transfers=None):
    app = create_app()
    app.state.crm_policy = policy
    app.state.crm_directory = Directory()
    if resources is not None:
        app.state.crm_resources = resources
    if transfers is not None:
        app.state.crm_transfers = transfers

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user_uid = ACTOR
        return await call_next(request)

    return TestClient(app)


def test_http_and_direct_contact_mutations_use_identical_normalized_commands():
    policy = Policy("crm.create", "crm.edit")
    direct_store, http_store = ResourceStore(), ResourceStore()
    service = CRMOperations(CRMContext(ACTOR, policy, Directory()), resources=direct_store)
    payload = {"first_name": "  Ada  ", "emails": []}
    direct = service.create_resource("contacts", payload)
    response = client_for(policy, resources=http_store).post("/api/crm/v1/contacts/", json=payload)
    assert response.status_code == 201
    assert direct == response.json()
    assert direct_store.calls[0] == http_store.calls[0]
    assert direct_store.calls[0][3]["first_name"] == "Ada"

    patch = {"expected_version": 1, "changes": {"first_name": "Grace"}}
    direct = service.update_resource("contacts", CONTACT, patch)
    response = client_for(policy, resources=http_store).patch(
        f"/api/crm/v1/contacts/{CONTACT}/", json=patch
    )
    assert response.status_code == 200
    assert direct == response.json()
    assert direct_store.calls[-1] == http_store.calls[-1]


def test_service_and_http_deny_before_reaching_repository():
    policy = Policy()
    store = ResourceStore()
    service = CRMOperations(CRMContext(ACTOR, policy, Directory()), resources=store)
    with pytest.raises(AccessDenied):
        service.create_resource("contacts", {"first_name": "Ada"})
    response = client_for(policy, resources=store).post(
        "/api/crm/v1/contacts/", json={"first_name": "Ada"}
    )
    assert response.status_code == 403
    assert (
        client_for(policy, resources=store).get("/api/crm/v1/contacts/?page_size=-1").status_code
        == 403
    )
    assert store.calls == []


def test_service_rejects_invalid_semantic_scope_without_http_parser():
    store = ResourceStore()
    service = CRMOperations(CRMContext(ACTOR, Policy("crm.read"), Directory()), resources=store)
    with pytest.raises(DomainValidationError):
        service.list_resources("contacts", QueryScope(filters={"has_open_tasks": 1}))
    assert store.calls == []


def test_transfer_action_rechecks_direction_capability_in_shared_service():
    class TransferStore:
        def __init__(self):
            self.cancelled = False

        def _job_row(self, uid, actor_uid):
            assert uid == TRANSFER and actor_uid == ACTOR
            return {"direction": "export"}

        def cancel(self, actor_uid, uid):
            self.cancelled = True
            return {"uid": str(uid)}

    policy = Policy("crm.read", "crm.transfer.import")
    store = TransferStore()
    service = TransferOperations(CRMContext(ACTOR, policy, Directory()), store)
    with pytest.raises(AccessDenied):
        service.transfer_action(TRANSFER, "cancel")
    response = client_for(policy, transfers=store).post(f"/api/crm/v1/transfers/{TRANSFER}/cancel/")
    assert response.status_code == 403
    assert store.cancelled is False


def test_disabled_methodology_cannot_be_called_through_service(config_file):
    config_file(solution_selling=False)

    class Records:
        def collection(self, *args, **kwargs):
            raise AssertionError("Disabled module reached persistence")

    service = CRMOperations(
        CRMContext(ACTOR, Policy("crm.read"), Directory()),
        resources=ResourceStore(),
        records=Records(),
    )
    with pytest.raises(ServiceUnavailable, match="disabled"):
        service.list_records("leads", page_index=0, page_size=25, search=None, filters={})


def test_direct_record_and_transfer_callers_cannot_bypass_request_models():
    class UntrustedPayload(BaseModel):
        arbitrary: str = "invalid"

    class Records:
        def create(self, *args):
            raise AssertionError("Invalid record reached persistence")

    class Transfers:
        def create_import(self, *args):
            raise AssertionError("Invalid import reached persistence")

    context = CRMContext(ACTOR, Policy("crm.create", "crm.transfer.import"), Directory())
    records = CRMOperations(context, resources=ResourceStore(), records=Records())
    transfers = TransferOperations(context, Transfers())
    with pytest.raises(DomainValidationError):
        records.create_record("interactions", UntrustedPayload())
    with pytest.raises(DomainValidationError):
        transfers.create_import(UntrustedPayload())
