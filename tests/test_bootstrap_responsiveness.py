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
