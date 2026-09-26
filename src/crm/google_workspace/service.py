"""Google OAuth connection lifecycle, separate from CRM sign-in."""

from __future__ import annotations

import uuid

import httpx
import jwt

from src.crm.repositories.errors import ResourceConflict, ResourceNotFound

from .security import (
    GOOGLE_REVOKE_URL,
    GOOGLE_TOKEN_URL,
    SCOPES,
    GoogleConfig,
    Sealer,
    digest,
    random_handle,
    verify_google_id_token,
)
from .store import GoogleStore


def _uid(value) -> uuid.UUID:
    return uuid.UUID(str(value))


def _scopes(value) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, str):
        return value.split()
    return []


class GoogleWorkspaceService:
    def __init__(
        self,
        store: GoogleStore | None = None,
        config: GoogleConfig | None = None,
        http: httpx.Client | None = None,
    ):
        self.store = store if store is not None else GoogleStore()
        self.config = config if config is not None else GoogleConfig.load()
        self.sealer = Sealer(self.config.token_key)
        self.http = http if http is not None else httpx.Client(timeout=10)

    @staticmethod
    def summary(row: dict) -> dict:
        return {
            "uid": str(row["uid"]),
            "display_email": row["display_email"],
            "granted_sources": [
                name for name, scopes in SCOPES.items()
                if all(scope in _scopes(row.get("granted_scopes")) for scope in scopes)
            ],
            "status": row["status"],
            "version": int(row["version"]),
        }

    def connection(self, actor_uid: uuid.UUID) -> dict | None:
        row = self.store.connection(actor_uid)
        return self.summary(row) if row else None

    @classmethod
    def connection_without_google_config(cls, actor_uid: uuid.UUID) -> dict | None:
        """Show existing actor-owned connection state while operator setup is incomplete."""
        row = GoogleStore().connection(actor_uid)
        return cls.summary(row) if row else None

    def start(self, actor_uid: uuid.UUID, source: str) -> dict:
        if source not in SCOPES:
            raise ValueError("Unsupported Google source")
        existing = self.store.connection(actor_uid)
        attempt_uid = uuid.uuid4()
        connection_uid = _uid(existing["uid"]) if existing else uuid.uuid4()
        state, verifier, nonce = random_handle(), random_handle(), random_handle()
        encrypted = self.sealer.seal(
            verifier, purpose="pkce", uid=attempt_uid, actor_uid=actor_uid
        )
        self.store.start(
            uid=attempt_uid,
            actor_uid=actor_uid,
            connection_uid=connection_uid,
            state_hash=digest(state),
            source=source,
            verifier_ciphertext=encrypted,
            nonce=nonce,
        )
        return {
            "authorization_url": self.config.authorization_url(
                source, state, verifier, nonce,
                prompt=existing is None or existing.get("status") != "connected" or not existing.get("refresh_ciphertext"),
            ),
            "attempt_uid": str(attempt_uid),
            "expires_in_seconds": 600,
        }

    def callback(self, *, code: str | None, state: str | None, error: str | None) -> str:
        if not state or len(state) > 512:
            return self.config.return_url(status="invalid_state")
        try:
            attempt = self.store.claim(digest(state))
        except ResourceConflict:
            return self.config.return_url(status="invalid_state")
        attempt_uid, actor_uid = _uid(attempt["uid"]), _uid(attempt["actor_uid"])
        if error:
            self.store.fail(attempt_uid)
            return self.config.return_url(status="denied" if error == "access_denied" else "failed")
        if not code or len(code) > 4096:
            self.store.fail(attempt_uid)
            return self.config.return_url(status="failed")
        try:
            verifier = self.sealer.open(
                attempt["verifier_ciphertext"], purpose="pkce", uid=attempt_uid,
                actor_uid=actor_uid,
            )
            response = self.http.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "redirect_uri": self.config.redirect_uri,
                    "code_verifier": verifier,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            tokens = response.json()
            if tokens.get("token_type", "Bearer").lower() != "bearer":
                raise ValueError("Google returned an unexpected token type")
            claims = verify_google_id_token(tokens["id_token"], self.config.client_id, attempt["nonce"])
            scopes = _scopes(tokens.get("scope"))
            if not scopes:
                raise ValueError("Google returned no granted scopes")
            pending = {
                "google_sub": claims["sub"],
                "display_email": str(claims.get("email") or "Google account")[:320],
                "scopes": scopes,
                "refresh_token": tokens.get("refresh_token"),
            }
            completion = random_handle()
            pending["completion_handle"] = completion
            sealed = self.sealer.seal(
                pending, purpose="pending", uid=attempt_uid, actor_uid=actor_uid
            )
            self.store.exchanged(attempt_uid, digest(completion), sealed)
        except (httpx.HTTPError, KeyError, ValueError, TypeError, jwt.PyJWTError):
            self.store.fail(attempt_uid)
            return self.config.return_url(status="failed")
        return self.config.return_url(status="ready")

    def attempt_status(self, actor_uid: uuid.UUID, attempt_uid: uuid.UUID) -> dict:
        row = self.store.attempt_status(actor_uid, attempt_uid)
        if not row:
            raise ResourceNotFound("Google authorization attempt not found")
        if row["status"] == "exchanged" and row.get("pending_ciphertext"):
            pending = self.sealer.open(
                row["pending_ciphertext"], purpose="pending", uid=attempt_uid,
                actor_uid=actor_uid,
            )
            return {"status": "ready", "completion_handle": pending["completion_handle"]}
        if row["status"] == "completed":
            return {"status": "completed"}
        if row["status"] == "expired":
            return {"status": "expired"}
        if row["status"] == "failed":
            return {"status": "failed"}
        return {"status": "waiting"}

    def complete(self, actor_uid: uuid.UUID, completion_handle: str) -> dict:
        if len(completion_handle) > 512:
            raise ValueError("Invalid Google completion handle")
        attempt = self.store.pending(actor_uid, digest(completion_handle))
        attempt_uid = _uid(attempt["uid"])
        connection_uid = _uid(attempt["connection_uid"])
        pending = self.sealer.open(
            attempt["pending_ciphertext"], purpose="pending", uid=attempt_uid,
            actor_uid=actor_uid,
        )
        existing = self.store.connection(actor_uid)
        if existing and _uid(existing["uid"]) != connection_uid:
            raise ResourceConflict("Google connection changed during authorization")
        if existing and existing["status"] != "disconnected" and existing["google_sub"] != pending["google_sub"]:
            raise ResourceConflict("Disconnect the current Google account before connecting another")
        refresh = pending.get("refresh_token")
        if not refresh and existing and existing["google_sub"] == pending["google_sub"]:
            encrypted = existing.get("refresh_ciphertext")
        elif refresh:
            encrypted = self.sealer.seal(
                refresh, purpose="refresh", uid=connection_uid, actor_uid=actor_uid
            )
        else:
            encrypted = None
        if not encrypted:
            raise ResourceConflict("Google did not grant offline access; reconnect with consent")
        row = self.store.activate(
            actor_uid=actor_uid,
            attempt_uid=attempt_uid,
            completion_hash=digest(completion_handle),
            connection_uid=connection_uid,
            google_sub=pending["google_sub"],
            email=pending["display_email"],
            scopes=pending["scopes"],
            refresh_ciphertext=encrypted,
        )
        return self.summary(row)

    def disconnect(self, actor_uid: uuid.UUID, connection_uid: uuid.UUID) -> dict:
        row = self.store.connection(actor_uid)
        if not row or _uid(row["uid"]) != connection_uid or row["status"] == "disconnected":
            raise ResourceNotFound("Google connection not found")
        ciphertext = self.store.disconnect(actor_uid, connection_uid)
        revoked = False
        if ciphertext:
            try:
                refresh = self.sealer.open(
                    ciphertext, purpose="refresh", uid=connection_uid,
                    actor_uid=actor_uid,
                )
                response = self.http.post(GOOGLE_REVOKE_URL, data={"token": refresh})
                revoked = response.is_success
            except (httpx.HTTPError, ValueError):
                pass
        return {"status": "disconnected", "google_revoked": revoked}

    def access_token(self, actor_uid: uuid.UUID, source: str) -> tuple[str, dict]:
        if source not in SCOPES:
            raise ValueError("Unsupported Google source")
        row = self.store.connection(actor_uid)
        if not row or row["status"] != "connected":
            raise ResourceConflict("Connect Google before reading this source")
        if not all(scope in _scopes(row.get("granted_scopes")) for scope in SCOPES[source]):
            raise ResourceConflict("The Google connection lacks this source permission")
        uid = _uid(row["uid"])
        refresh = self.sealer.open(
            row["refresh_ciphertext"], purpose="refresh", uid=uid, actor_uid=actor_uid
        )
        try:
            response = self.http.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
            )
            if response.status_code == 400 and response.json().get("error") == "invalid_grant":
                self.store.reauthorization_required(actor_uid, uid)
                raise ResourceConflict("Google access expired; reconnect the account")
            response.raise_for_status()
            access = response.json()["access_token"]
            if not isinstance(access, str) or not access:
                raise ValueError("Google returned no access token")
            return access, row
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ResourceConflict("Google access is temporarily unavailable") from exc
