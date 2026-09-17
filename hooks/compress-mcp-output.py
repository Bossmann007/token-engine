#!/usr/bin/env python3
"""postToolUse: compress MCP tool outputs via updated_mcp_tool_output (fail-open).

Requires Cursor to honor updated_mcp_tool_output (verified with marker test).
Skips when output is small, already compact, or looks RTK-pre-filtered.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_MARKER_SKIP = "rtk already"

_TE_SRC_CANDIDATES = (
    Path.home() / ".cursor/repos/token-engine/src",
    Path.home() / "token-engine/src",
    Path(__file__).resolve().parents[1] / "src",  # repo checkout layout
)


def _ensure_te_path() -> None:
    for candidate in _TE_SRC_CANDIDATES:
        if candidate.is_dir():
            sys.path.insert(0, str(candidate))
            return


def _read_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _unwrap_mcp_text(tool_output: object) -> tuple[str | None, dict | None]:
    """Return (text, envelope) where envelope is the object shape to rewrite."""
    if isinstance(tool_output, dict):
        # already object
        content = tool_output.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and isinstance(first.get("text"), str):
                return first["text"], tool_output
        text = tool_output.get("text")
        if isinstance(text, str):
            return text, tool_output
        return None, None

    if not isinstance(tool_output, str) or not tool_output.strip():
        return None, None

    # Cursor often JSON-stringifies the MCP envelope into tool_output
    try:
        parsed = json.loads(tool_output)
    except json.JSONDecodeError:
        return tool_output, None

    if isinstance(parsed, dict):
        text, _ = _unwrap_mcp_text(parsed)
        return text, parsed if text is not None else None
    return tool_output, None


def _looks_rtk_filtered(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    # Ultra-short summaries typical of RTK pipe filters
    if len(lines) <= 3 and len(text) < 240:
        if lines[0].startswith(("Pytest:", "Jest:", "Tests:", "PASS", "FAIL")):
            return True
    if text.lstrip().startswith("rtk:") or " [rtk " in text:
        return True
    return False


def main() -> None:
    payload = _read_payload()
    tool_output = payload.get("tool_output")
    text, envelope = _unwrap_mcp_text(tool_output)
    if not text or len(text) < 800:
        print("{}")
        return
    if _looks_rtk_filtered(text):
        print("{}")
        return

    _ensure_te_path()
    try:
        from token_engine.compressor.tool_output_compressor import ToolOutputCompressor
        from token_engine.core.config import EngineConfig

        cfg = EngineConfig.default()
        result = ToolOutputCompressor(enable_rtk=cfg.enable_rtk_filters).compress(
            text, aggressiveness=cfg.compression_aggressiveness()
        )
        if not result.compressed or len(result.content) >= len(text):
            print("{}")
            return
        # Prefer object envelope (Cursor schema: updated_mcp_tool_output is object)
        if envelope is not None and isinstance(envelope.get("content"), list):
            new_env = dict(envelope)
            new_content = []
            replaced = False
            for part in envelope["content"]:
                if not replaced and isinstance(part, dict) and part.get("type") == "text":
                    new_content.append({**part, "text": result.content})
                    replaced = True
                else:
                    new_content.append(part)
            if not replaced:
                new_content = [{"type": "text", "text": result.content}]
            new_env["content"] = new_content
            out_obj = new_env
        else:
            out_obj = {"content": [{"type": "text", "text": result.content}], "isError": False}

        print(
            json.dumps(
                {
                    "updated_mcp_tool_output": out_obj,
                    "additional_context": (
                        f"[token-engine] MCP compressed {len(text)}→{len(result.content)} "
                        f"chars via {result.strategy}"
                    ),
                }
            )
        )
    except Exception:
        print("{}")


if __name__ == "__main__":
    main()
