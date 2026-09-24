"""SQLAlchemy MetaTable declaration for contact_tag records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class ContactTag(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "contact_tag")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__contact_tag"
    __metatable_description__ = "One contact-to-tag association."
    __metatable_labels__ = ["crm", "contact-tag"]
    __table_args__ = (
        UniqueConstraint(
            "contact_uid", "tag_uid", name="uq_mainsequence_crm__contact_tag_contact_uid_tag_"
        ),
        ForeignKeyConstraint(
            ["contact_uid"],
            ["mainsequence_crm__contact.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__contact_tag_contact_uid",
        ),
        ForeignKeyConstraint(
            ["tag_uid"],
            ["mainsequence_crm__tag.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__contact_tag_tag_uid",
        ),
        Index("ix_mainsequence_crm__contact_tag_1", "tag_uid", "contact_uid"),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        nullable=False,
        info={"label": "Uid", "description": "uid"},
    )

    contact_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Contact Uid", "description": "contact uid"},
    )

    tag_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Tag Uid", "description": "tag uid"},
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={"label": "Created At", "description": "created at"},
    )
