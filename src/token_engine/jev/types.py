"""Shared types for optional Jev tool routing."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskTier(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class ChoiceAnswer(BaseModel):
    choice: str
    confidence: float
    probabilities: dict[str, float] = Field(default_factory=dict)


class JevEvaluateResult(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0
    model: str = ""


DESTRUCTIVE_NAME_HINTS = frozenset({
    "delete", "remove", "drop", "destroy", "rm", "purge", "wipe",
    "deploy", "publish", "push", "force", "payment", "pay", "transfer",
    "send_message", "email", "chmod", "chown", "grant", "revoke",
})

WRITE_NAME_HINTS = frozenset({
    "write", "create", "update", "edit", "put", "patch", "post",
    "upload", "commit", "merge", "apply", "set", "add", "insert",
})


def infer_risk_tier(tool_name: str, *, metadata: dict[str, Any] | None = None) -> RiskTier:
    meta = metadata or {}
    explicit = str(meta.get("risk_tier", "")).lower()
    if explicit in {t.value for t in RiskTier}:
        return RiskTier(explicit)
    name = tool_name.lower()
    if any(h in name for h in DESTRUCTIVE_NAME_HINTS):
        return RiskTier.DESTRUCTIVE
    if any(h in name for h in WRITE_NAME_HINTS):
        return RiskTier.WRITE
    return RiskTier.READ
