"""Shared 10 MiB rotating-file logging for the managed local service."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import unquote_plus


MAX_LOG_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
_SENSITIVE_QUERY_KEYS = (
    "access_token",
    "refresh_token",
    "authorization_code",
    "app_secret",
    "client_secret",
    "signature",
    "state",
    "sign",
    "code",
)
_SENSITIVE_QUERY_KEY_SET = frozenset(_SENSITIVE_QUERY_KEYS)
_QUERY_PARAMETER_RE = re.compile(
    r"(?P<prefix>[?&])(?P<key>[^=&#\s\"']+)=(?P<value>[^&#\s\"']*)"
)


def _redact_query_secrets(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        try:
            decoded_key = unquote_plus(match.group("key")).lower()
        except (UnicodeDecodeError, ValueError):
            return match.group(0)
        if decoded_key not in _SENSITIVE_QUERY_KEY_SET:
            return match.group(0)
        return f'{match.group("prefix")}{match.group("key")}=[REDACTED]'

    return _QUERY_PARAMETER_RE.sub(replace, value)


def _redact_logging_value(value):
    if isinstance(value, str):
        return _redact_query_secrets(value)
    if isinstance(value, tuple):
        return tuple(_redact_logging_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_logging_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_logging_value(item) for key, item in value.items()}
    return value


class OAuthQueryRedactionFilter(logging.Filter):
    """Remove OAuth and credential-like query values before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_query_secrets(record.msg)
        record.args = _redact_logging_value(record.args)
        return True


def _ensure_redaction_filter(target) -> None:
    if not any(isinstance(item, OAuthQueryRedactionFilter) for item in target.filters):
        target.addFilter(OAuthQueryRedactionFilter())


def build_rotating_handler(path: str | Path) -> RotatingFileHandler:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        target,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    _ensure_redaction_filter(handler)
    return handler


def configure_runtime_logging(path: str | Path, *, level: int = logging.INFO) -> logging.Logger:
    target = str(Path(path).resolve())
    root = logging.getLogger()
    root.setLevel(level)
    if not any(
        isinstance(handler, RotatingFileHandler)
        and str(Path(getattr(handler, "baseFilename", "")).resolve()) == target
        for handler in root.handlers
    ):
        root.addHandler(build_rotating_handler(target))
    for handler in root.handlers:
        _ensure_redaction_filter(handler)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        _ensure_redaction_filter(uvicorn_logger)
    return root
