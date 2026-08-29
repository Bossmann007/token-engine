"""CLI for Token Engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from token_engine.cli import console
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


@cli.command("optimize-messages")
@click.argument("path", type=click.Path(exists=True))
@click.option("--quality", type=click.Choice(["maximum", "balanced", "economy"]), default="balanced")
@click.option("--task", default="", help="Task query for relevance scoring")
@click.option("--output", "-o", type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Output stats as JSON")
def optimize_messages_cmd(
    path: str, quality: str, task: str, output: str | None, as_json: bool
) -> None:
    """Optimize a chat messages JSON file for harness/LLM prompts."""
    from token_engine.harness import HarnessClient

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    messages = data if isinstance(data, list) else data.get("messages", [])
    if not messages:
        raise click.ClickException("Expected a JSON array or {\"messages\": [...]}")

    client = HarnessClient(
        config=EngineConfig(quality_level=QualityLevel(quality), task_query=task),
        prefer_api=False,
    )
    result = client.optimize_messages(messages, task_query=task, quality=quality)

    if output:
        Path(output).write_text(result["content"], encoding="utf-8")

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    stats = result.get("stats", {})
    click.echo(f"Original:    {stats.get('original_tokens', 0):>8,} tokens")
    click.echo(f"Optimized:   {stats.get('optimized_tokens', 0):>8,} tokens")
    click.echo(f"Saved:       {stats.get('tokens_saved', 0):>8,} tokens")
    ratio = stats.get("compression_ratio", 0)
    click.echo(f"Compression: {ratio * 100:>7.1f}%")
    if not output:
        click.echo("\n--- Optimized prompt ---\n")
        click.echo(result["content"])


@cli.command("compact-tools")
@click.argument("path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path())
@click.option("--mode", type=click.Choice(["compact", "lazy"]), default="compact", show_default=True)
@click.option("--level", type=click.Choice(["low", "medium", "high", "max"]), default="medium", show_default=True)
def compact_tools_cmd(path: str, output: str | None, mode: str, level: str) -> None:
    """Compact MCP tool schema definitions to reduce token bloat."""
    engine = TokenEngine()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tools = data if isinstance(data, list) else data.get("tools", [])

    if mode == "lazy":
        catalog, session_id, stats = engine.lazy_tool_catalog(tools, level=level)
        if output:
            Path(output).write_text(catalog, encoding="utf-8")
        click.echo(f"Mode: lazy ({level})")
        click.echo(f"Session: {session_id}")
        click.echo(f"Tools: {stats.get('tools', len(tools))}")
        click.echo(f"Catalog:   {stats.get('catalog_chars', len(catalog)):,} chars")
        click.echo(f"Full JSON: {stats.get('full_chars', 0):,} chars")
        click.echo(f"Saved:     {stats.get('saved_vs_full', 0):,} chars ({stats.get('ratio_vs_full', 0) * 100:.1f}%)")
        if not output:
            click.echo("\n--- Catalog ---\n")
            click.echo(catalog)
        return

    compacted, stats = engine.compact_tool_schemas(tools)

    if output:
        Path(output).write_text(json.dumps(compacted, indent=2), encoding="utf-8")

    click.echo(f"Tools: {stats.get('tools', len(tools))}")
    click.echo(f"Original:  {stats.get('original_chars', 0):,} chars")
    click.echo(f"Compacted: {stats.get('compacted_chars', 0):,} chars")
    click.echo(f"Saved:     {stats.get('saved_chars', 0):,} chars ({stats.get('ratio', 0) * 100:.1f}%)")


@cli.command("cursor-setup")
@click.option("--global", "global_setup", is_flag=True, help="Show global MCP config")
def cursor_setup_cmd(global_setup: bool) -> None:
    """Set up Ponytail + Caveman + Token Engine for Cursor."""
    from token_engine.cli.cursor_setup import run_cursor_setup
    run_cursor_setup(global_setup=global_setup)


@cli.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8741, show_default=True, type=int)
def serve_cmd(host: str, port: int) -> None:
    """Start REST API for harness integration (optimize-context on :8741)."""
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException("Install API deps: pip install 'token-engine[api]'") from exc

    console.banner(f"API · http://{host}:{port}")
    console.ok("POST /optimize-context")
    console.ok("POST /optimize")
    click.echo()
    uvicorn.run("token_engine.api.server:app", host=host, port=port, log_level="info")


@cli.command("benchmark")
@click.option("--fixtures", type=click.Path(exists=True), default=None)
@click.option("--quality", type=click.Choice(["maximum", "balanced", "economy"]), default="balanced")
@click.option("--check-baseline", is_flag=True, help="Fail if ratios regress below benchmarks/baseline.json")
@click.option("--baseline", type=click.Path(exists=True), default=None, help="Baseline thresholds JSON")
def benchmark_cmd(
    fixtures: str | None, quality: str, check_baseline: bool, baseline: str | None
) -> None:
    """Run compression benchmarks."""
    from token_engine.benchmark.runner import BenchmarkRunner

    root = Path(__file__).parent.parent.parent.parent
    fixtures_dir = Path(fixtures) if fixtures else root / "benchmarks" / "fixtures"
    baseline_path = Path(baseline) if baseline else root / "benchmarks" / "baseline.json"
    runner = BenchmarkRunner(EngineConfig(quality_level=QualityLevel(quality)))
    results = runner.run_all(fixtures_dir)
    runner.print_report(results)

    if baseline_path.exists():
        ref = json.loads(baseline_path.read_text(encoding="utf-8")).get("reference_total_ratio")
        if ref is not None:
            total_orig = sum(r.original_tokens for r in results)
            total_saved = sum(r.tokens_saved for r in results)
            ratio = total_saved / total_orig if total_orig else 0.0
            gap = (ref - ratio) * 100
            console.section("Targets")
            console.stat_ratio("Total ref", ref, width=16)
            console.stat_ratio("Total now", ratio, width=16)
            click.secho(f"  {'Gap':<16} ", fg="bright_black", nl=False)
            gap_fg = "green" if gap <= 0 else "yellow"
            click.secho(f"{gap:+.1f} pp", fg=gap_fg, bold=True)
            session_ref = json.loads(baseline_path.read_text(encoding="utf-8")).get("reference_session_ratio")
            if session_ref is not None:
                session_results = [r for r in results if r.category == "session"]
                so = sum(r.original_tokens for r in session_results)
                ss = sum(r.tokens_saved for r in session_results)
                sr = ss / so if so else 0.0
                console.stat_ratio("Session ref", session_ref, width=16)
                console.stat_ratio("Session now", sr, width=16)
                sg = (session_ref - sr) * 100
                click.secho(f"  {'Session gap':<16} ", fg="bright_black", nl=False)
                click.secho(f"{sg:+.1f} pp", fg="green" if sg <= 0 else "yellow", bold=True)

    if check_baseline:
        failures = runner.check_baseline(results, baseline_path)
        if failures:
            console.section("Baseline regressions")
            for msg in failures:
                console.fail(msg)
            raise SystemExit(1)
        console.ok(f"Baseline OK ({baseline_path.name})")


@cli.command("stats")
@click.argument("path", type=click.Path(exists=True))
def stats_cmd(path: str) -> None:
    """Quick token count and cost estimate."""
    engine = TokenEngine()
    text = Path(path).read_text(encoding="utf-8")
    tokens = engine.count_tokens(text)
    cost = engine.estimate_cost(tokens)
    click.echo(f"File: {path}")
    console.stat("Tokens", f"{tokens:,}")
    console.stat("Characters", f"{len(text):,}")
    console.stat("Est. cost", f"${cost:.4f}")


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
    console.section("Compression")
    console.stat_tokens("Original", stats.original_tokens)
    console.stat_tokens("Optimized", stats.optimized_tokens)
    console.stat_tokens("Saved", stats.tokens_saved)
    console.stat_ratio("Ratio", stats.compression_ratio)
    console.stat("Latency", f"{stats.latency_ms:.1f} ms")


if __name__ == "__main__":
    cli()
