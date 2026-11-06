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

