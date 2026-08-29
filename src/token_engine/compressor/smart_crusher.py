"""SmartCrusher — statistical JSON array compression (headroom-inspired, Python)."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from token_engine.compressor.base import CompressResult, Compressor
from token_engine.core.types import ContentType

ERROR_KEYS = re.compile(r"(error|fail|exception|status|level|severity|code)", re.I)
PROTECTED_PATTERNS = re.compile(
    r"(error|fatal|critical|exception|failed|panic|traceback)", re.I
)


class SmartCrusher(Compressor):
    """Statistical JSON array crusher — preserves anomalies, errors, change points."""

    @property
    def name(self) -> str:
        return "smart_crusher"

    @property
    def content_types(self) -> set[ContentType]:
        return {ContentType.JSON}

    def compress(self, text: str, *, aggressiveness: float = 0.5, query: str = "") -> CompressResult:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return CompressResult(content=text, strategy=self.name, compressed=False)

        if not isinstance(data, list) or len(data) < 5:
            # Try dict with array values
            if isinstance(data, dict):
                compressed = self._compress_dict_arrays(data, aggressiveness, query)
                if compressed is not None:
                    out = json.dumps(compressed, separators=(",", ":"), ensure_ascii=False)
                    if len(out) < len(text):
                        return CompressResult(
                            content=out, strategy=self.name, lossless=False, compressed=True,
                            metadata={"strategy_detail": "dict_arrays"},
                        )
            return CompressResult(content=text, strategy=self.name, compressed=False)

        keep_ratio = max(0.05, 1.0 - aggressiveness * 0.9)
        max_keep = max(5, int(len(data) * keep_ratio))

        kept_indices = self._select_rows(data, max_keep, query)
        kept = [data[i] for i in sorted(kept_indices)]

        # Constant field factoring
        constants = self._extract_constants(data)
        result: dict[str, Any] = {"_items": kept, "_total": len(data), "_kept": len(kept)}
        if constants:
            result["_constants"] = constants
        if len(kept) < len(data):
            result["_omitted"] = len(data) - len(kept)

        out = json.dumps(result, separators=(",", ":"), ensure_ascii=False)
        if len(out) >= len(text):
            return CompressResult(content=text, strategy=self.name, compressed=False)

        return CompressResult(
            content=out,
            strategy=self.name,
            lossless=False,
            compressed=True,
            metadata={"rows_total": len(data), "rows_kept": len(kept)},
        )

    def _select_rows(self, rows: list[Any], max_keep: int, query: str) -> set[int]:
        n = len(rows)
        if n <= max_keep:
            return set(range(n))

        scores: dict[int, float] = {i: 0.0 for i in range(n)}

        # Always keep first and last
        scores[0] += 100
        scores[n - 1] += 100

        # Error/audit-safe rows
        for i, row in enumerate(rows):
            row_str = json.dumps(row) if not isinstance(row, str) else row
            if PROTECTED_PATTERNS.search(row_str):
                scores[i] += 1000

        # Query relevance
        if query:
            q_terms = set(query.lower().split())
            for i, row in enumerate(rows):
                row_str = json.dumps(row).lower() if not isinstance(row, str) else row.lower()
                overlap = sum(1 for t in q_terms if t in row_str)
                scores[i] += overlap * 10

        # Numeric variance outliers
        numeric_fields = self._find_numeric_fields(rows)
        for field in numeric_fields:
            values = []
            for i, row in enumerate(rows):
                if isinstance(row, dict) and field in row:
                    v = row[field]
                    if isinstance(v, (int, float)) and not math.isnan(float(v)):
                        values.append((i, float(v)))
            if len(values) < 3:
                continue
            nums = [v for _, v in values]
            mean = sum(nums) / len(nums)
            variance = sum((x - mean) ** 2 for x in nums) / len(nums)
            if variance < 1e-9:
                continue
            std = math.sqrt(variance)
            for i, v in values:
                z = abs(v - mean) / std if std > 0 else 0
                if z > 2.0:
                    scores[i] += z * 5

        # Top-N by score
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return {i for i, _ in ranked[:max_keep]}

    def _find_numeric_fields(self, rows: list[Any]) -> list[str]:
        if not rows or not isinstance(rows[0], dict):
            return []
        candidates = set(rows[0].keys())
        for row in rows[1:10]:
            if isinstance(row, dict):
                candidates &= set(row.keys())
        numeric = []
        for field in candidates:
            if ERROR_KEYS.search(field):
                continue
            count = 0
            for row in rows[:20]:
                if isinstance(row, dict) and isinstance(row.get(field), (int, float)):
                    count += 1
            if count >= 3:
                numeric.append(field)
        return numeric[:5]

    def _extract_constants(self, rows: list[Any]) -> dict[str, Any]:
        if not rows or not isinstance(rows[0], dict):
            return {}
        constants: dict[str, Any] = {}
        for key in rows[0]:
            vals = {json.dumps(r.get(key), sort_keys=True) for r in rows if isinstance(r, dict) and key in r}
            if len(vals) == 1:
                constants[key] = rows[0].get(key)
        return constants

    def _compress_dict_arrays(self, data: dict, aggressiveness: float, query: str) -> dict | None:
        out = dict(data)
        changed = False
        for key, val in data.items():
            if isinstance(val, list) and len(val) >= 5:
                keep_ratio = max(0.05, 1.0 - aggressiveness * 0.9)
                max_keep = max(5, int(len(val) * keep_ratio))
                kept_indices = self._select_rows(val, max_keep, query)
                out[key] = [val[i] for i in sorted(kept_indices)]
                if len(out[key]) < len(val):
                    out[f"_{key}_total"] = len(val)
                    changed = True
        return out if changed else None
