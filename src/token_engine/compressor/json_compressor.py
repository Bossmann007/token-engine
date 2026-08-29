"""JSON compression — preserve keys, collapse arrays (caveman-inspired)."""

from __future__ import annotations

import json
from typing import Any

from token_engine.compressor.base import CompressResult, Compressor
from token_engine.core.types import ContentType


class JSONCompressor(Compressor):
    @property
    def name(self) -> str:
        return "json"

    @property
    def content_types(self) -> set[ContentType]:
        return {ContentType.JSON}

    def compress(self, text: str, *, aggressiveness: float = 0.5, query: str = "") -> CompressResult:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return CompressResult(content=text, strategy=self.name, compressed=False)

        max_array_items = max(3, int(10 * (1 - aggressiveness)))
        max_depth = max(2, int(8 * (1 - aggressiveness * 0.5)))

        compressed_data = self._compress_value(data, max_array_items, max_depth, 0)
        out = json.dumps(compressed_data, separators=(",", ":"), ensure_ascii=False)

        if len(out) >= len(text):
            return CompressResult(content=text, strategy=self.name, compressed=False)

        return CompressResult(content=out, strategy=self.name, lossless=False, compressed=True)

    def _compress_value(self, val: Any, max_items: int, max_depth: int, depth: int) -> Any:
        if depth >= max_depth:
            if isinstance(val, (dict, list)):
                return f"<{type(val).__name__}:{len(val)} items>"
            return val

        if isinstance(val, list):
            if len(val) <= max_items:
                return [self._compress_value(v, max_items, max_depth, depth + 1) for v in val]
            head = [self._compress_value(v, max_items, max_depth, depth + 1) for v in val[:max_items]]
            head.append(f"... {len(val) - max_items} more items")
            return head

        if isinstance(val, dict):
            return {k: self._compress_value(v, max_items, max_depth, depth + 1) for k, v in val.items()}

        if isinstance(val, str) and len(val) > 500:
            keep = max(100, int(500 * (1 - 0.3)))
            return val[:keep] + f"... [{len(val) - keep} chars truncated]"

        return val
