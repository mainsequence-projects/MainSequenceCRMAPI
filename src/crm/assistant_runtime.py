"""Resolve the optional assistant from trusted runtime evidence."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

import httpx

CARD_PATH = Path(__file__).resolve().parents[2] / ".agents" / "agent_card.json"
logger = logging.getLogger(__name__)


def _card_name() -> str | None:
    try:
        card = json.loads(CARD_PATH.read_text(encoding="utf-8"))
        name = card["name"]
        description = card["description"]
        if not isinstance(name, str) or not name.strip() or not isinstance(description, str) or not description.strip():
            return None
        return name
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _uuid(value: object) -> str:
    return str(uuid.UUID(str(value)))


def _platform_agent(name: str) -> dict | None:
    """SDK context supplies the branch and Environment; no YAML or browser UID."""
    try:
        from mainsequence.client.agent_runtime_models import Agent
        from mainsequence.code_repository_context import (
            resolve_code_repository_branch_uid,
            resolve_organization_environment_uid,
        )

        environment_uid = _uuid(resolve_organization_environment_uid("CRM assistant bootstrap"))
        branch_uid = _uuid(resolve_code_repository_branch_uid("CRM assistant bootstrap"))
        candidates = list(Agent.filter(name=name))
        if len(candidates) != 1:
            return None
        agent = candidates[0]
        agent_uid = _uuid(agent.uid)
        if (agent.name != name
                or _uuid(agent.organization_environment_uid) != environment_uid
                or _uuid(agent.code_repository_branch_uid) != branch_uid
                or not agent.runtime_release_uid):
            return None
        return {
            "enabled": True,
            "runtime": {"mode": "platform"},
            "agent_uid": agent_uid,
            "environment_uid": environment_uid,
            "display_name": name,
        }
    except Exception:
        logger.warning("CRM platform assistant resolution failed", exc_info=True)
        return None


async def resolve_assistant(local_tau_origin: str | None) -> dict:
    name = _card_name()
    unavailable = {
        "enabled": False,
        "runtime": None,
        "agent_uid": None,
        "environment_uid": None,
        "display_name": name,
    }
    if name is None:
        logger.warning("CRM Agent Card is missing or invalid")
        return unavailable
    if local_tau_origin:
        try:
            async with httpx.AsyncClient(timeout=1.5, trust_env=False) as client:
                response = await client.get(f"{local_tau_origin}/ready")
                if response.status_code == 200:
                    health = response.json()
                    if health.get("ok") is True and health.get("mode") == "local":
                        return {
                            "enabled": True,
                            "runtime": {"mode": "local", "base_path": "/tau"},
                            "agent_uid": None,
                            "environment_uid": None,
                            "display_name": name,
                        }
        except (httpx.HTTPError, ValueError):
            pass
    return await asyncio.to_thread(_platform_agent, name) or unavailable
