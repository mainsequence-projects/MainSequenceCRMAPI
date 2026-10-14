"""Core reusable fixed Markdown prompt library."""

from sqlalchemy import CheckConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from metatables import PlatformManagedMetaTable, schema_table_name

from .base import Base, VersionedRecord, column_info


class Prompt(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "prompt")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__prompt"
    __metatable_description__ = (
        "One row per reusable prompt document authored by a CRM user. Fixed Markdown "
        "instructions for reading and copying, without variable substitution or automatic execution."
    )
    __metatable_labels__ = ["crm", "prompts", "reference-data"]
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_mainsequence_crm__prompt_version"),
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 255", name="ck_mainsequence_crm__prompt_name"
        ),
        CheckConstraint(
            "description IS NULL OR length(description) <= 2000",
            name="ck_mainsequence_crm__prompt_description",
        ),
        CheckConstraint(
            "octet_length(content_markdown) BETWEEN 1 AND 65536",
            name="ck_mainsequence_crm__prompt_content",
        ).ddl_if(dialect="postgresql"),
        Index("ix_mainsequence_crm__prompt_updated", "archived_at", "updated_at", "uid"),
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        info=column_info("Name", "Human-readable name of the reusable prompt."),
    )
    description: Mapped[str | None] = mapped_column(
        Text(),
        info=column_info(
            "Description",
            "Optional explanation of when to use the prompt; null means no explanation.",
        ),
    )
    content_markdown: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
        info=column_info(
            "Markdown content",
            "Canonical fixed Markdown instructions, at most 64 KiB in UTF-8; never evaluated as a template.",
        ),
    )
