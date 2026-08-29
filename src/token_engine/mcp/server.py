"""Token Engine MCP server — full stack for Cursor."""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.mcpserver import MCPServer

from token_engine import QualityLevel, TokenEngine
from token_engine.ccr.store import CCRStore
from token_engine.compressor.session_parser import try_parse_session
from token_engine.core.config import EngineConfig
from token_engine.sandbox.executor import execute_and_compress

mcp = MCPServer(
    "token-engine",
    instructions=(
        "Full token optimization. Use codebase-memory for code exploration. "
        "caveman_compress on large outputs. token_engine_sandbox for bulk analysis. "
        "token_engine_compact_tools for MCP schema bloat."
    ),
)

_ccr = CCRStore()
_lazy_sessions: dict[str, str] = {}
_session_stats = {
    "compress_calls": 0,
    "tokens_before": 0,
    "tokens_after": 0,
    "retrievals": 0,
}


def _engine(quality: str = "balanced", task_query: str = "") -> TokenEngine:
    config = EngineConfig.default()
    config.quality_level = QualityLevel(quality)
    config.task_query = task_query
    config.enable_ccr = False
    return TokenEngine(config)


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


def _compress_result_payload(
    engine: TokenEngine,
    original: str,
    compressed: str,
    *,
    quality: str,
    store_ccr: bool = True,
) -> dict[str, Any]:
    tokens_before = engine.count_tokens(original)
    tokens_after = engine.count_tokens(compressed)
    ratio = (tokens_before - tokens_after) / tokens_before if tokens_before else 0.0

    _session_stats["compress_calls"] += 1
    _session_stats["tokens_before"] += tokens_before
    _session_stats["tokens_after"] += tokens_after

    if ratio <= 0 or len(compressed) >= len(original):
        return {
            "compressed": original,
            "ratio": 0,
            "recovery_handle": None,
            "tokens_before": tokens_before,
            "tokens_after": tokens_before,
            "basis": "inferred",
        }

    handle = None
    if store_ccr:
        handle = f"ccr_{_ccr.store(original, metadata={'quality': quality})}"
    return {
        "compressed": compressed,
        "ratio": round(ratio, 4),
        "recovery_handle": handle,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "basis": "inferred",
    }


@mcp.tool(name="token_engine_compress_session")
def token_engine_compress_session(
    items_json: str,
    quality: str = "balanced",
    task_query: str = "",
) -> dict[str, Any]:
    """Compress a multi-item agent session (read-delta, dedup, query-slice, knapsack)."""
    data = json.loads(items_json)
    raw_items = data if isinstance(data, list) else data.get("items", [])
    if not raw_items:
        return {"error": "No items in payload", "compressed": ""}

    engine = _engine(quality, task_query)
    result = engine.optimize_context(raw_items)
    original = json.dumps(raw_items)
    return {
        **_compress_result_payload(engine, original, result.content, quality=quality),
        "items_in": len(raw_items),
        "items_out": len(result.items or []),
        "mode": "session",
    }


@mcp.tool(name="caveman_compress")
def caveman_compress(
    input: str,
    content_type: str = "",
    quality: str = "balanced",
    task_query: str = "",
) -> dict[str, Any]:
    """Compress large text or auto-detect session JSON/messages payloads."""
    session_items = try_parse_session(input)
    if session_items and len(session_items) > 1:
        engine = _engine(quality, task_query)
        result = engine.optimize_context(session_items)
        return {
            **_compress_result_payload(engine, input, result.content, quality=quality),
            "mode": "session_auto",
            "items": len(session_items),
        }

    engine = _engine(quality, task_query)
    result = engine.optimize(input, content_type=content_type)
    compressed = _strip_optimizer_header(result.content)
    return _compress_result_payload(engine, input, compressed, quality=quality)


@mcp.tool(name="caveman_retrieve")
def caveman_retrieve(recovery_handle: str) -> dict[str, Any]:
    """Recover original from recovery_handle."""
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
    """Analyze tokens and get recommendations."""
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
def token_engine_compact_tools(
    tools_json: str,
    mode: str = "compact",
    level: str = "medium",
) -> dict[str, Any]:
    """Compact MCP tool schemas. mode=lazy returns catalog + session_id for on-demand lookup."""
    data = json.loads(tools_json)
    tools = data if isinstance(data, list) else data.get("tools", [])
    engine = _engine()

    tool_count = len(tools)
    use_lazy = mode.lower() == "lazy" or (
        mode.lower() == "compact" and tool_count >= engine.config.lazy_schema_min_tools
    )
    if use_lazy:
        adaptive_level = level
        if tool_count >= 100:
            adaptive_level = "ultra"
        elif tool_count >= 50:
            adaptive_level = "high"
        catalog, session_id, stats = engine.lazy_tool_catalog(tools, level=adaptive_level)
        _lazy_sessions[session_id] = adaptive_level
        stats["auto_lazy"] = mode.lower() != "lazy"
        return {"catalog": catalog, "session_id": session_id, "stats": stats, "mode": "lazy"}

    compacted, stats = engine.compact_tool_schemas(tools)
    if tool_count >= engine.config.lazy_schema_min_tools and stats.get("ratio", 0) < 0.5:
        stats["hint"] = (
            f"{tool_count} tools — retry mode=lazy level={level} for on-demand schemas"
        )
    return {"tools": compacted, "stats": stats}


@mcp.tool(name="token_engine_get_tool_schema")
def token_engine_get_tool_schema(session_id: str, tool_name: str) -> dict[str, Any]:
    """Fetch full compacted schema for one tool from a lazy catalog session."""
    engine = _engine()
    schema, stats = engine.get_lazy_tool_schema(session_id, tool_name)
    if schema is None:
        return {"error": stats.get("error", "not found"), "stats": stats}
    return {"schema": schema, "stats": stats}


@mcp.tool(name="token_engine_sandbox")
def token_engine_sandbox(code: str, timeout: int = 30) -> dict[str, Any]:
    """Run Python outside context; return compressed stdout only."""
    result = execute_and_compress(code, timeout=timeout, config=EngineConfig.default())
    return {
        "compressed_output": result.compressed_stdout,
        "returncode": result.returncode,
        "tokens_saved": result.tokens_saved,
        "stderr_preview": result.stderr[:500] if result.stderr else "",
    }


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
