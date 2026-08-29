"""Token Engine MCP server — Caveman-compatible compression tools for Cursor."""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.mcpserver import MCPServer

from token_engine import EngineConfig, QualityLevel, TokenEngine
from token_engine.ccr.store import CCRStore

mcp = MCPServer(
    "token-engine",
    instructions=(
        "Token optimization for AI agents. Use caveman_compress on large tool outputs "
        "(logs, JSON, test results, file reads) before keeping them in context. "
        "Use caveman_retrieve only when you need exact bytes from a recovery_handle."
    ),
)

_ccr = CCRStore()
_session_stats = {
    "compress_calls": 0,
    "tokens_before": 0,
    "tokens_after": 0,
    "retrievals": 0,
}


def _engine(quality: str = "balanced", task_query: str = "") -> TokenEngine:
    return TokenEngine(EngineConfig(
        quality_level=QualityLevel(quality),
        live_zone_mode=True,
        enable_cross_turn_dedup=True,
        enable_smart_crusher=True,
        enable_ccr=False,  # MCP manages CCR store directly
        provider="anthropic",
        model="claude-sonnet-4",
        task_query=task_query,
    ))


def _strip_optimizer_header(text: str) -> str:
    if text.startswith("<!--"):
        parts = text.split("\n", 1)
        return parts[1] if len(parts) > 1 else text
    return text


def _normalize_handle(handle: str) -> str:
    handle = handle.strip()
    m = re.search(r"ccr_[a-f0-9]{12}", handle)
    if m:
        return m.group(0)
    return handle.removeprefix("ccr_").removeprefix("<<ccr:").rstrip(">>")


@mcp.tool(name="caveman_compress")
def caveman_compress(
    input: str,
    content_type: str = "",
    quality: str = "balanced",
    task_query: str = "",
) -> dict[str, Any]:
    """Compress large text (logs, JSON, tool output). Returns compressed, ratio, recovery_handle.

    Fail-closed: unchanged input with ratio 0 if compression doesn't help.
    """
    engine = _engine(quality, task_query)
    tokens_before = engine.count_tokens(input)
    result = engine.optimize(input, content_type=content_type)
    compressed = _strip_optimizer_header(result.content)
    tokens_after = engine.count_tokens(compressed)
    ratio = (tokens_before - tokens_after) / tokens_before if tokens_before else 0.0

    _session_stats["compress_calls"] += 1
    _session_stats["tokens_before"] += tokens_before
    _session_stats["tokens_after"] += tokens_after

    if ratio <= 0 or len(compressed) >= len(input):
        return {
            "compressed": input,
            "ratio": 0,
            "recovery_handle": None,
            "tokens_before": tokens_before,
            "tokens_after": tokens_before,
            "basis": "inferred",
        }

    handle = f"ccr_{_ccr.store(input, metadata={'quality': quality})}"
    return {
        "compressed": compressed,
        "ratio": round(ratio, 4),
        "recovery_handle": handle,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "basis": "inferred",
    }


@mcp.tool(name="caveman_retrieve")
def caveman_retrieve(recovery_handle: str) -> dict[str, Any]:
    """Recover original content from recovery_handle (ccr_* prefix)."""
    raw = _normalize_handle(recovery_handle)
    key = raw.removeprefix("ccr_")
    content = _ccr.retrieve(key)
    if content is None:
        return {"error": f"Unknown recovery handle: {recovery_handle}", "content": None}
    _session_stats["retrievals"] += 1
    return {"content": content, "recovery_handle": recovery_handle}


@mcp.tool(name="caveman_stats")
def caveman_stats() -> dict[str, Any]:
    """Session compression statistics."""
    before = _session_stats["tokens_before"]
    after = _session_stats["tokens_after"]
    ratio = (before - after) / before if before else 0.0
    return {
        "compress_calls": _session_stats["compress_calls"],
        "tokens_before": before,
        "tokens_after": after,
        "tokens_saved": max(0, before - after),
        "ratio": round(ratio, 4),
        "retrievals": _session_stats["retrievals"],
        "basis": "inferred",
        "scope": "session",
    }


@mcp.tool(name="token_engine_analyze")
def token_engine_analyze(input: str) -> dict[str, Any]:
    """Analyze token usage and compression recommendations."""
    engine = _engine()
    result = engine.analyze(input)
    report = result.analysis
    if not report:
        return {"total_tokens": engine.count_tokens(input)}
    return {
        "total_tokens": report.total_tokens,
        "critical_tokens": report.metrics.critical_tokens,
        "redundant_tokens": report.metrics.redundant_tokens,
        "recommendations": report.recommendations,
        "by_type": report.metrics.tokens_by_type,
    }


@mcp.tool(name="token_engine_compact_tools")
def token_engine_compact_tools(tools_json: str) -> dict[str, Any]:
    """Compact MCP tool schemas to reduce token bloat."""
    data = json.loads(tools_json)
    tools = data if isinstance(data, list) else data.get("tools", [])
    engine = _engine()
    compacted, stats = engine.compact_tool_schemas(tools)
    return {"tools": compacted, "stats": stats}


@mcp.tool(name="token_engine_compress")
def token_engine_compress(
    input: str,
    content_type: str = "",
    quality: str = "balanced",
    task_query: str = "",
) -> dict[str, Any]:
    """Alias for caveman_compress."""
    return caveman_compress(input, content_type, quality, task_query)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
