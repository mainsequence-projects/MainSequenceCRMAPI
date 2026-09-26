"""Local security and governed-command checks for the optional Google module."""

from __future__ import annotations

import base64
import json
import threading
import uuid
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import src.crm.config as deployment_config
from api.crm.main import create_app
from src.crm.config import crm_config
from src.crm.google_workspace.imports import GoogleImports, ImportDecision
from src.crm.google_workspace.security import SCOPES, GoogleConfig, Sealer, _configured_url, digest
from src.crm.google_workspace.service import GoogleWorkspaceService
from src.crm.google_workspace.store import GoogleStore
from src.crm.repositories.errors import ResourceConflict, ResourceNotFound
from src.crm.repositories.transfers.connections import SourceConnections


def config() -> GoogleConfig:
    return GoogleConfig(
        client_id="client.apps.googleusercontent.com",
        client_secret="test-secret",
        redirect_uri="https://crm.example.test/extensions/google/oauth/callback/",
        token_key=b"k" * 32,
    )


def test_extension_routes_follow_persisted_configuration(config_file):
    config_file(google_workspace=False)
    assert not any("/google/" in path for path in create_app().openapi()["paths"])
    config_file(google_workspace=True)
    paths = create_app().openapi()["paths"]
    assert "/extensions/google/oauth/start/" in paths
    assert "/extensions/google/preview/" in paths
    assert "/extensions/google/imports/" in paths
    assert "/api/crm/v1/google/oauth/callback/" not in paths
    deployment_config.CONFIG_PATH.write_text("extensions:\n  google_workspace:\n    active: yes\n", encoding="utf-8")
    crm_config.cache_clear()
    with pytest.raises(RuntimeError, match="config/crm.yaml"):
        create_app()


