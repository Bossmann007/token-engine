"""Shared task-query relevance helpers (path, symbol, content overlap)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from token_engine.core.types import ContentItem, ContentType
from token_engine.optimizer.read_lifecycle import _is_file_read

STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "when", "fix", "bug",
    "use", "not", "are", "was", "has", "have", "been", "into", "than", "then",
})

SYMBOL_NOISE = frozenset({
    "the", "and", "fix", "bug", "when", "with", "from", "that", "this", "test",
    "file", "src", "api", "returns", "instead", "flaky", "special", "characters",
})


def extract_query_terms(task_query: str) -> tuple[set[str], set[str], str]:
    """Return (word_terms, symbol_terms, query_lower)."""
    query_lower = task_query.lower()
    query_terms = {t for t in re.split(r"\W+", query_lower) if len(t) > 2} - STOPWORDS
    symbol_terms: set[str] = set()
    for match in re.finditer(r"\b([a-z_][a-z0-9_]{2,})\b", query_lower):
        word = match.group(1)
        if word not in SYMBOL_NOISE:
            symbol_terms.add(word)
    for segment in re.findall(r"[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|md)", query_lower):
        stem = PurePosixPath(segment.replace("\\", "/")).stem.lower()
        if len(stem) > 2:
            symbol_terms.add(stem)
        for part in segment.replace("\\", "/").split("/"):
            if len(part) > 2:
                query_terms.add(part.lower())
    return query_terms, symbol_terms | query_terms, query_lower


def path_matches_task(
    path: str,
    query_lower: str,
    query_terms: set[str],
    symbol_terms: set[str] | None = None,
) -> bool:
    normalized = path.replace("\\", "/")
    file_name = PurePosixPath(normalized).name
    stem = PurePosixPath(normalized).stem
    symbols = symbol_terms or query_terms

    if file_name.lower() in query_lower or normalized.lower() in query_lower:
        return True

    path_parts = {p.lower() for p in normalized.split("/") if p and len(p) > 2}
    overlap = query_terms & path_parts
    if overlap and (stem.lower() in overlap or file_name.lower() in overlap):
        return True

    if stem.lower() in symbols or file_name.lower() in symbols:
        return True

    return False


def content_overlap_ratio(content: str, query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    content_terms = {t for t in re.split(r"\W+", content.lower()) if len(t) > 2}
    return len(query_terms & content_terms) / max(len(query_terms), 1)


def is_file_read_item(item: ContentItem) -> bool:
    if item.content_type not in (ContentType.CODE, ContentType.TEXT):
        return False
    path = (item.source or item.metadata.get("path", "")).strip()
    return bool(path) and _is_file_read(item)


def score_path_relevance(item: ContentItem, task_query: str) -> float | None:
    """0.0 = unrelated file read, 1.0 = path match. None if not a file read."""
    if not task_query or not is_file_read_item(item):
        return None
    path = (item.source or item.metadata.get("path", "")).strip()
    query_terms, symbol_terms, query_lower = extract_query_terms(task_query)
    if path_matches_task(path, query_lower, query_terms, symbol_terms):
        return 1.0
    overlap = content_overlap_ratio(item.content, query_terms)
    if overlap > 0.15:
        return 0.5 + overlap
    return 0.0
