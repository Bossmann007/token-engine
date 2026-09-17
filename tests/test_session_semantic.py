"""SessionSemanticCompactor — structured session state + OMITTED aggregation."""

from __future__ import annotations

import json
from pathlib import Path

from token_engine.core.config import EngineConfig, QualityLevel
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType, RelevanceTier
from token_engine.compressor.session_semantic import SessionSemanticCompactor
from token_engine.benchmark.runner import BenchmarkRunner

ROOT = Path(__file__).resolve().parents[1]


class TestSessionSemanticCompactor:
    def test_collapses_meeting_notes_and_aggregates_omitted(self):
        items = [
            ContentItem(id="task", content="Fix auth bug in src/auth/login.py", content_type=ContentType.MESSAGE, source="user", tier=RelevanceTier.CRITICAL),
            ContentItem(id="err", content="AssertionError: Expected 200, got 500", content_type=ContentType.LOG, source="pytest", tier=RelevanceTier.CRITICAL, metadata={"is_error": True}),
            ContentItem(
                id="filler_notes",
                content="Meeting notes from last sprint: discussed UI polish, refactored sidebar nav",
                content_type=ContentType.TEXT,
                source="notes.md",
                tier=RelevanceTier.MEDIUM,
            ),
            ContentItem(
                id="drop1",
                content="[dropped:drop1|100tok|knapsack]",
                content_type=ContentType.TEXT,
                metadata={"knapsack_dropped": True},
                tier=RelevanceTier.LOW,
            ),
        ]
        out = SessionSemanticCompactor(quality=QualityLevel.BALANCED).render(items)
        assert "T:" in out or "TASK:" in out
        assert "Fix auth bug" in out
        assert "AssertionError" in out
        assert "Meeting notes from last sprint" not in out
        assert "OMIT:" in out or "O:" in out
        assert "knapsack" in out  # omit aggregate — id chrome dropped when structural tag present
        assert out.count("[dropped:") <= 1  # aggregated, not per-header spam

    def test_fail_closed_never_expands_vs_legacy(self):
        raw = json.loads((ROOT / "benchmarks/fixtures/session_unrelated_reads.json").read_text())
        items = [
            ContentItem(**{**item, "content_type": ContentType(item.get("content_type", "unknown"))})
            for item in raw["items"]
        ]
        on = TokenEngine(EngineConfig(enable_session_semantic_compactor=True)).optimize_context(items)
        off = TokenEngine(EngineConfig(enable_session_semantic_compactor=False)).optimize_context(items)
        assert on.stats.optimized_tokens <= off.stats.optimized_tokens

    def test_benchmark_quality_holds(self):
        runner = BenchmarkRunner()
        results = runner.run_all(ROOT / "benchmarks/fixtures")
        failures = runner.check_baseline(results, ROOT / "benchmarks/baseline.json")
        assert failures == [], "\n".join(failures)
        # Top session sinks should improve or stay vs prior 60.2% total (gross)
        orig = sum(r.original_tokens for r in results)
        opt = sum(r.optimized_tokens for r in results)
        gross = (orig - opt) / orig
        assert gross >= 0.602 - 0.002  # no regression vs measured baseline
