"""CLI for Token Engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from token_engine.core.config import CompressionLevel, EngineConfig, QualityLevel
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType


@click.group()
@click.version_option(version="0.1.0", prog_name="token-engine")
def cli() -> None:
    """Token Engine — LLM Token Optimization Engine."""


@cli.command("optimize")
@click.argument("path", type=click.Path(exists=True))
@click.option("--quality", type=click.Choice(["maximum", "balanced", "economy"]), default="balanced")
@click.option("--output", "-o", type=click.Path(), help="Write optimized output to file")
@click.option("--json", "as_json", is_flag=True, help="Output stats as JSON")
def optimize_cmd(path: str, quality: str, output: str | None, as_json: bool) -> None:
    """Optimize a text file."""
    config = EngineConfig(quality_level=QualityLevel(quality))
    engine = TokenEngine(config)
    text = Path(path).read_text(encoding="utf-8")
    result = engine.optimize(text)

    if output:
        Path(output).write_text(result.content, encoding="utf-8")

    if as_json:
        click.echo(json.dumps(_stats_dict(result), indent=2))
    else:
        _print_stats(result)
        if not output:
            click.echo("\n--- Optimized ---\n")
            click.echo(result.content)


@cli.command("optimize-context")
@click.argument("path", type=click.Path(exists=True))
@click.option("--max-tokens", type=int, default=None)
@click.option("--target-tokens", type=int, default=None)
@click.option("--quality", type=click.Choice(["maximum", "balanced", "economy"]), default="balanced")
@click.option("--task", default="", help="Task query for relevance scoring")
@click.option("--output", "-o", type=click.Path())
def optimize_context_cmd(
    path: str, max_tokens: int | None, target_tokens: int | None, quality: str, task: str, output: str | None
) -> None:
    """Optimize a JSON context file with multiple items."""
    config = EngineConfig(
        quality_level=QualityLevel(quality),
        max_tokens=max_tokens,
        target_tokens=target_tokens,
        task_query=task,
    )
    engine = TokenEngine(config)
    result = engine.optimize_context_file(path)

    if output:
        Path(output).write_text(result.content, encoding="utf-8")

    _print_stats(result)
    if not output:
        click.echo("\n--- Optimized Context ---\n")
        click.echo(result.content)


@cli.command("analyze")
@click.argument("path", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True)
def analyze_cmd(path: str, as_json: bool) -> None:
    """Analyze token usage in a file or directory."""
    engine = TokenEngine()
    p = Path(path)

    if p.is_dir():
        result = engine.analyze_project(p)
    else:
        text = p.read_text(encoding="utf-8")
        result = engine.analyze(text)

    if not result.analysis:
        click.echo("No analysis available.")
        sys.exit(1)

    report = result.analysis
    if as_json:
        click.echo(json.dumps({
            "total_tokens": report.total_tokens,
            "metrics": {
                "by_source": report.metrics.tokens_by_source,
                "by_type": report.metrics.tokens_by_type,
                "redundant": report.metrics.redundant_tokens,
                "discardable": report.metrics.discardable_tokens,
                "critical": report.metrics.critical_tokens,
            },
            "duplicates": report.duplicates,
            "recommendations": report.recommendations,
        }, indent=2))
    else:
        click.echo(f"Total tokens: {report.total_tokens:,}")
        click.echo(f"Critical: {report.metrics.critical_tokens:,}")
        click.echo(f"Redundant: {report.metrics.redundant_tokens:,}")
        click.echo(f"Discardable: {report.metrics.discardable_tokens:,}")
        if report.metrics.tokens_by_type:
            click.echo("\nBy type:")
            for t, n in sorted(report.metrics.tokens_by_type.items(), key=lambda x: -x[1]):
                click.echo(f"  {t}: {n:,}")
        if report.recommendations:
            click.echo("\nRecommendations:")
            for r in report.recommendations:
                click.echo(f"  • {r}")


@cli.command("benchmark")
@click.option("--fixtures", type=click.Path(exists=True), default=None)
@click.option("--quality", type=click.Choice(["maximum", "balanced", "economy"]), default="balanced")
def benchmark_cmd(fixtures: str | None, quality: str) -> None:
    """Run compression benchmarks."""
    from token_engine.benchmark.runner import BenchmarkRunner

    fixtures_dir = Path(fixtures) if fixtures else Path(__file__).parent.parent.parent.parent / "benchmarks" / "fixtures"
    runner = BenchmarkRunner(EngineConfig(quality_level=QualityLevel(quality)))
    results = runner.run_all(fixtures_dir)
    runner.print_report(results)


@cli.command("stats")
@click.argument("path", type=click.Path(exists=True))
def stats_cmd(path: str) -> None:
    """Quick token count and cost estimate."""
    engine = TokenEngine()
    text = Path(path).read_text(encoding="utf-8")
    tokens = engine.count_tokens(text)
    cost = engine.estimate_cost(tokens)
    click.echo(f"File: {path}")
    click.echo(f"Tokens: {tokens:,}")
    click.echo(f"Characters: {len(text):,}")
    click.echo(f"Estimated input cost: ${cost:.4f}")


def _stats_dict(result) -> dict:
    stats = result.stats
    if not stats:
        return {"content_length": len(result.content)}
    return {
        "original_tokens": stats.original_tokens,
        "optimized_tokens": stats.optimized_tokens,
        "tokens_saved": stats.tokens_saved,
        "compression_ratio": f"{stats.compression_ratio * 100:.1f}%",
        "strategy": stats.strategy,
        "latency_ms": round(stats.latency_ms, 2),
    }


def _print_stats(result) -> None:
    stats = result.stats
    if not stats:
        return
    click.echo(f"Original:    {stats.original_tokens:>8,} tokens")
    click.echo(f"Optimized:   {stats.optimized_tokens:>8,} tokens")
    click.echo(f"Saved:       {stats.tokens_saved:>8,} tokens")
    click.echo(f"Compression: {stats.compression_ratio * 100:>7.1f}%")
    click.echo(f"Latency:     {stats.latency_ms:>7.1f} ms")


if __name__ == "__main__":
    cli()
