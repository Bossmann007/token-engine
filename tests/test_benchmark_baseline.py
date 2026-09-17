"""Benchmark baseline regression guard."""

from pathlib import Path

from token_engine.benchmark.runner import BenchmarkRunner

ROOT = Path(__file__).parent.parent


class TestBenchmarkBaseline:
    def test_meets_baseline(self):
        fixtures = ROOT / "benchmarks" / "fixtures"
        baseline = ROOT / "benchmarks" / "baseline.json"
        runner = BenchmarkRunner()
        results = runner.run_all(fixtures)
        failures = runner.check_baseline(results, baseline)
        assert failures == [], "\n".join(failures)

    def test_fixture_floors_are_enforced(self):
        """Per-fixture floors in baseline.json must fail check_baseline when breached."""
        import json
        from token_engine.benchmark.runner import BenchmarkResult

        baseline = ROOT / "benchmarks" / "baseline.json"
        data = json.loads(baseline.read_text(encoding="utf-8"))
        floors = data.get("fixtures") or {}
        assert floors, "baseline.json must define per-fixture floors"
        name = next(iter(floors))
        floor = float(floors[name])
        # Synthetic result just under the floor
        bad = BenchmarkResult(
            name=name,
            original_tokens=1000,
            optimized_tokens=int(1000 * (1 - floor) + 50),
            tokens_saved=int(1000 * floor) - 50,
            compression_ratio=floor - 0.01,
            latency_ms=1.0,
            strategy="test",
            quality_checks={},
            quality_score=1.0,
            category="session",
        )
        failures = BenchmarkRunner().check_baseline([bad], baseline)
        assert any(name in f and "below floor" in f for f in failures), failures
