"""Core data types for the Token Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RelevanceTier(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    REDUNDANT = "REDUNDANT"
    DISCARDABLE = "DISCARDABLE"


class ContentType(str, Enum):
    TEXT = "text"
    CODE = "code"
    JSON = "json"
    LOG = "log"
    DIFF = "diff"
    TERMINAL = "terminal"
    SEARCH = "search"
    CONFIG = "config"
    TOOL_OUTPUT = "tool_output"
    MESSAGE = "message"
    UNKNOWN = "unknown"


@dataclass
class ContentItem:
    """A unit of content to analyze, rank, or compress."""

    id: str
    content: str
    content_type: ContentType = ContentType.UNKNOWN
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tier: RelevanceTier = RelevanceTier.MEDIUM
    token_count: int = 0
    dependencies: list[str] = field(default_factory=list)
    timestamp: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.content_type, str):
            self.content_type = ContentType(self.content_type)
        if isinstance(self.tier, str):
            self.tier = RelevanceTier(self.tier)


@dataclass
class TokenMetrics:
    total_tokens: int = 0
    tokens_by_source: dict[str, int] = field(default_factory=dict)
    tokens_by_type: dict[str, int] = field(default_factory=dict)
    redundant_tokens: int = 0
    discardable_tokens: int = 0
    critical_tokens: int = 0


@dataclass
class AnalysisReport:
    metrics: TokenMetrics
    items: list[ContentItem] = field(default_factory=list)
    duplicates: list[tuple[str, str]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.metrics.total_tokens


@dataclass
class CompressionStats:
    original_tokens: int
    optimized_tokens: int
    compression_ratio: float
    tokens_saved: int
    strategy: str
    lossless: bool = True
    latency_ms: float = 0.0

    @classmethod
    def compute(cls, original: str, optimized: str, original_tokens: int, optimized_tokens: int, strategy: str, *, lossless: bool = True, latency_ms: float = 0.0) -> CompressionStats:
        saved = max(0, original_tokens - optimized_tokens)
        ratio = saved / original_tokens if original_tokens else 0.0
        return cls(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            compression_ratio=ratio,
            tokens_saved=saved,
            strategy=strategy,
            lossless=lossless,
            latency_ms=latency_ms,
        )


@dataclass
class OptimizationResult:
    content: str
    items: list[ContentItem] = field(default_factory=list)
    stats: CompressionStats | None = None
    analysis: AnalysisReport | None = None
    cache_hits: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
