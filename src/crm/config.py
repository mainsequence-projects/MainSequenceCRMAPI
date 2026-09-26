"""Validated, process-persisted CRM deployment configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "crm.yaml"


class ExtensionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    active: StrictBool


class ExtensionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    solution_selling: ExtensionConfig
    google_workspace: ExtensionConfig


class CrmConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    extensions: ExtensionsConfig


@lru_cache(maxsize=1)
def crm_config() -> CrmConfig:
    try:
        content = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        return CrmConfig.model_validate(content)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise RuntimeError("config/crm.yaml is missing or invalid") from exc
