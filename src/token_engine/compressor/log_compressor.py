"""Log compression — preserve errors, stack traces, collapse noise (caveman/rtk-inspired)."""

from __future__ import annotations

import re

from token_engine.compressor.base import CompressResult, Compressor
from token_engine.compressor.log_template import mine_log_templates
from token_engine.core.types import ContentType

PYTEST_PASSED = re.compile(r"::test_\w+\s+PASSED", re.IGNORECASE)
PYTEST_FAILED = re.compile(r"::test_\w+\s+FAILED", re.IGNORECASE)
PYTEST_SECTION = re.compile(r"^(=+\s*(FAILURES|ERRORS|short test summary info)\s*=+)", re.IGNORECASE)
ERROR_PATTERNS = re.compile(
    r"(ERROR|FATAL|CRITICAL|Exception|Traceback|AssertionError|FAILED|Error:|panic!|fatal error)",
    re.IGNORECASE,
)
WARN_PATTERNS = re.compile(r"(WARN|WARNING|deprecated)", re.IGNORECASE)
DEBUG_PATTERNS = re.compile(r"(DEBUG|TRACE|verbose)", re.IGNORECASE)
STACK_LINE = re.compile(r"^\s*(at |File \"|  \w+\.py:\d+|^\s+\^)")

# Quality preservation: never drop these
CRITICAL_PATTERNS = re.compile(
    r"(Traceback|Stack trace|panic|Segmentation fault|OOM|out of memory|"
    r"SyntaxError|TypeError|ImportError|ModuleNotFoundError|"
    r"FAILED|AssertionError|exit code [1-9])",
    re.IGNORECASE,
)


