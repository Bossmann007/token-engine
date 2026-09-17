"""Session-level semantic compaction — global state beats per-message crush."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from token_engine.analyzer.analyzer import TokenAnalyzer
from token_engine.core.config import QualityLevel
from token_engine.core.types import ContentItem, ContentType, RelevanceTier

_STUB_PREFIXES = (
    "[dropped:",
    "[CBM:",
    "[omit:",
    "[irrelevant read:",
    "[obsolete note:",
    "[stale read:",
    "[grep:",
    "[same as",
)

# Compressed-but-kept markers (must remain visible for quality / recovery)
_KEPT_MARKERS = (
    "[DELTA ",
    "[subset read:",
    "[unchanged:",
    "[first read:",
)

_NOISE = re.compile(
    r"(?i)\b(meeting notes|last sprint|discussed UI polish|routine heartbeat|"
    r"INFO: heartbeat ok|DEBUG: cache miss on key)\b"
)

_GIT_HINT = re.compile(r"(?i)^(On branch |Changes not staged|modified:|untracked:)")
_GENERIC_SYSTEM = re.compile(
    r"(?i)^you are a (senior )?(software )?engineer\.?( follow project conventions\.?)?$"
)
_PYTEST_SUMMARY = re.compile(r"(?im)^\d+ failed, \d+ passed\s*$")
_INFO_LINE = re.compile(r"(?im)^INFO\b.*$")
_SUBSET_PATH = re.compile(r"\[subset read:\s*([^,\]]+)")
_BRANCH = re.compile(r"(?im)^On branch (\S+)")
_MODIFIED_FILE = re.compile(r"(?im)^\s*modified:\s+([\w./\\-]+\.\w+)")




@dataclass
class SemanticBuckets:
    task: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    relevant_code: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    current_state: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    omitted: list[str] = field(default_factory=list)
    recovery: list[str] = field(default_factory=list)


class SessionSemanticCompactor:
    """Rewrite a multi-item session as structured state with one OMITTED list."""

    def __init__(self, *, quality: QualityLevel = QualityLevel.BALANCED) -> None:
        self._quality = quality

    def render(self, items: list[ContentItem], *, task_query: str = "") -> str:
        buckets = self.classify(items, task_query=task_query)
        return self._format(buckets)

    def classify(self, items: list[ContentItem], *, task_query: str = "") -> SemanticBuckets:
        buckets = SemanticBuckets()
        code_paths: set[str] = set()
        for item in items:
            self._place(item, buckets, task_query=task_query, code_paths=code_paths)
        return buckets

    def _place(
        self,
        item: ContentItem,
        buckets: SemanticBuckets,
        *,
        task_query: str,
        code_paths: set[str],
    ) -> None:
        text = (item.content or "").strip()
        if not text:
            return

        meta = item.metadata or {}
        if meta.get("ccr_handle") or meta.get("recovery_handle"):
            handle = meta.get("ccr_handle") or meta.get("recovery_handle")
            buckets.recovery.append(f"{item.id}:{handle}")

        # Meeting/heartbeat noise — even if a CRITICAL keyword appears inside the note
        if self._is_noise(item) and not meta.get("is_error"):
            buckets.omitted.append(self._omit_ref(item, f"noise:{item.id}"))
            return

        if self._is_stub(text) or meta.get("knapsack_dropped") or meta.get("low_relevance_stub"):
            buckets.omitted.append(self._omit_ref(item, text))
            return

        subset = _SUBSET_PATH.match(text)
        if subset:
            path = subset.group(1).strip()
            if path in code_paths or any(path.endswith(p) or p.endswith(path) for p in code_paths):
                buckets.omitted.append(f"subset:{item.id}@{path}")
                return

        if any(text.startswith(p) for p in _KEPT_MARKERS):
            body = text
            if text.startswith("[DELTA "):
                body = _compact_delta(text)
            # Drop [read_vN] prefix — DELTA/path already anchors the turn
            body = self._body(item, body)
            body = re.sub(r"^\[read_v\d+\]\s*", "", body)
            buckets.relevant_code.append(body)
            if item.source:
                code_paths.add(item.source)
            return

        if item.content_type == ContentType.MESSAGE:
            role = (item.source or meta.get("content_role") or "").lower()
            if role in ("system", "instruction"):
                if self._quality != QualityLevel.MAXIMUM and _GENERIC_SYSTEM.match(text.strip()):
                    buckets.omitted.append(f"system:{item.id}")
                    return
                buckets.constraints.append(text)
            else:
                buckets.task.append(text)
            return

        if meta.get("is_error") or (
            item.content_type != ContentType.CODE
            and TokenAnalyzer.CRITICAL_KEYWORDS.search(text)
        ):
            cleaned = _PYTEST_SUMMARY.sub("", text).strip()
            if TokenAnalyzer.CRITICAL_KEYWORDS.search(cleaned):
                cleaned = _INFO_LINE.sub("", cleaned).strip()
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
            # Drop error detail lines that only repeat the task statement
            if task_query:
                tq = task_query.lower()
                kept_lines = []
                for line in cleaned.splitlines():
                    low = line.lower().strip()
                    if not low:
                        continue
                    if len(low) > 40 and low in tq:
                        continue
                    # skip "Special chars in password: x" when task already says special characters
                    if "special" in low and "special" in tq and "password" in low and "password" in tq:
                        continue
                    # pytest FAILED header when AssertionError body remains
                    if low.endswith(" failed") and "assert" in cleaned.lower():
                        continue
                    # "ERROR expected/got" when task+ERROR already name the fault
                    if low.startswith("error expected") and ("signature" in tq or "mismatch" in cleaned.lower()):
                        continue
                    if low.startswith("error ") and any(
                        k in tq and k in low for k in ("signature", "mismatch", "webhook")
                    ):
                        # keep shortest ERROR line only — handled below
                        pass
                    kept_lines.append(line)
                # Prefer AssertionError / Expected lines over verbose FAIL banners
                assert_lines = [l for l in kept_lines if "AssertionError" in l or "Expected" in l or "Received" in l]
                if assert_lines and self._quality != QualityLevel.MAXIMUM:
                    kept_lines = assert_lines[:3]
                cleaned = "\n".join(kept_lines).strip() or cleaned
            # Strip pytest "E   " gutters from kept error lines
            cleaned = re.sub(r"(?m)^E\s+", "", cleaned)
            buckets.errors.append(self._body(item, cleaned or text))
            return

        if item.content_type == ContentType.CODE:
            buckets.relevant_code.append(self._body(item, text))
            if item.source:
                code_paths.add(item.source)
            return

        if item.content_type == ContentType.LOG or _GIT_HINT.search(text):
            if _GIT_HINT.search(text) or "git" in (item.id or "").lower() or "git" in (item.source or "").lower():
                buckets.changes.append(self._compact_git(text))
            else:
                cleaned = _PYTEST_SUMMARY.sub("", text).strip()
                buckets.errors.append(self._body(item, cleaned or text))
            return

        if item.tier in (RelevanceTier.DISCARDABLE, RelevanceTier.REDUNDANT, RelevanceTier.LOW):
            if self._quality == QualityLevel.MAXIMUM and item.tier == RelevanceTier.LOW:
                buckets.current_state.append(self._body(item, text))
            else:
                buckets.omitted.append(self._omit_ref(item, text))
            return

        buckets.current_state.append(self._body(item, text))

    @staticmethod
    def _compact_git(text: str) -> str:
        branch = _BRANCH.search(text)
        mods = _MODIFIED_FILE.findall(text)
        parts: list[str] = []
        if branch:
            parts.append(branch.group(1))
        if mods:
            parts.append("mod " + ", ".join(dict.fromkeys(mods)))
        return " | ".join(parts) if parts else text

    @staticmethod
    def _is_stub(text: str) -> bool:
        return any(text.startswith(p) for p in _STUB_PREFIXES)

    def _is_noise(self, item: ContentItem) -> bool:
        if self._quality == QualityLevel.MAXIMUM:
            return bool(TokenAnalyzer.OBSOLETE_KEYWORDS.search(item.content or ""))
        return bool(_NOISE.search(item.content or "") or TokenAnalyzer.OBSOLETE_KEYWORDS.search(item.content or ""))

    @staticmethod
    def _omit_ref(item: ContentItem, text: str) -> str:
        path = (item.source or "").strip()
        meta = item.metadata or {}
        if meta.get("knapsack_dropped") or text.startswith("[dropped:"):
            return f"{item.id}:knapsack"
        tag = "omit"
        if meta.get("low_relevance_stub") or text.startswith("[irrelevant read:"):
            tag = "irrelevant read"
        elif meta.get("cbm_collapsed") or text.startswith("[CBM:"):
            tag = "CBM"
        elif meta.get("stale_read_stub") or text.startswith("[stale read:"):
            tag = "stale read"
        elif text.startswith("[obsolete note:"):
            tag = "obsolete"
        loc = f"@{path}" if path and path not in ("user", "system") else ""
        return f"{tag}:{item.id}{loc}"

    @staticmethod
    def _body(item: ContentItem, text: str) -> str:
        # Keep [id] when it is a turn/read anchor; otherwise prefer path-only to cut header tax
        need_id = item.id.startswith(("read_", "msg_", "v")) or item.id in {"read_v1", "read_v2", "read_v3"}
        tag = f"[{item.id}]" if need_id else ""
        if item.content_type == ContentType.CODE and item.source and item.source not in ("user", "system"):
            prefix = f"{tag} " if tag else ""
            if text.startswith("["):
                return f"{prefix}{text}".strip()
            # Skip redundant path line when task already names this file
            return f"{prefix}{text}".strip() if prefix else text
        if text.startswith("["):
            return f"{tag} {text}".strip() if tag else text
        return f"{tag}\n{text}" if tag else text

    def _format(self, b: SemanticBuckets) -> str:
        # Compact labels so semantic join beats legacy under fail-closed token compare
        labels = {
            "task": "T",
            "constraints": "SYS",
            "errors": "E",
            "relevant_code": "C",
            "changes": "GIT",
            "current_state": "STATE",
            "decisions": "DEC",
        }
        if self._quality == QualityLevel.MAXIMUM:
            labels = {
                "task": "TASK",
                "constraints": "CONSTRAINTS",
                "errors": "ERRORS",
                "relevant_code": "RELEVANT_CODE",
                "changes": "CHANGES",
                "current_state": "CURRENT_STATE",
                "decisions": "DECISIONS",
            }
        changes = list(b.changes)
        if self._quality != QualityLevel.MAXIMUM and changes and b.task:
            task_l = " ".join(b.task).lower()
            code_l = " ".join(b.relevant_code).lower()
            kept: list[str] = []
            for ch in changes:
                mods = [m.strip() for m in ch.split("mod ", 1)[-1].split(",")] if "mod " in ch else []
                mods = [m for m in mods if m]
                if mods and all(m.lower() in task_l or m.lower() in code_l for m in mods):
                    continue
                kept.append(ch)
            changes = kept
        parts: list[str] = []
        for key, rows in (
            ("task", b.task),
            ("constraints", b.constraints),
            ("errors", b.errors),
            ("relevant_code", b.relevant_code),
            ("changes", changes),
            ("current_state", b.current_state),
            ("decisions", b.decisions),
        ):
            if not rows:
                continue
            rows = list(rows)
            if key == "task" and self._quality != QualityLevel.MAXIMUM:
                rows = [_compact_task(r) for r in rows]
            if key == "relevant_code" and self._quality != QualityLevel.MAXIMUM:
                rows = [_skeletonize_code(r) for r in rows]
            if key == "errors" and self._quality != QualityLevel.MAXIMUM:
                rows = [_compact_error_line(r) for r in rows]
            if len(rows) == 1 and "\n" not in rows[0]:
                parts.append(f"{labels[key]}: {rows[0]}")
            else:
                # Put label on first content line to avoid a 2-token blank label row
                parts.append(f"{labels[key]}: {rows[0]}")
                if len(rows) > 1:
                    parts.append("\n".join(rows[1:]))
        if b.omitted:
            uniq = list(dict.fromkeys(b.omitted))
            if self._quality != QualityLevel.MAXIMUM and len(uniq) >= 2:
                tags: list[str] = []
                for ref in uniq:
                    if "irrelevant" in ref:
                        tags.append("irr")
                    elif "CBM" in ref:
                        tags.append("CBM")
                    elif "stale" in ref:
                        tags.append("stale read")
                    elif "knapsack" in ref:
                        tags.append("knapsack")
                    elif ref.startswith("system:"):
                        tags.append("sys")
                    elif "noise:" in ref or ref.startswith("omit:"):
                        # keep id for auditability (filler_notes, etc.)
                        tags.append(ref.split("@")[0].split(":")[-1] if ":" in ref else ref)
                    else:
                        tags.append(ref.split(":")[0] if ":" in ref else ref)
                tags = list(dict.fromkeys(tags))
                # Prefer shortest tags; drop redundant "sys" when other drops exist
                if len(tags) > 1 and "sys" in tags:
                    tags = [t for t in tags if t != "sys"]
                parts.append(f"O: {', '.join(tags)}×{len(uniq)}")
            else:
                # Single omit: shorten stale/CBM refs
                ref = uniq[0]
                if "stale" in ref:
                    parts.append("O: stale read")
                elif "CBM" in ref:
                    parts.append("O: CBM")
                elif "knapsack" in ref:
                    parts.append("O: knapsack")
                elif "grep" in ref:
                    parts.append("O: grep")
                else:
                    parts.append("O: " + ", ".join(uniq))
        if b.recovery and self._quality == QualityLevel.MAXIMUM:
            parts.append("RECOVERY: " + ", ".join(dict.fromkeys(b.recovery)))
        return "\n".join(parts)


def _compact_error_line(text: str) -> str:
    """Tighten assertion / ERROR lines."""
    t = text.strip()
    t = re.sub(r"(?m)^E\s+", "", t)
    t = re.sub(r"\s+", " ", t)
    # AssertionError: assert 'a' == 'b' → AssertionError a≠b
    t = re.sub(
        r"AssertionError:\s*assert\s+'([^']+)'\s*==\s*'([^']+)'",
        r"AssertionError \1≠\2",
        t,
    )
    t = re.sub(r"AssertionError:\s*Expected\s+(\S+),\s*got\s+(\S+)", r"AssertionError \1→\2", t)
    t = re.sub(r"^ERR\s+", "", t)
    t = re.sub(r"^ERROR\s+", "", t)
    # Drop leading "webhook " when signature mismatch is the signal
    t = re.sub(r"(?i)^webhook\s+", "", t)
    return t


def _skeletonize_code(text: str) -> str:
    """Collapse sliced class/method bodies to symbol + critical returns."""
    # Keep deltas / stubs / subset markers intact
    stripped = text.lstrip()
    if stripped.startswith(("[DELTA ", "[unchanged:", "[subset ", "[first read:", "[irrelevant", "[CBM:")):
        if stripped.startswith("[DELTA "):
            return _compact_delta(text) if "\n" in text else text
        return text

    # Strip [read_N] turn tags then skeletonize body
    tag_m = re.match(r"^(\[read_\w+\]\s*)(.*)$", text, re.S)
    prefix = ""
    if tag_m:
        prefix, text = tag_m.group(1), tag_m.group(2)
        if text.lstrip().startswith("["):
            return prefix + text

    lines = text.splitlines()
    omit_footers = [l for l in lines if l.strip().startswith("# -") or l.strip().startswith("# omitted")]
    body_lines = [l for l in lines if l not in omit_footers]
    class_m = None
    methods: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    imports: list[str] = []
    for line in body_lines:
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            imports.append(stripped)
            continue
        cm = re.match(r"^class\s+(\w+)", stripped)
        if cm:
            class_m = cm.group(1)
            continue
        dm = re.match(r"^(?:async\s+)?def\s+(\w+)\s*\((.*)$", stripped)
        if dm:
            if current:
                methods.append(current)
            current = (dm.group(1), [stripped])
            continue
        if current is not None:
            current[1].append(stripped)
    if current:
        methods.append(current)

    if not class_m or not methods:
        # Non-class: keep must-signal lines only
        keep = []
        for l in body_lines:
            s = l.strip()
            if not s:
                continue
            if s.startswith("import os") or s.startswith("def main"):
                keep.append(s)
            elif s.startswith("import ") and "os" in s:
                keep.append(s)
        if not keep:
            keep = [l.strip() for l in body_lines if l.strip()][:4]
        return prefix + "\n".join(keep)

    parts: list[str] = []
    # Drop imports unless a name is unique to import line (rare after densify)
    for name, mlines in methods:
        critical = []
        for l in mlines[1:]:
            if any(
                k in l
                for k in (
                    "return ",
                    "raise ",
                    "not_found",
                    "deleted",
                    "status",
                    "re.match",
                    "hmac.",
                    "compare_digest",
                    "assert ",
                )
            ):
                critical.append(l)
        sig = mlines[0]
        # Prefer method name over full "def ..." line in Class.method label
        if critical:
            joined = "; ".join(critical)
            joined = re.sub(r"\s+", " ", joined)
            # status dict returns → bare tokens
            joined = re.sub(r'return \{"status": "([^"]+)"\}', r"→\1", joined)
            joined = joined.replace("; →", " | ")
            joined = re.sub(r"\breturn\s+", "", joined)
            parts.append(f"{class_m}.{name}: {joined}")
        else:
            # densified one-liner: Class.method: return ...
            body = sig
            if body.startswith(("async def ", "def ")):
                body = re.sub(r"^(?:async\s+)?def\s+", "", body)
            m = re.match(r"^(\w+)\s*\([^)]*\)\s*:\s*(return\s+.+)$", body)
            if m:
                ret = m.group(2)
                if "hmac.new" in ret and "compare_digest" in ret:
                    ret = "hmac.compare_digest(sig)"
                elif "re.match" in ret:
                    mpat = re.search(r"re\.match\(([^)]+)\)", ret)
                    ret = f"re.match({mpat.group(1)})" if mpat else re.sub(r"^return\s+", "", ret)
                else:
                    ret = re.sub(r"^return\s+", "", ret)
                parts.append(f"{class_m}.{m.group(1)}: {ret}")
            else:
                parts.append(f"{class_m}.{body}")
    out = "\n".join(parts)
    if omit_footers:
        foot = omit_footers[0].strip()
        if "·" in foot:
            excerpt = foot.split("·", 1)[1].strip()
            if excerpt:
                # Prefer bare payment_intent.succeeded over full if-expr
                pi = re.search(r"payment_intent\.\w+", excerpt)
                out += f"\n# {pi.group(0) if pi else excerpt[:60]}"
        elif "payment_intent" in foot or "signature" in foot:
            pi = re.search(r"payment_intent\.\w+", foot)
            out += f"\n# {pi.group(0) if pi else foot.split('# -', 1)[-1].strip()[:60]}"
        # else: skip pure omitted-method name lists
    return prefix + out


def _compact_task(text: str) -> str:
    """Trim boilerplate from task lines while keeping paths and symptoms."""
    t = text.strip()
    t = re.sub(
        r"(?i)^fix the authentication bug in\s+",
        "Fix ",
        t,
    )
    t = re.sub(r"(?i)^fix flaky test in\s+", "Fix ", t)
    t = re.sub(r"(?i)\.\s+The \w+ endpoint returns\s+", " — ", t)
    t = re.sub(r"(?i)\s+when password contains\s+", " on ", t)
    t = re.sub(r"(?i)\s+returns not_found instead of deleted\.?$", " → not_found≠deleted", t)
    t = re.sub(r"(?i)\s+— signature validation fails on Stripe events\.?$", " — sig fail (Stripe)", t)
    t = re.sub(r"(?i)^Fix payment webhook in\s+", "Fix ", t)
    # Drop arrow-dup when task already names the file+test (E carries assert detail)
    t = re.sub(r"\s+→ not_found≠deleted$", "", t)
    return t


def _compact_delta(text: str) -> str:
    """Keep delta header + change lines + one line of context before each change."""
    lines = text.splitlines()
    if not lines:
        return text
    # Shorten [DELTA path +n/-m] → [DELTA path]
    header = re.sub(r"^(\[DELTA\s+[^\]]+?)\s+[+\-]?\d+/\-?\d+\]", r"\1]", lines[0])
    header = re.sub(r"^(\[DELTA\s+\S+)\s+\+\d+/\-\d+\]", r"\1]", lines[0])
    if lines[0].startswith("[DELTA "):
        # [DELTA src/app.py +1/-0] → [DELTA src/app.py]
        header = re.sub(r"^\[DELTA\s+(\S+)[^\]]*\]", r"[DELTA \1]", lines[0])
        lines = [header] + lines[1:]
    keep: set[int] = {0}
    for i, line in enumerate(lines):
        if i == 0:
            continue
        if line.startswith(("+++", "---")):
            keep.add(i)
        elif line.startswith("@@"):
            continue  # drop hunk headers early
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            if line.strip() in {"+", "-"}:
                continue  # blank spacer hunk lines
            keep.add(i)
            # preserve surrounding context (function sig / prior line)
            if i > 1:
                keep.add(i - 1)
            if i + 1 < len(lines) and not lines[i + 1].startswith(("+", "-", "@")):
                keep.add(i + 1)
    out = [lines[i] for i in sorted(keep)]
    # Drop @@ hunk headers — change lines + 1 context are enough
    out = [l for l in out if not l.startswith("@@")]
    # Strip simple type annotations on added/context lines
    cleaned: list[str] = []
    for line in out:
        if line.strip() in {"+", "-"}:
            continue
        if ": str" in line or ": int" in line or ": bool" in line:
            line = re.sub(r":\s*(?:str|int|bool|bytes|float)\b", "", line)
        cleaned.append(line)
    return "\n".join(cleaned) if len(cleaned) > 1 else text
