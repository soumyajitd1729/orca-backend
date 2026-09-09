"""
Lightweight in-memory cache with TTL for marine data sources.

Cache candidates:
- marine observations
- PFZ data
- warnings
- health/source status
- expensive connector metadata
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("orca")


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime] = None
    source: Optional[str] = None
    valid_time: Optional[datetime] = None
    confidence: Optional[float] = None
    status: str = "live"

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status,
            "source": self.source,
            "valid_time": self.valid_time.isoformat() if self.valid_time else None,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired(),
        }


class MarineCache:
    def __init__(self, default_ttl_seconds: int = 300) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                logger.debug("Cache miss for key=%s", key)
                return None
            if entry.is_expired():
                logger.debug("Cache expired for key=%s", key)
                del self._store[key]
                return None
            logger.debug("Cache hit for key=%s", key)
            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
        source: Optional[str] = None,
        valid_time: Optional[datetime] = None,
        confidence: Optional[float] = None,
        status: str = "live",
    ) -> None:
        now = datetime.now(timezone.utc)
        expires_at = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = now + __import__("datetime").timedelta(seconds=ttl_seconds)
        elif self._default_ttl > 0:
            expires_at = now + __import__("datetime").timedelta(seconds=self._default_ttl)

        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=expires_at,
            source=source,
            valid_time=valid_time,
            confidence=confidence,
            status=status,
        )
        async with self._lock:
            self._store[key] = entry
            logger.debug("Cache set for key=%s, ttl=%s", key, ttl_seconds or self._default_ttl)

    async def invalidate(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)
            logger.debug("Cache invalidated for key=%s", key)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
            logger.debug("Cache cleared")

    async def get_stats(self) -> dict[str, Any]:
        async with self._lock:
            total = len(self._store)
            expired = sum(1 for entry in self._store.values() if entry.is_expired())
            return {
                "total_entries": total,
                "expired_entries": expired,
                "active_entries": total - expired,
            }

    async def get_entry(self, key: str) -> Optional[CacheEntry]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._store[key]
                return None
            return entry

    async def get_entries(self, source: Optional[str] = None) -> list[dict[str, Any]]:
        async with self._lock:
            entries = []
            for entry in self._store.values():
                if source is None or entry.source == source:
                    entries.append(entry.to_dict())
            return entries


marine_cache = MarineCache()
