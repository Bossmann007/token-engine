"""Tests for Token Engine."""

import json
from pathlib import Path

import pytest

from token_engine import TokenEngine, EngineConfig, QualityLevel
from token_engine.core.types import ContentItem, ContentType, RelevanceTier
from token_engine.compressor.detect import detect_content_type
from token_engine.compressor.json_compressor import JSONCompressor
from token_engine.compressor.log_compressor import LogCompressor
from token_engine.compressor.deduplicator import Deduplicator
from token_engine.cache.cache import SmartCache


FIXTURES = Path(__file__).parent.parent / "benchmarks" / "fixtures"


class TestDetection:
    def test_detect_json(self):
        assert detect_content_type('{"key": "value"}') == ContentType.JSON

    def test_detect_diff(self):
        text = "diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,3 @@"
        assert detect_content_type(text) == ContentType.DIFF

    def test_detect_log(self):
        text = "2024-01-01 ERROR something\nTraceback (most recent call last):"
        assert detect_content_type(text) == ContentType.LOG

    def test_detect_code(self):
        text = "def hello():\n    return 'world'"
        assert detect_content_type(text) == ContentType.CODE


class TestCompressors:
    def test_json_compression(self):
        data = {"items": list(range(100)), "name": "test"}
        text = json.dumps(data)
        comp = JSONCompressor()
        result = comp.compress(text, aggressiveness=0.7)
        assert result.compressed
        assert len(result.content) < len(text)

    def test_json_object_array_preserves_error_rows(self):
        rows = [{"cpu": 12.0, "status": "ok"}] * 8
        rows.append({"cpu": 99.0, "status": "error", "message": "CPU threshold exceeded"})
        rows.extend({"cpu": 13.0, "status": "ok"} for _ in range(8))
        text = json.dumps(rows)
        result = JSONCompressor().compress(text, aggressiveness=0.5)
        assert result.compressed
        assert "error" in result.content
        assert "_total" in result.content

    def test_log_collapses_pytest_passed(self):
        passed = [f"tests/test_api.py::test_{i} PASSED" for i in range(12)]
        text = "\n".join([
            "============================= test session starts ==============================",
            "platform linux -- Python 3.12.0",
            "collected 13 items",
            *passed,
            "tests/test_api.py::test_three FAILED",
            "=================================== FAILURES ===================================",
            "E       AssertionError: boom",
            "=========================== short test summary info ============================",
        ])
        result = LogCompressor().compress(text, aggressiveness=0.5)
        assert result.compressed
        assert "PYTEST PASSED (12 tests omitted)" in result.content
        assert "FAILED" in result.content
        assert "AssertionError" in result.content

    def test_log_preserves_errors(self):
        text = (FIXTURES / "app_log.txt").read_text()
        comp = LogCompressor()
        result = comp.compress(text, aggressiveness=0.5)
        assert result.compressed
        assert "ERROR" in result.content or "ConnectionError" in result.content
        assert "Traceback" in result.content

    def test_fail_closed_no_expansion(self):
        comp = JSONCompressor()
        result = comp.compress('{"a": 1}', aggressiveness=0.1)
        assert not result.compressed or len(result.content) <= len('{"a": 1}')


class TestDeduplication:
    def test_find_duplicates(self):
        dedup = Deduplicator()
        items = [
            ("a", "same content here " * 10),
            ("b", "same content here " * 10),
            ("c", "different content"),
        ]
        pairs = dedup.find_duplicates_among_items(items)
        assert len(pairs) >= 1


class TestCache:
    def test_ttl_and_invalidation(self):
        cache = SmartCache(ttl_seconds=3600)
        cache.set("k1", "value", dependencies={"file.py"})
        assert cache.get("k1") == "value"
        assert cache.invalidate_dependency("file.py") == 1
        assert cache.get("k1") is None


