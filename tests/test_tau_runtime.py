"""The Tau ASGI entrypoint respects the deployment's process settings."""

import os
import subprocess
import sys
from pathlib import Path

from ms_tau_sdk.resources.loader import resource_root, tau_resource_paths
from tau_coding.context import discover_project_context
from tau_coding.resources import discover_system_prompt_resources
from tau_coding.system_prompt import BuildSystemPromptOptions, build_system_prompt

from api.tau.crm_tools import build_crm_tools, unavailable_runtime


def _entrypoint_tool_settings(base: str, mcp: str) -> tuple[bool, bool]:
    environment = {
        **os.environ,
        "TAU_EXCLUDE_BASE_TOOLS": base,
        "TAU_EXCLUDE_MAINSEQUENCE_MCP": mcp,
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from api.tau.main import app; s = app.state.settings; "
            "print(s.exclude_base_tools, s.exclude_mainsequence_mcp)",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(value == "True" for value in result.stdout.strip().split())


def test_tau_tool_exclusions_follow_runtime_configuration():
    assert _entrypoint_tool_settings("false", "false") == (False, False)
    assert _entrypoint_tool_settings("true", "true") == (True, True)


def test_runtime_replaces_packaged_general_prompt_with_crm_prompt(tmp_path):
    root = Path(__file__).resolve().parents[1]
    plain_project = tmp_path / "plain"
    plain_project.mkdir()
    packaged = discover_system_prompt_resources(
        tau_resource_paths(plain_project, state_home=tmp_path)
    )
    assert packaged.custom_prompt_path == resource_root() / "SYSTEM.md"
    paths = tau_resource_paths(root, state_home=tmp_path)
    resources = discover_system_prompt_resources(paths)
    assert resources.custom_prompt_path == root / ".tau" / "SYSTEM.md"
    context_files = discover_project_context(paths)
    assert any(item.path == str(root / "AGENTS.md") for item in context_files)
    prompt = build_system_prompt(
        BuildSystemPromptOptions(
            cwd=root,
            tools=build_crm_tools(unavailable_runtime),
            custom_prompt=resources.custom_prompt,
            context_files=context_files,
        )
    )
    assert "You are CRM assistant" in prompt
    assert "On a simple greeting" in prompt
    assert "I can help with contacts, deals, tasks" in prompt
    assert "Do not introduce yourself as a Tau coding agent" in prompt
    assert "these coding\ninstructions do not grant that runtime file editing" in prompt
    assert packaged.custom_prompt not in prompt
