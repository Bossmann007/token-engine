"""Myers diff for file re-reads (TokenDamper/token-optimizer-inspired)."""

from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass
class DeltaResult:
    content: str
    is_delta: bool
    lines_added: int = 0
    lines_removed: int = 0
    strategy: str = "passthrough"


class ReadDelta:
    """Track file contents and return unified diff on re-read."""

    def __init__(self) -> None:
        self._versions: dict[str, str] = {}

    def reset(self) -> None:
        self._versions.clear()

    def process(self, path: str, new_content: str, *, context_lines: int = 3) -> DeltaResult:
        path = path.strip()
        old = self._versions.get(path)

        if old is None:
            self._versions[path] = new_content
            return DeltaResult(content=new_content, is_delta=False, strategy="first_read")

        if old == new_content:
            return DeltaResult(
                content=f"[unchanged: {path}]",
                is_delta=True,
                strategy="unchanged",
            )

        old_lines = old.splitlines()
        new_lines = new_content.splitlines()
        diff = list(difflib.unified_diff(
            [l + "\n" for l in old_lines],
            [l + "\n" for l in new_lines],
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=context_lines,
        ))

        if not diff:
            self._versions[path] = new_content
            return DeltaResult(content=f"[unchanged: {path}]", is_delta=True, strategy="unchanged")

        diff_text = "".join(diff)
        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

        header_overhead = 80  # unified diff headers
        if len(diff_text) >= len(new_content) + header_overhead:
            self._versions[path] = new_content
            return DeltaResult(content=new_content, is_delta=False, strategy="passthrough")

        self._versions[path] = new_content
        header = f"=== DELTA {path} (+{added}/-{removed}) ===\n"
        return DeltaResult(
            content=header + diff_text,
            is_delta=True,
            lines_added=added,
            lines_removed=removed,
            strategy="read_delta",
        )
