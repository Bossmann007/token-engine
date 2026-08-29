"""Cursor setup utilities."""

from __future__ import annotations

import json
from pathlib import Path

import click

from token_engine.cli import console

WORKSPACE = Path(__file__).resolve().parents[3]
CURSOR_DIR = WORKSPACE / ".cursor"
RULES_SRC = CURSOR_DIR / "rules"
MCP_TEMPLATE = CURSOR_DIR / "mcp.json"


def run_cursor_setup(*, global_setup: bool = False) -> None:
    """Print Cursor setup instructions and verify project files."""
    console.banner("Cursor Setup")

    rules = list(RULES_SRC.glob("*.mdc")) if RULES_SRC.exists() else []
    console.section("Project rules")
    for r in rules:
        console.ok(r.name)

    console.section("MCP")
    console.ok("token-engine — caveman_compress, token_engine_compress_session, caveman_stats")
    console.ok("codebase-memory — search_graph, get_code_snippet")

    console.section("Enable in Cursor")
    steps = [
        "Open this project in Cursor",
        "Settings → MCP → enable token-engine + codebase-memory",
        "Rules: ponytail, caveman, token-engine, cbm-first",
        "Global env: see ~/cursor-kit (Ultimate Cursor Environment)",
        "API: token-engine serve → POST /optimize-context",
    ]
    for i, step in enumerate(steps, 1):
        click.secho(f"  {i}. ", fg="cyan", nl=False)
        click.echo(step)

    if global_setup and MCP_TEMPLATE.exists():
        console.section("Global MCP template")
        mcp_config = json.loads(MCP_TEMPLATE.read_text())
        abs_src = str(WORKSPACE / "src")
        mcp_config["mcpServers"]["token-engine"]["env"]["PYTHONPATH"] = abs_src
        click.echo(json.dumps(mcp_config, indent=2))

    click.echo()
    click.secho("  ponytail ", fg="green", nl=False)
    click.secho("= minimal code  ", nl=False)
    click.secho("caveman ", fg="yellow", nl=False)
    click.secho("= terse output  ", nl=False)
    click.secho("MCP ", fg="cyan", nl=False)
    click.secho("= compress tools")
