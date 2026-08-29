"""Stale read pruning — collapse superseded file reads (headroom-inspired)."""

from __future__ import annotations

from token_engine.core.types import ContentItem, RelevanceTier


def prune_stale_reads(items: list[ContentItem]) -> list[ContentItem]:
    """Mark older reads of the same path as REDUNDANT; keep only the latest."""
    by_path: dict[str, int] = {}

    for idx, item in enumerate(items):
        path = item.source or item.metadata.get("path", "")
        if not path:
            continue
        if item.content_type.value not in ("code", "text", "unknown"):
            continue
        by_path[path] = idx

    latest_indices = set(by_path.values())
    for idx, item in enumerate(items):
        path = item.source or item.metadata.get("path", "")
        if path and idx not in latest_indices:
            item.tier = RelevanceTier.REDUNDANT
            item.metadata["stale_read"] = True

    return items
