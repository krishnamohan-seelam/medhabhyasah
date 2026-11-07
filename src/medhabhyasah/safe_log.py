"""Local error log that never holds API keys.

Raw provider errors can be long or odd, so they go to a log file in the app
data folder instead of the screen. Everything is scrubbed first: stored keys
are removed by exact value, and anything shaped like a key is removed by
pattern. Text is capped so a huge error cannot fill the disk.
"""
import logging
import re
import traceback
from logging.handlers import RotatingFileHandler

from medhabhyasah import credentials
from medhabhyasah.db import get_data_dir

LOG_NAME = "medhabhyasah.log"
_MAX_CHARS = 4000
_REDACTED = "[redacted]"

_KEY_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(x-api-key|x-goog-api-key|authorization|api[_-]?key)(['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+"),
]


def _stored_secrets() -> list[str]:
    secrets = []
    for getter in (credentials.get_api_key, credentials.get_openai_key, credentials.get_gemini_key):
        try:
            value = getter()
        except Exception:
            continue
        if isinstance(value, str) and len(value) >= 8:
            secrets.append(value)
    return secrets


def scrub(text: str) -> str:
    """Remove stored keys and key-shaped strings, then cap the length."""
    for secret in _stored_secrets():
        text = text.replace(secret, _REDACTED)
    for pattern in _KEY_PATTERNS[:4]:
        text = pattern.sub(_REDACTED, text)
    text = _KEY_PATTERNS[4].sub(lambda m: m.group(1) + m.group(2) + _REDACTED, text)
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + " …[truncated]"
    return text


def _logger() -> logging.Logger:
    logger = logging.getLogger("medhabhyasah.errors")
    path = get_data_dir() / LOG_NAME
    current = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    if not current or current[0].baseFilename != str(path):
        for h in current:
            logger.removeHandler(h)
            h.close()
        handler = RotatingFileHandler(path, maxBytes=500_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_exception(context: str, exc: BaseException) -> None:
    """Write a scrubbed record of exc. Never raises: logging must not break the app."""
    try:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _logger().error("%s | %s: %s\n%s", scrub(context), type(exc).__name__, scrub(str(exc)), scrub(detail))
    except Exception:
        pass
