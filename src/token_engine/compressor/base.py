"""Compressor plugin interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from token_engine.core.types import ContentType


@dataclass
class CompressResult:
    content: str
    strategy: str
    lossless: bool = True
    compressed: bool = False
    metadata: dict | None = None


class Compressor(ABC):
    """Base class for content compressors."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def content_types(self) -> set[ContentType]:
        ...

    @abstractmethod
    def compress(self, text: str, *, aggressiveness: float = 0.5, query: str = "") -> CompressResult:
        """Compress text. aggressiveness: 0.0-1.0."""

    def can_handle(self, content_type: ContentType) -> bool:
        return content_type in self.content_types
