"""Lead read labels remain derived, governed and separate from write payloads."""

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.crm.main import create_app
from src.crm.repositories.records import VersionedRecordStore
from src.crm.solution_selling.models import LeadChanges, LeadCreate, SolutionSellingLead


def lead(company=True):
    return {
        "uid": str(uuid.uuid4()), "contact_uid": str(uuid.uuid4()), "version": 3,
        "created_at": "2026-10-13T10:00:00Z", "updated_at": "2026-10-13T11:00:00Z",
        "created_by_uid": None, "updated_by_uid": None, "archived_at": None,
        "status": "contacted", "contact_display_name": "Maria Silva",
        "company_uid": str(uuid.uuid4()) if company else None,
        "company_name": "Example Capital" if company else None,
    }


class ReadStore(VersionedRecordStore):
    def __init__(self, records):
        self.records = records
        self.calls = []

    def _operation(self, **kwargs):
        self.calls.append(kwargs)
        if "uid" in kwargs["parameters"]:
            return {"rows": [{"item": self.records[0]}]}
        return {"rows": [{"items": self.records, "total_items": 7}]}


def test_display_fields_are_read_only_not_a_second_person_or_company_record():
    record = lead()
    assert SolutionSellingLead.model_validate(record).company_name == "Example Capital"
    for field in ("contact_display_name", "company_uid", "company_name"):
        with pytest.raises(ValidationError):
            LeadCreate(contact_uid=record["contact_uid"], status="contacted", **{field: record[field]})
        with pytest.raises(ValidationError):
            LeadChanges(**{field: record[field]})


def test_collection_enriches_only_page_in_one_governed_read_and_keeps_companyless_leads():
    records = [lead(), lead(company=False)]
    store = ReadStore(records)
    result = store.collection("leads", page_index=1, page_size=2, search="outreach", filters={"status": "contacted"})
    assert len(store.calls) == 1
    call = store.calls[0]
    assert call["operation"] == "select" and call["max_rows"] == 1
    assert call["parameters"] == {"limit": 2, "offset": 2, "f_status": "contacted", "search": "%outreach%"}
    assert 'FROM paged t LEFT JOIN "mainsequence_crm__contact" c ON c.uid=t.contact_uid' in call["sql"]
    assert 'LEFT JOIN "mainsequence_crm__company" company ON company.uid=c.company_uid' in call["sql"]
    assert "(SELECT count(*) FROM q) AS total_items" in call["sql"]
    assert result["items"][0]["uid"] == records[0]["uid"]
    assert result["items"][0]["contact_display_name"] == "Maria Silva"
    assert result["items"][1]["company_name"] is None
    assert result["pageInfo"] == {"pageIndex": 1, "pageSize": 2, "totalItems": 7, "hasNextPage": True, "hasPreviousPage": True}


def test_http_list_and_detail_return_same_labels_and_recheck_read_permission(signed_caller):
    actor = uuid.uuid4()
    capabilities = {"crm.read"}
    record = lead()
    store = ReadStore([record])

    class Policy:
        def capabilities(self, uid):
            assert uid == actor
            return capabilities

    app = create_app()
    app.state.crm_record_store = store
    app.state.crm_policy = Policy()
    app.state.crm_directory = object()
    client = TestClient(app, headers=signed_caller(actor))
    base = "/extensions/solution-selling/leads/"
    listing = client.get(base)
    detail = client.get(base + record["uid"] + "/")
    assert listing.status_code == detail.status_code == 200
    assert listing.json()["items"][0] == detail.json()
    assert detail.json()["company_name"] == "Example Capital"
    assert "WHERE t.uid=%(uid)s::uuid AND t.archived_at IS NULL" in store.calls[1]["sql"]
    assert "LEFT JOIN" in store.calls[1]["sql"]
    capabilities.clear()
    assert client.get(base).status_code == client.get(base + record["uid"] + "/").status_code == 403
    assert len(store.calls) == 2
