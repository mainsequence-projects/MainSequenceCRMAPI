"""Request-scoped MCP timings and exception metadata without business payloads."""

from __future__ import annotations

import contextvars
import json
import logging
import traceback
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter

from mainsequence.client.exceptions import ApiError

logger = logging.getLogger(__name__)
_request_uid: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "crm_diagnostic_request_uid", default=None
)
_active: contextvars.ContextVar[ToolObservation | None] = contextvars.ContextVar(
    "crm_tool_observation", default=None
)


def _uuid(value: object) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


@dataclass
class ToolObservation:
    tool: str
    request_uid: str
    code: str = "interrupted"
    failed_stage: str | None = None
    timings: dict[str, float] = field(default_factory=dict)
    exception: list[dict] = field(default_factory=list)

    def fields(self) -> dict:
        return {"crm_mcp_tool": self.tool, "crm_request_uid": self.request_uid}

    def public_details(self) -> dict:
        details = {"request_uid": self.request_uid}
        if self.failed_stage:
            details["failed_stage"] = self.failed_stage
        return details


@contextmanager
def request_diagnostics(request_uid: object) -> Iterator[None]:
    token = _request_uid.set(_uuid(request_uid) or str(uuid.uuid4()))
    try:
        yield
    finally:
        _request_uid.reset(token)


def record_exception(error: BaseException) -> None:
    """Keep stack locations/types, never exception text, source lines or locals.

    SDK ApiError messages can contain URLs, credentials, SQL and response bodies.
    Even chained exception messages and normal logger.exception() are unsafe here.
    """
    observation = _active.get()
    if observation is None:
        return
    chain, seen = [], set()
    while error is not None and id(error) not in seen and len(chain) < 5:
        seen.add(id(error))
        item = {
            "error_type": type(error).__name__,
            "frames": [
                {
                    "file": frame.filename.rsplit("/", 1)[-1],
                    "function": frame.name,
                    "line": frame.lineno,
                }
                for frame in traceback.extract_tb(error.__traceback__, limit=-12)
            ],
        }
        if isinstance(error, ApiError):
            if type(error.status_code) is int and 100 <= error.status_code <= 599:
                item["upstream_status"] = error.status_code
            headers = error.headers or {}
            # Correlation is accepted only as a UUID, never arbitrary header text.
            request_uid = _uuid(headers.get("X-Request-ID") or headers.get("x-request-id"))
            if request_uid:
                item["upstream_request_id"] = request_uid
        chain.append(item)
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    observation.exception = chain


@contextmanager
def observe_tool(name: str) -> Iterator[ToolObservation]:
    observation = ToolObservation(name, _request_uid.get() or str(uuid.uuid4()))
    token = _active.set(observation)
    started = perf_counter()
    logger.info(
        "crm_mcp_tool_started tool=%s request_uid=%s",
        name,
        observation.request_uid,
        extra={"event": "crm.mcp.tool.started", **observation.fields()},
    )
    try:
        yield observation
    except BaseException as exc:
        record_exception(exc)
        raise
    finally:
        elapsed = round((perf_counter() - started) * 1000, 3)
        level = logging.ERROR if observation.exception else logging.INFO
        fields = {
            "event": "crm.mcp.tool.completed",
            **observation.fields(),
            "crm_result_code": observation.code,
            "crm_failed_stage": observation.failed_stage,
            "duration_ms": elapsed,
            "crm_stage_timings_ms": observation.timings,
            "crm_exceptions": observation.exception,
        }
        try:
            logger.log(
                level,
                "crm_mcp_tool_completed tool=%s request_uid=%s code=%s "
                "duration_ms=%s failed_stage=%s timings_ms=%s exceptions=%s",
                name,
                observation.request_uid,
                observation.code,
                elapsed,
                observation.failed_stage,
                json.dumps(observation.timings),
                json.dumps(observation.exception),
                extra=fields,
            )
        finally:
            _active.reset(token)


@contextmanager
def observe_stage(stage: str, *, cache_hit: bool | None = None) -> Iterator[None]:
    observation = _active.get()
    if observation is None:
        yield
        return
    fields = {**observation.fields(), "crm_stage": stage}
    if cache_hit is not None:
        fields["crm_cache_hit"] = cache_hit
    logger.info(
        "crm_mcp_stage_started tool=%s request_uid=%s stage=%s cache_hit=%s",
        observation.tool,
        observation.request_uid,
        stage,
        cache_hit,
        extra={"event": "crm.mcp.stage.started", **fields},
    )
    started, outcome = perf_counter(), "ok"
    try:
        yield
    except BaseException:
        outcome = "failed"
        if observation.failed_stage is None:
            observation.failed_stage = stage
        raise
    finally:
        elapsed = round((perf_counter() - started) * 1000, 3)
        observation.timings[stage] = round(observation.timings.get(stage, 0) + elapsed, 3)
        logger.info(
            "crm_mcp_stage_completed tool=%s request_uid=%s stage=%s "
            "duration_ms=%s outcome=%s cache_hit=%s",
            observation.tool,
            observation.request_uid,
            stage,
            elapsed,
            outcome,
            cache_hit,
            extra={
                "event": "crm.mcp.stage.completed",
                **fields,
                "duration_ms": elapsed,
                "outcome": outcome,
            },
        )
