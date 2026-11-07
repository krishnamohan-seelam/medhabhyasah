"""Credential Manager access via keyring. API keys never leave this module."""
import hmac

import keyring

_SERVICE = "medhabhyasah"
_PIN_USER = "parent-pin"
_API_KEY_USER = "anthropic-api-key"
_GEMINI_KEY_USER = "gemini-api-key"
_OPENAI_KEY_USER = "openai-api-key"


def store_pin(pin: str) -> None:
    keyring.set_password(_SERVICE, _PIN_USER, pin)


def verify_pin(pin: str) -> bool:
    stored = keyring.get_password(_SERVICE, _PIN_USER)
    return stored is not None and hmac.compare_digest(stored.encode(), pin.encode())


def has_pin() -> bool:
    return keyring.get_password(_SERVICE, _PIN_USER) is not None


# ── Anthropic ─────────────────────────────────────────────────────────────────

def store_api_key(api_key: str) -> None:
    keyring.set_password(_SERVICE, _API_KEY_USER, api_key)


def get_api_key() -> str | None:
    return keyring.get_password(_SERVICE, _API_KEY_USER)


# ── Google Gemini ─────────────────────────────────────────────────────────────

def store_gemini_key(api_key: str) -> None:
    keyring.set_password(_SERVICE, _GEMINI_KEY_USER, api_key)


def get_gemini_key() -> str | None:
    return keyring.get_password(_SERVICE, _GEMINI_KEY_USER)


def has_gemini_key() -> bool:
    return keyring.get_password(_SERVICE, _GEMINI_KEY_USER) is not None


# ── OpenAI ────────────────────────────────────────────────────────────────────

def store_openai_key(api_key: str) -> None:
    keyring.set_password(_SERVICE, _OPENAI_KEY_USER, api_key)


def get_openai_key() -> str | None:
    return keyring.get_password(_SERVICE, _OPENAI_KEY_USER)


def has_openai_key() -> bool:
    return keyring.get_password(_SERVICE, _OPENAI_KEY_USER) is not None


# ── Key routing ──────────────────────────────────────────────────────────────

def store_key_by_prefix(key: str) -> str:
    """Route an API key to the correct Credential Manager slot based on its prefix.

    Returns the provider name ('anthropic', 'openai' or 'gemini').
    """
    if key.startswith("sk-ant-"):
        store_api_key(key)
        return "anthropic"
    if key.startswith("sk-"):
        store_openai_key(key)
        return "openai"
    store_gemini_key(key)
    return "gemini"


# ── Provider detection ────────────────────────────────────────────────────────

def configured_provider() -> str | None:
    """Return 'anthropic', 'openai', 'gemini', or None depending on which key is stored.

    If more than one is stored, Anthropic takes precedence, then OpenAI (set up first).
    """
    if keyring.get_password(_SERVICE, _API_KEY_USER) is not None:
        return "anthropic"
    if keyring.get_password(_SERVICE, _OPENAI_KEY_USER) is not None:
        return "openai"
    if keyring.get_password(_SERVICE, _GEMINI_KEY_USER) is not None:
        return "gemini"
    return None


def has_key_for(provider: str) -> bool:
    if provider == "anthropic":
        return keyring.get_password(_SERVICE, _API_KEY_USER) is not None
    if provider == "openai":
        return keyring.get_password(_SERVICE, _OPENAI_KEY_USER) is not None
    if provider == "gemini":
        return keyring.get_password(_SERVICE, _GEMINI_KEY_USER) is not None
    return False


def get_key_for(provider: str) -> str | None:
    if provider == "anthropic":
        return get_api_key()
    if provider == "openai":
        return get_openai_key()
    if provider == "gemini":
        return get_gemini_key()
    return None
