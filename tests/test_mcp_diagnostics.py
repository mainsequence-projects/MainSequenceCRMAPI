"""Correlated MCP stages locate stalls without logging business data or secrets."""

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_application import _settings_row
from test_catalog import catalog_rows
from test_mcp_tools import Policy, app_for, call, delegated

from mainsequence.client.exceptions import ApiError
from metatables.compiled_sql.v1 import compile_sqlalchemy_statement
from src.crm.platform.catalog import CatalogRegistry
from src.crm.platform.diagnostics import observe_stage, observe_tool, request_diagnostics
from src.crm.repositories.resources.store import GovernedResourceStore
from src.crm.services.application import BootstrapService, CatalogSettingsStore

SECRET = "private-contact-token-and-sql-parameter"
UPSTREAM_REQUEST = "77777777-7777-4777-8777-777777777777"
STAGES = ["identity", "permissions", "catalog", "metatables"]


def records(caplog, event):
    return [record for record in caplog.records if getattr(record, "event", None) == event]


@pytest.fixture
def governed_app(monkeypatch, caplog, signed_caller):
    caplog.set_level(logging.INFO, logger="src.crm.platform.diagnostics")
    counts = {"catalog": 0, "permissions": 0, "metatables": 0}

    class CountingPolicy(Policy):
        def capabilities(self, actor_uid):
            counts["permissions"] += 1
            return super().capabilities(actor_uid)

    def discover(**filters):
        counts["catalog"] += 1
        return catalog_rows()

    def execute(operation):
        counts["metatables"] += 1
        assert operation["operation"] == "select"
        assert operation["limits"] == {"max_rows": 1, "statement_timeout_ms": 15000}
        return {"rows": [{"items": [], "total_items": 0}]}

    monkeypatch.setattr("src.crm.platform.catalog.MetaTable.filter", discover)
    monkeypatch.setattr("src.crm.repositories.gateway.MetaTable.execute_operation", execute)
    app = app_for(CountingPolicy("crm.read"), GovernedResourceStore(CatalogRegistry()))
    return app, counts


def test_protocol_success_stage_order_cache_and_redaction(governed_app, signed_caller, caplog):
    app, counts = governed_app
    with TestClient(app, headers=delegated(signed_caller)) as client:
        results = [call(client, "crm_contacts_list", {"search": SECRET}) for _ in range(2)]
    assert all(result["isError"] is False for result in results)
    assert all(set(result["structuredContent"]) == {"code", "data"} for result in results)
    assert counts == {"catalog": 1, "permissions": 2, "metatables": 2}
    starts = records(caplog, "crm.mcp.stage.started")
    assert [r.crm_stage for r in starts] == STAGES * 2
    assert [r.crm_cache_hit for r in starts if r.crm_stage == "catalog"] == [False, True]
    completed = records(caplog, "crm.mcp.tool.completed")
    assert len(completed) == 2
    assert completed[0].crm_request_uid != completed[1].crm_request_uid
    for record in completed:
        assert record.crm_result_code == "ok"
        assert set(record.crm_stage_timings_ms) == set(STAGES)
        assert all(duration >= 0 for duration in record.crm_stage_timings_ms.values())
        assert record.duration_ms >= max(record.crm_stage_timings_ms.values())
        assert record.crm_exceptions == []
    assert SECRET not in json.dumps([r.__dict__ for r in caplog.records], default=str)


def test_settings_read_includes_its_second_permission_check_and_governed_stages(
    governed_app,
    signed_caller,
    caplog,
    monkeypatch,
):
    app, counts = governed_app
    app.state.crm_bootstrap = BootstrapService(
        policy=app.state.crm_policy,
        directory=app.state.crm_directory,
        store=CatalogSettingsStore(app.state.crm_resources.reads.registry),
    )
    monkeypatch.setattr(
        "src.crm.services.application.compile_sqlalchemy_statement",
        lambda statement, **kwargs: compile_sqlalchemy_statement(
            statement, dialect="postgresql", **kwargs
        ),
    )
    monkeypatch.setattr(
        "src.crm.services.application.MetaTable.execute_operation",
        lambda operation: {"rows": [_settings_row()]},
    )
    with TestClient(app, headers=delegated(signed_caller)) as client:
        result = call(client, "crm_settings_get")
    assert result["structuredContent"]["code"] == "ok"
    assert counts["permissions"] == 2 and counts["catalog"] == 1
    assert [r.crm_stage for r in records(caplog, "crm.mcp.stage.started")] == [
        "identity",
        "permissions",
        "permissions",
        "catalog",
        "metatables",
    ]
    (completed,) = records(caplog, "crm.mcp.tool.completed")
    assert set(completed.crm_stage_timings_ms) == set(STAGES)


def upstream_failure(*args, **kwargs):
    try:
        raise ValueError(SECRET)
    except ValueError as exc:
        raise ApiError(
            SECRET,
            payload={"sql": SECRET},
            response=SimpleNamespace(
                status_code=503,
                url=f"https://example.invalid/{SECRET}",
                headers={"X-Request-ID": UPSTREAM_REQUEST, "Authorization": SECRET},
            ),
        ) from exc


