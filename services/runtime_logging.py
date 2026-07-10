"""Shared 10 MiB rotating-file logging for the managed local service."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


MAX_LOG_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5


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
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    return root
