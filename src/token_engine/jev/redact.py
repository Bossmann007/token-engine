"""Minimize and redact intent text before any external Jev call."""

from __future__ import annotations

import re

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)\b(sk|pk|rk|ghp|gho|xox[baprs])-[A-Za-z0-9\-_]{8,}"),
    re.compile(r"https?://[^\s]*[?&](signature|token|key|sig)=[^\s&]+"),
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
]


def redact_secrets(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def minimize_intent(text: str, *, max_chars: int = 500, redact: bool = True) -> str:
    cleaned = " ".join(text.split())
    if redact:
        cleaned = redact_secrets(cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1] + "…"
    return cleaned
