"""Net compression harness smoke tests."""

from pathlib import Path

from token_engine.benchmark.net_metrics import measure_corpus
from token_engine.core.config import QualityLevel

ROOT = Path(__file__).resolve().parents[1]


def test_net_metrics_balanced_reports_gross():
    m = measure_corpus(ROOT / "benchmarks" / "fixtures", quality=QualityLevel.BALANCED)
    assert m.fixture_count >= 10
    assert m.original_tokens > m.compressed_tokens
    assert m.gross_ratio >= 0.60
    assert "floors_ok" in m.notes or m.notes == ["floors_ok"]
