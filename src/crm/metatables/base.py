from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, MetaData, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData()


def column_info(label: str, description: str) -> dict[str, str]:
    return {"label": label, "description": description}


class VersionedRecord:
    """Shared columns for records, not a database model of its own."""

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, info=column_info("UID", "Stable CRM record identifier.")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info=column_info("Created at", "Creation instant."),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info=column_info("Updated at", "Last edit instant."),
    )
    created_by_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=column_info("Created by", "Existing platform user UID.")
    )
    updated_by_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=column_info("Updated by", "Existing platform user UID.")
    )
    version: Mapped[int] = mapped_column(
        BigInteger(),
        nullable=False,
        info=column_info("Version", "Positive optimistic edit version."),
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), info=column_info("Archived at", "Soft archive marker.")
    )
