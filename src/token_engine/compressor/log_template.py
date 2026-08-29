"""Log template mining — collapse repeated lines (slimctx/caveman-inspired)."""

from __future__ import annotations

import re
from collections import Counter


def mine_log_templates(lines: list[str], *, min_count: int = 3) -> tuple[list[str], int]:
    """Collapse repeated log lines into [×N] template form.

    Returns (processed_lines, lines_collapsed).
    """
    if len(lines) < min_count * 2:
        return lines, 0

    # Normalize for template: replace numbers, hex, paths with placeholders
    def template_key(line: str) -> str:
        s = line.strip()
        s = re.sub(r"\b\d+\b", "#", s)
        s = re.sub(r"0x[0-9a-fA-F]+", "0x#", s)
        s = re.sub(r"/[\w./-]+", "/<path>", s)
        s = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "<ts>", s)
        return s[:120]

    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for line in lines:
        key = template_key(line)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(line)

    out: list[str] = []
    collapsed = 0
    for key in order:
        bucket = groups[key]
        if len(bucket) >= min_count:
            sample = bucket[0].strip()
            if len(sample) > 100:
                sample = sample[:97] + "..."
            out.append(f"[×{len(bucket)}] {sample}")
            collapsed += len(bucket) - 1
        else:
            out.extend(bucket)

    return out, collapsed
