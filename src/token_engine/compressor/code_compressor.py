"""Code compression — signatures, gutter stripping, body elision (caveman/token-savior-inspired)."""

from __future__ import annotations

import re

from token_engine.compressor.base import CompressResult, Compressor
from token_engine.core.types import ContentType

# Line number gutter: "   123| code" or "  123: code"
GUTTER_PATTERN = re.compile(r"^(\s*\d+[|:]\s?)(.*)$")

SIGNATURE_PATTERNS = [
    re.compile(r"^((?:export\s+)?(?:async\s+)?(?:def|class|function|fn|func|interface|type|struct|enum)\s+\w+.*)$", re.MULTILINE),
    re.compile(r"^((?:public|private|protected|static)\s+.*(?:class|interface|void|int|string).*)$", re.MULTILINE),
]

IMPORT_PATTERN = re.compile(
    r"^((?:import|from|use|require|#include)\s+.+)$", re.MULTILINE
)


class CodeCompressor(Compressor):
    @property
    def name(self) -> str:
        return "code"

    @property
    def content_types(self) -> set[ContentType]:
        return {ContentType.CODE, ContentType.SEARCH}

    def compress(self, text: str, *, aggressiveness: float = 0.5, query: str = "") -> CompressResult:
        # Strip line number gutters first
        lines = text.splitlines()
        stripped_lines = []
        had_gutter = False
        for line in lines:
            m = GUTTER_PATTERN.match(line)
            if m:
                had_gutter = True
                stripped_lines.append(m.group(2))
            else:
                stripped_lines.append(line)

        code = "\n".join(stripped_lines)

        if aggressiveness < 0.3 or len(code) < 500:
            if had_gutter and code != text:
                return CompressResult(content=code, strategy=f"{self.name}:gutter-strip", compressed=True)
            return CompressResult(content=text, strategy=self.name, compressed=False)

        return self._structural_compress(code, aggressiveness, query, gutter_stripped=had_gutter)

    def _structural_compress(self, code: str, aggressiveness: float, query: str, *, gutter_stripped: bool) -> CompressResult:
        lines = code.splitlines()
        max_body_lines = max(5, int(30 * (1 - aggressiveness)))

        imports: list[str] = []
        signatures: list[str] = []
        body_sections: list[str] = []
        current_block: list[str] = []
        in_block = False
        block_sig = ""

        sig_pattern = re.compile(
            r"^\s*(export\s+)?(async\s+)?(def|class|function|fn|func|interface|type|struct|enum)\s+"
        )
        import_pat = re.compile(r"^\s*(import|from|use|require|#include)\s+")

        for line in lines:
            if import_pat.match(line):
                imports.append(line.strip())
                continue

            if sig_pattern.match(line):
                if current_block and block_sig:
                    body_sections.append(self._elide_block(block_sig, current_block, max_body_lines))
                block_sig = line.strip()
                signatures.append(block_sig)
                current_block = [line]
                in_block = True
            elif in_block:
                current_block.append(line)
                if line.strip() == "" and len(current_block) > max_body_lines:
                    body_sections.append(self._elide_block(block_sig, current_block, max_body_lines))
                    current_block = []
                    in_block = False
            elif not in_block and line.strip():
                signatures.append(line.strip()[:120])

        if current_block and block_sig:
            body_sections.append(self._elide_block(block_sig, current_block, max_body_lines))

        parts: list[str] = []
        if imports:
            parts.append("=== IMPORTS ===")
            parts.extend(imports[:20])
            if len(imports) > 20:
                parts.append(f"... {len(imports) - 20} more imports")

        if signatures:
            parts.append("=== STRUCTURE ===")
            parts.extend(signatures[:50])

        if body_sections:
            parts.append("=== BODIES (elided) ===")
            parts.extend(body_sections)

        out = "\n".join(parts)
        if not out or len(out) >= len(code) * 0.9:
            strategy = f"{self.name}:gutter-strip" if gutter_stripped else self.name
            return CompressResult(
                content=code if gutter_stripped else code,
                strategy=strategy,
                compressed=gutter_stripped,
            )

        return CompressResult(content=out, strategy=f"{self.name}:structural", lossless=False, compressed=True)

    def _elide_block(self, signature: str, lines: list[str], max_lines: int) -> str:
        if len(lines) <= max_lines:
            return "\n".join(lines)

        head = lines[: max_lines // 2]
        tail = lines[-(max_lines // 2):]
        omitted = len(lines) - len(head) - len(tail)
        return "\n".join(head) + f"\n// ... [{omitted} lines elided in {signature[:60]}] ...\n" + "\n".join(tail)
