"""Query-aware code slicing — keep task-relevant symbols, elide the rest (token-savior/SuperCompress)."""

from __future__ import annotations

import re

IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+")
CLASS_RE = re.compile(r"^(\s*)class\s+(\w+)")
DEF_RE = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(")


def slice_code_by_query(code: str, query: str, *, min_chars: int = 200) -> tuple[str, bool]:
    """Extract imports + query-relevant blocks; elide others to signatures."""
    terms = {t for t in re.split(r"\W+", query.lower()) if len(t) > 2}
    if not terms or len(code) < min_chars:
        return code, False

    lines = code.splitlines()
    imports = [line for line in lines if IMPORT_RE.match(line)]
    body_lines = [line for line in lines if not IMPORT_RE.match(line) and line.strip()]

    if not body_lines:
        return code, False

    blocks = _extract_blocks(body_lines)
    if not blocks:
        return code, False

    all_scores: list[int] = []
    for block in blocks:
        all_scores.append(_score_block(block, terms))
        all_scores.extend(_score_block(sub, terms) for sub in block.children)
    if not any(s > 0 for s in all_scores):
        return code, False

    max_score = max(all_scores)
    threshold = max(1, max_score // 2)

    parts: list[str] = []
    if imports:
        parts.extend(imports)

    changed = False
    for block in blocks:
        if block.kind == "class":
            parts.append(block.lines[0])
            for sub in block.children:
                sub_score = _score_block(sub, terms)
                if sub_score >= threshold:
                    parts.extend(sub.lines)
                else:
                    parts.append(f"{sub.indent}{sub.lines[0].strip()}  # ...")
                    changed = True
            parts.append("")
            if any(_score_block(sub, terms) < threshold for sub in block.children):
                changed = True
            continue

        score = _score_block(block, terms)
        if score >= threshold:
            parts.extend(block.lines)
            if block.kind == "function":
                parts.append("")
        else:
            sig = block.lines[0].strip()
            parts.append(f"{block.indent}{sig}  # ...")
            changed = True

    if not changed:
        return code, False

    out = "\n".join(parts).strip()
    if not _preserves_query_terms(out, terms):
        return code, False
    return out, True


def _preserves_query_terms(text: str, terms: set[str]) -> bool:
    lower = text.lower()
    hits = sum(1 for t in terms if t in lower)
    return hits >= max(1, len(terms) // 4)


def _score_block(block: "CodeBlock", terms: set[str]) -> int:
    name = block.name.lower()
    body = "\n".join(block.lines).lower()
    score = 0
    for term in terms:
        if term in name:
            score += 3
        if term in body:
            score += 1
    if block.name == "__init__" and block.parent_class:
        score += 1
    return score


class CodeBlock:
    __slots__ = ("kind", "name", "lines", "indent", "parent_class", "children")

    def __init__(
        self,
        kind: str,
        name: str,
        lines: list[str],
        indent: str,
        *,
        parent_class: str | None = None,
        children: list[CodeBlock] | None = None,
    ) -> None:
        self.kind = kind
        self.name = name
        self.lines = lines
        self.indent = indent
        self.parent_class = parent_class
        self.children = children or []


def _extract_blocks(lines: list[str]) -> list[CodeBlock]:
    blocks: list[CodeBlock] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        class_match = CLASS_RE.match(line)
        if class_match:
            indent, name = class_match.group(1), class_match.group(2)
            class_lines = [line]
            methods, i = _collect_class_methods(lines, i + 1, indent)
            blocks.append(CodeBlock("class", name, class_lines, indent, children=methods))
            continue

        def_match = DEF_RE.match(line)
        if def_match:
            indent, name = def_match.group(1), def_match.group(2)
            def_lines, i = _collect_block(lines, i, indent)
            blocks.append(CodeBlock("function", name, def_lines, indent))
            continue

        if line.strip():
            blocks.append(CodeBlock("text", "module", [line], ""))
        i += 1
    return blocks


def _collect_block(lines: list[str], start: int, base_indent: str) -> tuple[list[str], int]:
    block = [lines[start]]
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            block.append(line)
            i += 1
            continue
        current_indent = line[: len(line) - len(line.lstrip())]
        if len(current_indent) <= len(base_indent) and line.strip():
            break
        block.append(line)
        i += 1
    return block, i


def _collect_class_methods(lines: list[str], start: int, class_indent: str) -> tuple[list[CodeBlock], int]:
    methods: list[CodeBlock] = []
    i = start
    method_indent = class_indent + "    " if class_indent else "    "

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        current_indent = line[: len(line) - len(line.lstrip())]
        if CLASS_RE.match(line) or (DEF_RE.match(line) and len(current_indent) <= len(class_indent)):
            break
        def_match = DEF_RE.match(line)
        if def_match and current_indent == method_indent:
            def_lines, i = _collect_block(lines, i, current_indent)
            methods.append(
                CodeBlock(
                    "method",
                    def_match.group(2),
                    def_lines,
                    current_indent,
                    parent_class="class",
                )
            )
            continue
        i += 1
    return methods, i
