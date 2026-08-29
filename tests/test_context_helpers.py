"""Tests for context-level dedup helpers."""

import json
from pathlib import Path

from token_engine.compressor.context_helpers import (
    collapse_grep_into_reads,
    filter_git_noise_paths,
    strip_line_gutters,
)
from token_engine.compressor.deduplicator import Deduplicator
from token_engine.core.types import ContentItem, ContentType


class TestContextHelpers:
    def test_strip_line_gutters(self):
        text = "   1| import os\n   2| import sys"
        stripped, changed = strip_line_gutters(text)
        assert changed
        assert "1|" not in stripped
        assert "import os" in stripped

    def test_collapse_grep_into_reads(self):
        items = [
            ContentItem(
                id="read",
                content="def main():\n    print('hello')",
                content_type=ContentType.CODE,
                source="src/app.py",
            ),
            ContentItem(
                id="grep",
                content="src/app.py:4: def main():\nsrc/app.py:5:     print('hello')",
                content_type=ContentType.SEARCH,
                source="grep",
            ),
        ]
        assert collapse_grep_into_reads(items) == 1
        assert "see earlier read" in items[1].content

    def test_git_noise_filter(self):
        signal, noise = filter_git_noise_paths(
            ["debug.log", "node_modules/pkg", ".pytest_cache/x", "src/auth/login.py"]
        )
        assert "debug.log" in signal
        assert "src/auth/login.py" in signal
        assert any("node_modules" in path for path in noise)


class TestSubsetDuplicates:
    def test_subset_duplicate_pair(self):
        full = "alpha beta gamma " * 20
        subset = "alpha beta gamma " * 10
        pairs = Deduplicator().find_duplicates_among_items([("full", full), ("partial", subset)])
        assert ("full", "partial") in pairs

    def test_agent_context_fixture_pair(self):
        data = json.loads((Path(__file__).parent.parent / "benchmarks/fixtures/agent_context.json").read_text())
        pairs = Deduplicator().find_duplicates_among_items(
            [(item["id"], item["content"]) for item in data["items"]]
        )
        assert any(dup_id == "duplicate_read" for _, dup_id in pairs)
