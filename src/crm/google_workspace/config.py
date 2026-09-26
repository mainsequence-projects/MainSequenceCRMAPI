"""Persisted availability for the optional Google Workspace module."""

from __future__ import annotations

from ..config import crm_config


def google_workspace_enabled() -> bool:
    return crm_config().extensions.google_workspace.active
