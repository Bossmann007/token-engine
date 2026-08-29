"""Content router — split mixed content and route to compressors (headroom-inspired)."""

from __future__ import annotations

import re

from token_engine.compressor.detect import detect_content_type
from token_engine.core.types import ContentType


def split_mixed_content(text: str) -> list[tuple[str, ContentType]]:
    """Split text into typed segments for per-segment compression."""
    if not text.strip():
        return []

    # Try to split on obvious boundaries
    segments: list[tuple[str, ContentType]] = []
    current_lines: list[str] = []
    current_type: ContentType | None = None

    def flush() -> None:
        nonlocal current_lines, current_type
        if current_lines:
            content = "\n".join(current_lines)
            ct = current_type or detect_content_type(content)
            segments.append((content, ct))
            current_lines = []
            current_type = None

    for line in text.splitlines():
        line_type = _line_type_hint(line)
        if line_type and current_lines and current_type and line_type != current_type:
            flush()
            current_type = line_type
        elif line_type and not current_type:
            current_type = line_type
        current_lines.append(line)

    flush()

    if len(segments) <= 1:
        return [(text, detect_content_type(text))]

    return segments


def _line_type_hint(line: str) -> ContentType | None:
    if line.startswith("diff --git") or line.startswith("@@"):
        return ContentType.DIFF
    if re.match(r"^\{", line.strip()) or re.match(r"^\[", line.strip()):
        return ContentType.JSON
    if re.search(r"(ERROR|Traceback|FAILED|\d{4}-\d{2}-\d{2})", line):
        return ContentType.LOG
    if re.match(r"^(def |class |import |function )", line):
        return ContentType.CODE
    return None


def route_and_join(
    text: str,
    compress_fn,
    *,
    aggressiveness: float = 0.5,
    query: str = "",
) -> tuple[str, list[str]]:
    """Split, compress each segment, rejoin."""
    segments = split_mixed_content(text)
    if len(segments) == 1:
        result = compress_fn(text, aggressiveness=aggressiveness, query=query)
        return result.content, [result.strategy]

    parts: list[str] = []
    strategies: list[str] = []
    for content, ct in segments:
        result = compress_fn(content, content_type=ct, aggressiveness=aggressiveness, query=query)
        parts.append(result.content)
        strategies.append(result.strategy)

    return "\n\n---\n\n".join(parts), strategies
