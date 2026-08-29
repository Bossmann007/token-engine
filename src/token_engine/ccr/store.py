"""CCR — Compression Cache Recovery store (headroom-inspired)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CCREntry:
    handle: str
    content: str
    created_at: float
    metadata: dict[str, Any] = field(default_factory=dict)


class CCRStore:
    """Reversible compression store. Aggressive compressors offload content here."""

    def __init__(self, ttl_seconds: int = 1800, max_entries: int = 5000) -> None:
        self._store: dict[str, CCREntry] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries

    @staticmethod
    def make_handle(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def store(self, content: str, *, metadata: dict[str, Any] | None = None) -> str:
        handle = self.make_handle(content)
        if len(self._store) >= self._max_entries:
            self._evict_oldest()
        self._store[handle] = CCREntry(
            handle=handle,
            content=content,
            created_at=time.time(),
            metadata=metadata or {},
        )
        return handle

    def retrieve(self, handle: str) -> str | None:
        entry = self._store.get(handle)
        if entry is None:
            return None
        if time.time() - entry.created_at > self._ttl:
            del self._store[handle]
            return None
        return entry.content

    def marker(self, handle: str, *, rows_dropped: int = 0, chars_dropped: int = 0) -> str:
        parts = [f"<<ccr:{handle}"]
        if rows_dropped:
            parts.append(f" {rows_dropped}_rows")
        if chars_dropped:
            parts.append(f" {chars_dropped}_chars")
        parts.append(">>")
        return "".join(parts)

    def _evict_oldest(self) -> None:
        if not self._store:
            return
        oldest = min(self._store, key=lambda k: self._store[k].created_at)
        del self._store[oldest]

    @property
    def stats(self) -> dict[str, int]:
        return {"entries": len(self._store)}

    def clear(self) -> None:
        self._store.clear()
