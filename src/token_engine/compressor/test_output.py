"""Unified test runner output compression (pytest, jest, vitest, playwright)."""

from __future__ import annotations

import re

from token_engine.compressor.base import CompressResult

_PYTEST = re.compile(r"(=+ FAILURES =+|FAILED|passed|pytest|PASSED|ERROR collecting)", re.M)
_JEST = re.compile(r"(Test Suites:|^Tests:\s+\d+|^FAIL \S|^\s*● )", re.M)
_VITEST = re.compile(r"(FAIL\s+\S+|Tests\s+\d+\s+passed|RUN\s+v)", re.M)
_PLAYWRIGHT = re.compile(r"(\d+ failed|\d+ passed|Error:|TimeoutError|expect\()", re.M)


def detect_test_runner(text: str) -> str | None:
    if _JEST.search(text):
        return "jest"
    if _PYTEST.search(text):
        return "pytest"
    if _VITEST.search(text):
        return "vitest"
    if _PLAYWRIGHT.search(text) and "playwright" in text.lower():
        return "playwright"
    return None


def compress_test_output(text: str, runner: str, *, aggressiveness: float = 0.5) -> CompressResult:
    fn = {
        "pytest": _compress_pytest,
        "jest": _compress_jest,
        "vitest": _compress_vitest,
        "playwright": _compress_playwright,
    }.get(runner)
    if not fn:
        return CompressResult(content=text, strategy="test_output", compressed=False)
    return fn(text, aggressiveness)


def _compress_pytest(text: str, aggressiveness: float) -> CompressResult:
    from token_engine.compressor.tool_output_compressor import ToolOutputCompressor

    return ToolOutputCompressor()._compress_pytest(text, aggressiveness)


def _compress_jest(text: str, aggressiveness: float) -> CompressResult:
    from token_engine.compressor import rtk_filters

    return rtk_filters._compress_jest(text, aggressiveness)


def _compress_vitest(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    fails = [l for l in lines if l.startswith("FAIL ") or "AssertionError" in l or "Expected" in l]
    summary = [l for l in lines if re.search(r"Tests\s+\d+|Test Files", l)]
    passes = [l for l in lines if l.startswith("PASS ") or l.strip().startswith("✓")]
    parts = summary[:2]
    if fails:
        parts.append(f"=== FAIL ({len(fails)}) ===")
        parts.extend(l.strip() for l in fails[:8])
    if passes and len(passes) > 2:
        parts.append(f"PASS: {len(passes)} omitted")
    out = "\n".join(parts)
    if not out or len(out) >= len(text):
        return CompressResult(content=text, strategy="vitest", compressed=False)
    return CompressResult(content=out, strategy="vitest", lossless=False, compressed=True)


def _compress_playwright(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"Error:|TimeoutError|expect\(|failed", l, re.I)]
    summary = [l for l in lines if re.search(r"\d+ (failed|passed|skipped)", l, re.I)]
    parts = summary[:3]
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:10])
    out = "\n".join(parts)
    if not out or len(out) >= len(text):
        return CompressResult(content=text, strategy="playwright", compressed=False)
    return CompressResult(content=out, strategy="playwright", lossless=False, compressed=True)
