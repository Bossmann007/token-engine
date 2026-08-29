"""Integration tests for multi-phase compression improvements."""

import json
from pathlib import Path

from token_engine.compressor.session_parser import try_parse_session
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType

FIXTURES = Path(__file__).parent.parent / "benchmarks" / "fixtures"


class TestSessionParser:
    def test_parses_messages(self):
        payload = json.dumps({"messages": [{"role": "user", "content": "fix bug"}]})
        items = try_parse_session(payload)
        assert items is not None
        assert len(items) == 1

    def test_parses_items_array(self):
        data = json.loads(FIXTURES.joinpath("agent_context.json").read_text(encoding="utf-8"))
        items = try_parse_session(json.dumps(data["items"]))
        assert items is not None
        assert len(items) >= 5


class TestLargeAgentSession:
    def test_large_session_compresses(self):
        data = json.loads(FIXTURES.joinpath("large_agent_session.json").read_text(encoding="utf-8"))
        engine = TokenEngine()
        items = [
            ContentItem(**{**it, "content_type": ContentType(it.get("content_type", "unknown"))})
            for it in data["items"]
        ]
        result = engine.optimize_context(items)
        assert result.stats.compression_ratio >= 0.08
        assert "UserService" in result.content
        assert "delete_user" in result.content


class TestStaleReadStub:
    def test_stale_read_collapsed(self):
        items = [
            ContentItem(id="v1", content="x\n" * 30, content_type=ContentType.CODE, source="f.py"),
            ContentItem(id="v2", content="y\n" * 30, content_type=ContentType.CODE, source="f.py"),
        ]
        engine = TokenEngine()
        result = engine.optimize_context(items)
        assert "stale read" in result.content or "superseded" in result.content
