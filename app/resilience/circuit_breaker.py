"""
Lightweight in-process circuit breaker for external data sources.

Prevents repeated expensive calls to unhealthy upstream sources.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger("orca")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 60.0
    half_open_max_calls: int = 1


@dataclass
class CircuitBreakerState:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    half_open_calls: int = 0


class CircuitBreaker:
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitBreakerState()
        self._lock = asyncio.Lock()

    def _is_open(self) -> bool:
        if self._state.state == CircuitState.CLOSED:
            return False
        if self._state.state == CircuitState.OPEN:
            if self._state.opened_at is None:
                return True
            elapsed = (datetime.now(timezone.utc) - self._state.opened_at).total_seconds()
            if elapsed >= self.config.recovery_timeout_seconds:
                self._state.state = CircuitState.HALF_OPEN
                self._state.half_open_calls = 0
                logger.info("Circuit breaker %s moving to half-open", self.name)
                return False
            return True
        if self._state.state == CircuitState.HALF_OPEN:
            return self._state.half_open_calls >= self.config.half_open_max_calls
        return False

    async def call(self, func: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> Any:
        if self._is_open():
            logger.warning("Circuit breaker %s is open, rejecting call", self.name)
            raise RuntimeError(f"circuit_breaker_open: {self.name}")

        async with self._lock:
            if self._state.state == CircuitState.HALF_OPEN:
                if self._state.half_open_calls >= self.config.half_open_max_calls:
                    raise RuntimeError(f"circuit_breaker_open: {self.name}")
                self._state.half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
        except Exception as exc:
            async with self._lock:
                self._state.failure_count += 1
                self._state.last_failure_at = datetime.now(timezone.utc)
                if self._state.failure_count >= self.config.failure_threshold:
                    self._state.state = CircuitState.OPEN
                    self._state.opened_at = datetime.now(timezone.utc)
                    logger.error(
                        "Circuit breaker %s opened after %d failures",
                        self.name,
                        self._state.failure_count,
                    )
            raise exc

        async with self._lock:
            if self._state.state == CircuitState.HALF_OPEN:
                self._state.state = CircuitState.CLOSED
                self._state.failure_count = 0
                self._state.half_open_calls = 0
                logger.info("Circuit breaker %s closed after successful call", self.name)

        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self._state.state.value,
            "failure_count": self._state.failure_count,
            "last_failure_at": self._state.last_failure_at.isoformat() if self._state.last_failure_at else None,
            "opened_at": self._state.opened_at.isoformat() if self._state.opened_at else None,
        }


class CircuitBreakerRegistry:
    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]

    def reset(self, name: str) -> None:
        if name in self._breakers:
            self._breakers[name]._state = CircuitBreakerState()

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        return {name: breaker.to_dict() for name, breaker in self._breakers.items()}


circuit_breakers = CircuitBreakerRegistry()
