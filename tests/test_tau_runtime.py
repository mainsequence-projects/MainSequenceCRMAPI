"""The Tau ASGI entrypoint respects the deployment's process settings."""

import os
import subprocess
import sys


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
