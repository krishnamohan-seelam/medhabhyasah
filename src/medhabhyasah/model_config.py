"""Parent-chosen AI model settings.

Stored as JSON in the app data folder. It holds the provider, model id and
prices only. API keys stay in Windows Credential Manager (see credentials.py).
"""
import json
import re
from dataclasses import dataclass

from medhabhyasah.db import get_data_dir

# Defaults are a starting point only. The parent can change the model id and
# prices in Settings, so the app keeps working when a provider retires a model.
PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "name": "Anthropic",
        "model": "claude-opus-5-5",
        "input_cost_per_mtok": 4.00,
        "output_cost_per_mtok": 20.00,
        "links": [
            {"label": "Anthropic model list",
             "url": "https://docs.anthropic.com/en/docs/about-claude/models"},
            {"label": "Anthropic model deprecations",
             "url": "https://docs.anthropic.com/en/docs/about-claude/model-deprecations"},
            {"label": "Anthropic API keys",
             "url": "https://console.anthropic.com/settings/keys"},
        ],
    },
    "openai": {
        "name": "OpenAI",
        "model": "gpt-5.1",
        "input_cost_per_mtok": 1.25,
        "output_cost_per_mtok": 10.00,
        "links": [
            {"label": "OpenAI model list",
             "url": "https://platform.openai.com/docs/models"},
            {"label": "OpenAI deprecations",
             "url": "https://platform.openai.com/docs/deprecations"},
            {"label": "OpenAI API keys",
             "url": "https://platform.openai.com/api-keys"},
        ],
    },
    "gemini": {
        "name": "Google Gemini",
        "model": "gemini-3.8-flash",
        "input_cost_per_mtok": 0.10,
        "output_cost_per_mtok": 0.40,
        "links": [
            {"label": "Gemini model list",
             "url": "https://ai.google.dev/gemini-api/docs/models"},
            {"label": "Gemini deprecations",
             "url": "https://ai.google.dev/gemini-api/docs/deprecations"},
            {"label": "Google AI Studio API keys",
             "url": "https://aistudio.google.com/apikey"},
        ],
    },
}

_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")


def allowed_link_urls() -> set[str]:
    return {link["url"] for p in PROVIDERS.values() for link in p["links"]}


@dataclass
class ModelSettings:
    provider: str | None
    model: str
    input_cost_per_mtok: float
    output_cost_per_mtok: float


def get_config_path():
    return get_data_dir() / "models.json"


def _read() -> dict:
    try:
        data = json.loads(get_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _number(value, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value) if 0 <= value <= 10_000 else default


def selected_provider() -> str | None:
    provider = _read().get("provider")
    return provider if provider in PROVIDERS else None


def settings_for(provider: str) -> ModelSettings:
    """Model id and prices for a provider: saved values over built-in defaults."""
    default = PROVIDERS[provider]
    saved = _read().get("models", {}).get(provider, {})
    if not isinstance(saved, dict):
        saved = {}
    model = saved.get("model")
    if not isinstance(model, str) or not _MODEL_ID_RE.match(model):
        model = default["model"]
    return ModelSettings(
        provider=provider,
        model=model,
        input_cost_per_mtok=_number(saved.get("input_cost_per_mtok"), default["input_cost_per_mtok"]),
        output_cost_per_mtok=_number(saved.get("output_cost_per_mtok"), default["output_cost_per_mtok"]),
    )


def save(
    provider: str,
    model: str,
    input_cost_per_mtok: float | None = None,
    output_cost_per_mtok: float | None = None,
) -> None:
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider")
    model = model.strip()
    if not _MODEL_ID_RE.match(model):
        raise ValueError("Model id may contain only letters, digits and . _ : / -")
    current = settings_for(provider)
    data = _read()
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    models[provider] = {
        "model": model,
        "input_cost_per_mtok": _number(input_cost_per_mtok, current.input_cost_per_mtok),
        "output_cost_per_mtok": _number(output_cost_per_mtok, current.output_cost_per_mtok),
    }
    data["models"] = models
    data["provider"] = provider
    get_config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def select_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider")
    data = _read()
    data["provider"] = provider
    get_config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
