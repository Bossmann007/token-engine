"""Hybrid knapsack: live-zone keeps message slots, drops LOW under budget pressure."""

from token_engine.core.config import EngineConfig
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType, RelevanceTier
from token_engine.compressor.context_helpers import knapsack_stub


def _count(engine: TokenEngine, text: str) -> int:
    return engine.tokenizer.count(text)


class TestKnapsackStub:
    def test_stub_preserves_id_and_tier(self):
        item = ContentItem(
            id="old_notes",
            content="TODO: remove legacy module",
            tier=RelevanceTier.DISCARDABLE,
            token_count=12,
        )
        stub = knapsack_stub(item)
        assert stub.id == "old_notes"
        assert stub.metadata["knapsack_dropped"] is True
        assert "knapsack" in stub.content


class TestHybridKnapsack:
    def test_no_drop_when_under_threshold(self):
        config = EngineConfig(
            live_zone_mode=True,
            enable_hybrid_knapsack=True,
            target_tokens=10_000,
            enable_cache=False,
        )
        engine = TokenEngine(config)
        items = [
            ContentItem(
                id="user",
                content="Fix auth login bug in src/auth/login.py",
                content_type=ContentType.MESSAGE,
                source="user",
                token_count=_count(engine, "Fix auth login bug in src/auth/login.py"),
            ),
        ]
        result = engine.optimize_context(items)
        assert result.metadata.get("knapsack_dropped", 0) == 0
        assert "login" in result.content

    def test_drops_low_tiers_when_over_budget(self):
        config = EngineConfig(
            live_zone_mode=True,
            enable_hybrid_knapsack=True,
            enable_proactive_low_tier_collapse=False,
            target_tokens=180,
            knapsack_budget_threshold=0.8,
            hybrid_knapsack_target_ratio=0.95,
            enable_cache=False,
            enable_ccr=False,
            enable_cbm_bridge=False,
        )
        engine = TokenEngine(config)
        filler = "lorem ipsum dolor sit amet " * 80
        items = [
            ContentItem(
                id="user_task",
                content="Fix authentication login bug in src/auth/login.py special characters",
                content_type=ContentType.MESSAGE,
                source="user",
                token_count=_count(
                    engine,
                    "Fix authentication login bug in src/auth/login.py special characters",
                ),
            ),
            ContentItem(
                id="auth_code",
                content="class AuthService:\n    def login(self, email, password):\n        pass\n",
                content_type=ContentType.CODE,
                source="src/auth/login.py",
                token_count=_count(
                    engine,
                    "class AuthService:\n    def login(self, email, password):\n        pass\n",
                ),
            ),
            ContentItem(
                id="filler_a",
                content=filler,
                content_type=ContentType.TEXT,
                source="notes_a.md",
                token_count=_count(engine, filler),
            ),
            ContentItem(
                id="filler_b",
                content=filler,
                content_type=ContentType.TEXT,
                source="notes_b.md",
                token_count=_count(engine, filler),
            ),
            ContentItem(
                id="obsolete",
                content="TODO: remove this legacy auth module no longer used since v2 migration.",
                content_type=ContentType.TEXT,
                source="notes.md",
                token_count=_count(
                    engine,
                    "TODO: remove this legacy auth module no longer used since v2 migration.",
                ),
            ),
        ]
        result = engine.optimize_context(items)
        assert result.metadata.get("knapsack_dropped", 0) >= 1
        assert "knapsack" in result.content
        assert "AuthService" in result.content or "login" in result.content
        assert len(result.items) == len(items)

    def test_disabled_keeps_all_items(self):
        config = EngineConfig(
            live_zone_mode=True,
            enable_hybrid_knapsack=False,
            target_tokens=100,
            enable_cache=False,
        )
        engine = TokenEngine(config)
        big = "x " * 500
        items = [
            ContentItem(id="a", content=big, token_count=_count(engine, big)),
            ContentItem(id="b", content=big, token_count=_count(engine, big)),
        ]
        result = engine.optimize_context(items)
        assert result.metadata.get("knapsack_dropped", 0) == 0
        assert "knapsack" not in result.content
