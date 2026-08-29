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


WEBPACK_LOG = "\n".join([
    "asset main.js 842 KiB [emitted] (name: main)",
    "asset vendor.js 1.2 MiB [emitted] (name: vendor)",
    "asset runtime.js 12 KiB [emitted] (name: runtime)",
] * 8 + [
    "WARNING in ./src/App.tsx",
    "Module not found: Error: Can't resolve './missing'",
    "ERROR in ./src/auth/login.ts",
    "webpack compiled with 1 error and 2 warnings in 4521 ms",
])

GRADLE_LOG = "\n".join([
    "> Task :app:compileJava",
    "> Task :app:processResources",
    "> Task :app:classes",
    "> Task :app:jar",
    "> Task :app:bootJar",
] * 6 + [
    "BUILD SUCCESSFUL in 18s",
    "12 actionable tasks: 12 executed",
])

JOURNAL_LOG = "\n".join([
    "-- Logs begin at Mon 2026-01-01 00:00:00 UTC --",
] + [
    f"Jan 15 10:{i:02d}:01 host systemd[1]: Started session {i}."
    for i in range(40)
] + [
    "Jan 15 10:40:01 host app[999]: ERROR: database connection refused",
    "Jan 15 10:40:02 host app[999]: FATAL: service shutdown",
])

TERRAFORM_LOG = "\n".join([
    "Terraform used the selected providers to generate the following execution plan.",
    "Plan: 3 to add, 1 to change, 0 to destroy.",
    '  # module.network.aws_subnet.public will be created',
    '  + resource "aws_subnet" "public" {',
    '      + cidr_block = "10.0.1.0/24"',
    '  + resource "aws_subnet" "private" {',
    '  ~ resource "aws_instance" "web" {',
] * 5 + [
    "Error: creating EC2 Instance: UnauthorizedOperation",
])


class TestRTKExtendedFilters:
    def test_webpack(self):
        assert rtk_filters.detect_rtk_tool(WEBPACK_LOG) == "webpack"
        result = rtk_filters.compress_rtk_tool(WEBPACK_LOG, "webpack", aggressiveness=0.5)
        assert result.compressed
        assert "ERROR in" in result.content
        assert "webpack compiled" in result.content

    def test_gradle(self):
        assert rtk_filters.detect_rtk_tool(GRADLE_LOG) == "gradle"
        result = rtk_filters.compress_rtk_tool(GRADLE_LOG, "gradle", aggressiveness=0.5)
        assert result.compressed
        assert "BUILD SUCCESSFUL" in result.content

    def test_journalctl(self):
        assert rtk_filters.detect_rtk_tool(JOURNAL_LOG) == "journalctl"
        result = rtk_filters.compress_rtk_tool(JOURNAL_LOG, "journalctl", aggressiveness=0.5)
        assert result.compressed
        assert "ERROR:" in result.content
        assert "older log lines omitted" in result.content

    def test_terraform(self):
        assert rtk_filters.detect_rtk_tool(TERRAFORM_LOG) == "terraform"
        result = rtk_filters.compress_rtk_tool(TERRAFORM_LOG, "terraform", aggressiveness=0.5)
        assert result.compressed
        assert "Plan: 3 to add" in result.content
        assert "Error:" in result.content

    def test_via_tool_output_compressor(self):
        from token_engine.compressor.tool_output_compressor import ToolOutputCompressor

        comp = ToolOutputCompressor(enable_rtk=True)
        result = comp.compress(GRADLE_LOG, aggressiveness=0.5)
        assert result.compressed
        assert result.strategy == "rtk:gradle"


NPM_LOG = "\n".join([
    "npm http fetch GET 200 https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
    "npm WARN deprecated inflight@1.0.6: This module is not supported",
] * 15 + [
    "added 847 packages, and audited 848 packages in 23s",
    "found 3 vulnerabilities (1 moderate, 2 high)",
])

JEST_LOG = "\n".join([
    "PASS src/utils/format.test.ts",
    "PASS src/utils/date.test.ts",
] * 8 + [
    "FAIL src/auth/login.test.ts",
    "  ● login › rejects special characters in password",
    "    Expected: 200",
    "    Received: 500",
    "      at Object.<anonymous> (src/auth/login.test.ts:42:5)",
    "Test Suites: 1 failed, 8 passed, 9 total",
    "Tests:       1 failed, 64 passed, 65 total",
])

PNPM_LOG = "\n".join([
    "Progress: resolved 1, reused 0, downloaded 0, added 0",
] * 20 + [
    "Packages: +512",
    "Done in 14.2s",
])

VITE_LOG = "\n".join([
    "vite v5.4.0 building for production...",
    "transforming...",
] + [
    f"dist/assets/chunk-{i}.js  120.{i} kB │ gzip: 40.{i} kB"
    for i in range(15)
] + [
    "✓ built in 8.42s",
])


class TestRTKNodeFilters:
    def test_npm(self):
        assert rtk_filters.detect_rtk_tool(NPM_LOG) == "npm"
        result = rtk_filters.compress_rtk_tool(NPM_LOG, "npm", aggressiveness=0.5)
        assert result.compressed
        assert "added 847 packages" in result.content

    def test_jest(self):
        assert rtk_filters.detect_rtk_tool(JEST_LOG) == "jest"
        result = rtk_filters.compress_rtk_tool(JEST_LOG, "jest", aggressiveness=0.5)
        assert result.compressed
        assert "Test Suites:" in result.content
        assert "FAIL src/auth" in result.content
        assert "Expected:" in result.content
        assert "suites omitted" in result.content

    def test_pnpm(self):
        assert rtk_filters.detect_rtk_tool(PNPM_LOG) == "pnpm"
        result = rtk_filters.compress_rtk_tool(PNPM_LOG, "pnpm", aggressiveness=0.5)
        assert result.compressed
        assert "Done in 14.2s" in result.content

    def test_vite(self):
        assert rtk_filters.detect_rtk_tool(VITE_LOG) == "vite"
        result = rtk_filters.compress_rtk_tool(VITE_LOG, "vite", aggressiveness=0.5)
        assert result.compressed
        assert "built in 8.42s" in result.content

    def test_jest_via_tool_output(self):
        from token_engine.compressor.tool_output_compressor import ToolOutputCompressor

        comp = ToolOutputCompressor(enable_rtk=True)
        result = comp.compress(JEST_LOG, aggressiveness=0.5)
        assert result.compressed
        assert result.strategy == "rtk:jest"


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
