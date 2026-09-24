"""SQLAlchemy MetaTable declaration for task records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class Task(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "task")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__task"
    __metatable_description__ = "One follow-up belonging to a contact."
    __metatable_labels__ = ["crm", "task"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["contact_uid"],
            ["mainsequence_crm__contact.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__task_contact_uid",
        ),
        CheckConstraint("length(trim(text)) > 0", name="ck_mainsequence_crm__task_1"),
        Index("ix_mainsequence_crm__task_1", "contact_uid"),
        Index(
            "ix_mainsequence_crm__task_open_due",
            "owner_uid",
            "due_at",
            "uid",
            postgresql_where=text("completed_at IS NULL AND archived_at IS NULL"),
        ),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        nullable=False,
        info={
            "label": "Uid",
            "description": "Stable application record UUID; never an Atomic bigint.",
        },
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={
            "label": "Created At",
            "description": "Creation time in this application; source dates are preserved separately where needed.",
        },
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={"label": "Updated At", "description": "updated at"},
    )

    created_by_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={
            "label": "Created By Uid",
            "description": "Existing platform user UID, nullable only for preserved historical/system origin.",
        },
    )

    updated_by_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Updated By Uid", "description": "updated by uid"},
    )

    version: Mapped[int] = mapped_column(
        BigInteger(),
        primary_key=False,
        nullable=False,
        info={
            "label": "Version",
            "description": "Optimistic entity version, positive and incremented by each successful edit.",
        },
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Archived At", "description": "Archive marker, not a hard-delete request."},
    )

    contact_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Contact Uid", "description": "contact uid"},
    )

    owner_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Owner Uid", "description": "owner uid"},
    )

    type_key: Mapped[str] = mapped_column(
        String(100),
        primary_key=False,
        nullable=False,
        info={"label": "Type Key", "description": "type key"},
    )

    text: Mapped[str] = mapped_column(
        Text(),
        primary_key=False,
        nullable=False,
        info={"label": "Text", "description": "text"},
    )

    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Due At", "description": "due at"},
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Completed At", "description": "completed at"},
    )

    completed_by_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={
            "label": "Completed By Uid",
            "description": "Live completing user or explicit mapped historical attribution; do not invent.",
        },
    )

    source_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Source Created At", "description": "source created at"},
    )

    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Source Updated At", "description": "source updated at"},
    )
