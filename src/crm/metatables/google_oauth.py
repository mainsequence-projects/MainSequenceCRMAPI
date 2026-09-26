"""Backend-only Google OAuth state. Neither table is a CRM resource."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base, column_info


class GoogleOAuthAttempt(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "google_oauth_attempt")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__google_oauth_attempt"
    __metatable_description__ = "Short-lived, single-use Google OAuth exchange state."
    __metatable_labels__ = ["crm", "google-oauth", "private"]
    __table_args__ = (
        Index("ix_mainsequence_crm__google_oauth_attempt_state", "state_hash", unique=True),
        Index("ix_mainsequence_crm__google_oauth_attempt_handle", "completion_hash", unique=True),
        Index("ix_mainsequence_crm__google_oauth_attempt_expiry", "expires_at"),
    )

    uid: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, info=column_info("UID", "Attempt ID."))
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, info=column_info("State hash", "SHA-256 of OAuth state."))
    actor_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, info=column_info("Actor", "Initiating platform principal."))
    connection_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, info=column_info("Connection", "Proposed or existing connection UID."))
    source: Mapped[str] = mapped_column(String(20), nullable=False, info=column_info("Source", "Requested Google source."))
    verifier_ciphertext: Mapped[str] = mapped_column(Text(), nullable=False, info=column_info("PKCE verifier", "Encrypted PKCE verifier."))
    nonce: Mapped[str] = mapped_column(String(128), nullable=False, info=column_info("OIDC nonce", "Expected ID-token nonce."))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, info=column_info("Expires", "Start deadline."))
    status: Mapped[str] = mapped_column(String(20), nullable=False, info=column_info("Status", "started, redeeming, exchanged or completed."))
    completion_hash: Mapped[str | None] = mapped_column(String(64), info=column_info("Completion hash", "SHA-256 of one-time completion handle."))
    pending_ciphertext: Mapped[str | None] = mapped_column(Text(), info=column_info("Pending credential", "Encrypted exchange result; short-lived."))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), info=column_info("Completed", "Exchange or consumption time."))


class GoogleOAuthConnection(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "google_oauth_connection")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__google_oauth_connection"
    __metatable_description__ = "One actor-owned Google grant; refresh token ciphertext is backend-only."
    __metatable_labels__ = ["crm", "google-oauth", "private"]
    __table_args__ = (
        Index("uq_mainsequence_crm__google_connection_actor", "actor_uid", unique=True),
        Index("uq_mainsequence_crm__google_connection_sub_active", "google_sub", unique=True, postgresql_where=text("status <> 'disconnected'")),
    )

    uid: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, info=column_info("UID", "Connection ID."))
    actor_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, info=column_info("Actor", "Owning platform principal."))
    source_connection_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, info=column_info("Provenance", "Nonsecret source connection ID."))
    google_sub: Mapped[str] = mapped_column(String(255), nullable=False, info=column_info("Google subject", "Stable OIDC subject."))
    display_email: Mapped[str] = mapped_column(String(320), nullable=False, info=column_info("Display email", "Google account label; not identity key."))
    granted_scopes: Mapped[Any] = mapped_column(JSONB(), nullable=False, info=column_info("Scopes", "Actually granted scope URLs."))
    refresh_ciphertext: Mapped[str | None] = mapped_column(Text(), info=column_info("Refresh token", "AES-256-GCM ciphertext."))
    status: Mapped[str] = mapped_column(String(30), nullable=False, info=column_info("Status", "connected, reauthorization_required or disconnected."))
    version: Mapped[int] = mapped_column(BigInteger(), nullable=False, info=column_info("Version", "Optimistic connection version."))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, info=column_info("Created", "Connection creation instant."))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, info=column_info("Updated", "Last connection edit instant."))
