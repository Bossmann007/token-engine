"""Diff compression — focus on changed hunks (caveman-inspired)."""

from __future__ import annotations

import re

from token_engine.compressor.base import CompressResult, Compressor
from token_engine.core.types import ContentType

HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")


class DiffCompressor(Compressor):
    @property
    def name(self) -> str:
        return "diff"

    @property
    def content_types(self) -> set[ContentType]:
        return {ContentType.DIFF}

    def compress(self, text: str, *, aggressiveness: float = 0.5, query: str = "") -> CompressResult:
        lines = text.splitlines()
        if len(lines) <= 30:
            return CompressResult(content=text, strategy=self.name, compressed=False)

        context_lines = max(1, int(3 * (1 - aggressiveness)))
        max_hunks = max(5, int(20 * (1 - aggressiveness * 0.5)))

        header_lines: list[str] = []
        hunks: list[list[str]] = []
        current_hunk: list[str] = []
        in_hunk = False

        for line in lines:
            if line.startswith("diff --git") or line.startswith("---") or line.startswith("+++"):
                header_lines.append(line)
                continue

            if HUNK_HEADER.match(line):
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = [line]
                in_hunk = True
            elif in_hunk:
                current_hunk.append(line)
            else:
                header_lines.append(line)

        if current_hunk:
            hunks.append(current_hunk)

        # Prioritize hunks with actual changes (+/-)
        scored_hunks: list[tuple[int, list[str]]] = []
        for hunk in hunks:
            changes = sum(1 for l in hunk if l.startswith("+") or l.startswith("-"))
            scored_hunks.append((changes, hunk))

        scored_hunks.sort(key=lambda x: -x[0])
        selected = scored_hunks[:max_hunks]

        parts = header_lines[:10]
        for score, hunk in selected:
            trimmed = self._trim_hunk(hunk, context_lines)
            parts.extend(trimmed)

        if len(hunks) > max_hunks:
            parts.append(f"\n... {len(hunks) - max_hunks} more hunks omitted ({len(hunks)} total)")

        out = "\n".join(parts)
        if len(out) >= len(text) * 0.95:
            return CompressResult(content=text, strategy=self.name, compressed=False)

        return CompressResult(content=out, strategy=self.name, lossless=False, compressed=True,
                            metadata={"hunks_total": len(hunks), "hunks_kept": len(selected)})

    def _trim_hunk(self, hunk: list[str], context: int) -> list[str]:
        if len(hunk) <= context * 2 + 5:
            return hunk

        change_indices = [i for i, l in enumerate(hunk) if l.startswith("+") or l.startswith("-")]
        if not change_indices:
            return hunk[: context * 2 + 1]

        keep: set[int] = set()
        for idx in change_indices:
            for j in range(max(0, idx - context), min(len(hunk), idx + context + 1)):
                keep.add(j)

        return [hunk[i] for i in sorted(keep)]
