"""Persisted availability, separate from platform authorization."""

from __future__ import annotations

from ..config import crm_config


def solution_selling_enabled() -> bool:
    return crm_config().extensions.solution_selling.active
