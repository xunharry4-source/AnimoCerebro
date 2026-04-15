from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Any


class CacheNamespace(StrEnum):
    SESSION = "session"
    STATE = "state"
    TRANSCRIPT_SUMMARY = "transcript_summary"


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float

    def is_expired(self, now: float) -> bool:
        return now >= self.expires_at


class WebConsoleCacheManager:
    """Small in-process cache for facade-backed web_console reads."""

    def __init__(self, *, default_ttl_seconds: int = 3600):
        self._default_ttl_seconds = max(int(default_ttl_seconds), 1)
        self._entries: dict[tuple[str, str], _CacheEntry] = {}
        self._lock = RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "expirations": 0,
            "sets": 0,
            "invalidations": 0,
        }

    def get(self, namespace: CacheNamespace, key: str) -> Any | None:
        compound_key = (str(namespace), key)
        now = time.time()
        with self._lock:
            entry = self._entries.get(compound_key)
            if entry is None:
                self._stats["misses"] += 1
                return None
            if entry.is_expired(now):
                self._entries.pop(compound_key, None)
                self._stats["misses"] += 1
                self._stats["expirations"] += 1
                return None
            self._stats["hits"] += 1
            return entry.value

    def set(
        self,
        namespace: CacheNamespace,
        key: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        ttl = max(int(ttl_seconds or self._default_ttl_seconds), 1)
        compound_key = (str(namespace), key)
        with self._lock:
            self._entries[compound_key] = _CacheEntry(value=value, expires_at=time.time() + ttl)
            self._stats["sets"] += 1

    def invalidate_namespace(
        self,
        namespace: CacheNamespace,
        *,
        key_prefix: str | None = None,
    ) -> int:
        with self._lock:
            matching_keys = [
                compound_key
                for compound_key in self._entries
                if compound_key[0] == str(namespace)
                and (key_prefix is None or compound_key[1].startswith(key_prefix))
            ]
            for compound_key in matching_keys:
                self._entries.pop(compound_key, None)
            self._stats["invalidations"] += len(matching_keys)
            return len(matching_keys)

    def clear(self) -> None:
        with self._lock:
            removed = len(self._entries)
            self._entries.clear()
            self._stats["invalidations"] += removed

    def get_stats(self) -> dict[str, int | float]:
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total_requests if total_requests else 0.0
            return {
                **self._stats,
                "current_size": len(self._entries),
                "total_requests": total_requests,
                "hit_rate": hit_rate,
            }
