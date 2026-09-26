"""The operator helper must read Secret state before retrying writes."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

script_path = Path(__file__).resolve().parents[1] / "scripts/configure_google_oauth_secrets.py"
spec = importlib.util.spec_from_file_location("configure_google_oauth_secrets", script_path)
assert spec and spec.loader
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_placeholder_is_replaced_and_verified(monkeypatch):
    state = {"value": "PASTE_GOOGLE_OAUTH_CLIENT_ID"}

    class Record:
        @property
        def value(self):
            return state["value"]

        def delete(self):
            state["value"] = None

    def create(*, name, value, timeout):
        state["value"] = value
        return SimpleNamespace(name=name)

    monkeypatch.setattr(setup.Secret, "get_or_none", lambda **_: Record() if state["value"] else None)
    monkeypatch.setattr(setup.Secret, "create", create)
    setup.replace_placeholder("CRM_GOOGLE_OAUTH_CLIENT_ID", "PASTE_GOOGLE_OAUTH_CLIENT_ID", "client.apps.googleusercontent.com")
    assert state["value"] == "client.apps.googleusercontent.com"


def test_existing_real_secret_is_preserved(monkeypatch):
    class Record:
        value = "someone-else's-value"

        def delete(self):
            pytest.fail("existing configured Secret must not be deleted")

    monkeypatch.setattr(setup.Secret, "get_or_none", lambda **_: Record())
    with pytest.raises(RuntimeError, match="another value"):
        setup.replace_placeholder("CRM_GOOGLE_OAUTH_CLIENT_ID", "PASTE_GOOGLE_OAUTH_CLIENT_ID", "new-value")
