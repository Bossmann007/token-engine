"""Tests for MCP tool functions."""

import json

import pytest

from token_engine.mcp.server import (
    caveman_compress,
    caveman_retrieve,
    caveman_stats,
    token_engine_compact_tools,
)


class TestMCPCompress:
    def test_compress_log(self):
        log = "ERROR: failed\n" + "INFO: ok\n" * 100
        result = caveman_compress(log, content_type="log")
        assert result["ratio"] > 0 or result["compressed"] == log
        if result["ratio"] > 0:
            assert result["recovery_handle"] is not None
            assert "ERROR" in result["compressed"]

    def test_retrieve_roundtrip(self):
        original = '{"data": ' + json.dumps(list(range(50))) + '}'
        result = caveman_compress(original, content_type="json", quality="economy")
        if result["recovery_handle"]:
            recovered = caveman_retrieve(result["recovery_handle"])
            assert recovered["content"] == original

    def test_fail_closed_small(self):
        small = "hello world"
        result = caveman_compress(small)
        assert result["ratio"] == 0
        assert result["compressed"] == small

    def test_stats(self):
        caveman_compress("x" * 5000, content_type="log", quality="economy")
        stats = caveman_stats()
        assert stats["compress_calls"] >= 1


class TestMCPCompactTools:
    def test_compact(self):
        tools = json.dumps([{
            "name": "search",
            "description": "Search the codebase for matching files and line numbers in the project.",
            "inputSchema": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "properties": {"query": {"type": "string", "description": "The search query string"}},
            },
        }])
        result = token_engine_compact_tools(tools)
        assert result["stats"]["saved_chars"] > 0
