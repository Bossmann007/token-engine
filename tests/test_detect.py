"""Tests for content type detection."""

from token_engine.compressor.detect import detect_content_type
from token_engine.core.types import ContentType


class TestDetectRTK:
    def test_npm_is_tool_output(self):
        text = "npm WARN deprecated pkg\nadded 42 packages, and audited 43 packages in 5s"
        assert detect_content_type(text) == ContentType.TOOL_OUTPUT

    def test_jest_is_tool_output(self):
        text = "PASS src/a.test.ts\nTest Suites: 1 passed, 1 total"
        assert detect_content_type(text) == ContentType.TOOL_OUTPUT

    def test_plain_text_unchanged(self):
        assert detect_content_type("hello world") == ContentType.TEXT
