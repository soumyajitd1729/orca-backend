"""
Structured logging utilities for ORCA.

Provides consistent logging format with request_id, agent, status,
duration_ms, source, retry_count, and error category.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional


class RequestContext:
    """Thread-safe request context for logging."""
    _local: Any = None

    def __init__(self) -> None:
        try:
            import contextvars
            self._local = contextvars.ContextVar("request_context", default={})
        except ImportError:
            self._local = None

    def set(self, **kwargs: Any) -> None:
        if self._local is not None:
            current = self._local.get({})
            current.update(kwargs)
            self._local.set(current)

    def get(self) -> dict[str, Any]:
        if self._local is not None:
            return self._local.get({})
        return {}

    def clear(self) -> None:
        if self._local is not None:
            self._local.set({})


request_context = RequestContext()


class StructuredLogger:
    """Wrapper around standard logger with structured context."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _log(self, level: str, message: str, **extra: Any) -> None:
        context = request_context.get()
        log_data = {**context, **extra}
        log_data["message"] = message

        safe_data = {k: v for k, v in log_data.items() if k not in ("api_key", "password", "token", "authorization")}

        getattr(self._logger, level)(
            "%s",
            message,
            extra={"structured": safe_data},
        )

    def debug(self, message: str, **extra: Any) -> None:
        self._log("debug", message, **extra)

    def info(self, message: str, **extra: Any) -> None:
        self._log("info", message, **extra)

    def warning(self, message: str, **extra: Any) -> None:
        self._log("warning", message, **extra)

    def error(self, message: str, **extra: Any) -> None:
        self._log("error", message, **extra)

    def critical(self, message: str, **extra: Any) -> None:
        self._log("critical", message, **extra)


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)


def configure_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
