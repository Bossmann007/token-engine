"""Codebase-memory bridge — replace large file reads with graph pointers (CBM pattern)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from token_engine.analyzer.analyzer import TokenAnalyzer
from token_engine.core.types import ContentItem, ContentType

SIGNATURE_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|fn|func|interface|type|struct|enum)\s+\S+",
    re.MULTILINE,
)
IMPORT_RE = re.compile(r"^\s*(?:import|from|use|require|#include)\s+\S+", re.MULTILINE)

DEFAULT_MIN_LINES = 35
DEFAULT_MIN_CHARS = 800


def collapse_large_reads_to_cbm(
    items: list[ContentItem],
    *,
    task_query: str = "",
    min_lines: int = DEFAULT_MIN_LINES,
    min_chars: int = DEFAULT_MIN_CHARS,
    session_code_tokens: int = 0,
    session_min_lines: int = 15,
    session_min_chars: int = 400,
    session_code_threshold: int = 200,
) -> int:
    """Replace exploratory full-file reads with codebase-memory pointers + outline."""
    use_session_thresholds = session_code_tokens >= session_code_threshold
    effective_min_lines = session_min_lines if use_session_thresholds else min_lines
    effective_min_chars = session_min_chars if use_session_thresholds else min_chars

    collapsed = 0
    query_lower = task_query.lower()
    query_terms = {t for t in re.split(r"\W+", query_lower) if len(t) > 2}
    symbol_terms = _extract_symbol_terms(query_lower, query_terms)

    for item in items:
        if item.content_type not in (ContentType.CODE, ContentType.TEXT):
            continue
        if item.metadata.get("cbm_preserved") or item.metadata.get("read_delta"):
            continue

        path = item.source or item.metadata.get("path", "")
        if not path or _is_pointer(item.content):
            continue

        content = item.content
        lines = content.splitlines()
        if len(lines) < effective_min_lines and len(content) < effective_min_chars:
            continue

        if _is_task_focus_file(path, query_lower, query_terms, symbol_terms):
            item.metadata["cbm_preserved"] = True
            continue

        if TokenAnalyzer.CRITICAL_KEYWORDS.search(content):
            item.metadata["cbm_preserved"] = True
            continue

        outline = _extract_outline(content)
        file_name = PurePosixPath(path.replace("\\", "/")).name
        item.content = (
            f"[CBM: {path} — {len(lines)}L omitted. "
            f"Use search_graph/get_code_snippet for {file_name}. "
            f"{outline}]"
        )
        item.metadata["cbm_collapsed"] = True
        item.metadata["cbm_original_lines"] = len(lines)
        collapsed += 1

    return collapsed


def _extract_symbol_terms(query_lower: str, query_terms: set[str]) -> set[str]:
    symbols: set[str] = set()
    for match in re.finditer(r"\b([a-z_][a-z0-9_]{2,})\b", query_lower):
        word = match.group(1)
        if word not in {"the", "and", "fix", "bug", "when", "with", "from", "that", "this"}:
            symbols.add(word)
    return symbols | query_terms


def _is_pointer(content: str) -> bool:
    stripped = content.strip()
    return stripped.startswith("[") and (
        "same as" in stripped
        or stripped.startswith("[CBM:")
        or stripped.startswith("[unchanged:")
        or "same as msg" in stripped
    )


def _is_task_focus_file(path: str, query_lower: str, query_terms: set[str], symbol_terms: set[str] | None = None) -> bool:
    normalized = path.replace("\\", "/")
    file_name = PurePosixPath(normalized).name
    stem = PurePosixPath(normalized).stem
    symbols = symbol_terms or query_terms

    if file_name.lower() in query_lower or normalized.lower() in query_lower:
        return True

    path_parts = {p.lower() for p in normalized.split("/") if p}
    overlap = query_terms & path_parts
    if overlap and (stem.lower() in overlap or file_name.lower() in overlap):
        return True

    if stem.lower() in symbols or file_name.lower() in symbols:
        return True

    return False


def _extract_outline(content: str, *, max_sigs: int = 6, max_imports: int = 4) -> str:
    imports = [m.group(0).strip() for m in IMPORT_RE.finditer(content)][:max_imports]
    sigs = [m.group(0).strip() for m in SIGNATURE_RE.finditer(content)][:max_sigs]

    parts: list[str] = []
    if imports:
        parts.append("imports: " + "; ".join(imports))
    if sigs:
        parts.append("symbols: " + "; ".join(sigs))
    if not parts:
        preview = " ".join(content.split())[:120]
        return preview + ("..." if len(content) > 120 else "")
    return " | ".join(parts)
