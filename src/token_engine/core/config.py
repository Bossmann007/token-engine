"""Engine configuration and token budget settings."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QualityLevel(str, Enum):
    MAXIMUM = "maximum"   # conservative compression
    BALANCED = "balanced"   # moderate compression
    ECONOMY = "economy"     # aggressive compression


class CompressionLevel(str, Enum):
    NONE = "none"
    LIGHT = "light"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class EngineConfig(BaseModel):
    """Configuration for the Token Optimization Engine."""

    model_config = {"extra": "ignore"}

    # Provider
    provider: str = "openai"
    model: str = "gpt-4o"

    # Token budget
    max_tokens: int | None = None
    target_tokens: int | None = None
    budget_usd: float | None = None

    # Quality / compression
    quality_level: QualityLevel = QualityLevel.BALANCED
    compression_level: CompressionLevel | None = None

    # Feature flags
    enable_deduplication: bool = True
    enable_cache: bool = True
    enable_code_aware: bool = True
    enable_tool_output_compression: bool = True
    fail_closed: bool = True  # pass-through if compression doesn't help

    # Cache
    cache_ttl_seconds: int = 3600
    cache_max_entries: int = 10_000

    # Task context (for relevance scoring)
    task_query: str = ""
    task_complexity: str = "medium"  # simple | medium | complex

    # Cost estimation (USD per 1M tokens)
    input_cost_per_million: float = 2.50
    output_cost_per_million: float = 10.00

    def effective_compression_level(self) -> CompressionLevel:
        if self.compression_level is not None:
            return self.compression_level
        mapping = {
            QualityLevel.MAXIMUM: CompressionLevel.LIGHT,
            QualityLevel.BALANCED: CompressionLevel.MODERATE,
            QualityLevel.ECONOMY: CompressionLevel.AGGRESSIVE,
        }
        return mapping[self.quality_level]

    def compression_aggressiveness(self) -> float:
        """0.0 = minimal, 1.0 = maximum compression."""
        levels = {
            CompressionLevel.NONE: 0.0,
            CompressionLevel.LIGHT: 0.25,
            CompressionLevel.MODERATE: 0.55,
            CompressionLevel.AGGRESSIVE: 0.85,
        }
        return levels[self.effective_compression_level()]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EngineConfig:
        return cls.model_validate(data)
