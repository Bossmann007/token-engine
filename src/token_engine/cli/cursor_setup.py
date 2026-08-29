"""Cursor setup utilities."""

from __future__ import annotations

import json
from pathlib import Path

import click

WORKSPACE = Path(__file__).resolve().parents[3]
CURSOR_DIR = WORKSPACE / ".cursor"
RULES_SRC = CURSOR_DIR / "rules"
MCP_TEMPLATE = CURSOR_DIR / "mcp.json"


def run_cursor_setup(*, global_setup: bool = False) -> None:
    """Print Cursor setup instructions and verify project files."""
    click.echo("Token Engine — Cursor Setup")
    click.echo("=" * 40)

    rules = list(RULES_SRC.glob("*.mdc")) if RULES_SRC.exists() else []
    click.echo(f"\n✓ Project rules ({len(rules)} files in .cursor/rules/):")
    for r in rules:
        click.echo(f"  • {r.name}")

    click.echo("\n✓ MCP server: .cursor/mcp.json")
    click.echo("  Tools: caveman_compress, caveman_retrieve, caveman_stats")

    click.echo("\n--- Enable in Cursor ---")
    click.echo("1. Open this project in Cursor")
    click.echo("2. Settings → MCP → enable 'token-engine'")
    click.echo("3. Rules auto-apply: ponytail + caveman + token-engine + cbm-first")
    click.echo("4. Harness API: token-engine serve  →  POST /optimize-context")

    if global_setup and MCP_TEMPLATE.exists():
        click.echo("\n--- Global MCP (optional) ---")
        mcp_config = json.loads(MCP_TEMPLATE.read_text())
        abs_src = str(WORKSPACE / "src")
        mcp_config["mcpServers"]["token-engine"]["env"]["PYTHONPATH"] = abs_src
        click.echo(json.dumps(mcp_config, indent=2))

    click.echo("\n✓ Ponytail = minimal code | Caveman = terse output | MCP = compress tools")
