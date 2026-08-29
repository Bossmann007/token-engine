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


class TestQualityPreservation:
    def test_pytest_fixture_quality(self):
        engine = TokenEngine()
        data = json.loads((FIXTURES / "pytest_failures.json").read_text())
        result = engine.optimize(data["content"], content_type="log")
        for term in data["must_preserve"]:
            assert term in result.content, f"Lost critical term: {term}"
