"""Isolate persisted CRM configuration in tests that change module activation."""

import pytest

from src.crm.config import crm_config


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "crm.yaml"
    monkeypatch.setattr("src.crm.config.CONFIG_PATH", path)

    def write(*, solution_selling=True, google_workspace=True):
        path.write_text(
            "extensions:\n"
            f"  solution_selling:\n    active: {str(solution_selling).lower()}\n"
            f"  google_workspace:\n    active: {str(google_workspace).lower()}\n",
            encoding="utf-8",
        )
        crm_config.cache_clear()

    write()
    yield write
    crm_config.cache_clear()
