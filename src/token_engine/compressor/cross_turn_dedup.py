"""Cross-turn verbatim deduplication (headroom-inspired)."""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_MIN_LINES = 3
DEFAULT_MIN_CHARS = 40
MAX_ANCHOR_CANDIDATES = 16

_LINENO_RE = re.compile(r"^([1-9]\d*)(:|\t)(.*)$", re.DOTALL)


@dataclass
class DedupBlock:
    text: str
    turn: int
    protected: bool = False


def _num_and_key(line: str) -> tuple[int | None, str, str]:
    m = _LINENO_RE.match(line)
    if m is None:
        return None, line, line
    return int(m.group(1)), m.group(2) + m.group(3), m.group(3)


def _is_trivial(line: str) -> bool:
    s = line.strip()
    return len(s) < 4 or s in {"return", "pass", "else:", "try:", "except:", "break", "continue"}


def _pointer(span: list[str], ref_turn: int, delta: int = 0) -> str:
    anchor = next((_num_and_key(ln)[2].strip() for ln in span if ln.strip()), "")
    if len(anchor) > 20:
        anchor = anchor[:17] + "..."
    if delta:
        return f"[↑{len(span)}L same as msg {ref_turn} {delta:+d}L: {anchor!r}]"
    return f"[↑{len(span)}L same as msg {ref_turn}: {anchor!r}]"


def dedup_blocks(
    blocks: list[DedupBlock],
    *,
    min_lines: int = DEFAULT_MIN_LINES,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> tuple[list[DedupBlock], dict]:
    """Prefix-monotonic cross-turn dedup. Never raises."""
    stats = {"spans_folded": 0, "lines_removed": 0, "chars_removed": 0, "blocks": len(blocks)}
    try:
        corpus: list[list[str | None]] = []
        anchor_index: dict[str, list[tuple[int, int]]] = {}
        out_blocks: list[DedupBlock] = []

        for blk in blocks:
            lines = blk.text.split("\n")
            if blk.protected:
                verbatim: list[str | None] = list(lines)
                _index_lines(verbatim, len(corpus), anchor_index)
                corpus.append(verbatim)
                out_blocks.append(blk)
                continue

            out_lines: list[str] = []
            i = 0
            while i < len(lines):
                match = _longest_match(lines, i, anchor_index, corpus)
                if match is None:
                    out_lines.append(lines[i])
                    i += 1
                    continue
                length, ref_bp, _, delta = match
                span = lines[i : i + length]
                if length < min_lines or sum(len(l) for l in span) < min_chars:
                    out_lines.append(lines[i])
                    i += 1
                    continue
                ref_turn = blocks[ref_bp].turn if ref_bp < len(blocks) else ref_bp
                out_lines.append(_pointer(span, ref_turn, delta))
                stats["spans_folded"] += 1
                stats["lines_removed"] += length - 1
                stats["chars_removed"] += sum(len(l) for l in span) - len(out_lines[-1])
                i += length

            new_text = "\n".join(out_lines)
            verbatim_out: list[str | None] = list(out_lines)
            _index_lines(verbatim_out, len(corpus), anchor_index)
            corpus.append(verbatim_out)
            out_blocks.append(DedupBlock(text=new_text, turn=blk.turn, protected=blk.protected))

        return out_blocks, stats
    except Exception:
        return blocks, stats


def _index_lines(
    lines: list[str | None],
    block_pos: int,
    anchor_index: dict[str, list[tuple[int, int]]],
) -> None:
    for li, ln in enumerate(lines):
        if ln is None:
            continue
        _, key, content = _num_and_key(ln)
        if _is_trivial(content):
            continue
        bucket = anchor_index.setdefault(key, [])
        if len(bucket) < MAX_ANCHOR_CANDIDATES:
            bucket.append((block_pos, li))


def _longest_match(
    cur: list[str],
    start: int,
    anchor_index: dict[str, list[tuple[int, int]]],
    corpus: list[list[str | None]],
) -> tuple[int, int, int, int] | None:
    _, anchor_key, _ = _num_and_key(cur[start])
    candidates = anchor_index.get(anchor_key)
    if not candidates:
        return None
    best_len = 0
    best_bp = best_li = -1
    best_delta = 0
    for bp, li in candidates:
        block_lines = corpus[bp]
        k = 0
        delta: int | None = None
        while start + k < len(cur) and li + k < len(block_lines):
            ca = cur[start + k]
            cb = block_lines[li + k]
            if cb is None:
                break
            na, ka, _ = _num_and_key(ca)
            nb, kb, _ = _num_and_key(cb)
            if ka != kb:
                break
            if na is not None and nb is not None:
                d = na - nb
                if delta is None:
                    delta = d
                elif delta != d:
                    break
            elif ca != cb:
                break
            k += 1
        if k > best_len:
            best_len, best_bp, best_li, best_delta = k, bp, li, (delta or 0)
    if best_len == 0:
        return None
    return best_len, best_bp, best_li, best_delta


def dedup_conversation(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Apply cross-turn dedup to (id, content) pairs in order."""
    blocks = [DedupBlock(text=content, turn=i) for i, (_, content) in enumerate(items)]
    deduped, _ = dedup_blocks(blocks)
    ids = [item[0] for item in items]
    return list(zip(ids, [b.text for b in deduped]))
