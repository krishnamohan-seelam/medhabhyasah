import os

import pytest

# TestClient sends Host: testserver; production accepts localhost only.
# Set at import so module-scoped fixtures see it too.
os.environ.setdefault("MEDHABHYASAH_EXTRA_ALLOWED_HOSTS", "testserver")


@pytest.fixture(autouse=True)
def _isolated_model_config(tmp_path, monkeypatch):
    """Keep tests away from the developer's real models.json."""
    from medhabhyasah import model_config
    monkeypatch.setattr(model_config, "get_config_path", lambda: tmp_path / "models.json")


@pytest.fixture(autouse=True)
def _isolated_app_data(tmp_path, monkeypatch):
    """Send the default data folder (database, log) to a temp dir, never the real one."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
