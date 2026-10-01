from __future__ import annotations

from metatables.migrations import build_metatable_model_registry
from src.crm.metatables import MODELS, Base


def metatable_provider_models() -> list[type]:
    return build_metatable_model_registry(list(MODELS.values()), base=Base)


__all__ = ["metatable_provider_models"]
