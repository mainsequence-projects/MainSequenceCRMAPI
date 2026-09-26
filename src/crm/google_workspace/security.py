"""Google OAuth configuration, token verification and sealed short-lived data."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

from mainsequence.client import Secret

SCOPES = {
    "contacts": ("https://www.googleapis.com/auth/contacts.readonly",),
    "gmail": ("https://www.googleapis.com/auth/gmail.readonly",),
    "calendar": ("https://www.googleapis.com/auth/calendar.events.readonly",),
}
CALENDAR_PICKER_SCOPE = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def random_handle() -> str:
    return secrets.token_urlsafe(32)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _secret(name: str) -> str:
    try:
        record = Secret.get(name=name)
        value = record.value
    except Exception as exc:
        raise RuntimeError(f"Google integration Secret {name} is unavailable") from exc
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if not isinstance(value, str) or not value or value.startswith("PASTE_GOOGLE_"):
        raise RuntimeError(f"Google integration Secret {name} is not configured")
    return value


def _configured_url(name: str, *, callback: bool) -> str:
    value = os.environ.get(name, "").strip()
    parsed = urlsplit(value)
    loopback = parsed.hostname in {"localhost", "127.0.0.1"}
    if not value or parsed.scheme not in ({"https", "http"} if loopback else {"https"}):
        raise RuntimeError(f"{name} must be an HTTPS URL, or HTTP on loopback")
    if not parsed.netloc or parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise RuntimeError(f"{name} has an invalid URL")
    if callback and parsed.path != "/extensions/google/oauth/callback/":
        raise RuntimeError(f"{name} must name the exact Google callback route")
    return value


@dataclass(frozen=True)
class GoogleConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    token_key: bytes

    @classmethod
    def load(cls) -> GoogleConfig:
        redirect_uri = _configured_url("GOOGLE_OAUTH_REDIRECT_URI", callback=True)
        with ThreadPoolExecutor(max_workers=3) as pool:
            client_id_future = pool.submit(_secret, "CRM_GOOGLE_OAUTH_CLIENT_ID")
            client_secret_future = pool.submit(_secret, "CRM_GOOGLE_OAUTH_CLIENT_SECRET")
            key_future = pool.submit(_secret, "CRM_GOOGLE_TOKEN_ENCRYPTION_KEY")
            client_id = client_id_future.result().strip()
            client_secret = client_secret_future.result()
            key_text = key_future.result()
        if not client_id:
            raise RuntimeError("Google integration Secret CRM_GOOGLE_OAUTH_CLIENT_ID is empty")
        try:
            key = base64.urlsafe_b64decode(key_text + "=" * (-len(key_text) % 4))
        except Exception as exc:
            raise RuntimeError("Google token encryption key is invalid") from exc
        if len(key) != 32:
            raise RuntimeError("Google token encryption key must be 32 bytes")
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            token_key=key,
        )

    def authorization_url(self, source: str, state: str, verifier: str, nonce: str, *, prompt: bool) -> str:
        if source not in SCOPES:
            raise ValueError("Unsupported Google source")
        query = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(("openid", "email", *SCOPES[source], *((CALENDAR_PICKER_SCOPE,) if source == "calendar" else ()))),
            "state": state,
            "nonce": nonce,
            "code_challenge": _b64url(hashlib.sha256(verifier.encode("ascii")).digest()),
            "code_challenge_method": "S256",
            "access_type": "offline",
            "include_granted_scopes": "true",
        }
        if prompt:
            query["prompt"] = "consent"
        return f"{GOOGLE_AUTH_URL}?{urlencode(query)}"

    def return_url(self, *, status: str) -> str:
        # Fixed API page: an embedded Command Center frontend polls with its own CRM identity.
        destination = self.redirect_uri.removesuffix("callback/") + "done/"
        return f"{destination}?{urlencode({'google_status': status})}"


class Sealer:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("AES-256-GCM needs a 32-byte key")
        self.aes = AESGCM(key)

    def seal(self, value: object, *, purpose: str, uid: uuid.UUID, actor_uid: uuid.UUID) -> str:
        nonce = os.urandom(12)
        aad = f"v1:{purpose}:{uid}:{actor_uid}".encode()
        ciphertext = self.aes.encrypt(nonce, json.dumps(value, separators=(",", ":")).encode(), aad)
        return "v1." + _b64url(nonce + ciphertext)

    def open(self, value: str, *, purpose: str, uid: uuid.UUID, actor_uid: uuid.UUID):
        if not value.startswith("v1."):
            raise ValueError("Unknown sealed payload version")
        raw = base64.urlsafe_b64decode(value[3:] + "=" * (-len(value[3:]) % 4))
        if len(raw) < 29:
            raise ValueError("Sealed payload is invalid")
        aad = f"v1:{purpose}:{uid}:{actor_uid}".encode()
        return json.loads(self.aes.decrypt(raw[:12], raw[12:], aad))


_jwks = jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_jwk_set=True, lifespan=3600)


def verify_google_id_token(token: str, client_id: str, nonce: str) -> dict:
    key = _jwks.get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=["https://accounts.google.com", "accounts.google.com"],
        options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
    )
    if not secrets.compare_digest(str(claims["nonce"]), nonce):
        raise ValueError("Google ID-token nonce mismatch")
    if not isinstance(claims["sub"], str) or not claims["sub"] or len(claims["sub"]) > 255:
        raise ValueError("Google ID-token subject is invalid")
    return claims


def expiry(minutes: int) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)
