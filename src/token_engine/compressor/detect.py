"""Content type detection — inspired by caveman engine/detect.go."""

from __future__ import annotations

import json
import re

from token_engine.core.types import ContentType


def detect_content_type(text: str, hint: str = "") -> ContentType:
    if hint:
        hint_map = {
            "code": ContentType.CODE,
            "json": ContentType.JSON,
            "log": ContentType.LOG,
            "diff": ContentType.DIFF,
            "terminal": ContentType.TERMINAL,
            "message": ContentType.MESSAGE,
            "tool_output": ContentType.TOOL_OUTPUT,
        }
        if hint in hint_map:
            return hint_map[hint]

    stripped = text.strip()
    if not stripped:
        return ContentType.TEXT

    # JSON
    if stripped[0] in "{[":
        try:
            json.loads(stripped[: min(len(stripped), 100_000)])
            return ContentType.JSON
        except (json.JSONDecodeError, ValueError):
            pass

    # Diff
    if re.search(r"^diff --git|^--- a/|^\+{3} ", stripped, re.MULTILINE):
        return ContentType.DIFF
    if re.search(r"^@@ -\d+", stripped, re.MULTILINE):
        return ContentType.DIFF

    # Log patterns
    log_patterns = [
        r"\[(ERROR|WARN|INFO|DEBUG|TRACE)\]",
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}",
        r"Traceback \(most recent call last\)",
        r"^\s*at .+\(.+:\d+:\d+\)",
    ]
    log_hits = sum(1 for p in log_patterns if re.search(p, stripped, re.MULTILINE | re.IGNORECASE))
    if log_hits >= 2 or "Traceback" in stripped:
        return ContentType.LOG

    # Terminal output (command results)
    if re.search(r"^(total \d+|drwx|[-rwx]{10}|\$ |>>> |> )", stripped, re.MULTILINE):
        return ContentType.TERMINAL

    # Search/grep results
    if re.search(r"^\d+:\s*.+", stripped, re.MULTILINE) and stripped.count("\n") > 3:
        path_like = re.search(r"^[\w./-]+\.(py|ts|js|go|rs|java|rb|tsx|jsx|md):", stripped, re.MULTILINE)
        if path_like:
            return ContentType.SEARCH

    # Config (yaml/toml/ini)
    if re.match(r"^[\w.-]+\s*[:=]\s*", stripped) and stripped.count("\n") > 2:
        if not re.search(r"^(def |class |function |import |const |let |var )", stripped, re.MULTILINE):
            return ContentType.CONFIG

    # Code
    code_patterns = [
        r"^(def |class |import |from |function |const |let |var |pub fn |func |package )",
        r"^\s*(if |for |while |return |async |await |export |interface |type )",
    ]
    if any(re.search(p, stripped, re.MULTILINE) for p in code_patterns):
        return ContentType.CODE

    return ContentType.TEXT
