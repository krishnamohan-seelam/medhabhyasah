"""Credential Manager access via keyring. API key never leaves this module."""
import keyring

_SERVICE = "medhabhyasah"
_PIN_USER = "parent-pin"
_API_KEY_USER = "anthropic-api-key"


def store_pin(pin: str) -> None:
    keyring.set_password(_SERVICE, _PIN_USER, pin)


def verify_pin(pin: str) -> bool:
    stored = keyring.get_password(_SERVICE, _PIN_USER)
    return stored is not None and stored == pin


def has_pin() -> bool:
    return keyring.get_password(_SERVICE, _PIN_USER) is not None


def store_api_key(api_key: str) -> None:
    keyring.set_password(_SERVICE, _API_KEY_USER, api_key)


def get_api_key() -> str | None:
    return keyring.get_password(_SERVICE, _API_KEY_USER)
