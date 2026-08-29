"""Lazy MCP tool schema catalog (mcp-compressor pattern)."""

import json

from token_engine.compressor.tool_schema_compactor import LazySchemaLevel, ToolSchemaCompactor
from token_engine.core.engine import TokenEngine
from token_engine.mcp.server import token_engine_compact_tools, token_engine_get_tool_schema


def _sample_tools(n: int = 25) -> list[dict]:
    tools = []
    for i in range(n):
        tools.append({
            "name": f"tool_{i}",
            "description": f"Perform operation {i} on the backend. Returns detailed results and metadata.",
            "inputSchema": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "title": f"Tool{i}Input",
                "properties": {
                    "query": {"type": "string", "description": "The search query string to use"},
                    "limit": {"type": "integer", "description": "Maximum number of results"},
                    "offset": {"type": "integer", "description": "Pagination offset"},
                },
                "required": ["query"],
                "examples": [{"query": "test", "limit": 10}],
            },
        })
    return tools


class TestLazyCatalog:
    def test_catalog_smaller_than_full(self):
        tools = _sample_tools(30)
        compactor = ToolSchemaCompactor()
        catalog, session_id, stats = compactor.lazy_catalog(tools, level=LazySchemaLevel.MEDIUM)
        assert stats["ratio_vs_full"] > 0.8
        assert session_id
        assert "tool_0(query" in catalog
        assert "$schema" not in catalog

    def test_levels(self):
        tool = _sample_tools(1)[0]
        compactor = ToolSchemaCompactor()
        for level in LazySchemaLevel:
            catalog, _, _ = compactor.lazy_catalog([tool], level=level)
            if level == LazySchemaLevel.MAX:
                assert catalog.splitlines()[-1] == "tool_0"
            elif level == LazySchemaLevel.HIGH:
                assert "Perform operation" not in catalog
            elif level == LazySchemaLevel.LOW:
                assert "Perform operation 0" in catalog

    def test_get_schema_roundtrip(self):
        tools = _sample_tools(5)
        compactor = ToolSchemaCompactor()
        _, session_id, _ = compactor.lazy_catalog(tools)
        schema, stats = compactor.get_lazy_schema(session_id, "tool_2")
        assert schema is not None
        assert schema["name"] == "tool_2"
        assert schema["inputSchema"] is not None
        assert "$schema" not in json.dumps(schema["inputSchema"])
        assert stats["tool_name"] == "tool_2"

    def test_unknown_tool(self):
        compactor = ToolSchemaCompactor()
        _, session_id, _ = compactor.lazy_catalog(_sample_tools(2))
        schema, stats = compactor.get_lazy_schema(session_id, "missing")
        assert schema is None
        assert "error" in stats


class TestLazyMCP:
    def test_compact_tools_lazy_mode(self):
        tools_json = json.dumps(_sample_tools(25))
        result = token_engine_compact_tools(tools_json, mode="lazy", level="high")
        assert result["session_id"]
        assert result["stats"]["mode"] == "lazy"
        assert result["stats"]["ratio_vs_full"] > 0.85

    def test_get_tool_schema_mcp(self):
        tools_json = json.dumps(_sample_tools(10))
        lazy = token_engine_compact_tools(tools_json, mode="lazy", level="medium")
        got = token_engine_get_tool_schema(lazy["session_id"], "tool_3")
        assert got["schema"]["name"] == "tool_3"
        assert "query" in json.dumps(got["schema"]["inputSchema"])


class TestEngineFacade:
    def test_lazy_via_engine(self):
        engine = TokenEngine()
        tools = _sample_tools(22)
        catalog, session_id, stats = engine.lazy_tool_catalog(tools, level="medium")
        assert len(catalog) < stats["full_chars"]
        schema, _ = engine.get_lazy_tool_schema(session_id, "tool_1")
        assert schema["signature"].startswith("tool_1(")
