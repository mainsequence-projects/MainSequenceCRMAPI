"""SQLAlchemy MetaTable declaration for deal_contact records."""

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


class DealContact(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "deal_contact")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__deal_contact"
    __metatable_description__ = "One deal-to-contact association."
    __metatable_labels__ = ["crm", "deal-contact"]
    __table_args__ = (
        UniqueConstraint(
            "deal_uid", "contact_uid", name="uq_mainsequence_crm__deal_contact_deal_uid_contac"
        ),
        ForeignKeyConstraint(
            ["deal_uid"],
            ["mainsequence_crm__deal.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__deal_contact_deal_uid",
        ),
        ForeignKeyConstraint(
            ["contact_uid"],
            ["mainsequence_crm__contact.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__deal_contact_contact_uid",
        ),
        Index("ix_mainsequence_crm__deal_contact_1", "contact_uid", "deal_uid"),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        nullable=False,
        info={"label": "Uid", "description": "uid"},
    )

    deal_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Deal Uid", "description": "deal uid"},
    )

    contact_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Contact Uid", "description": "contact uid"},
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={"label": "Created At", "description": "created at"},
    )
