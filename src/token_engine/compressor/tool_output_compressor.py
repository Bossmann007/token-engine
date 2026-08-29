"""Tool output compression — git, grep, pytest, npm, etc. (rtk/token-optimizer-inspired)."""

from __future__ import annotations

import re

from token_engine.compressor.base import CompressResult, Compressor
from token_engine.core.types import ContentType
from token_engine.compressor.context_helpers import filter_git_noise_paths
from token_engine.compressor.detect import detect_content_type
from token_engine.compressor.log_compressor import LogCompressor


class ToolOutputCompressor(Compressor):
    """Routes tool output to specialized compactors."""

    def __init__(self) -> None:
        self._log = LogCompressor()

    @property
    def name(self) -> str:
        return "tool_output"

    @property
    def content_types(self) -> set[ContentType]:
        return {ContentType.TOOL_OUTPUT, ContentType.TERMINAL, ContentType.SEARCH, ContentType.UNKNOWN}

    def compress(self, text: str, *, aggressiveness: float = 0.5, query: str = "") -> CompressResult:
        tool_hint = self._detect_tool(text)

        if tool_hint == "git":
            return self._compress_git(text, aggressiveness)
        if tool_hint == "pytest":
            return self._compress_pytest(text, aggressiveness)
        if tool_hint == "grep":
            return self._compress_grep(text, aggressiveness)
        if tool_hint == "ls":
            return self._compress_ls(text, aggressiveness)
        if tool_hint == "npm":
            return self._compress_npm(text, aggressiveness)

        # Fallback to log compressor for generic output
        detected = detect_content_type(text)
        if detected in (ContentType.LOG, ContentType.TERMINAL):
            return self._log.compress(text, aggressiveness=aggressiveness, query=query)

        return CompressResult(content=text, strategy=self.name, compressed=False)

    def _detect_tool(self, text: str) -> str | None:
        if re.search(r"^(On branch |Changes not staged|Untracked files|diff --git)", text, re.MULTILINE):
            return "git"
        if re.search(r"(=+ FAILURES =+|FAILED|passed|pytest|PASSED|ERROR collecting)", text, re.MULTILINE):
            return "pytest"
        if re.search(r"^(npm WARN|npm ERR|added \d+ packages|up to date)", text, re.MULTILINE):
            return "npm"
        if re.search(r"^(total \d+|drwx|[-rwxls]{10})", text, re.MULTILINE):
            return "ls"
        if text.count(":") > 5 and re.search(r"^\S+\.(py|ts|js|go|rs):\d+:", text, re.MULTILINE):
            return "grep"
        return None

    def _compress_git(self, text: str, aggressiveness: float) -> CompressResult:
        lines = text.splitlines()
        parts: list[str] = []

        branch = next((l for l in lines if l.startswith("On branch")), None)
        if branch:
            parts.append(branch)

        sections = {"modified": [], "added": [], "deleted": [], "untracked": []}
        current = None
        for line in lines:
            if "Changes not staged" in line or "Changes to be committed" in line:
                current = "modified"
            elif "Untracked files" in line:
                current = "untracked"
            elif line.startswith("\t") or line.startswith("  "):
                stripped = line.strip()
                if current and stripped:
                    sections[current].append(stripped)

        max_files = max(5, int(15 * (1 - aggressiveness)))
        for name, files in sections.items():
            if not files:
                continue
            if name == "untracked":
                signal, noise = filter_git_noise_paths(files)
                parts.append(f"{name}: {len(files)} files ({len(noise)} noise omitted)")
                parts.extend(f"  {f}" for f in signal[:max_files])
                if len(signal) > max_files:
                    parts.append(f"  ... {len(signal) - max_files} more")
                continue
            parts.append(f"{name}: {len(files)} files")
            parts.extend(f"  {f}" for f in files[:max_files])
            if len(files) > max_files:
                parts.append(f"  ... {len(files) - max_files} more")

        out = "\n".join(parts) if parts else text
        if len(out) >= len(text):
            return CompressResult(content=text, strategy="git", compressed=False)
        return CompressResult(content=out, strategy="git", lossless=False, compressed=True)

    def _compress_pytest(self, text: str, aggressiveness: float) -> CompressResult:
        lines = text.splitlines()
        summary: list[str] = []
        failed_tests: list[str] = []
        failure_sections: list[str] = []
        error_lines: list[str] = []
        in_failures_section = False
        current_section: list[str] = []

        for line in lines:
            if re.search(r"\d+ passed|\d+ failed|\d+ error", line, re.IGNORECASE):
                summary.append(line)
            if "FAILED" in line and "::" in line:
                failed_tests.append(line.strip())
            if line.strip().startswith("E ") and (
                "AssertionError" in line or "Error" in line or "Exception" in line
            ):
                error_lines.append(line.strip())
            if "FAILURES" in line and line.startswith("="):
                in_failures_section = True
                current_section = [line]
                continue
            if in_failures_section:
                if line.startswith("=") and len(current_section) > 1:
                    failure_sections.append("\n".join(current_section))
                    in_failures_section = False
                    current_section = []
                else:
                    current_section.append(line)

        if current_section:
            failure_sections.append("\n".join(current_section))

        max_failures = max(3, int(10 * (1 - aggressiveness * 0.5)))
        parts: list[str] = []
        if summary:
            parts.extend(summary[:5])
        if failed_tests:
            parts.append(f"=== FAILED TESTS ({len(failed_tests)}) ===")
            parts.extend(failed_tests[:max_failures])
        if error_lines and not failure_sections:
            parts.append(f"=== ERROR LINES ({len(error_lines)}) ===")
            parts.extend(error_lines[:max_failures])
        if failure_sections:
            parts.append(f"=== FAILURE DETAILS ({len(failure_sections)}) ===")
            parts.extend(failure_sections[:max_failures])

        out = "\n".join(parts)
        if not out or len(out) >= len(text):
            return CompressResult(content=text, strategy="pytest", compressed=False)
        return CompressResult(content=out, strategy="pytest", lossless=False, compressed=True)

    def _compress_grep(self, text: str, aggressiveness: float) -> CompressResult:
        lines = [l for l in text.splitlines() if l.strip()]
        max_lines = max(10, int(50 * (1 - aggressiveness)))

        if len(lines) <= max_lines:
            return CompressResult(content=text, strategy="grep", compressed=False)

        # Group by file
        by_file: dict[str, list[str]] = {}
        for line in lines:
            if ":" in line:
                file, _, rest = line.partition(":")
                by_file.setdefault(file, []).append(rest.strip())

        parts: list[str] = []
        max_per_file = max(2, int(5 * (1 - aggressiveness)))
        for file, matches in sorted(by_file.items(), key=lambda x: -len(x[1]))[:max_lines // max_per_file]:
            parts.append(f"{file}: {len(matches)} matches")
            for m in matches[:max_per_file]:
                parts.append(f"  {m[:120]}")
            if len(matches) > max_per_file:
                parts.append(f"  ... {len(matches) - max_per_file} more")

        out = "\n".join(parts)
        if len(out) >= len(text):
            return CompressResult(content=text, strategy="grep", compressed=False)
        return CompressResult(content=out, strategy="grep", lossless=False, compressed=True)

    def _compress_ls(self, text: str, aggressiveness: float) -> CompressResult:
        lines = [l for l in text.splitlines() if l.strip()]
        max_entries = max(15, int(50 * (1 - aggressiveness)))
        if len(lines) <= max_entries:
            return CompressResult(content=text, strategy="ls", compressed=False)
        out = "\n".join(lines[:max_entries]) + f"\n... {len(lines) - max_entries} more entries"
        return CompressResult(content=out, strategy="ls", lossless=False, compressed=True)

    def _compress_npm(self, text: str, aggressiveness: float) -> CompressResult:
        lines = text.splitlines()
        errors = [l for l in lines if "ERR" in l or "error" in l.lower()]
        warnings = [l for l in lines if "WARN" in l]
        summary = [l for l in lines if re.search(r"added \d+|up to date|audited", l)]

        parts = summary[:3]
        if errors:
            parts.append(f"errors: {len(errors)}")
            parts.extend(errors[:10])
        if warnings and aggressiveness < 0.7:
            parts.append(f"warnings: {len(warnings)}")
            parts.extend(warnings[:5])

        out = "\n".join(parts) if parts else text
        if len(out) >= len(text):
            return CompressResult(content=text, strategy="npm", compressed=False)
        return CompressResult(content=out, strategy="npm", lossless=False, compressed=True)
