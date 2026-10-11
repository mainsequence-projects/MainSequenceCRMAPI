"""Bind a frontend workflow only to the current branch's active CRM MCP release.

Run after the API workflow succeeds. No release is created, deployed or granted
by this command. --apply changes only the supplied local frontend workflow.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from mainsequence.client import ResourceRelease
from mainsequence.code_repository_context import get_code_repository_context


def active_binding(context, releases) -> dict[str, str]:
    if not context.code_repository_branch_uid or not context.organization_environment_uid:
        raise RuntimeError("Current Git branch and Environment must be resolved")
    candidates = [
        release for release in releases
        if release.name == "crm" and release.release_kind == "fastapi"
        and release.code_repository_branch_uid == context.code_repository_branch_uid
        and release.mcp_enabled
    ]
    if len(candidates) != 1:
        raise RuntimeError("Expected one MCP-enabled CRM release on the current branch")
    release = candidates[0]
    connection = release.mcp_connection
    if (not release.active_revision or connection is None
            or connection.active_revision_uid != release.active_revision
            or connection.organization_environment_uid != context.organization_environment_uid
            or connection.transport != "streamable-http"):
        raise RuntimeError("The CRM release has no active MCP revision in this Environment")
    parsed = urlsplit(connection.url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.path != "/mcp"
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise RuntimeError("The backend advertised an unsupported CRM MCP URL")
    return {
        "release_uid": str(uuid.UUID(release.uid)),
        "active_revision_uid": str(uuid.UUID(release.active_revision)),
        "google_callback_uri": connection.url.removesuffix("/mcp") + "/extensions/google/oauth/callback/",
    }


def bind_workflow(path: Path, binding: dict[str, str], *, apply: bool) -> bool:
    source = path.read_text(encoding="utf-8")
    pattern = r"(?m)^(\s*VITE_CRM_FASTAPI_RELEASE_UID:\s*)[^\n]+$"
    updated, count = re.subn(pattern, lambda match: match[1] + binding["release_uid"], source)
    if count != 1:
        raise RuntimeError("Expected one CRM API release binding in the frontend workflow")
    changed = updated != source
    if changed and apply:
        path.write_text(updated, encoding="utf-8")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frontend_workflow", type=Path)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    context = get_code_repository_context()
    releases = ResourceRelease.filter(
        name="crm", release_kind="fastapi",
        code_repository_branch_uid=context.code_repository_branch_uid,
    )
    try:
        binding = active_binding(context, releases)
        changed = bind_workflow(arguments.frontend_workflow, binding, apply=arguments.apply)
    except RuntimeError as exc:
        parser.exit(1, f"CRM release binding is not ready: {exc}\n")
    print(json.dumps({**binding, "changed": changed, "applied": changed and arguments.apply}))


if __name__ == "__main__":
    main()
