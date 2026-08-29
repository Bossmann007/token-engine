"""Tests for Phase 2 modules."""

from token_engine.compressor.log_template import mine_log_templates
from token_engine.compressor.read_delta import ReadDelta
from token_engine.compressor.toon_encoder import ToonEncoder
from token_engine.optimizer.knapsack import knapsack_select
from token_engine.optimizer.read_lifecycle import prune_stale_reads
from token_engine.analyzer.cache_aligner import detect_volatile_content
from token_engine.cache.feedback import CompressionFeedback
from token_engine.core.types import ContentItem, ContentType, RelevanceTier
from token_engine.core.config import EngineConfig


class TestLogTemplate:
    def test_collapse_repeated(self):
        lines = ["INFO: ok"] * 20 + ["ERROR: fail"]
        out, collapsed = mine_log_templates(lines, min_count=5)
        assert collapsed > 0
        assert any("×" in l for l in out)


class TestReadDelta:
    def test_delta_on_reread(self):
        rd = ReadDelta()
        content = "\n".join(f"def func_{i}(): pass" for i in range(50))
        rd.process("a.py", content)
        modified = content + "\ndef func_50(): pass"
        second = rd.process("a.py", modified)
        assert second.is_delta
        assert second.strategy == "read_delta"

    def test_unchanged(self):
        rd = ReadDelta()
        rd.process("b.py", "same")
        r = rd.process("b.py", "same")
        assert "unchanged" in r.content


class TestToon:
    def test_uniform_array(self):
        data = '[{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}]'
        enc = ToonEncoder()
        r = enc.compress(data, aggressiveness=0.5)
        assert r.compressed
        assert "TOON" in r.content


class TestKnapsack:
    def test_respects_budget(self):
        items = [
            ContentItem(id="a", content="x" * 100, token_count=50, tier=RelevanceTier.HIGH),
            ContentItem(id="b", content="y" * 200, token_count=100, tier=RelevanceTier.MEDIUM),
            ContentItem(id="c", content="z" * 400, token_count=200, tier=RelevanceTier.LOW),
        ]
        selected = knapsack_select(items, 120)
        total = sum(i.token_count for i in selected)
        assert total <= 120


class TestReadLifecycle:
    def test_prune_stale(self):
        items = [
            ContentItem(id="1", content="old", source="f.py", content_type=ContentType.CODE, token_count=10),
            ContentItem(id="2", content="new", source="f.py", content_type=ContentType.CODE, token_count=10),
        ]
        prune_stale_reads(items)
        assert items[0].tier == RelevanceTier.REDUNDANT


class TestCacheAligner:
    def test_detect_uuid(self):
        w = detect_volatile_content("session id: 550e8400-e29b-41d4-a716-446655440000")
        assert any(x["type"] == "uuid" for x in w)


class TestFeedback:
    def test_adjust_aggressiveness(self):
        fb = CompressionFeedback()
        for _ in range(5):
            fb.record("pytest", compressed=True, ratio=0.5)
        assert fb.suggested_aggressiveness("pytest", 0.5) > 0.5


class TestDefaultConfig:
    def test_all_features_on(self):
        c = EngineConfig.default()
        assert c.live_zone_mode is True
        assert c.enable_knapsack_selection is True
        assert c.enable_sandbox_execute is True
