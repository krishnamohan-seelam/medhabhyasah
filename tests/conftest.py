import pytest


@pytest.fixture(autouse=True)
def _isolated_model_config(tmp_path, monkeypatch):
    """Keep tests away from the developer's real models.json."""
    from medhabhyasah import model_config
    monkeypatch.setattr(model_config, "get_config_path", lambda: tmp_path / "models.json")
