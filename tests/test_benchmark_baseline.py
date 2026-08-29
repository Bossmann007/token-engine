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
