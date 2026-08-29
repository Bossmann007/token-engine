#!/usr/bin/env python3
"""postToolUse: compress large Shell/Read outputs via token-engine (fail-open)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIN_CHARS = 1500


def _find_output(payload: dict) -> tuple[str, str] | None:
    for key in ("output", "result", "content", "text"):
        val = payload.get(key)
        if isinstance(val, str) and len(val) >= MIN_CHARS:
            return key, val
    tool_result = payload.get("tool_result") or payload.get("toolResult")
    if isinstance(tool_result, dict):
        for key in ("output", "content", "text", "stdout"):
            val = tool_result.get(key)
            if isinstance(val, str) and len(val) >= MIN_CHARS:
                return key, val
    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print("{}")
            return 0
        payload = json.loads(raw)
        found = _find_output(payload)
        if not found:
            print("{}")
            return 0

        sys.path.insert(0, str(ROOT / "src"))
        from token_engine.core.engine import TokenEngine

        _, text = found
        engine = TokenEngine()
        result = engine.optimize(text)
        compressed = result.content
        if len(compressed) >= len(text):
            print("{}")
            return 0

        ratio = (len(text) - len(compressed)) / len(text)
        print(json.dumps({
            "additional_context": (
                f"[token-engine] Tool output compressed {ratio * 100:.0f}% "
                f"({len(text)}→{len(compressed)} chars). Use caveman_retrieve if full text needed."
            ),
        }))
        return 0
    except Exception:
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
