"""Smart cache with TTL, invalidation, and dependency tracking."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: float
    ttl: float
    dependencies: set[str] = field(default_factory=set)
    hits: int = 0

    @property
    def expired(self) -> bool:
        return time.time() > self.created_at + self.ttl


class SmartCache:
    """In-memory cache with TTL and dependency-based invalidation."""

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 10_000) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._dep_index: dict[str, set[str]] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(*parts: str) -> str:
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        if entry.expired:
            self.delete(key)
            self._misses += 1
            return None
        entry.hits += 1
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, *, ttl: float | None = None, dependencies: set[str] | None = None) -> None:
        if len(self._store) >= self._max_entries:
            self._evict_oldest()

        deps = dependencies or set()
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=time.time(),
            ttl=ttl or self._ttl,
            dependencies=deps,
        )
        self._store[key] = entry
        for dep in deps:
            self._dep_index.setdefault(dep, set()).add(key)

    def delete(self, key: str) -> None:
        entry = self._store.pop(key, None)
        if entry:
            for dep in entry.dependencies:
                if dep in self._dep_index:
                    self._dep_index[dep].discard(key)

    def invalidate_dependency(self, dependency: str) -> int:
        """Invalidate all entries depending on a file/path."""
        keys = self._dep_index.pop(dependency, set())
        for key in keys:
            self._store.pop(key, None)
        return len(keys)

    def invalidate_path(self, path: str | Path) -> int:
        p = str(Path(path).resolve())
        count = self.invalidate_dependency(p)
        # Also invalidate parent directory caches
        parent = str(Path(p).parent)
        count += self.invalidate_dependency(parent)
        return count

    def _evict_oldest(self) -> None:
        if not self._store:
            return
        oldest_key = min(self._store, key=lambda k: self._store[k].created_at)
        self.delete(oldest_key)

    @property
    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "entries": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total else 0.0,
        }

    def clear(self) -> None:
        self._store.clear()
        self._dep_index.clear()
