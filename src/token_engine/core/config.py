"""Engine configuration and token budget settings."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class QualityLevel(str, Enum):
    MAXIMUM = "maximum"
    BALANCED = "balanced"
    ECONOMY = "economy"


class CompressionLevel(str, Enum):
    NONE = "none"
    LIGHT = "light"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class EngineConfig(BaseModel):
    """Configuration for the Token Optimization Engine.

    Defaults match the full recommended stack (15+ tools analyzed).
    """

    model_config = {"extra": "ignore"}

    # Token counting (tiktoken encoding; harness picks the model, not this engine)
    encoding: str = "o200k_base"

    # Token budget
    max_tokens: int | None = 128_000
    target_tokens: int | None = 32_000
    budget_usd: float | None = None

    # Quality / compression
    quality_level: QualityLevel = QualityLevel.BALANCED
    compression_level: CompressionLevel | None = None

    # Core compression (all on by default)
    enable_deduplication: bool = True
    enable_cross_turn_dedup: bool = True
    enable_cache: bool = True
    enable_code_aware: bool = True
    enable_tool_output_compression: bool = True
    enable_smart_crusher: bool = True
    enable_ccr: bool = True
    enable_tool_schema_compaction: bool = True
    live_zone_mode: bool = True
    fail_closed: bool = True

    # Phase 2 features (on by default)
    enable_log_template_mining: bool = True
    enable_toon_encoding: bool = True
    enable_read_delta: bool = True
    enable_knapsack_selection: bool = True
    enable_read_lifecycle: bool = True
    enable_compression_feedback: bool = True
    enable_cache_aligner: bool = True
    enable_sandbox_execute: bool = True
    enable_rtk_filters: bool = True
    enable_cbm_bridge: bool = True

    # Codebase-memory bridge
    cbm_min_lines: int = 35
    cbm_min_chars: int = 800

    # Cache
    cache_ttl_seconds: int = 3600
    cache_max_entries: int = 10_000

    # Task context
    task_query: str = ""
    task_complexity: str = "medium"

    # Tool schema compaction
    tool_desc_max_chars: int = 120
    tool_desc_strip_semantic: bool = True

    # CCR
    ccr_ttl_seconds: int = 1800

    # Cost estimation (USD per 1M tokens)
    input_cost_per_million: float = 3.00
    output_cost_per_million: float = 15.00

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

    @classmethod
    def default(cls) -> EngineConfig:
        return cls()
