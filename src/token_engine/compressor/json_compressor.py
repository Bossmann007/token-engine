"""JSON compression — preserve keys, collapse arrays (caveman-inspired)."""

from __future__ import annotations

import json
import re
from typing import Any

from token_engine.compressor.base import CompressResult, Compressor
from token_engine.core.types import ContentType

SCALAR_TYPES = (str, int, float, bool, type(None))
PROTECTED_ROW = re.compile(
    r"(error|fatal|critical|exception|failed|warning|panic|traceback)",
    re.IGNORECASE,
)


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

        max_array_items = max(2, int(8 * (1 - aggressiveness)))
        max_depth = max(2, int(8 * (1 - aggressiveness * 0.5)))
        query_terms = {t for t in re.split(r"\W+", query.lower()) if len(t) > 2}

        compressed_data = self._compress_value(data, max_array_items, max_depth, 0, query_terms)
        if isinstance(data, list) and isinstance(compressed_data, list) and len(compressed_data) < len(data):
            kept = sum(1 for item in compressed_data if not (isinstance(item, str) and item.startswith("...")))
            compressed_data = {
                "_items": compressed_data,
                "_total": len(data),
                "_omitted": len(data) - kept,
            }
        if isinstance(compressed_data, dict) and "_omitted" in compressed_data:
            # _omitted is recoverable from _total - len(_items); drop for tokens
            compressed_data.pop("_omitted", None)
        out = json.dumps(compressed_data, separators=(",", ":"), ensure_ascii=False)

        if len(out) >= len(text):
            return CompressResult(content=text, strategy=self.name, compressed=False)

        return CompressResult(content=out, strategy=self.name, lossless=False, compressed=True)

    def _compress_value(
        self,
        val: Any,
        max_items: int,
        max_depth: int,
        depth: int,
        query_terms: set[str],
    ) -> Any:
        if depth >= max_depth:
            if isinstance(val, (dict, list)):
                return f"<{type(val).__name__}:{len(val)} items>"
            return val

        if isinstance(val, list):
            if not val:
                return val
            if all(isinstance(x, dict) for x in val):
                return self._compress_object_array(val, max_items, max_depth, depth, query_terms)
            if all(isinstance(x, SCALAR_TYPES) for x in val):
                return self._compress_scalar_array(val, max_items)
            if len(val) <= max_items:
                return [self._compress_value(v, max_items, max_depth, depth + 1, query_terms) for v in val]
            head = [self._compress_value(v, max_items, max_depth, depth + 1, query_terms) for v in val[:max_items]]
            head.append(f"... {len(val) - max_items} more items")
            return head

        if isinstance(val, dict):
            drop = {
                "email", "phone", "address", "avatar", "uuid",
                "page", "per_page", "has_more", "extra_data",
            }
            return {
                k: self._compress_value(v, max_items, max_depth, depth + 1, query_terms)
                for k, v in val.items()
                if query_terms
                or k.lower() not in drop
                or any(t in k.lower() for t in query_terms)
            }

        if isinstance(val, str) and len(val) > 500:
            keep = max(100, int(500 * (1 - 0.3)))
            return val[:keep] + f"... [{len(val) - keep} chars truncated]"

        return val

    def _compress_scalar_array(self, val: list[Any], max_items: int) -> list[Any]:
        if len(val) <= max_items:
            return val
        head = val[:max_items]
        head.append(f"... {len(val) - max_items} more items")
        return head

    def _compress_object_array(
        self,
        items: list[dict[str, Any]],
        max_items: int,
        max_depth: int,
        depth: int,
        query_terms: set[str],
    ) -> list[Any]:
        # One exemplar is enough for shape; query can justify a second
        sample_count = 2 if query_terms and max_items > 3 else 1
        if len(items) <= sample_count:
            return [self._shallow_object(item, max_depth, depth + 1, query_terms) for item in items]

        indices = self._select_object_samples(items, sample_count, query_terms)
        samples = [self._shallow_object(items[i], max_depth, depth + 1, query_terms) for i in indices]
        omitted = len(items) - len(indices)
        if omitted > 0:
            samples.append(f"... {omitted} more objects")
        return samples

    def _select_object_samples(
        self,
        items: list[dict[str, Any]],
        sample_count: int,
        query_terms: set[str],
    ) -> list[int]:
        scores: dict[int, float] = {i: 0.0 for i in range(len(items))}
        scores[0] += 10
        scores[len(items) - 1] += 10
        protected: list[int] = []

        for i, item in enumerate(items):
            row_str = json.dumps(item, separators=(",", ":"))
            if PROTECTED_ROW.search(row_str):
                scores[i] += 1000
                protected.append(i)
            if query_terms:
                row_lower = row_str.lower()
                scores[i] += sum(10 for term in query_terms if term in row_lower)

        # Collect one row per signal, then keep only the worst severities (error/critical).
        _severity = {
            "fatal": 0,
            "panic": 0,
            "error": 1,
            "traceback": 1,
            "critical": 2,
            "exception": 3,
            "failed": 3,
            "warning": 4,
        }
        kept_by_signal: dict[str, int] = {}
        for i in protected:
            item = items[i]
            signal = str(
                item.get("status") or item.get("level") or item.get("severity") or ""
            ).lower()
            if not signal:
                m = PROTECTED_ROW.search(json.dumps(item, separators=(",", ":")))
                signal = m.group(0).lower() if m else f"row{i}"
            kept_by_signal.setdefault(signal, i)
        # Prefer error/critical; keep warning only if nothing worse exists
        has_severe = any(_severity.get(s, 50) <= 2 for s in kept_by_signal)
        selected: set[int] = set()
        for signal, idx in kept_by_signal.items():
            rank = _severity.get(signal, 50)
            if has_severe and rank >= 4:
                continue
            selected.add(idx)
        if len(selected) > sample_count:
            ordered = sorted(
                ((s, i) for s, i in kept_by_signal.items() if i in selected),
                key=lambda kv: (_severity.get(kv[0], 50), kv[1]),
            )[:sample_count]
            selected = {i for _, i in ordered}
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        # Prefer protected/query hits; only pad with first/last when under sample_count
        for i, _ in ranked:
            if len(selected) >= sample_count:
                break
            selected.add(i)
        if not selected:
            selected.add(0)
            selected.add(len(items) - 1)
        return sorted(selected)

    def _shallow_object(
        self,
        obj: dict[str, Any],
        max_depth: int,
        depth: int,
        query_terms: set[str],
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in obj.items():
            key_lower = key.lower()
            query_match = any(term in key_lower for term in query_terms)

            if isinstance(value, dict):
                if (
                    not query_match
                    and depth >= 1
                    and key_lower in {"metadata", "preferences", "extra", "extra_data", "attrs"}
                ):
                    continue  # drop nest entirely
                elif query_match or depth + 1 >= max_depth:
                    out[key] = self._compress_value(value, 2, max_depth, depth + 1, query_terms)
                elif len(json.dumps(value, separators=(",", ":"))) > 80:
                    continue
                else:
                    out[key] = self._compress_value(value, 2, max_depth, depth + 1, query_terms)
            elif isinstance(value, list):
                if query_match:
                    out[key] = self._compress_value(value, 3, max_depth, depth + 1, query_terms)
                elif len(value) > 3:
                    out[key] = f"<list:{len(value)} items>"
                else:
                    out[key] = self._compress_value(value, 2, max_depth, depth + 1, query_terms)
            elif isinstance(value, str) and len(value) > 200:
                out[key] = value[:100] + f"...[{len(value) - 100} chars]"
            else:
                if (
                    not query_match
                    and key_lower in {
                        "email", "phone", "address", "avatar", "uuid",
                        "page", "per_page", "has_more", "extra_data",
                        "metadata", "timestamp", "memory", "host",
                        "preferences", "attrs", "name", "message",
                    }
                ):
                    continue
                out[key] = value
        return out
