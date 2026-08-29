"""MCP tool schema compaction (headroom / mcp-compressor-inspired)."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
from enum import Enum
from typing import Any

TOOL_SCHEMA_DROP_KEYS = frozenset({
    "$id", "$schema", "$comment", "deprecated", "examples", "example",
    "markdownDescription", "readOnly", "title", "writeOnly",
})

_SEMANTIC_PARAM_NAMES = frozenset({
    "query", "search", "filter", "sort", "order", "limit", "offset", "page",
    "per_page", "cursor", "after", "before", "owner", "repo", "repository",
    "org", "organization", "user", "username", "email", "name", "title",
    "id", "number", "count", "url", "path", "file", "filename", "branch",
    "tag", "sha", "commit", "ref", "key", "token",
})


class LazySchemaLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


class LazyToolRegistry:
    """Session store for on-demand schema lookup (mcp-compressor pattern)."""

    _sessions: dict[str, list[dict[str, Any]]] = {}
    _max_sessions = 100

    @classmethod
    def store(cls, tools: list[dict[str, Any]]) -> str:
        session_id = secrets.token_hex(8)
        cls._sessions[session_id] = copy.deepcopy(tools)
        while len(cls._sessions) > cls._max_sessions:
            cls._sessions.pop(next(iter(cls._sessions)))
        return session_id

    @classmethod
    def get(cls, session_id: str, tool_name: str) -> dict[str, Any] | None:
        tools = cls._sessions.get(session_id)
        if not tools:
            return None
        for tool in tools:
            if tool.get("name") == tool_name:
                return copy.deepcopy(tool)
        return None

    @classmethod
    def list_names(cls, session_id: str) -> list[str]:
        tools = cls._sessions.get(session_id)
        if not tools:
            return []
        return [str(t.get("name", "")) for t in tools if t.get("name")]


class ToolSchemaCompactor:
    """Reduce MCP tool definition token bloat."""

    def __init__(
        self,
        desc_max_chars: int = 120,
        strip_semantic: bool = True,
    ) -> None:
        self._desc_max = desc_max_chars
        self._strip_semantic = strip_semantic
        self._cache: dict[str, list[dict]] = {}

    def compact_tools(self, tools: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict]:
        cache_key = hashlib.sha256(
            json.dumps(tools, sort_keys=True).encode()
        ).hexdigest()[:16]

        if cache_key in self._cache:
            return copy.deepcopy(self._cache[cache_key]), {"cache_hit": True}

        original_size = len(json.dumps(tools))
        compacted = [self._compact_tool(copy.deepcopy(t)) for t in tools]
        new_size = len(json.dumps(compacted))

        self._cache[cache_key] = copy.deepcopy(compacted)
        stats = {
            "tools": len(tools),
            "original_chars": original_size,
            "compacted_chars": new_size,
            "saved_chars": max(0, original_size - new_size),
            "ratio": 1 - new_size / original_size if original_size else 0,
            "cache_hit": False,
        }
        return compacted, stats

    def lazy_catalog(
        self,
        tools: list[dict[str, Any]],
        *,
        level: str | LazySchemaLevel = LazySchemaLevel.MEDIUM,
    ) -> tuple[str, str, dict[str, Any]]:
        """Build compact tool listing; store full schemas for on-demand lookup."""
        if isinstance(level, str):
            level = LazySchemaLevel(level.lower())

        session_id = LazyToolRegistry.store(tools)
        lines = [self._format_lazy_line(t, level) for t in tools]
        if level == LazySchemaLevel.MAX:
            header = (
                f"# {len(tools)} tools — call token_engine_get_tool_schema"
                f"(session_id, tool_name) for full schema"
            )
            catalog = header + "\n" + "\n".join(lines)
        else:
            catalog = "\n".join(lines)

        full_chars = len(json.dumps(tools))
        compacted, _ = self.compact_tools(tools)
        compact_chars = len(json.dumps(compacted))
        catalog_chars = len(catalog)
        stats = {
            "mode": "lazy",
            "level": level.value,
            "tools": len(tools),
            "session_id": session_id,
            "catalog_chars": catalog_chars,
            "full_chars": full_chars,
            "compact_chars": compact_chars,
            "saved_vs_full": max(0, full_chars - catalog_chars),
            "saved_vs_compact": max(0, compact_chars - catalog_chars),
            "ratio_vs_full": 1 - catalog_chars / full_chars if full_chars else 0,
        }
        return catalog, session_id, stats

    def get_lazy_schema(
        self,
        session_id: str,
        tool_name: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Return full compacted schema for one tool from a lazy session."""
        raw = LazyToolRegistry.get(session_id, tool_name)
        if raw is None:
            return None, {"error": "unknown session or tool", "session_id": session_id, "tool_name": tool_name}

        compacted = self._compact_tool(raw)
        args = self._format_args(raw)
        name = raw.get("name", tool_name)
        sig = f"{name}({args})" if args else name
        desc = raw.get("description", "")
        stats = {
            "session_id": session_id,
            "tool_name": tool_name,
            "signature": sig,
            "original_chars": len(json.dumps(raw)),
            "schema_chars": len(json.dumps(compacted)),
        }
        return {
            "name": name,
            "signature": sig,
            "description": desc,
            "inputSchema": compacted.get("inputSchema") or compacted.get("parameters"),
            "tool": compacted,
        }, stats

    def _format_lazy_line(self, tool: dict[str, Any], level: LazySchemaLevel) -> str:
        name = tool.get("name", "unknown")
        args = self._format_args(tool)
        sig = f"{name}({args})" if args else name

        desc = (tool.get("description") or "").strip()
        if level == LazySchemaLevel.MAX:
            return name
        if level == LazySchemaLevel.HIGH:
            return sig
        if level == LazySchemaLevel.MEDIUM:
            first = self._first_sentence(desc)
            return f"{sig}: {first}" if first else sig
        return f"{sig}: {desc}" if desc else sig

    @staticmethod
    def _format_args(tool: dict[str, Any]) -> str:
        schema = tool.get("inputSchema") or tool.get("parameters") or {}
        if not isinstance(schema, dict):
            return ""
        props = schema.get("properties")
        if not isinstance(props, dict):
            return ""
        required = set(schema.get("required") or [])
        ordered = [n for n in props if n in required] + [n for n in props if n not in required]
        return ", ".join(ordered)

    @staticmethod
    def _first_sentence(desc: str) -> str:
        if not desc:
            return ""
        match = re.match(r"^(.+?[.!?])(?:\s|$)", desc)
        if match:
            return match.group(1).strip()
        first_line = desc.splitlines()[0].strip()
        return first_line[:120] + ("..." if len(first_line) > 120 else "")

    def _compact_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        if "description" in tool and self._desc_max > 0:
            tool["description"] = self._truncate_desc(tool["description"])

        params = tool.get("inputSchema") or tool.get("parameters")
        if isinstance(params, dict):
            self._compact_schema(params)
        return tool

    def _compact_schema(self, schema: dict[str, Any]) -> None:
        for key in list(schema.keys()):
            if key in TOOL_SCHEMA_DROP_KEYS:
                del schema[key]

        if "description" in schema:
            name = schema.get("name", "")
            if self._strip_semantic and name.lower() in _SEMANTIC_PARAM_NAMES:
                del schema["description"]
            elif self._desc_max > 0:
                schema["description"] = self._truncate_desc(schema["description"])

        props = schema.get("properties")
        if isinstance(props, dict):
            for prop_name, prop_schema in props.items():
                if isinstance(prop_schema, dict):
                    if self._strip_semantic and prop_name.lower() in _SEMANTIC_PARAM_NAMES:
                        prop_schema.pop("description", None)
                    else:
                        for k in list(prop_schema.keys()):
                            if k in TOOL_SCHEMA_DROP_KEYS:
                                del prop_schema[k]
                        if "description" in prop_schema and self._desc_max > 0:
                            prop_schema["description"] = self._truncate_desc(prop_schema["description"])
                    if "properties" in prop_schema:
                        self._compact_schema(prop_schema)

        for key in ("items", "additionalProperties"):
            val = schema.get(key)
            if isinstance(val, dict):
                self._compact_schema(val)

    def _truncate_desc(self, desc: str) -> str:
        if not desc or len(desc) <= self._desc_max:
            return desc.strip()
        # Keep first sentence
        m = re.match(r"^(.+?[.!?])\s", desc)
        if m and len(m.group(1)) <= self._desc_max:
            return m.group(1)
        return desc[: self._desc_max - 3].rstrip() + "..."
