"""Pytest/git compression polish for weak benchmark fixtures."""

import json
from pathlib import Path

from token_engine.compressor.tool_output_compressor import ToolOutputCompressor
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType

FIXTURES = Path(__file__).parent.parent / "benchmarks" / "fixtures"


class TestPytestPolish:
    def test_drops_session_header_and_dedupes(self):
        text = FIXTURES.joinpath("pytest_failures.json").read_text(encoding="utf-8")
        content = json.loads(text)["content"]
        result = ToolOutputCompressor().compress(content, aggressiveness=0.5)
        assert result.compressed
        assert "test session starts" not in result.content
        assert "test_delete_user" in result.content
        assert "AssertionError" in result.content
        assert result.content.count("FAILED tests/test_api.py::test_delete_user") <= 1

    def test_fixture_improves(self):
        data = json.loads(FIXTURES.joinpath("pytest_failures.json").read_text(encoding="utf-8"))
        engine = TokenEngine()
        result = engine.optimize(data["content"], content_type="log")
        assert result.stats.compression_ratio >= 0.42


class TestGitTaskFilter:
    def test_hides_unrelated_untracked(self):
        git_text = (
            "On branch fix/auth\n"
            "Changes not staged for commit:\n"
            "  modified:   src/auth/login.py\n"
            "  modified:   README.md\n\n"
            "Untracked files:\n"
            "  debug.log\n"
            "  tmp_output.txt\n"
        )
        comp = ToolOutputCompressor()
        query = "Fix bug in src/auth/login.py"
        result = comp.compress(git_text, aggressiveness=0.5, query=query)
        assert "login.py" in result.content
        assert "README.md" not in result.content
        assert "debug.log" not in result.content
        assert "none task-relevant" in result.content

    def test_agent_context_git_shrinks(self):
        data = json.loads(FIXTURES.joinpath("agent_context.json").read_text(encoding="utf-8"))
        engine = TokenEngine()
        items = [
            ContentItem(**{**it, "content_type": ContentType(it.get("content_type", "unknown"))})
            for it in data["items"]
        ]
        result = engine.optimize_context(items)
        assert result.stats.compression_ratio >= 0.38
        assert "login.py" in result.content
        assert "debug.log" not in result.content
