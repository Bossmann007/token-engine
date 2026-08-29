"""Stale read pruning — collapse superseded file reads (headroom-inspired)."""

from __future__ import annotations

import re

from token_engine.core.types import ContentItem, RelevanceTier

_FILE_PATH = re.compile(r"[/\\]|\.(?:py|ts|tsx|js|jsx|go|rs|md|json|yaml|yml|toml|java|rb|php|cs)$", re.I)
_SKIP_SOURCES = frozenset({"user", "system", "assistant", "pytest", "git status", "grep", "notes.md"})


def _is_file_read(item: ContentItem) -> bool:
    path = (item.source or item.metadata.get("path", "")).strip()
    if not path or path in _SKIP_SOURCES:
        return False
    if item.content_type.value not in ("code", "text"):
        return False
    return bool(_FILE_PATH.search(path))


def prune_stale_reads(items: list[ContentItem]) -> list[ContentItem]:
    """Mark older reads of the same file path as stale; keep only the latest."""
    by_path: dict[str, int] = {}

    for idx, item in enumerate(items):
        if not _is_file_read(item):
            continue
        path = (item.source or item.metadata.get("path", "")).strip()
        by_path[path] = idx

    latest_indices = set(by_path.values())
    for idx, item in enumerate(items):
        path = (item.source or item.metadata.get("path", "")).strip()
        if not path or path not in by_path:
            continue
        if idx not in latest_indices:
            item.tier = RelevanceTier.REDUNDANT
            item.metadata["stale_read"] = True

    return items
