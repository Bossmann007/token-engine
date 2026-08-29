"""MCP tool schema compaction (headroom / mcp-compressor-inspired)."""

from __future__ import annotations

import copy
import hashlib
import json
import re
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