class TestEngine:
    def test_optimize_log(self):
        engine = TokenEngine(EngineConfig(quality_level=QualityLevel.BALANCED))
        text = (FIXTURES / "app_log.txt").read_text()
        result = engine.optimize(text)
        assert result.stats is not None
        assert result.stats.optimized_tokens < result.stats.original_tokens
        assert "ConnectionError" in result.content or "ERROR" in result.content

    def test_optimize_context(self):
        engine = TokenEngine(EngineConfig(target_tokens=2000, task_query="authentication bug login"))
        data = json.loads((FIXTURES / "agent_context.json").read_text())
        items = [
            ContentItem(
                id=i["id"],
                content=i["content"],
                content_type=ContentType(i.get("content_type", "unknown")),
                source=i.get("source", ""),
                metadata=i.get("metadata", {}),
            )
            for i in data["items"]
        ]
        result = engine.optimize_context(items)
        assert result.stats is not None
        assert "AuthService" in result.content

    def test_analyze(self):
        engine = TokenEngine()
        result = engine.analyze("def hello(): pass\n" * 100)
        assert result.analysis is not None
        assert result.analysis.total_tokens > 0

    def test_token_count(self):
        engine = TokenEngine()
        assert engine.count_tokens("") == 0
        assert engine.count_tokens("hello world") > 0


class TestSmartCrusher:
    def test_preserves_outliers(self):
        from token_engine.compressor.smart_crusher import SmartCrusher
        import json
        data = json.loads((FIXTURES / "metrics_timeseries.json").read_text())["content"]
        comp = SmartCrusher()
        result = comp.compress(data, aggressiveness=0.7)
        assert result.compressed
        assert "error" in result.content or "critical" in result.content


class TestCrossTurnDedup:
    def test_dedup_reread(self):
        from token_engine.compressor.cross_turn_dedup import dedup_blocks, DedupBlock
        data = json.loads((FIXTURES / "cross_turn_reread.json").read_text())
        blocks = [DedupBlock(text=i["content"], turn=idx) for idx, i in enumerate(data["items"])]
        deduped, stats = dedup_blocks(blocks)
        assert stats["spans_folded"] >= 1
        assert "same as msg" in deduped[-1].text

    def test_cross_turn_fixture_saves_tokens(self):
        import json
        data = json.loads((FIXTURES / "cross_turn_reread.json").read_text())
        items = [
            ContentItem(**{**item, "content_type": ContentType(item["content_type"])})
            for item in data["items"]
        ]
        engine = TokenEngine()
        result = engine.optimize_context(items)
        assert result.stats.tokens_saved > 0
        assert "[read_2]" in result.content
        assert "unchanged:" in result.content or "same as msg" in result.content


class TestToolSchemaCompaction:
    def test_compact_mcp_tools(self):
        from token_engine.compressor.tool_schema_compactor import ToolSchemaCompactor
        tools = [{
            "name": "search",
            "description": "Search the codebase for a query string. Returns matching files and line numbers.",
            "inputSchema": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "title": "SearchInput",
                "properties": {
                    "query": {"type": "string", "description": "The search query to find in the codebase"},
                    "limit": {"type": "integer", "description": "Maximum number of results to return"},
                },
                "examples": [{"query": "auth", "limit": 10}],
            },
        }]
        compactor = ToolSchemaCompactor()
        compacted, stats = compactor.compact_tools(tools)
        assert stats["saved_chars"] > 0
        assert "$schema" not in json.dumps(compacted)


class TestCCR:
    def test_store_and_retrieve(self):
        from token_engine.ccr.store import CCRStore
        store = CCRStore()
        handle = store.store("original content here")
        assert store.retrieve(handle) == "original content here"
        assert "<<ccr:" in store.marker(handle)


class TestQualityPreservation:
    def test_pytest_fixture_quality(self):
        engine = TokenEngine()
        data = json.loads((FIXTURES / "pytest_failures.json").read_text())
        result = engine.optimize(data["content"], content_type="log")
        for term in data["must_preserve"]:
            assert term in result.content, f"Lost critical term: {term}"
