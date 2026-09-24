from __future__ import annotations

from mainsequence.meta_tables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.crm.metatables import Base
from src.crm.migrations.registry import metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="mainsequence-crm",
    identifier="mainsequence_crm.alembic_version",
    schema=None,
    table_name="mainsequence_crm__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.crm",
    migration_namespace="mainsequence-crm",
    script_location="src.crm.migrations:",
    version_location_prefix="src.crm.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
