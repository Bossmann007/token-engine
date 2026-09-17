"""Query-aware code slicing — keep task-relevant symbols, elide the rest (token-savior/SuperCompress)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+")
CLASS_RE = re.compile(r"^(\s*)class\s+(\w+)")
DEF_RE = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(")
BUG_CONTEXT_TERMS = frozenset(
    {
        "special",
        "character",
        "invalid",
        "encode",
        "unicode",
        "regex",
        "signature",
        "validation",
        "verify",
        "hmac",
        "auth",
        "password",
        "webhook",
    }
)

# Query term expansions so "signature" matches `sig=` / verify()
TERM_SYNONYMS: dict[str, frozenset[str]] = {
    "signature": frozenset({"sig", "sign", "hmac", "digest"}),
    "validation": frozenset({"validate", "verify", "check"}),
    "validate": frozenset({"validation", "verify"}),
    "verify": frozenset({"validation", "signature", "sig"}),
    "password": frozenset({"passwd", "pwd"}),
    "delete": frozenset({"remove", "destroy"}),
    "error": frozenset({"exception", "fail", "failed"}),
}


def slice_code_by_query(code: str, query: str, *, min_chars: int = 200) -> tuple[str, bool]:
    """Extract imports + query-relevant blocks; elide others to signatures."""
    terms = {t for t in re.split(r"\W+", query.lower()) if len(t) > 2}
    for segment in re.findall(r"[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs)", query.lower()):
        stem = PurePosixPath(segment.replace("\\", "/")).stem.lower()
        if len(stem) > 2:
            terms.add(stem)
    # Split snake_case / camel fragments so test_delete_user → delete, user
    expanded: set[str] = set()
    for term in terms:
        expanded.add(term)
        if "_" in term:
            expanded.update(p for p in term.split("_") if len(p) > 2)
        parts = re.findall(r"[a-z][a-z0-9]+|[A-Z][a-z0-9]+", term)
        expanded.update(p.lower() for p in parts if len(p) > 2)
    terms = expanded
    core_terms = set(terms)
    # Synonym expansion (signature → sig, validation → verify)
    with_syn: set[str] = set(terms)
    for term in terms:
        with_syn.update(TERM_SYNONYMS.get(term, ()))
    terms = with_syn
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
    changed = False
    if imports:
        if len(imports) > 3:
            collapsed_imports = ", ".join(
                re.sub(r"^(import|from)\s+", "", line.strip()) for line in imports[:8]
            )
            parts.append(f"import {collapsed_imports}")
            changed = True
        else:
            parts.extend(imports)

    for block in blocks:
        if block.kind == "class":
            parts.append(block.lines[0])
            child_scores = [
                (sub, _score_block(sub, terms) + _bug_relevance_boost(sub, terms))
                for sub in block.children
            ]
            max_child = max((score for _, score in child_scores), default=0)
            # Bug-fix queries: keep only the best method(s). Otherwise allow near-ties.
            if terms & BUG_CONTEXT_TERMS and max_child > 0:
                keep_floor = max_child
            else:
                keep_floor = max(1, max_child - 1) if max_child > 2 else threshold
            # Clear winner (e.g. delete_user >> list_users): do not keep near-miss signatures
            ranked_scores = sorted((score for _, score in child_scores), reverse=True)
            if len(ranked_scores) >= 2 and ranked_scores[0] >= ranked_scores[1] + 3:
                keep_floor = max(keep_floor, ranked_scores[0])
            omitted_methods: list[str] = []
            omitted_excerpts: list[str] = []
            kept_blocks: list = []
            for sub, score in child_scores:
                if score >= threshold and score >= keep_floor:
                    kept_blocks.append(sub)
                else:
                    omitted_methods.append(sub.name)
            kept_so_far = "\n".join(parts).lower()
            for sub in kept_blocks:
                densified = _densify_method(sub.lines)
                parts.extend(densified)
                kept_so_far += "\n" + "\n".join(densified).lower()
            for sub, score in child_scores:
                if score >= threshold and score >= keep_floor:
                    continue
                excerpt = _query_hit_excerpt(sub, terms, already=kept_so_far)
                if excerpt:
                    omitted_excerpts.append(excerpt[:60])
                    changed = True
            if omitted_methods:
                changed = True
                indent = child_scores[0][0].indent if child_scores else "    "
                # Skip pure boilerplate omit lists (__init__/login only) unless excerpt carries a must-keep term
                interesting = [m for m in omitted_methods if m not in {"__init__", "__repr__", "__str__"}]
                if interesting or omitted_excerpts:
                    names = (interesting or omitted_methods)[:2]
                    extra = len(interesting or omitted_methods) - len(names)
                    name_s = ", ".join(names) + (f"+{extra}" if extra else "")
                    if omitted_excerpts:
                        parts.append(f"{indent}# - {name_s} · {omitted_excerpts[0]}")
                    else:
                        parts.append(f"{indent}# - {name_s}")
            parts.append("")
            continue

        score = _score_block(block, terms)
        if score >= threshold:
            parts.extend(block.lines)
            if block.kind == "function":
                parts.append("")
        else:
            if block.kind in {"function", "method"}:
                sig = block.lines[0].strip()
                parts.append(f"{block.indent}{sig}  # ...")
            else:
                # module-level noise (logger = …) — drop entirely
                changed = True

    if not changed:
        return code, False

    out = "\n".join(parts).strip()
    out = _drop_unused_imports(out)
    stripped = _strip_type_annotations(out)
    if stripped != out:
        out = stripped
        changed = True
    out = re.sub(r"\n{2,}", "\n", out)
    if not _preserves_query_terms(out, core_terms):
        return code, False
    return out, True


_ANN_PARAM = re.compile(
    r":\s*(?:int|str|bytes|bool|dict|list|float|None|[A-Z]\w*(?:\[[^\]]+\])?)(?=\s*[,)=])"
)
_ANN_RETURN = re.compile(r"\)\s*->\s*[^:\n]+:")


def _strip_type_annotations(code: str) -> str:
    """Drop common type hints — symbols stay, tokens go."""
    out = _ANN_PARAM.sub("", code)
    return _ANN_RETURN.sub("):", out)


def _densify_method(lines: list[str]) -> list[str]:
    """Collapse short methods onto fewer lines."""
    if len(lines) < 2:
        return list(lines)
    body = [l for l in lines[1:] if l.strip() and not l.strip().startswith("#")]
    if len(body) == 1:
        stmt = body[0].strip()
        if stmt.startswith(("return ", "raise ", "pass")) or "=" in stmt:
            return [f"{lines[0].rstrip()} {stmt}"]
    # assign + return-that-name → inline
    if len(body) == 2:
        a, b = body[0].strip(), body[1].strip()
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", a)
        if m and b.startswith("return ") and m.group(1) in b:
            name, expr = m.group(1), m.group(2)
            # only inline if name appears once in return
            if b.count(name) == 1:
                inlined = b.replace(name, f"({expr})", 1)
                return [f"{lines[0].rstrip()} {inlined}"]
    return list(lines)


def _drop_unused_imports(code: str) -> str:
    lines = code.splitlines()
    # Ignore comments when deciding if an import name is used
    body_lines = []
    for l in lines:
        if IMPORT_RE.match(l):
            continue
        body_lines.append(l.split("#", 1)[0])
    body_l = "\n".join(body_lines).lower()
    kept: list[str] = []
    for line in lines:
        if not IMPORT_RE.match(line):
            kept.append(line)
            continue
        names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", line)
        names = [n for n in names if n.lower() not in {"import", "from", "as"}]
        if any(n.lower() in body_l for n in names):
            kept.append(line)
    return "\n".join(kept).strip()


def _query_hit_excerpt(block: CodeBlock, terms: set[str], *, already: str = "") -> str | None:
    """Pull one omitted line that still carries a query term missing from kept code."""
    for line in block.lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lower = stripped.lower()
        novel = [t for t in terms if len(t) > 3 and t in lower and t not in already]
        if novel:
            return stripped[:100]
    return None


def _preserves_query_terms(text: str, terms: set[str]) -> bool:
    lower = text.lower()
    hits = sum(1 for t in terms if t in lower)
    return hits >= max(1, len(terms) // 4)


def _bug_relevance_boost(block: CodeBlock, terms: set[str]) -> int:
    if not terms & BUG_CONTEXT_TERMS:
        return 0
    body = "\n".join(block.lines).lower()
    boost = 0
    name = block.name.lower()
    if "validate" in name or "sanitize" in name or "check" in name or "verify" in name:
        boost += 4
    if "re.match" in body or "regex" in body or "special" in body:
        boost += 3
    if "hmac" in body or "compare_digest" in body or "signature" in body or " sig" in body:
        boost += 3
    return boost


def _score_block(block: "CodeBlock", terms: set[str]) -> int:
    name = block.name.lower()
    body = "\n".join(block.lines).lower()
    score = 0
    for term in terms:
        if term == name:
            score += 8
        elif term in name:
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
