"""Parse multi-item session payloads for MCP auto-routing."""

from __future__ import annotations

import json
from typing import Any

from token_engine.core.types import ContentItem, ContentType


def try_parse_session(text: str) -> list[ContentItem] | None:
    """Return ContentItems if input looks like a session/messages payload."""
    stripped = text.strip()
    if not stripped.startswith(("[", "{")):
        return None

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None

    if isinstance(data, list):
        if not data:
            return None
        if all(isinstance(x, dict) and ("content" in x or "items" in x) for x in data[:3]):
            return _items_from_list(data)
        if all(isinstance(x, dict) and "role" in x and "content" in x for x in data[:3]):
            return _items_from_messages(data)

    if isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            return _items_from_list(data["items"], name_prefix=data.get("name", "session"))
        if "messages" in data and isinstance(data["messages"], list):
            return _items_from_messages(data["messages"])

    return None


def _items_from_list(items: list[dict[str, Any]], *, name_prefix: str = "session") -> list[ContentItem]:
    out: list[ContentItem] = []
    for i, raw in enumerate(items):
        if "items" in raw:
            continue
        ct = raw.get("content_type", "unknown")
        try:
            content_type = ContentType(ct)
        except ValueError:
            content_type = ContentType.UNKNOWN
        out.append(
            ContentItem(
                id=raw.get("id", f"{name_prefix}_{i}"),
                content=raw.get("content", ""),
                content_type=content_type,
                source=raw.get("source", raw.get("role", "")),
                metadata=dict(raw.get("metadata") or {}),
            )
        )
    return out if out else None  # type: ignore[return-value]


def _items_from_messages(messages: list[dict[str, Any]]) -> list[ContentItem]:
    out: list[ContentItem] = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content)
        out.append(
            ContentItem(
                id=f"msg_{i}",
                content=content,
                content_type=ContentType.MESSAGE,
                source=role,
                metadata={"content_role": role},
            )
        )
    return out
