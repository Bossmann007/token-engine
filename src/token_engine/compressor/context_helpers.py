"""Context-level dedup helpers (headroom / token-optimizer / rtk patterns)."""

from __future__ import annotations

import re

from token_engine.analyzer.analyzer import TokenAnalyzer
from token_engine.core.types import ContentItem, ContentType, RelevanceTier

GUTTER_PATTERN = re.compile(r"^(\s*\d+[|:]\s?)(.*)$")

def knapsack_stub(item: ContentItem) -> ContentItem:
    """One-line placeholder when hybrid knapsack drops an item under budget pressure."""
    stub = (
        f"[dropped: {item.id} | {item.tier.value} | "
        f"{item.token_count}tok — knapsack budget; use ccr_retrieve if needed]"
    )
    return ContentItem(
        id=item.id,
        content=stub,
        content_type=ContentType.TEXT,
        source=item.source,
        metadata={**item.metadata, "knapsack_dropped": True, "original_tokens": item.token_count},
        tier=item.tier,
        token_count=len(stub.split()),  # overwritten by caller
        dependencies=item.dependencies,
        timestamp=item.timestamp,
    )


GIT_NOISE_PATH = re.compile(
    r"(?:^|/)(?:node_modules|__pycache__|\.pytest_cache|\.venv|venv|dist|coverage|"
    r"\.idea|\.vscode|\.mypy_cache|\.ruff_cache|build|\.tox|\.nox|htmlcov|"
    r"\.egg-info|\.coverage)(?:/|$)|"
    r"^(?:\*\.(?:pyc|pyo|swp|swo)|\*~|\.DS_Store|Thumbs\.db|"
    r"package-lock\.json|yarn\.lock|pip-log\.txt|pip-delete-this-directory\.txt)$",
    re.IGNORECASE,
)


def strip_line_gutters(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    out: list[str] = []
    changed = False
    for line in lines:
        match = GUTTER_PATTERN.match(line)
        if match:
            out.append(match.group(2))
            changed = True
        else:
            out.append(line)
    return "\n".join(out), changed


def collapse_grep_into_reads(items: list[ContentItem]) -> int:
    """Collapse grep output already covered by an earlier file read."""
    reads: dict[str, str] = {}
    collapsed = 0

    for item in items:
        path = item.source or item.metadata.get("path", "")
        if item.content_type == ContentType.CODE and path:
            reads[path] = item.content

    for item in items:
        if item.content_type != ContentType.SEARCH:
            continue
        if not item.content.strip():
            continue

        lines = [line.strip() for line in item.content.splitlines() if line.strip()]
        if not lines:
            continue

        by_file: dict[str, list[str]] = {}
        for line in lines:
            if ":" not in line:
                continue
            file_path, _, rest = line.partition(":")
            by_file.setdefault(file_path, []).append(rest.strip())

        covered_files: list[str] = []
        for file_path, snippets in by_file.items():
            read_content = reads.get(file_path)
            if not read_content:
                continue
            if all(_grep_snippet_in_read(snippet, read_content) for snippet in snippets):
                covered_files.append(file_path)

        if covered_files and len(covered_files) == len(by_file):
            match_count = len(lines)
            item.content = (
                f"[grep: {match_count} matches in {', '.join(covered_files)} — see earlier read]"
            )
            item.metadata["grep_collapsed"] = True
            collapsed += 1

    return collapsed


def collapse_duplicate_items(items: list[ContentItem], pairs: list[tuple[str, str]]) -> int:
    """Replace duplicate/near-duplicate items with back-references (live-zone safe)."""
    by_id = {item.id: item for item in items}
    collapsed = 0

    for keep_id, dup_id in pairs:
        dup = by_id.get(dup_id)
        keep = by_id.get(keep_id)
        if not dup or not keep:
            continue
        source = dup.source or keep.source or keep_id
        dup.content = f"[same as {keep_id}: {source}]"
        dup.metadata["duplicate_of"] = keep_id
        dup.tier = RelevanceTier.REDUNDANT
        dup.metadata["is_duplicate"] = True
        collapsed += 1

    return collapsed


def collapse_obsolete_items(items: list[ContentItem]) -> int:
    """Compress obsolete/legacy notes to a one-line summary."""
    collapsed = 0
    for item in items:
        if item.tier != RelevanceTier.DISCARDABLE:
            continue
        if not TokenAnalyzer.OBSOLETE_KEYWORDS.search(item.content):
            continue
        preview = " ".join(item.content.split())
        if len(preview) > 80:
            preview = preview[:77] + "..."
        item.content = f"[obsolete note: {preview}]"
        item.metadata["obsolete_collapsed"] = True
        collapsed += 1
    return collapsed


def collapse_superseded_reads(items: list[ContentItem]) -> int:
    """Stub earlier full reads when a later item carries a Myers delta for the same path."""
    delta_index_by_path: dict[str, int] = {}
    for i, item in enumerate(items):
        if item.metadata.get("read_delta") == "read_delta":
            path = (item.source or item.metadata.get("path", "")).strip()
            if path:
                delta_index_by_path[path] = i

    collapsed = 0
    for i, item in enumerate(items):
        path = (item.source or item.metadata.get("path", "")).strip()
        if not path or delta_index_by_path.get(path, -1) <= i:
            continue
        if item.metadata.get("read_delta") in ("read_delta", "unchanged", "subset"):
            continue
        if item.content_type not in (ContentType.CODE, ContentType.TEXT):
            continue
        line_count = item.content.count("\n") + 1 if item.content else 0
        item.content = f"[first read: {path}, {line_count}L — see DELTA below]"
        item.metadata["read_superseded_by_delta"] = True
        collapsed += 1
    return collapsed


def filter_git_noise_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """Split git untracked paths into signal vs boilerplate noise (rtk-inspired)."""
    signal: list[str] = []
    noise: list[str] = []
    for path in paths:
        if GIT_NOISE_PATH.search(path.strip()):
            noise.append(path.strip())
        else:
            signal.append(path.strip())
    return signal, noise


def _grep_snippet_in_read(snippet: str, read_content: str) -> bool:
    """Match grep hit text against a prior read (handles `4: def foo()` gutters)."""
    if snippet in read_content:
        return True
    code_match = re.match(r"\d+:\s*(.+)", snippet)
    if code_match and code_match.group(1).strip() in read_content:
        return True
    return snippet.strip() in read_content
