"""RTK enable flag + detector/compressor consistency."""

from token_engine.compressor import rtk_filters
from token_engine.compressor.tool_output_compressor import ToolOutputCompressor

NPM = "\n".join([
    "npm warn deprecated foo@1.0.0: stuff",
    "npm warn deprecated bar@2.0.0: stuff",
    "added 200 packages in 12s",
    "audited 200 packages in 3s",
] * 2)

JEST = "\n".join([
    "PASS src/a.test.js",
    "FAIL src/b.test.js",
    "  ● something failed",
    "Test Suites: 1 failed, 1 passed, 2 total",
    "Tests:       1 failed, 5 passed, 6 total",
])

PLAYWRIGHT = "\n".join([
    "Running 3 tests using 1 worker",
    "  1 passed (playwright)",
    "  2 failed",
    "TimeoutError: timeout 30000ms exceeded",
    "Error: expect(received).toBe(expected)",
] * 3)

TRACEBACK = "\n".join([
    "Traceback (most recent call last):",
    '  File "app.py", line 1, in <module>',
    "    main()",
    '  File "app.py", line 10, in main',
    "    boom()",
    "ValueError: bad",
] + [f"  noise line {i}" for i in range(40)])


class TestEnableRtkFlag:
    def test_npm_respects_disable(self):
        on = ToolOutputCompressor(enable_rtk=True).compress(NPM)
        off = ToolOutputCompressor(enable_rtk=False).compress(NPM)
        assert on.compressed
        assert on.strategy.startswith("rtk:")
        assert not off.compressed or not off.strategy.startswith("rtk:")

    def test_jest_respects_disable(self):
        on = ToolOutputCompressor(enable_rtk=True).compress(JEST)
        off = ToolOutputCompressor(enable_rtk=False).compress(JEST)
        assert on.compressed
        assert on.strategy.startswith("rtk:") or on.strategy == "jest"
        assert not (off.compressed and off.strategy.startswith("rtk:"))


class TestRtkMapConsistency:
    def test_every_detector_has_compressor(self):
        missing = [name for name, _ in rtk_filters.DETECTORS if name not in rtk_filters._COMPRESSORS]
        assert missing == []

    def test_playwright_compresses(self):
        assert rtk_filters.detect_rtk_tool(PLAYWRIGHT) == "playwright"
        result = rtk_filters.compress_rtk_tool(PLAYWRIGHT, "playwright", aggressiveness=0.7)
        assert result.compressed
        assert len(result.content) < len(PLAYWRIGHT)

    def test_traceback_mapped(self):
        assert rtk_filters.detect_rtk_tool(TRACEBACK) == "traceback"
        result = rtk_filters.compress_rtk_tool(TRACEBACK, "traceback", aggressiveness=0.7)
        assert result.compressed
        assert "ValueError" in result.content
        assert len(result.content) < len(TRACEBACK)

    def test_node_stack_not_eaten_by_terraform(self):
        node = "\n".join(
            ["Error: boom", "    at Object.<anonymous> (/app/src/a.js:10:5)"]
            + [f"    at frame_{i} (/app/src/x.js:{i}:1)" for i in range(60)]
        )
        assert rtk_filters.detect_rtk_tool(node) is None
        result = ToolOutputCompressor(enable_rtk=True).compress(node)
        assert result.content.count(" at ") >= 60
        assert "frame_59" in result.content

    def test_json_with_error_strings_stays_json(self):
        from token_engine.compressor.detect import detect_content_type
        from token_engine.core.types import ContentType
        import json

        payload = json.dumps({"errors": [f"Error: n{i}" for i in range(20)]})
        assert rtk_filters.detect_rtk_tool(payload) is None
        assert detect_content_type(payload) == ContentType.JSON

    def test_node_stack_typed_as_log(self):
        from token_engine.compressor.detect import detect_content_type
        from token_engine.core.types import ContentType

        node = "\n".join(
            ["Error: boom"] + [f"    at frame_{i} (/app/x.js:{i}:1)" for i in range(5)]
        )
        assert detect_content_type(node) == ContentType.LOG
