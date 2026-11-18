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
    assert m.net_ratio <= m.gross_ratio  # overhead never increases net
    assert m.tokens_saved_net <= m.tokens_saved_gross
    assert "floors_ok" in m.notes or m.notes == ["floors_ok"]


def test_net_metrics_splits_main_and_holdout():
    fixtures = ROOT / "benchmarks" / "fixtures"
    every = measure_corpus(fixtures)
    main = measure_corpus(fixtures, holdout=False)
    adv = measure_corpus(fixtures, holdout=True)
    assert adv.fixture_count >= 1
    assert main.fixture_count + adv.fixture_count == every.fixture_count
    assert main.original_tokens + adv.original_tokens == every.original_tokens
    assert main.compressed_tokens + adv.compressed_tokens == every.compressed_tokens


def test_benchmark_cli_net_prints_main_and_holdout():
    from click.testing import CliRunner

    from token_engine.cli.main import cli

    res = CliRunner().invoke(cli, ["benchmark", "--net"])
    assert res.exit_code == 0, res.output
    assert "Main net" in res.output
    assert "Holdout gross" in res.output
