"""Read delta session improvements."""

import json
from pathlib import Path

from token_engine.compressor.context_helpers import collapse_superseded_reads
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType

FIXTURES = Path(__file__).parent.parent / "benchmarks" / "fixtures"


class TestSupersededReads:
    def test_collapse_first_read_before_delta(self):
        items = [
            ContentItem(id="v1", content="line\n" * 20, content_type=ContentType.CODE, source="a.py"),
            ContentItem(
                id="v2",
                content="[DELTA a.py +1/-0]\n+new",
                content_type=ContentType.CODE,
                source="a.py",
                metadata={"read_delta": "read_delta"},
            ),
        ]
        assert collapse_superseded_reads(items) == 1
        assert items[0].content.startswith("[first read: a.py")

    def test_read_delta_fixture_improves(self):
        data = json.loads(FIXTURES.joinpath("read_delta_session.json").read_text(encoding="utf-8"))
        engine = TokenEngine()
        items = [
            ContentItem(**{**it, "content_type": ContentType(it.get("content_type", "unknown"))})
            for it in data["items"]
        ]
        result = engine.optimize_context(items)
        assert result.stats.compression_ratio >= 0.45
        assert "DELTA" in result.content
        assert "logger.info" in result.content
        assert "first read" in result.content or "stale read" in result.content
