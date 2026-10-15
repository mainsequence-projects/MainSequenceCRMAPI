"""Safe diagnostics for protected CRM startup, never raw SDK exceptions."""

import logging
import uuid

from fastapi import Request

from mainsequence.client.exceptions import ApiError

from .catalog import CatalogValidationError

logger = logging.getLogger(__name__)


def _request_id(value: object) -> str | None:
    # Gateways can repeat the same correlation header. Accept only UUIDs, not
    # arbitrary response-header content, tokens or unbounded diagnostic strings.
    if not isinstance(value, str) or len(value) > 256:
        return None
    parts = [part.strip() for part in value.split(",")]
    if not parts or len(set(parts)) != 1:
        return None
    candidate = parts[0]
    try:
        parsed = uuid.UUID(candidate)
    except (ValueError, AttributeError):
        return None
    return candidate if candidate in {str(parsed), parsed.hex} else None


def report_readiness_failure(
    request: Request, stage: str, error: Exception, fallback: str
) -> str:
    """Log correlation and return an allowlisted, credential-free public message.

    ApiError.__str__ includes the request URL and arbitrary upstream content.
    Neither it nor traceback/headers/payloads belong in a startup response/log.
    """
    message = str(error) if isinstance(error, CatalogValidationError) else fallback
    status = None
    code = None
    upstream_request_id = None
    if isinstance(error, ApiError):
        if type(error.status_code) is int and 100 <= error.status_code <= 599:
            status = error.status_code
        public_errors = {
            "authentication_unavailable": "FastAPI authentication is temporarily unavailable.",
            "runtime_starting": "The Main Sequence MetaTables runtime is starting.",
            "gateway_error": "The Main Sequence FastAPI gateway could not complete the request.",
        }
        candidate = error.payload.get("code") if isinstance(error.payload, dict) else None
        if isinstance(candidate, str) and candidate in public_errors:
            code = candidate
        upstream_request_id = _request_id((error.headers or {}).get("X-Request-ID"))
        if status is not None:
            message += f" Upstream HTTP {status}" + (f" ({code})" if code else "") + "."
        if code:
            message += " " + public_errors[code]
        if upstream_request_id:
            message += f" Upstream request ID: {upstream_request_id}."
    local_request_id = _request_id(str(getattr(request.state, "crm_request_uid", "")))
    logger.error(
        "CRM readiness check failed: stage=%s error_type=%s request_uid=%s "
        "upstream_status=%s upstream_code=%s upstream_request_id=%s reason=%s",
        stage, type(error).__name__, local_request_id,
        status, code, upstream_request_id, message,
        extra={
            "event": "crm.readiness_check_failed", "crm_stage": stage,
            "crm_request_uid": local_request_id, "error_type": type(error).__name__,
            "upstream_status": status, "upstream_code": code,
            "upstream_request_id": upstream_request_id,
        },
    )
    return message
