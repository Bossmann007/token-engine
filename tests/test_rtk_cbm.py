"""Tests for RTK filters and codebase-memory bridge."""

from token_engine.compressor.cbm_bridge import collapse_large_reads_to_cbm
from token_engine.compressor import rtk_filters
from token_engine.core.types import ContentItem, ContentType


DOCKER_LOG = "\n".join([
    "Sending build context to Docker daemon  2.048kB",
    "Step 1/12 : FROM python:3.12",
    " ---> Using cache",
    "Step 2/12 : WORKDIR /app",
    " ---> Running in abc123",
    "Step 3/12 : COPY requirements.txt .",
    "Step 4/12 : RUN pip install -r requirements.txt",
    "Step 5/12 : COPY . .",
    "Successfully built deadbeef",
    "Successfully tagged app:latest",
] * 3)

CARGO_LOG = "\n".join([
    "   Compiling libc v0.2.150",
    "   Compiling serde v1.0.193",
    "   Compiling tokio v1.35.0",
    "   Compiling my-app v0.1.0 (/src)",
    "    Finished dev [unoptimized + debuginfo] target(s) in 12.34s",
] * 4 + [
    "error[E0308]: mismatched types",
    "  --> src/main.rs:42:9",
])


LARGE_FILE = "\n".join(
    [f"def helper_{i}():\n    return {i}\n" for i in range(40)]
    + ["class Widget:\n    def run(self):\n        pass"]
)


class TestRTKFilters:
    def test_detect_docker(self):
        assert rtk_filters.detect_rtk_tool(DOCKER_LOG) == "docker"

    def test_compress_docker(self):
        result = rtk_filters.compress_rtk_tool(DOCKER_LOG, "docker", aggressiveness=0.5)
        assert result.compressed
        assert len(result.content) < len(DOCKER_LOG)
        assert "Successfully built" in result.content

    def test_detect_cargo_errors(self):
        assert rtk_filters.detect_rtk_tool(CARGO_LOG) == "cargo"

    def test_compress_cargo_preserves_errors(self):
        result = rtk_filters.compress_rtk_tool(CARGO_LOG, "cargo", aggressiveness=0.5)
        assert result.compressed
        assert "error[E0308]" in result.content

    def test_pip_via_tool_output(self):
        from token_engine.compressor.tool_output_compressor import ToolOutputCompressor

        text = "\n".join([
            "Collecting requests",
            "Collecting urllib3",
            "Installing collected packages: urllib3, requests",
            "Successfully installed requests-2.31.0 urllib3-2.0.0",
        ] * 5)
        comp = ToolOutputCompressor()
        result = comp.compress(text, aggressiveness=0.5)
        assert result.compressed
        assert "Successfully installed" in result.content


class TestCBMBridge:
    def test_collapses_large_exploratory_read(self):
        items = [
            ContentItem(
                id="user",
                content="fix bug in utils",
                content_type=ContentType.MESSAGE,
                source="user",
            ),
            ContentItem(
                id="read_utils",
                content=LARGE_FILE,
                content_type=ContentType.CODE,
                source="src/utils/helpers.py",
            ),
        ]
        collapsed = collapse_large_reads_to_cbm(items, task_query="fix bug in utils")
        assert collapsed == 1
        assert "search_graph" in items[1].content
        assert "CBM:" in items[1].content

    def test_preserves_task_focus_file(self):
        auth_file = "\n".join([f"line {i} = {i}" for i in range(50)])
        items = [
            ContentItem(
                id="task",
                content="Fix auth bug in src/auth/login.py",
                content_type=ContentType.MESSAGE,
                source="user",
            ),
            ContentItem(
                id="auth",
                content=auth_file,
                content_type=ContentType.CODE,
                source="src/auth/login.py",
            ),
        ]
        collapsed = collapse_large_reads_to_cbm(
            items, task_query="Fix auth bug in src/auth/login.py special characters"
        )
        assert collapsed == 0
        assert "CBM:" not in items[1].content
