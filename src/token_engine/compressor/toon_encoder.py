"""TOON-like compact encoding for uniform JSON arrays (caveman/kompact-inspired)."""

from __future__ import annotations

import json
from typing import Any

from token_engine.compressor.base import CompressResult, Compressor
from token_engine.core.types import ContentType


class ToonEncoder(Compressor):
    """Encode uniform JSON arrays of objects as compact tabular text."""

    @property
    def name(self) -> str:
        return "toon"

    @property
    def content_types(self) -> set[ContentType]:
        return {ContentType.JSON}

    def compress(self, text: str, *, aggressiveness: float = 0.5, query: str = "") -> CompressResult:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return CompressResult(content=text, strategy=self.name, compressed=False)

        encoded = self._encode(data)
        if encoded is None:
            return CompressResult(content=text, strategy=self.name, compressed=False)

        if len(encoded) >= len(text):
            return CompressResult(content=text, strategy=self.name, compressed=False)

        return CompressResult(content=encoded, strategy=self.name, lossless=True, compressed=True)

    def _encode(self, data: Any) -> str | None:
        if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
            keys = list(data[0].keys())
            if not all(set(d.keys()) == set(keys) for d in data[1:10]):
                return None
            header = "\t".join(keys)
            rows = []
            for item in data:
                rows.append("\t".join(self._cell(item.get(k)) for k in keys))
            return f"# TOON {len(data)} rows\n{header}\n" + "\n".join(rows)
        return None

    @staticmethod
    def _cell(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, (dict, list)):
            return json.dumps(val, separators=(",", ":"))
        return str(val).replace("\t", " ").replace("\n", " ")
