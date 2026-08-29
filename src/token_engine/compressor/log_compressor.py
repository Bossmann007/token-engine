"""Log compression — preserve errors, stack traces, collapse noise (caveman/rtk-inspired)."""

from __future__ import annotations

import re

from token_engine.compressor.base import CompressResult, Compressor
from token_engine.compressor.log_template import mine_log_templates
from token_engine.core.types import ContentType

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
        lines = text.splitlines()
        if len(lines) <= 5:
            return CompressResult(content=text, strategy=self.name, compressed=False)

        # Template mining for repeated INFO/DEBUG lines (slimctx)
        if use_template_mining and aggressiveness >= 0.3:
            mined, collapsed = mine_log_templates(lines, min_count=max(3, int(5 * (1 - aggressiveness))))
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

        in_traceback = False
        traceback_lines: list[str] = []

        for line in lines:
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
                # Collapse repeated info lines
                key = line.strip()[:80]
                if key:
                    info_collapsed[key] = info_collapsed.get(key, 0) + 1
                elif len(info) < max_info:
                    info.append(line)

        if traceback_lines:
            critical_blocks.append("\n".join(traceback_lines))

        parts: list[str] = []
        if critical_blocks:
            parts.append("=== CRITICAL ===")
            parts.extend(critical_blocks)

        if errors:
            parts.append(f"=== ERRORS ({len(errors)}) ===")
            parts.extend(errors)

        if warnings:
            parts.append(f"=== WARNINGS ({len(warnings)}) ===")
            parts.extend(warnings)

        if info:
            parts.append(f"=== INFO ({len(info)} lines) ===")
            parts.extend(info[:max_info])

        if info_collapsed:
            collapsed = []
            for k, count in sorted(info_collapsed.items(), key=lambda x: -x[1])[:max_info]:
                if count > 1:
                    collapsed.append(f"[×{count}] {k}")
                else:
                    collapsed.append(k)
            if collapsed:
                parts.append(f"=== INFO SUMMARY ({len(info_collapsed)} unique) ===")
                parts.extend(collapsed)

        if debug_count:
            parts.append(f"=== DEBUG ({debug_count} lines omitted) ===")

        out = "\n".join(parts)
        if len(out) >= len(text) * 0.95:
            return CompressResult(content=text, strategy=self.name, compressed=False)

        return CompressResult(content=out, strategy=self.name, lossless=False, compressed=True,
                            metadata={"errors": len(errors), "warnings": len(warnings), "debug_omitted": debug_count})
