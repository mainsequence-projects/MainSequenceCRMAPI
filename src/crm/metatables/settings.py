"""Application configuration, without an application-owned tenant identity."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, BigInteger, CheckConstraint, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class Settings(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "settings")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__settings"
    __metatable_description__ = "CRM application configuration."
    __metatable_labels__ = ["crm", "settings"]
    __table_args__ = (
        UniqueConstraint("key", name="uq_mainsequence_crm__settings_key"),
        CheckConstraint("key = 'default'", name="ck_mainsequence_crm__settings_key"),
        CheckConstraint(
            "default_currency ~ '^[A-Z]{3}$'", name="ck_mainsequence_crm__settings_currency"
        ),
        CheckConstraint("configuration_version > 0", name="ck_mainsequence_crm__settings_version"),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        nullable=False,
        info={"label": "Uid", "description": "Settings record UID"},
    )
    key: Mapped[str] = mapped_column(
        String(32), nullable=False, info={"label": "Key", "description": "Singleton settings key"}
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, info={"label": "Name", "description": "CRM name"}
    )
    default_currency: Mapped[str] = mapped_column(
        CHAR(3),
        nullable=False,
        info={"label": "Default Currency", "description": "ISO currency code"},
    )
    timezone: Mapped[str] = mapped_column(
        String(100), nullable=False, info={"label": "Timezone", "description": "CRM timezone"}
    )
    configuration: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, info={"label": "Configuration", "description": "CRM option lists"}
    )
    configuration_version: Mapped[int] = mapped_column(
        BigInteger(),
        nullable=False,
        info={"label": "Configuration Version", "description": "Optimistic settings version"},
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info={"label": "Created At", "description": "Creation time"},
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info={"label": "Updated At", "description": "Last update time"},
    )
