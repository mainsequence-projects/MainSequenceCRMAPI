"""Explicit single-user, loopback-only development launcher.

The deployed entrypoint remains ``api.crm.main:app``. Its installed request
identity runs here in local mode, where it verifies a direct Bearer token with
the Main Sequence backend. This launcher presents the SDK sign-in of this
process as that token on every loopback request, so Vite can proxy /api
without a FastAPI ResourceRelease and the only caller is the signed-in
developer. It must never be used behind a public proxy.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import time
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from threading import Lock
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mainsequence.client import User
from mainsequence.client.utils import get_authorization_headers
from src.crm.google_workspace.config import google_workspace_enabled
from src.crm.platform.catalog import configured_registry
from src.crm.platform.local_runtime import build_local_services

from .main import create_app as create_crm_app

LOCAL_SIGN_IN_TIMEOUT_SECONDS = 20
LOCAL_SIGN_IN_CACHE_SECONDS = 300
# The deployment's public ingress in .mainsequence/workflows/crm-api.yaml.
GOOGLE_PUBLIC_ROUTES = (
    ("GET", "/extensions/google/oauth/callback/"),
    ("GET", "/extensions/google/oauth/done/"),
)
# A direct caller cannot claim an identity or present a credential. The only
# user in this explicit local mode is the account signed into the SDK process.
CALLER_HEADERS = frozenset(
    {
        b"authorization",
        b"x-mainsequence-caller-assertion",
        b"x-public-ingress",
        b"x-user-id",
        b"x-user-uid",
        b"x-username",
    }
)


def _is_loopback(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def _anonymous_routes() -> tuple[tuple[str, str], ...]:
    """Routes served without the local sign-in.

    ``/healthz`` checks only the process. The Google callback and completion
    page are anonymous in the deployed API too; they exist while the module is
    active.
    """
    google = GOOGLE_PUBLIC_ROUTES if google_workspace_enabled() else ()
    return (("GET", "/healthz"), *google)


@contextmanager
def _public_ingress(routes: tuple[tuple[str, str], ...]) -> Iterator[None]:
    """Declare ``routes`` public while the CRM factory installs request identity.

    A deployment receives this declaration as ``FASTAPI_PUBLIC_INGRESS``, which
    the SDK reads once, at installation. The process value is restored after.
    """
    previous = os.environ.get("FASTAPI_PUBLIC_INGRESS")
    os.environ["FASTAPI_PUBLIC_INGRESS"] = json.dumps(
        [{"method": method, "path": path} for method, path in routes]
    )
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("FASTAPI_PUBLIC_INGRESS", None)
        else:
            os.environ["FASTAPI_PUBLIC_INGRESS"] = previous


def _signed_in_authorization() -> bytes:
    """Return this process's SDK sign-in as a Bearer credential.

    The SDK renews its access token first when it is about to expire.
    """
    value = str(get_authorization_headers().get("Authorization") or "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise RuntimeError("The SDK sign-in has no Bearer token.")
    return f"Bearer {token.strip()}".encode("latin-1")


def create_app() -> FastAPI:
    anonymous = _anonymous_routes()
    with _public_ingress(anonymous):
        application = create_crm_app()
    if application.state.mainsequence_request_identity["mode"] != "local":
        raise RuntimeError(
            "The loopback CRM launcher runs only outside a Main Sequence deployment."
        )
    signed_user_lock = Lock()
    signed_user_cache = None
    signed_user_expires_at = 0.0
    signed_user_future: Future | None = None
    signed_user_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="crm-local-sign-in")

    async def locally_signed_user():
        nonlocal signed_user_cache, signed_user_expires_at, signed_user_future
        with signed_user_lock:
            if signed_user_cache is not None and time.monotonic() < signed_user_expires_at:
                return signed_user_cache
            if signed_user_future is None or signed_user_future.done():
                signed_user_future = signed_user_executor.submit(User.get_authenticated_user_details)
            pending = signed_user_future
        signed_user = await asyncio.wait_for(
            asyncio.wrap_future(pending), timeout=LOCAL_SIGN_IN_TIMEOUT_SECONDS
        )
        with signed_user_lock:
            signed_user_cache = signed_user
            signed_user_expires_at = time.monotonic() + LOCAL_SIGN_IN_CACHE_SECONDS
            return signed_user

    @application.on_event("shutdown")
    def stop_sign_in_worker():
        signed_user_executor.shutdown(wait=False, cancel_futures=True)

    origin = os.environ.get("CRM_LOCAL_TAU_ORIGIN", "")
    if origin:
        parsed = urlsplit(origin)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
                or parsed.port is None or parsed.path or parsed.query or parsed.fragment
                or parsed.username or parsed.password):
            raise RuntimeError("CRM_LOCAL_TAU_ORIGIN must be a loopback HTTP origin")
        application.state.crm_local_tau_origin = origin.rstrip("/")

    @application.middleware("http")
    async def local_signed_user(request: Request, call_next):
        if not _is_loopback(request):
            return JSONResponse(
                {"detail": "Local CRM accepts loopback requests only."}, status_code=403
            )
        headers = [
            (name, value)
            for name, value in request.scope["headers"]
            if name.lower() not in CALLER_HEADERS
        ]
        if (request.method, request.scope["path"]) in anonymous:
            # The gateway's admission marker for a declared public route.
            request.scope["headers"] = [*headers, (b"x-public-ingress", b"1")]
            return await call_next(request)
        if len(headers) != len(request.scope["headers"]):
            return JSONResponse(
                {"detail": "Local CRM does not accept caller identity headers."}, status_code=401
            )
        try:
            signed_user = await locally_signed_user()
            authorization = await asyncio.wait_for(
                asyncio.to_thread(_signed_in_authorization),
                timeout=LOCAL_SIGN_IN_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return JSONResponse(
                {"error": {"code": "LOCAL_SIGN_IN_TIMEOUT", "message":
                    f"Main Sequence signed-in user lookup did not respond within {LOCAL_SIGN_IN_TIMEOUT_SECONDS} seconds. Check the local Main Sequence backend and SDK session."}},
                status_code=503,
            )
        except Exception:
            return JSONResponse(
                {"detail": "A valid Main Sequence local sign-in is required."}, status_code=401
            )
        registry = configured_registry()
        request.state.crm_registry = registry
        try:
            policy, directory, bootstrap = build_local_services(
                signed_user=signed_user,
                registry=registry,
            )
        except Exception:
            return JSONResponse(
                {"detail": "The local CRM dataset is unavailable."},
                status_code=503,
            )
        request.state.crm_policy = policy
        request.state.crm_directory = directory
        request.state.crm_bootstrap = bootstrap
        # The installed request identity verifies this credential with
        # MAINSEQUENCE_ENDPOINT/api/v1/users/me/, binds that user as the caller
        # and removes the header before any route runs. The local policy grants
        # CRM capabilities only to the signed-in user above.
        request.scope["headers"] = [*headers, (b"authorization", authorization)]
        return await call_next(request)

    return application


app = create_app()
