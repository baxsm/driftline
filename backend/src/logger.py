import logging
import os
import re
import sys
from typing import Any

_WHITESPACE = re.compile(r"\s+")

_LEVELS = {
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}


def _sanitize(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _format_details(data: Any) -> str:
    if isinstance(data, BaseException):
        return f"{type(data).__name__}: {_sanitize(str(data))}"
    if isinstance(data, (list, tuple)):
        return "Details: " + _sanitize(" | ".join(str(item) for item in data))
    if isinstance(data, dict):
        pairs = " | ".join(f"{key}: {_sanitize(str(value))}" for key, value in data.items())
        return f"Details: {pairs}"
    return f"Details: {_sanitize(str(data))}"


def _configure() -> logging.Logger:
    logger = logging.getLogger("driftline")
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(_LEVELS.get(os.getenv("LOG_LEVEL", "info").lower(), logging.INFO))
    logger.propagate = False
    return logger


_logger = _configure()


def error(path: str, data: Any) -> None:
    _logger.error("[ERROR] Path: %s | %s", path, _format_details(data))


def warn(path: str, data: Any) -> None:
    _logger.warning("[WARN] Path: %s | %s", path, _format_details(data))


def info(path: str, data: Any) -> None:
    _logger.info("[INFO] Path: %s | %s", path, _format_details(data))


def debug(path: str, data: Any) -> None:
    _logger.debug("[DEBUG] Path: %s | %s", path, _format_details(data))
