"""Codebase-memory bridge — replace large file reads with graph pointers (CBM pattern)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from token_engine.analyzer.analyzer import TokenAnalyzer
from token_engine.analyzer.relevance import extract_query_terms, path_matches_task
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
    collapse_irrelevant: bool = True,
) -> int:
    """Replace exploratory full-file reads with codebase-memory pointers + outline."""
    use_session_thresholds = session_code_tokens >= session_code_threshold
    effective_min_lines = session_min_lines if use_session_thresholds else min_lines
    effective_min_chars = session_min_chars if use_session_thresholds else min_chars

    collapsed = 0
    query_terms, symbol_terms, query_lower = extract_query_terms(task_query)

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
        task_focus = path_matches_task(path, query_lower, query_terms, symbol_terms)
        too_small = len(lines) < effective_min_lines and len(content) < effective_min_chars
        if too_small and not (collapse_irrelevant and task_query and not task_focus):
            continue

        if task_focus:
            item.metadata["cbm_preserved"] = True
            continue

        if TokenAnalyzer.CRITICAL_KEYWORDS.search(content):
            item.metadata["cbm_preserved"] = True
            continue

        outline = _extract_outline(content)
        file_name = PurePosixPath(path.replace("\\", "/")).name
        candidate = (
            f"[CBM: {path} — {len(lines)}L omitted. "
            f"Use search_graph/get_code_snippet for {file_name}. "
            f"{outline}]"
        )
        if len(candidate) >= len(content):
            candidate = f"[omit:{path}|{len(lines)}L]"
        item.content = candidate
        item.metadata["cbm_collapsed"] = True
        item.metadata["cbm_original_lines"] = len(lines)
        collapsed += 1

    return collapsed


def _is_pointer(content: str) -> bool:
    stripped = content.strip()
    return stripped.startswith("[") and (
        "same as" in stripped
        or stripped.startswith("[CBM:")
        or stripped.startswith("[unchanged:")
        or "same as msg" in stripped
    )


def _extract_outline(content: str, *, max_sigs: int = 6, max_imports: int = 4) -> str:
    imports = [m.group(0).strip() for m in IMPORT_RE.finditer(content)][:max_imports]
    sigs = [m.group(0).strip() for m in SIGNATURE_RE.finditer(content)][:max_sigs]

    parts: list[str] = []
    if imports:
        parts.append("imports: " + "; ".join(imports))
    if sigs:
        short = []
        for s in sigs:
            name = s.split("(")[0].split()[-1] if "(" in s else s[:40]
            short.append(name[:48])
        parts.append("symbols: " + ", ".join(short))
    if not parts:
        preview = " ".join(content.split())[:120]
        return preview + ("..." if len(content) > 120 else "")
    return " | ".join(parts)
