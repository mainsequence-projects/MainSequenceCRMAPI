"""Slow platform readiness must not block the API event loop."""

import asyncio
import time
import uuid
from threading import Event

from starlette.requests import Request

from api.crm.main import bootstrap


def test_bootstrap_readiness_runs_off_event_loop(monkeypatch):
    started = Event()
    release = Event()

    def slow_readiness(_request, _actor_uid):
        started.set()
        release.wait(timeout=2)
        return {"status": "not_ready", "checks": []}

    monkeypatch.setattr("api.crm.main.readiness", slow_readiness)
    request = Request({"type": "http", "method": "GET", "path": "/api/crm/v1/bootstrap/", "headers": []})

    async def exercise():
        task = asyncio.create_task(bootstrap(request, uuid.uuid4()))
        began = time.monotonic()
        await asyncio.to_thread(started.wait, 1)
        elapsed = time.monotonic() - began
        release.set()
        response = await task
        assert elapsed < 1.5
        assert response.status_code == 503

    asyncio.run(exercise())


def test_bootstrap_reports_the_readiness_stage_on_timeout(monkeypatch):
    release = Event()

    def slow_readiness(_request, _actor_uid):
        release.wait(1)
        return {"status": "ready", "checks": []}

    monkeypatch.setattr("api.crm.main.readiness", slow_readiness)
    monkeypatch.setattr("api.crm.main.BOOTSTRAP_STAGE_TIMEOUT_SECONDS", 0.01)
    request = Request({"type": "http", "method": "GET", "path": "/api/crm/v1/bootstrap/", "headers": []})
    request.state.crm_request_uid = uuid.uuid4()
    try:
        response = asyncio.run(bootstrap(request, uuid.uuid4()))
        assert response.status_code == 503
        assert b"platform-readiness" in response.body
        assert b"did not respond" in response.body
    finally:
        release.set()
