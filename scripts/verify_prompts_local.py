"""Verify Prompt migration/catalog persistence using a private local MetaTables API.

Only developer identity/Team facts are fixtures. The MetaTables API, migrations,
catalog, compiled SQL and SQLite persistence are real. No platform HTTP request
is allowed, and neither the normal developer runtime nor production is selected.
This does not replace the real-provider Tau pre-push gate.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify() -> None:
    from mainsequence.code_repository_context import get_git_source_context
    from metatables import MetaTable, configure_local_client, get_runtime_status
    from metatables.api.app.main import create_app
    from metatables.api.app.runtime import LocalIdentity, RuntimeConfig
    from metatables.api.backend.integrations.local_workspace import LocalWorkspace
    from metatables.compiled_sql.v1 import compile_sqlalchemy_statement
    from metatables.local_connection import (
        clear_development_client,
        publish_development_client,
    )
    from metatables.runtime import initialize_runtime, upgrade_application

    source = get_git_source_context()
    actor = uuid.uuid4()
    original_request = requests.sessions.Session.request

    with tempfile.TemporaryDirectory(prefix="crm-prompts-metatables-") as directory:
        private = Path(directory).resolve()
        config_path = private / "configuration.yaml"
        config_path.write_text(
            "local_mode_available: true\nlocal_credentials:\n  provider: file\n"
            f"  key_directory: {private / 'keys'}\n",
            encoding="utf-8",
        )
        workspace = LocalWorkspace(uuid.uuid4(), source, private / "metatables.sqlite")
        identity = LocalIdentity(actor, workspace, (frozenset(), True), time.monotonic() + 3600)
        token = secrets.token_urlsafe(48)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        config = RuntimeConfig(
            local_mode=True,
            bind_host="127.0.0.1",
            bind_port=port,
            listener_fd=listener.fileno(),
            local_token=token,
            configuration_path=config_path,
        )

        def local_requests(session, method, url, *args, **kwargs):
            if not url.startswith(origin + "/"):
                raise RuntimeError("The isolated Prompt verifier forbids platform/external HTTP")
            return original_request(session, method, url, *args, **kwargs)

        server = None
        thread = None
        launch_id = None
        with (
            patch.dict(os.environ, {"METATABLES_LOCAL_STORAGE_DIR": str(private)}),
            patch("metatables.api.app.runtime.resolve_sdk_identity", return_value=identity),
            patch("requests.sessions.Session.request", local_requests),
        ):
            try:
                server = uvicorn.Server(uvicorn.Config(create_app(config), log_level="error"))
                thread = threading.Thread(
                    target=server.run, kwargs={"sockets": [listener]}, daemon=True
                )
                thread.start()
                for _ in range(200):
                    if server.started:
                        break
                    if not thread.is_alive():
                        raise RuntimeError("Isolated MetaTables API failed to start")
                    time.sleep(0.05)
                if not server.started:
                    raise RuntimeError("Isolated MetaTables API did not start")
                launch_id = publish_development_client(
                    private / "server.json", port=port, token=token
                )
                assert configure_local_client() == origin
                before = get_runtime_status()
                assert before["local_mode"] is True
                assert before["bootstrap"]["candidate"]["configuration"]["path"] == str(
                    workspace.database_path
                )
                initialize_runtime()
                state = get_runtime_status()
                assert state["local_mode"] is True and state["dialect"] == "sqlite"
                assert state["data_source"]["class_type"] == "sqlite"
                assert state["bootstrap"]["active"] is True and not state["data_source_error"]
                result = upgrade_application("src.crm.migrations:migration")
                assert result["revision"] == "0010"
                assert result["data_source_uid"] == state["data_source"]["uid"]

                from src.crm.metatables import MODELS

                prompt = MODELS["prompt"].__table__
                uid = uuid.uuid4()
                markdown = "# Isolated local fixture\n\nLiteral {{ value }} and `code`.\n"
                now = datetime.now(timezone.utc)
                MetaTable.execute_operation(
                    compile_sqlalchemy_statement(
                        prompt.insert().values(
                            uid=uid,
                            name="Owned local fixture",
                            description=None,
                            content_markdown=markdown,
                            version=1,
                            created_at=now,
                            updated_at=now,
                            created_by_uid=actor,
                            updated_by_uid=actor,
                            archived_at=None,
                        ),
                        operation="insert",
                    )
                )
                MetaTable.execute_operation(
                    compile_sqlalchemy_statement(
                        prompt.update()
                        .where(prompt.c.uid == uid, prompt.c.version == 1)
                        .values(content_markdown=markdown + "\nUpdated.\n", version=2),
                        operation="update",
                    )
                )
                child = """
import json, sys
import sqlalchemy as sa
from metatables import MetaTable, configure_local_client, get_runtime_status
from metatables.compiled_sql.v1 import compile_sqlalchemy_statement
configure_local_client()
state = get_runtime_status()
assert state['local_mode'] is True and state['dialect'] == 'sqlite'
assert state['data_source']['uid'] == sys.argv[2]
from src.crm.platform.catalog import CatalogRegistry
from src.crm.metatables import MODELS
registry = CatalogRegistry()
registry.validate()
registry.validate_settings()
assert len(registry.bindings) == 27
table = MODELS['prompt'].__table__
result = MetaTable.execute_operation(compile_sqlalchemy_statement(
    sa.select(table.c.content_markdown, table.c.version).where(table.c.uid == __import__('uuid').UUID(sys.argv[1])),
    operation='select'))
assert result['rows'][0]['version'] == 2
assert result['rows'][0]['content_markdown'] == sys.argv[3]
print(json.dumps({'local_mode': True, 'dialect': 'sqlite', 'bindings': len(registry.bindings), 'version': 2, 'fresh_process': True}))
"""
                fresh = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        child,
                        str(uid),
                        state["data_source"]["uid"],
                        markdown + "\nUpdated.\n",
                    ],
                    cwd=ROOT,
                    env=os.environ.copy(),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if fresh.returncode:
                    raise RuntimeError(
                        "Fresh-process local catalog check failed:\n" + fresh.stderr[-8000:]
                    )
                print(fresh.stdout.strip())
                # Cleanup only the explicitly owned fixture, after verifying its current version.
                MetaTable.execute_operation(
                    compile_sqlalchemy_statement(
                        prompt.delete().where(prompt.c.uid == uid, prompt.c.version == 2),
                        operation="delete",
                    )
                )
                print(json.dumps({"prompt_fixture_cleaned": True, "production_access": False}))
            finally:
                if launch_id:
                    clear_development_client(private / "server.json", launch_id)
                if server:
                    server.should_exit = True
                if thread:
                    thread.join(timeout=10)
                    if thread.is_alive():
                        raise RuntimeError("The owned local MetaTables API did not stop")
                listener.close()


if __name__ == "__main__":
    verify()
