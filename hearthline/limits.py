"""In-memory cache and request limits. No network."""

from __future__ import annotations

import threading
import time
from typing import Generic, TypeVar

_T = TypeVar("_T")


class TtlCache(Generic[_T]):
    def __init__(self, ttl_s: float, max_items: int = 200):
        self.ttl = ttl_s
        self.max_items = max_items
        self._data: dict[object, tuple[float, _T]] = {}
        self._lock = threading.Lock()

    def get(self, key: object) -> _T | None:
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None or item[0] < now:
                self._data.pop(key, None)
                return None
            return item[1]

    def set(self, key: object, value: _T) -> None:
        with self._lock:
            if len(self._data) >= self.max_items:
                self._data.clear()
            self._data[key] = (time.monotonic() + self.ttl, value)


class RateLimiter:
    def __init__(self, limit: int, window_s: float):
        self.limit = limit
        self.window = window_s
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [stamp for stamp in self._hits.get(key, []) if now - stamp < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 4000:
                self._hits.clear()
            return True
