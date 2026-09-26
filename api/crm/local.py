"""Explicit single-user, loopback-only development launcher.

The deployed entrypoint remains ``api.crm.main:app``. This module binds the
authenticated SDK login to local browser requests so Vite can proxy /api
without a FastAPI ResourceRelease. It must never be used behind a public proxy.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mainsequence.client.models_user import RequestUserIdentity, User
from src.crm.platform.catalog import configured_registry
from src.crm.platform.local_runtime import build_local_services

from .main import create_app as create_crm_app

LOCAL_SIGN_IN_TIMEOUT_SECONDS = 10


def _is_loopback(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def create_app() -> FastAPI:
    application = create_crm_app()
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
            signed_user_expires_at = time.monotonic() + 30
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
        if request.url.path in {
            "/healthz",
            "/extensions/google/oauth/callback/",
            "/extensions/google/oauth/done/",
        }:
            return await call_next(request)
        # A direct caller cannot claim a different identity. The only user in
        # this explicit local mode is the account signed into the SDK process.
        if any(
            request.headers.get(name)
            for name in ("x-user-uid", "x-username", "x-user-id", "authorization")
        ):
            return JSONResponse(
                {"detail": "Local CRM does not accept caller identity headers."}, status_code=401
            )
        try:
            signed_user = await locally_signed_user()
            identity = RequestUserIdentity(uid=signed_user.uid, username=signed_user.username)
        except TimeoutError:
            return JSONResponse(
                {"error": {"code": "LOCAL_SIGN_IN_TIMEOUT", "message":
                    "Main Sequence signed-in user lookup did not respond within 10 seconds. Check the local Main Sequence backend and SDK session."}},
                status_code=503,
            )
        except Exception:
            return JSONResponse(
                {"detail": "A valid Main Sequence local sign-in is required."}, status_code=401
            )
        request.state.user = identity
        request.state.user_uid = str(identity.uid)
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
        return await call_next(request)

    return application


app = create_app()