class LogCompressor(Compressor):
    @property
    def name(self) -> str:
        return "log"

    @property
    def content_types(self) -> set[ContentType]:
        return {ContentType.LOG, ContentType.TERMINAL}

    def compress(self, text: str, *, aggressiveness: float = 0.5, query: str = "", use_template_mining: bool = True) -> CompressResult:
        original = text
        lines = text.splitlines()
        if len(lines) <= 5:
            return CompressResult(content=text, strategy=self.name, compressed=False)

        # Template mining for repeated INFO/DEBUG lines (slimctx)
        if use_template_mining and aggressiveness >= 0.3:
            min_count = max(2, int(5 * (1 - aggressiveness))) if aggressiveness >= 0.7 else max(3, int(5 * (1 - aggressiveness)))
            mined, collapsed = mine_log_templates(lines, min_count=min_count)
            if collapsed > 0:
                lines = mined
                text = "\n".join(lines)

        max_errors = max(5, int(20 * (1 - aggressiveness * 0.5)))
        max_warnings = max(3, int(10 * (1 - aggressiveness * 0.5)))
        max_info = max(2, int(5 * (1 - aggressiveness)))

        errors: list[str] = []
        warnings: list[str] = []
        info: list[str] = []
        critical_blocks: list[str] = []
        debug_count = 0
        info_collapsed: dict[str, int] = {}
        pytest_passed = 0
        pytest_failed: list[str] = []

        in_traceback = False
        in_pytest_section = False
        pytest_section_lines: list[str] = []
        traceback_lines: list[str] = []

        for line in lines:
            if PYTEST_SECTION.match(line.strip()):
                if pytest_section_lines:
                    critical_blocks.append("\n".join(pytest_section_lines))
                in_pytest_section = True
                pytest_section_lines = [line]
                continue

            if in_pytest_section:
                pytest_section_lines.append(line)
                if line.strip().startswith("====") and len(pytest_section_lines) > 3:
                    in_pytest_section = False
                    critical_blocks.append("\n".join(pytest_section_lines))
                    pytest_section_lines = []
                continue

            if PYTEST_FAILED.search(line):
                pytest_failed.append(line.strip())
                continue

            if PYTEST_PASSED.search(line):
                pytest_passed += 1
                continue
            if CRITICAL_PATTERNS.search(line):
                if traceback_lines:
                    critical_blocks.append("\n".join(traceback_lines))
                    traceback_lines = []
                in_traceback = "Traceback" in line or "Stack trace" in line.lower()

            if in_traceback or STACK_LINE.match(line):
                traceback_lines.append(line)
                if line.strip() and not line.startswith(" ") and "Traceback" not in line and not STACK_LINE.match(line):
                    in_traceback = False
                    critical_blocks.append("\n".join(traceback_lines))
                    traceback_lines = []
                continue

            if ERROR_PATTERNS.search(line):
                if len(errors) < max_errors:
                    errors.append(line)
            elif WARN_PATTERNS.search(line):
                if len(warnings) < max_warnings:
                    warnings.append(line)
            elif DEBUG_PATTERNS.search(line):
                debug_count += 1
            else:
                # Collapse repeated info lines; skip blanks
                key = line.strip()[:80]
                if key:
                    info_collapsed[key] = info_collapsed.get(key, 0) + 1

        if traceback_lines:
            critical_blocks.append("\n".join(traceback_lines))
        if pytest_section_lines:
            critical_blocks.append("\n".join(pytest_section_lines))

        parts: list[str] = []
        if critical_blocks:
            if aggressiveness >= 0.5:
                # Keep final exception line only — stack frames rarely worth the tokens
                trimmed: list[str] = []
                for block in critical_blocks:
                    blines = [l for l in block.splitlines() if l.strip()]
                    exc = [l for l in blines if re.match(r"^\w+(Error|Exception|Warning)", l)]
                    trimmed.append(exc[-1] if exc else blines[-1])
                # Single-line CRIT — label+exception share one row
                if len(trimmed) == 1:
                    parts.append(f"CRIT: {trimmed[0]}")
                else:
                    parts.append("CRIT:")
                    parts.extend(trimmed)
            else:
                parts.append("CRIT:")
                parts.extend(critical_blocks)

        if pytest_failed:
            parts.append(f"PYTEST FAIL ({len(pytest_failed)}):")
            parts.extend(pytest_failed)

        if pytest_passed:
            parts.append(f"PYTEST PASS omitted:{pytest_passed}")

        if errors:
            # Dedup ERROR lines; drop redundant gateway/timeout noise at high agg
            uniq_err: list[str] = []
            seen: set[str] = set()
            crit_blob = " ".join(parts).lower()
            for e in errors:
                key = re.sub(r"\d+", "#", e.strip())[:80]
                if key in seen:
                    continue
                seen.add(key)
                stripped = _strip_log_timestamps(e.strip())
                # Drop ERR rows that only restate a CRIT exception already kept
                if aggressiveness >= 0.5 and crit_blob:
                    core = re.sub(r"^(ERROR|ERR|CRIT)\s+", "", stripped, flags=re.I)
                    low = core.lower()
                    if low in crit_blob:
                        continue
                    # Phrase overlap (e.g. Connection refused already on CRIT line)
                    if any(
                        phrase in crit_blob and phrase in low
                        for phrase in (
                            "connection refused",
                            "timed out",
                            "timeout",
                            "permission denied",
                        )
                    ):
                        continue
                    if any(
                        tok.lower() in crit_blob
                        for tok in re.findall(r"\b\w+(?:Error|Exception)\b", core)
                    ):
                        continue
                uniq_err.append(stripped)
            if uniq_err or errors:
                cap = max(2, int(6 * (1 - aggressiveness)))
                shown = uniq_err[:cap]
                if aggressiveness >= 0.5 and shown:
                    # Skip ERR (n): chrome — count is recoverable from listed rows
                    parts.extend(shown)
                else:
                    parts.append(f"ERR ({len(errors)}):")
                    parts.extend(shown)

        if warnings and not (errors and aggressiveness >= 0.5):
            parts.append(f"WARN ({len(warnings)}):")
            parts.extend(warnings)

        if info:
            parts.append(f"INFO ({len(info)}):")
            parts.extend(info[:max_info])

        if info_collapsed:
            # When errors exist at high aggressiveness, INFO summary is noise
            if not (errors and aggressiveness >= 0.5):
                collapsed = []
                for k, count in sorted(info_collapsed.items(), key=lambda x: -x[1])[:max_info]:
                    if count > 1:
                        collapsed.append(f"[×{count}] {k}")
                    else:
                        collapsed.append(k)
                if collapsed:
                    parts.append(f"INFO×{len(info_collapsed)}:")
                    parts.extend(collapsed)

        if debug_count and aggressiveness < 0.5:
            parts.append(f"DEBUG omitted:{debug_count}")

        out = "\n".join(parts)
        if len(out) < len(text) * 0.95:
            out = _strip_log_timestamps(out)
            return CompressResult(
                content=out,
                strategy=self.name,
                lossless=False,
                compressed=True,
                metadata={"errors": len(errors), "warnings": len(warnings), "debug_omitted": debug_count},
            )
        if len(text) < len(original) * 0.95:
            return CompressResult(
                content=_strip_log_timestamps(text),
                strategy=self.name,
                lossless=False,
                compressed=True,
            )
        return CompressResult(content=original, strategy=self.name, compressed=False)


_TS_PREFIX = re.compile(
    r"(?m)^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\s+"
)


def _strip_log_timestamps(text: str) -> str:
    return _TS_PREFIX.sub("", text)
