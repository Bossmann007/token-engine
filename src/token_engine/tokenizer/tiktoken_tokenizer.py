"""Tiktoken-based tokenizer with provider adapters."""

from __future__ import annotations

import tiktoken

from token_engine.tokenizer.base import Tokenizer

# Model → encoding mapping (provider-agnostic core uses tiktoken encodings)
PROVIDER_ENCODINGS: dict[str, str] = {
    # OpenAI
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "o1": "o200k_base",
    "o1-mini": "o200k_base",
    "o3-mini": "o200k_base",
    # Anthropic (approximate via cl100k — Anthropic uses own tokenizer)
    "claude-3-5-sonnet": "cl100k_base",
    "claude-3-opus": "cl100k_base",
    "claude-3-haiku": "cl100k_base",
    "claude-sonnet-4": "cl100k_base",
    # Google (approximate)
    "gemini-pro": "cl100k_base",
    "gemini-2.0-flash": "cl100k_base",
    # Local / generic
    "default": "cl100k_base",
}

PROVIDER_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "o1", "o1-mini", "o3-mini"],
    "anthropic": ["claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku", "claude-sonnet-4"],
    "google": ["gemini-pro", "gemini-2.0-flash"],
    "local": ["default"],
}


class TiktokenTokenizer(Tokenizer):
    """Accurate BPE token counting via tiktoken."""

    def __init__(self, provider: str = "openai", model: str = "gpt-4o") -> None:
        self._provider = provider
        self._model = model
        encoding_name = PROVIDER_ENCODINGS.get(model, PROVIDER_ENCODINGS["default"])
        try:
            self._encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            self._encoding = tiktoken.get_encoding("cl100k_base")

    @property
    def name(self) -> str:
        return f"tiktoken/{self._model}"

    @property
    def provider(self) -> str:
        return self._provider

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text, disallowed_special=()))

    def encode(self, text: str) -> list[int]:
        return self._encoding.encode(text, disallowed_special=())


class CharEstimateTokenizer(Tokenizer):
    """Fast fallback: calibrated chars/token heuristic (inspired by token-optimizer)."""

    CHARS_PER_TOKEN = 3.3

    def __init__(self, provider: str = "generic", model: str = "estimate") -> None:
        self._provider = provider
        self._model = model

    @property
    def name(self) -> str:
        return "char-estimate"

    @property
    def provider(self) -> str:
        return self._provider

    def count(self, text: str) -> int:
        if not text:
            return 0
        # CJK characters count roughly 1 token each
        cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff")
        ascii_chars = len(text) - cjk
        return max(1, int(ascii_chars / self.CHARS_PER_TOKEN) + cjk)

    def encode(self, text: str) -> list[int]:
        return list(range(self.count(text)))


def create_tokenizer(provider: str = "openai", model: str = "gpt-4o", *, use_estimate: bool = False) -> Tokenizer:
    if use_estimate:
        return CharEstimateTokenizer(provider, model)
    return TiktokenTokenizer(provider, model)
