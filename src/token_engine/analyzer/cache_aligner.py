"""Cache prefix volatility detection (headroom cache_aligner-inspired)."""

from __future__ import annotations

import re
import uuid

VOLATILE_PATTERNS = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "uuid"),
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"), "timestamp"),
    (re.compile(r"\b\d{10,13}\b"), "unix_ms"),
    (re.compile(r"session[_-]?id[=:\s]+\S+", re.I), "session_id"),
    (re.compile(r"request[_-]?id[=:\s]+\S+", re.I), "request_id"),
]


def detect_volatile_content(text: str) -> list[dict[str, str]]:
    """Return warnings for content that may break provider prompt cache."""
    warnings: list[dict[str, str]] = []
    for pattern, kind in VOLATILE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            warnings.append({
                "type": kind,
                "count": str(len(matches)),
                "hint": f"Volatile {kind} in context may reduce provider cache hit rate",
            })
    return warnings
