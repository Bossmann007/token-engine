"""Tokenizer plugin interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Tokenizer(ABC):
    """Provider-agnostic token counting interface."""

    @abstractmethod
    def count(self, text: str) -> int:
        """Count tokens in text."""

    @abstractmethod
    def encode(self, text: str) -> list[int]:
        """Encode text to token IDs."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tokenizer identifier."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider name (openai, anthropic, etc.)."""
