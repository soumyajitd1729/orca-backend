"""
Base connector abstraction for external marine data sources.

All source-specific connectors inherit from this class and must implement:
- _fetch_data() - source-specific HTTP/data retrieval
- normalize() - convert raw source data to internal schema

This ensures consistent timeout, retry, error handling, and evidence generation
across all marine data connectors.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger("orca")


@dataclass
class ConnectorEvidence:
    source: str
    variable: str
    value: Any
    unit: Optional[str] = None
    valid_time: Optional[datetime] = None
    confidence: Optional[float] = None
    why_it_matters: Optional[str] = None
    url_ref: Optional[str] = None


@dataclass
class ConnectorResult:
    status: str
    data: Any = None
    evidence: list[ConnectorEvidence] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    source_status: str = "unavailable"
    retrieved_at: Optional[datetime] = None
    source_time: Optional[datetime] = None
    stale: bool = False


class BaseConnector(ABC):
    def __init__(
        self,
        base_url: str,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or getattr(settings, "CONNECTOR_TIMEOUT_SECONDS", 10.0)
        self.max_retries = max_retries if max_retries is not None else getattr(settings, "CONNECTOR_MAX_RETRIES", 2)

    async def fetch(self, **kwargs: Any) -> ConnectorResult:
        attempt = 0
        last_error: str | None = None

        while attempt <= self.max_retries:
            attempt += 1
            try:
                data = await asyncio.wait_for(
                    self._fetch_data(**kwargs),
                    timeout=self.timeout,
                )
                return ConnectorResult(
                    status="success",
                    data=data,
                    source_status="live",
                    retrieved_at=datetime.utcnow(),
                )
            except asyncio.TimeoutError:
                last_error = f"timeout after {self.timeout}s"
                logger.warning(
                    "Connector %s timed out on attempt %d/%d",
                    self.__class__.__name__,
                    attempt,
                    self.max_retries + 1,
                )
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Connector %s failed on attempt %d/%d: %s",
                    self.__class__.__name__,
                    attempt,
                    self.max_retries + 1,
                    last_error,
                )

            if attempt > self.max_retries:
                break

            backoff = 2 ** (attempt - 1)
            await asyncio.sleep(backoff)

        return ConnectorResult(
            status="error",
            errors=[last_error or "connector failed after retries"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    @abstractmethod
    async def _fetch_data(self, **kwargs: Any) -> Any:
        """Retrieve raw data from the external source."""
        ...

    def normalize(self, raw: Any, **kwargs: Any) -> ConnectorResult:
        """Convert raw source data into normalized ConnectorResult with evidence."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement generic normalize(). "
            "Use a source-specific normalize_*() method instead."
        )