def test_pkce_url_and_actor_bound_encryption():
    actor, other, attempt = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    url = urlsplit(config().authorization_url("contacts", "state", "verifier", "nonce", prompt=True))
    query = parse_qs(url.query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert SCOPES["contacts"][0] in query["scope"][0]
    assert "test-secret" not in url.geturl()
    sealed = Sealer(config().token_key).seal("refresh-token", purpose="refresh", uid=attempt, actor_uid=actor)
    assert "refresh-token" not in sealed
    assert Sealer(config().token_key).open(sealed, purpose="refresh", uid=attempt, actor_uid=actor) == "refresh-token"
    with pytest.raises(Exception):
        Sealer(config().token_key).open(sealed, purpose="refresh", uid=attempt, actor_uid=other)


def test_google_redirect_uri_uses_extension_route(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://crm.example.test/extensions/google/oauth/callback/")
    assert _configured_url("GOOGLE_OAUTH_REDIRECT_URI", callback=True).endswith("/extensions/google/oauth/callback/")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://crm.example.test/api/crm/v1/google/oauth/callback/")
    with pytest.raises(RuntimeError, match="exact Google callback route"):
        _configured_url("GOOGLE_OAUTH_REDIRECT_URI", callback=True)


def test_google_config_reads_credentials_from_platform_secrets(monkeypatch):
    values = {
        "CRM_GOOGLE_OAUTH_CLIENT_ID": "platform-client.apps.googleusercontent.com",
        "CRM_GOOGLE_OAUTH_CLIENT_SECRET": "platform-secret",
        "CRM_GOOGLE_TOKEN_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
    }
    requested = []
    concurrent_reads = threading.Barrier(3, timeout=2)

    def get_secret(*, name):
        requested.append(name)
        concurrent_reads.wait()
        return SimpleNamespace(value=SecretStr(values[name]))

    monkeypatch.setattr("src.crm.google_workspace.security.Secret.get", get_secret)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "ignored-env-client")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://127.0.0.1:38641/extensions/google/oauth/callback/")

    loaded = GoogleConfig.load()
    assert loaded.client_id == values["CRM_GOOGLE_OAUTH_CLIENT_ID"]
    assert loaded.client_secret == values["CRM_GOOGLE_OAUTH_CLIENT_SECRET"]
    assert len(loaded.token_key) == 32
    assert set(requested) == set(values)

    values["CRM_GOOGLE_OAUTH_CLIENT_ID"] = "PASTE_GOOGLE_OAUTH_CLIENT_ID"
    with pytest.raises(RuntimeError, match="not configured"):
        GoogleConfig.load()


class MemoryStore:
    def __init__(self):
        self.attempt = None
        self.connection_row = None

    def connection(self, actor_uid):
        return self.connection_row if self.connection_row and self.connection_row["actor_uid"] == actor_uid else None

    def start(self, **values):
        self.attempt = {**values, "status": "started"}

    def claim(self, state_hash):
        if not self.attempt or self.attempt["state_hash"] != state_hash or self.attempt["status"] != "started":
            raise ResourceConflict("reused")
        self.attempt["status"] = "redeeming"
        return self.attempt

    def exchanged(self, uid, completion_hash, pending_ciphertext):
        assert self.attempt["uid"] == uid
        self.attempt.update(status="exchanged", completion_hash=completion_hash, pending_ciphertext=pending_ciphertext)

    def fail(self, uid):
        assert self.attempt["uid"] == uid
        self.attempt.update(status="failed", verifier_ciphertext="", pending_ciphertext=None)

    def attempt_status(self, actor_uid, uid):
        if not self.attempt or self.attempt["actor_uid"] != actor_uid or self.attempt["uid"] != uid:
            return None
        return self.attempt

    def pending(self, actor_uid, completion_hash):
        if self.attempt["actor_uid"] != actor_uid or self.attempt["completion_hash"] != completion_hash or self.attempt["status"] != "exchanged":
            raise ResourceConflict("wrong actor or used")
        return self.attempt

    def activate(self, **values):
        self.attempt["status"] = "completed"
        self.attempt["pending_ciphertext"] = None
        self.connection_row = {
            "uid": values["connection_uid"], "actor_uid": values["actor_uid"],
            "source_connection_uid": uuid.uuid4(), "google_sub": values["google_sub"],
            "display_email": values["email"], "granted_scopes": values["scopes"],
            "refresh_ciphertext": values["refresh_ciphertext"],
            "status": "connected", "version": 1,
        }
        return self.connection_row

    def disconnect(self, actor_uid, uid):
        assert actor_uid == self.connection_row["actor_uid"] and uid == self.connection_row["uid"]
        ciphertext = self.connection_row["refresh_ciphertext"]
        self.connection_row.update(status="disconnected", refresh_ciphertext=None, granted_scopes=[])
        return ciphertext


def test_oauth_state_replay_completion_actor_and_no_url_secret(monkeypatch):
    store = MemoryStore()
    seen = []

    def transport(request):
        seen.append(request)
        if request.url.path == "/token":
            return httpx.Response(200, json={
                "id_token": "signed-id-token", "refresh_token": "private-refresh",
                "access_token": "short-access", "scope": SCOPES["contacts"][0],
                "token_type": "Bearer",
            })
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    service = GoogleWorkspaceService(store=store, config=config(), http=client)
    monkeypatch.setattr(
        "src.crm.google_workspace.service.verify_google_id_token",
        lambda token, audience, nonce: {"sub": "stable-sub", "email": "owner@example.com", "nonce": nonce},
    )
    actor, other = uuid.uuid4(), uuid.uuid4()
    started = service.start(actor, "contacts")
    state = parse_qs(urlsplit(started["authorization_url"]).query)["state"][0]
    assert store.attempt["state_hash"] == digest(state)
    assert state not in store.attempt["verifier_ciphertext"]
    redirect = service.callback(code="one-time-code", state=state, error=None)
    assert redirect.endswith("/google/oauth/done/?google_status=ready")
    assert "private-refresh" not in redirect and "short-access" not in redirect
    assert service.callback(code="one-time-code", state=state, error=None).endswith("google_status=invalid_state")
    assert len(seen) == 1
    with pytest.raises(ResourceNotFound):
        service.attempt_status(other, uuid.UUID(started["attempt_uid"]))
    handle = service.attempt_status(actor, uuid.UUID(started["attempt_uid"]))["completion_handle"]
    with pytest.raises(ResourceConflict):
        service.complete(other, handle)
    summary = service.complete(actor, handle)
    assert summary["granted_sources"] == ["contacts"]
    assert "refresh" not in json.dumps(summary)
    with pytest.raises(ResourceConflict):
        service.complete(actor, handle)
    result = service.disconnect(actor, uuid.UUID(summary["uid"]))
    assert result == {"status": "disconnected", "google_revoked": True}
    assert store.connection_row["refresh_ciphertext"] is None


def test_callback_route_does_not_require_crm_identity():
    app = create_app()
    app.state.crm_google_service = GoogleWorkspaceService(store=MemoryStore(), config=config())
    response = TestClient(app).get("/extensions/google/oauth/callback/?state=unknown&code=no", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("google_status=invalid_state")
    assert TestClient(app).get("/extensions/google/oauth/done/").status_code == 200
    assert TestClient(app).get("/extensions/google/connections/").status_code == 401


def test_denied_google_consent_finishes_attempt_without_exchanging_code():
    store = MemoryStore()
    service = GoogleWorkspaceService(store=store, config=config())
    actor = uuid.uuid4()
    started = service.start(actor, "contacts")
    state = parse_qs(urlsplit(started["authorization_url"]).query)["state"][0]
    assert service.callback(code=None, state=state, error="access_denied").endswith("google_status=denied")
    assert service.attempt_status(actor, uuid.UUID(started["attempt_uid"])) == {"status": "failed"}
    assert store.attempt["verifier_ciphertext"] == ""


def test_connection_summary_is_available_before_google_operator_setup(monkeypatch):
    actor = uuid.uuid4()
    store = MemoryStore()
    store.connection_row = {
        "uid": uuid.uuid4(), "actor_uid": actor, "display_email": "owner@example.com",
        "granted_scopes": [SCOPES["contacts"][0]], "status": "connected", "version": 1,
    }
    monkeypatch.setattr("src.crm.google_workspace.service.GoogleStore", lambda: store)
    summary = GoogleWorkspaceService.connection_without_google_config(actor)
    assert summary["granted_sources"] == ["contacts"]
    assert GoogleWorkspaceService.connection_without_google_config(uuid.uuid4()) is None


def test_gmail_parser_reads_only_selected_headers_and_excludes_own_address():
    seen = []

    def transport(request):
        seen.append(request)
        return httpx.Response(200, json={"payload": {"headers": [
            {"name": "From", "value": 'Alice <alice@example.com>'},
            {"name": "To", "value": 'Owner <owner@example.com>'},
            {"name": "Subject", "value": "Private subject"},
        ]}})

    oauth = GoogleWorkspaceService(store=MemoryStore(), config=config(), http=httpx.Client(transport=httpx.MockTransport(transport)))
    candidates = GoogleImports(oauth)._gmail("access", {"messages": [{"id": "m1"}]}, "owner@example.com")
    assert len(candidates) == 1
    assert candidates[0]["email"] == "alice@example.com"
    assert "Private subject" not in json.dumps(candidates)
    assert all(request.url.path.endswith("/messages/m1") for request in seen)
    assert "format=metadata" in str(seen[0].url)


class CapturingStore(GoogleStore):
    def __init__(self):
        self.calls = []

    def _operation(self, **kwargs):
        self.calls.append(kwargs)
        return {"rows": [{"entity_uid": kwargs["parameters"].get("uid")}]}


def test_google_preview_uses_bounded_batch_reads():
    class PreviewStore(GoogleStore):
        def __init__(self):
            self.calls = []

        def _operation(self, **kwargs):
            self.calls.append(kwargs)
            return {"rows": []}

    store = PreviewStore()
    source_uid = uuid.uuid4()
    assert store.source_links(source_uid, "contact", ["people:1", "people:2"]) == {}
    assert store.contact_matches_many(["one@example.com", "two@example.com"]) == {}
    assert len(store.calls) == 2
    assert store.calls[0]["tables"] == {"source_identity": "read", "contact": "read"}
    assert json.loads(store.calls[0]["parameters"]["external_ids"]) == ["people:1", "people:2"]
    assert store.calls[1]["tables"] == {"contact": "read"}
    assert store.calls[1]["max_rows"] == 8


def test_reviewed_contact_fields_are_used_in_governed_import():
    actor, connection_uid, source_uid, target_uid = (uuid.uuid4() for _ in range(4))
    captured = {}

    class Store:
        def connection(self, actor_uid):
            assert actor_uid == actor
            return {
                "uid": connection_uid, "source_connection_uid": source_uid,
                "status": "connected", "granted_scopes": [SCOPES["contacts"][0]],
                "google_sub": "google-user",
            }

        def source_link(self, *_):
            return None

        def import_candidate(self, **kwargs):
            captured.update(kwargs)
            return target_uid

    candidate = {
        "external_id": "people:people/123", "source": "contacts",
        "first_name": "Source", "last_name": "Name",
        "email": "source@example.com", "emails": ["source@example.com"], "phones": [],
    }
    sealed = {
        "expires_at": 4102444800, "source": "contacts", "google_sub": "google-user",
        "candidate": candidate,
    }
    oauth = SimpleNamespace(store=Store(), sealer=SimpleNamespace(open=lambda *_args, **_kwargs: sealed))
    decision = ImportDecision.model_validate({
        "preview_token": "p" * 32, "action": "create",
        "contact_fields": {
            "first_name": "Reviewed", "last_name": "Person", "title": "Director",
            "emails": [{"email": "reviewed@example.com", "type": "other"}],
            "phones": [{"number": "+43 123", "type": "other"}],
        },
    })
    result = GoogleImports(oauth).commit(actor, decision)
    assert result["target_uid"] == str(target_uid)
    assert captured["values"]["first_name"] == "Reviewed"
    assert captured["values"]["emails"] == [{"email": "reviewed@example.com", "type": "other"}]
    assert captured["values"]["owner_uid"] is None


def test_import_is_one_governed_record_provenance_and_activity_write():
    store = CapturingStore()
    actor = uuid.uuid4()
    store.import_candidate(
        actor_uid=actor, source_connection_uid=uuid.uuid4(), entity_type="contact",
        external_id="people:people/123", payload_hash="a" * 64,
        action="create", target_uid=None, expected_version=None,
        values={"first_name": "Ada", "last_name": "Lovelace", "emails": [{"email": "ada@example.com", "type": "other"}], "phones": []},
    )
    call = store.calls[0]
    assert call["operation"] == "insert"
    assert call["tables"]["contact"] == "write"
    assert call["tables"]["source_identity"] == "write"
    assert call["tables"]["activity_event"] == "write"
    assert call["tables"]["google_oauth_connection"] == "read"
    assert "WITH gate AS" in call["sql"] and "linked AS" in call["sql"]
    assert "private-refresh" not in json.dumps(call["parameters"])


def test_google_provenance_is_hidden_from_file_import_source_picker():
    class Capture(SourceConnections):
        def _operation(self, **kwargs):
            assert "adapter_id <> 'google-workspace-v1'" in kwargs["sql"]
            return {"rows": [{"items": [], "total_items": 0}]}

    assert Capture().source_connections(0, 20)["items"] == []
