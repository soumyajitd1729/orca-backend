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
from app.resilience.circuit_breaker import circuit_breakers, CircuitBreakerConfig

logger = logging.getLogger("orca")


class ConnectorFailureCategory(str):
    NO_DATA = "no_data"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_ERROR = "upstream_error"
    INVALID_RESPONSE = "invalid_response"


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
    failure_category: Optional[str] = None


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
        self._circuit_breaker = circuit_breakers.get(
            self.__class__.__name__,
            CircuitBreakerConfig(
                failure_threshold=getattr(settings, "CIRCUIT_BREAKER_FAILURE_THRESHOLD", 3),
                recovery_timeout_seconds=getattr(settings, "CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS", 60.0),
            ),
        )

    def _categorize_failure(self, exc: Exception) -> str:
        error_str = str(exc).lower()
        if "timeout" in error_str:
            return ConnectorFailureCategory.TIMEOUT
        if "rate limit" in error_str or "429" in error_str:
            return ConnectorFailureCategory.RATE_LIMITED
        if "no matching results" in error_str or "404" in error_str:
            return ConnectorFailureCategory.NO_DATA
        if "invalid" in error_str or "400" in error_str:
            return ConnectorFailureCategory.INVALID_RESPONSE
        return ConnectorFailureCategory.UPSTREAM_ERROR

    async def fetch(self, **kwargs: Any) -> ConnectorResult:
        attempt = 0
        last_error: str | None = None
        last_exc: Exception | None = None

        while attempt <= self.max_retries:
            attempt += 1
            try:
                async def _do_fetch() -> Any:
                    return await asyncio.wait_for(
                        self._fetch_data(**kwargs),
                        timeout=self.timeout,
                    )

                if hasattr(self, "_circuit_breaker") and self._circuit_breaker is not None:
                    data = await self._circuit_breaker.call(_do_fetch)
                else:
                    data = await _do_fetch()
                return ConnectorResult(
                    status="success",
                    data=data,
                    source_status="live",
                    retrieved_at=datetime.utcnow(),
                )
            except asyncio.TimeoutError:
                last_error = f"timeout after {self.timeout}s"
                last_exc = TimeoutError(last_error)
                logger.warning(
                    "Connector %s timed out on attempt %d/%d",
                    self.__class__.__name__,
                    attempt,
                    self.max_retries + 1,
                )
            except Exception as exc:
                last_error = str(exc)
                last_exc = exc
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

        failure_category = self._categorize_failure(last_exc) if last_exc else ConnectorFailureCategory.UPSTREAM_ERROR
        return ConnectorResult(
            status="error",
            errors=[last_error or "connector failed after retries"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
            failure_category=failure_category,
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
