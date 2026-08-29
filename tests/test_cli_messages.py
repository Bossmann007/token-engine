"""CLI optimize-messages command tests."""

import json
from pathlib import Path

from click.testing import CliRunner

from token_engine.cli.main import cli

FIXTURES = Path(__file__).parent.parent / "benchmarks" / "fixtures"


class TestOptimizeMessagesCLI:
    def test_optimize_messages(self):
        runner = CliRunner()
        path = FIXTURES / "messages_session.json"
        result = runner.invoke(cli, ["optimize-messages", str(path), "--task", "fix auth login"])
        assert result.exit_code == 0
        assert "Optimized prompt" in result.output
        assert "AssertionError" in result.output or "auth" in result.output.lower()

    def test_optimize_messages_json(self):
        runner = CliRunner()
        path = FIXTURES / "messages_session.json"
        result = runner.invoke(cli, ["optimize-messages", str(path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["content"]
        assert data["stats"]["tokens_saved"] >= 0
