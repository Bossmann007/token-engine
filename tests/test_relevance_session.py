"""Tests for path-aware relevance and proactive session compression."""

import json
from pathlib import Path

from token_engine.analyzer.relevance import extract_query_terms, path_matches_task, score_path_relevance
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType, RelevanceTier

FIXTURES = Path(__file__).parent.parent / "benchmarks" / "fixtures"


class TestPathRelevance:
    def test_path_match_from_query(self):
        terms, symbols, ql = extract_query_terms("Fix src/api/users.py delete_user")
        assert path_matches_task("src/api/users.py", ql, terms, symbols)

    def test_unrelated_path_low_score(self):
        item = ContentItem(
            id="h",
            content="def helper_a(): return 1",
            content_type=ContentType.CODE,
            source="src/utils/helpers.py",
        )
        score = score_path_relevance(item, "Fix src/api/users.py delete_user")
        assert score == 0.0


class TestProactiveSession:
    def test_unrelated_reads_collapsed(self):
        data = json.loads(FIXTURES.joinpath("session_unrelated_reads.json").read_text(encoding="utf-8"))
        engine = TokenEngine()
        items = [
            ContentItem(**{**it, "content_type": ContentType(it.get("content_type", "unknown"))})
            for it in data["items"]
        ]
        result = engine.optimize_context(items)
        assert "irrelevant read" in result.content or "CBM:" in result.content
        assert "WebhookHandler" in result.content
        assert "def helper_a" not in result.content

    def test_large_agent_improves(self):
        data = json.loads(FIXTURES.joinpath("large_agent_session.json").read_text(encoding="utf-8"))
        engine = TokenEngine()
        items = [
            ContentItem(**{**it, "content_type": ContentType(it.get("content_type", "unknown"))})
            for it in data["items"]
        ]
        result = engine.optimize_context(items)
        assert result.stats.compression_ratio >= 0.15
        assert "helpers" not in result.content or "irrelevant" in result.content.lower()

    def test_reread_chain_dedupes(self):
        data = json.loads(FIXTURES.joinpath("session_reread_chain.json").read_text(encoding="utf-8"))
        engine = TokenEngine()
        items = [
            ContentItem(**{**it, "content_type": ContentType(it.get("content_type", "unknown"))})
            for it in data["items"]
        ]
        result = engine.optimize_context(items)
        assert result.stats.compression_ratio >= 0.25
        assert "invalidate" in result.content or "DELTA" in result.content
