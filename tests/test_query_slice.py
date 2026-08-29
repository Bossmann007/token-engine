"""Tests for query-aware code slicing."""

import json
from pathlib import Path

from token_engine.compressor.query_slice import slice_code_by_query
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType

FIXTURES = Path(__file__).parent.parent / "benchmarks" / "fixtures"


class TestQuerySlice:
    def test_elides_irrelevant_method(self):
        data = json.loads(FIXTURES.joinpath("agent_context.json").read_text(encoding="utf-8"))
        auth = next(i for i in data["items"] if i["id"] == "file_auth")
        query = data["items"][1]["content"]
        sliced, changed = slice_code_by_query(auth["content"], query)
        assert changed
        assert "validate_password" in sliced
        assert "login" in sliced
        assert "elided" not in sliced or "# ..." in sliced

    def test_agent_context_improves(self):
        data = json.loads(FIXTURES.joinpath("agent_context.json").read_text(encoding="utf-8"))
        engine = TokenEngine()
        items = [
            ContentItem(**{**it, "content_type": ContentType(it.get("content_type", "unknown"))})
            for it in data["items"]
        ]
        result = engine.optimize_context(items)
        assert result.stats.compression_ratio > 0.20
        assert "AuthService" in result.content
        assert "AssertionError" in result.content

    def test_ccr_skipped_on_small_savings(self):
        from token_engine.core.config import EngineConfig
        from token_engine.optimizer.context_optimizer import ContextOptimizer
        from token_engine.tokenizer.tiktoken_tokenizer import create_tokenizer

        config = EngineConfig(ccr_min_token_saved=500, ccr_min_chars_saved=5000)
        opt = ContextOptimizer(config, create_tokenizer())
        item = ContentItem(
            id="git",
            content="On branch main\nmodified: 1 file\n  modified: app.py\n",
            content_type=ContentType.TERMINAL,
            source="git status",
            token_count=20,
        )
        out, _ = opt._compress_item(item, 0.5, task_query="")
        assert "<<ccr:" not in out.content
