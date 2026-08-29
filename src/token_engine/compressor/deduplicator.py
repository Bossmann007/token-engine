"""Content deduplication across messages, files, and tool outputs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


@dataclass
class DedupResult:
    content: str
    duplicates_removed: int = 0
    tokens_saved_estimate: int = 0
    duplicate_pairs: list[tuple[str, str]] = field(default_factory=list)


def _normalize(text: str) -> str:
    """Normalize whitespace for comparison."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _hash_content(text: str) -> str:
    return hashlib.sha256(_normalize(text).encode()).hexdigest()[:16]


def _find_repeated_blocks(text: str, min_lines: int = 3) -> list[tuple[str, int]]:
    """Find repeated multi-line blocks."""
    lines = text.splitlines()
    if len(lines) < min_lines * 2:
        return []

    block_size = min_lines
    counts: dict[str, int] = {}
    blocks: dict[str, str] = {}

    while block_size <= min(len(lines) // 2, 20):
        for i in range(len(lines) - block_size + 1):
            block = "\n".join(lines[i : i + block_size])
            key = _hash_content(block)
            counts[key] = counts.get(key, 0) + 1
            blocks[key] = block
        block_size += 2

    return [(blocks[k], c) for k, c in counts.items() if c > 1]


class Deduplicator:
    """Detect and remove duplicate content."""

    def __init__(self, min_block_lines: int = 3) -> None:
        self._seen_hashes: dict[str, str] = {}
        self._min_block_lines = min_block_lines

    def reset(self) -> None:
        self._seen_hashes.clear()

    def deduplicate_text(self, text: str, *, reference_id: str = "") -> DedupResult:
        """Remove repeated blocks within text."""
        repeated = _find_repeated_blocks(text, self._min_block_lines)
        if not repeated:
            return DedupResult(content=text)

        out = text
        removed = 0
        for block, count in sorted(repeated, key=lambda x: -len(x[0])):
            if count <= 1:
                continue
            marker = f"\n[... repeated block ×{count - 1} omitted ...]\n"
            # Keep first occurrence, replace subsequent
            parts = out.split(block)
            if len(parts) > 2:
                out = parts[0] + block + marker.join(parts[1:])
                removed += count - 1

        return DedupResult(
            content=out,
            duplicates_removed=removed,
            tokens_saved_estimate=int(len(text) - len(out)) // 4,
        )

    def check_cross_item_duplicate(self, content: str, item_id: str) -> tuple[bool, str | None]:
        """Check if content was seen before (cross-item dedup)."""
        h = _hash_content(content)
        if h in self._seen_hashes:
            return True, self._seen_hashes[h]
        self._seen_hashes[h] = item_id
        return False, None

    def find_duplicates_among_items(self, items: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Find duplicate pairs among (id, content) items."""
        hash_to_id: dict[str, str] = {}
        pairs: list[tuple[str, str]] = []

        for item_id, content in items:
            if len(content.strip()) < 50:
                continue
            h = _hash_content(content)
            if h in hash_to_id:
                pairs.append((hash_to_id[h], item_id))
            else:
                hash_to_id[h] = item_id

        return pairs
