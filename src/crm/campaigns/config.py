"""Persisted availability of the Campaigns module, separate from authorization."""

from __future__ import annotations

from ..config import crm_config


def campaigns_enabled() -> bool:
    return crm_config().extensions.campaigns.active
