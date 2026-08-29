"""Tiktoken-based token counting."""

from __future__ import annotations

import tiktoken

from token_engine.tokenizer.base import Tokenizer

DEFAULT_ENCODING = "o200k_base"  # current agent/chat APIs
FALLBACK_ENCODING = "cl100k_base"  # cl100k parity when o200k unavailable


def resolve_encoding(encoding: str) -> str:
    """Return a tiktoken encoding name, falling back when invalid."""
    for candidate in (encoding, DEFAULT_ENCODING, FALLBACK_ENCODING):
        try:
            tiktoken.get_encoding(candidate)
            return candidate
        except Exception:
            continue
    return FALLBACK_ENCODING


class TiktokenTokenizer(Tokenizer):
    """Accurate BPE token counting via tiktoken."""

    def __init__(self, encoding: str = DEFAULT_ENCODING) -> None:
        self._encoding_name = resolve_encoding(encoding)
        self._encoding = tiktoken.get_encoding(self._encoding_name)

    @property
    def name(self) -> str:
        return f"tiktoken/{self._encoding_name}"

    @property
    def encoding(self) -> str:
        return self._encoding_name

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text, disallowed_special=()))

    def encode(self, text: str) -> list[int]:
        return self._encoding.encode(text, disallowed_special=())


class CharEstimateTokenizer(Tokenizer):
    """Fast fallback: calibrated chars/token heuristic (inspired by token-optimizer)."""

    CHARS_PER_TOKEN = 3.3

    @property
    def name(self) -> str:
        return "char-estimate"

    @property
    def encoding(self) -> str:
        return "char-estimate"

    def count(self, text: str) -> int:
        if not text:
            return 0
        cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff")
        ascii_chars = len(text) - cjk
        return max(1, int(ascii_chars / self.CHARS_PER_TOKEN) + cjk)

    def encode(self, text: str) -> list[int]:
        return list(range(self.count(text)))


def create_tokenizer(encoding: str = DEFAULT_ENCODING, *, use_estimate: bool = False) -> Tokenizer:
    if use_estimate:
        return CharEstimateTokenizer()
    return TiktokenTokenizer(encoding)