@pytest.mark.parametrize(
    "stage,code",
    [
        ("identity", "unavailable"),
        ("permissions", "unavailable"),
        ("catalog", "internal_error"),
        ("metatables", "internal_error"),
    ],
)
def test_protocol_failure_locates_stage_and_logs_safe_chain(
    governed_app,
    signed_caller,
    caplog,
    monkeypatch,
    stage,
    code,
):
    app, counts = governed_app
    if stage == "identity":

        def identity_failure(request):
            try:
                upstream_failure()
            except ApiError as exc:
                raise HTTPException(503, SECRET) from exc

        monkeypatch.setattr("api.crm.mcp_server.context_for", identity_failure)
    elif stage == "permissions":
        app.state.crm_policy.capabilities = upstream_failure
    elif stage == "catalog":
        monkeypatch.setattr("src.crm.platform.catalog.MetaTable.filter", upstream_failure)
    else:
        monkeypatch.setattr(
            "src.crm.repositories.gateway.MetaTable.execute_operation", upstream_failure
        )
    with TestClient(app, headers=delegated(signed_caller)) as client:
        result = call(client, "crm_contacts_list", {"search": SECRET})
    assert result["isError"] is True
    details = result["structuredContent"]
    assert details["code"] == code
    assert details["diagnostics"]["failed_stage"] == stage
    request_uid = details["diagnostics"]["request_uid"]
    assert str(uuid.UUID(request_uid)) == request_uid
    (completed,) = records(caplog, "crm.mcp.tool.completed")
    assert completed.crm_request_uid == request_uid
    assert completed.crm_failed_stage == stage
    assert completed.crm_result_code == code
    assert completed.levelno == logging.ERROR
    assert [r.crm_stage for r in records(caplog, "crm.mcp.stage.started")] == STAGES[
        : STAGES.index(stage) + 1
    ]
    stages = records(caplog, "crm.mcp.stage.completed")
    assert stages[-1].outcome == "failed"
    errors = completed.crm_exceptions
    (api_error,) = [e for e in errors if e["error_type"] == "ApiError"]
    assert api_error["upstream_status"] == 503
    assert api_error["upstream_request_id"] == UPSTREAM_REQUEST
    assert errors[-1]["error_type"] == "ValueError"
    assert all(set(frame) == {"file", "function", "line"} for e in errors for frame in e["frames"])
    assert any(frame["function"] == "upstream_failure" for frame in api_error["frames"])
    assert completed.exc_info is None and completed.stack_info is None
    assert SECRET not in json.dumps([r.__dict__ for r in caplog.records], default=str)
    assert SECRET not in json.dumps(result)
    assert counts["metatables"] == 0


def test_started_stage_visible_during_stall_and_context_isolated(caplog):
    caplog.set_level(logging.INFO, logger="src.crm.platform.diagnostics")
    barrier = threading.Barrier(3)
    release = threading.Event()
    uids = [str(uuid.uuid4()), str(uuid.uuid4())]

    def stalled(request_uid):
        with request_diagnostics(request_uid), observe_tool("crm_contacts_get") as observation:
            with observe_stage("metatables"):
                barrier.wait(timeout=5)
                assert release.wait(timeout=5)
            observation.code = "ok"
        # Reusing this worker must not inherit an ended request or tool.
        with observe_stage("permissions"):
            pass
        with observe_tool("crm_settings_get") as observation:
            assert observation.request_uid not in uids
            observation.code = "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(stalled, uid) for uid in uids]
        try:
            barrier.wait(timeout=5)
            started = records(caplog, "crm.mcp.stage.started")
            assert {r.crm_request_uid for r in started} == set(uids)
            assert not records(caplog, "crm.mcp.stage.completed")
        finally:
            release.set()
        for future in futures:
            future.result(timeout=5)
    ended = records(caplog, "crm.mcp.stage.completed")
    assert len(ended) == 2
    assert {r.crm_request_uid for r in ended} == set(uids)
    assert all(r.crm_stage == "metatables" for r in ended)


def test_exception_metadata_bounds_and_untrusted_correlation(caplog):
    caplog.set_level(logging.INFO, logger="src.crm.platform.diagnostics")
    with pytest.raises(ApiError), request_diagnostics(SECRET), observe_tool("crm_settings_get"):
        error = None
        for _ in range(8):
            new_error = ApiError(
                SECRET,
                response=SimpleNamespace(
                    status_code=503,
                    headers={"X-Request-ID": SECRET},
                ),
            )
            new_error.__cause__ = error
            error = new_error
        raise error
    (completed,) = records(caplog, "crm.mcp.tool.completed")
    assert len(completed.crm_exceptions) == 5
    assert all("upstream_request_id" not in e for e in completed.crm_exceptions)
    assert all(len(e["frames"]) <= 12 for e in completed.crm_exceptions)
    assert str(uuid.UUID(completed.crm_request_uid)) == completed.crm_request_uid
    assert completed.crm_request_uid != SECRET
    assert SECRET not in json.dumps([r.__dict__ for r in caplog.records], default=str)
