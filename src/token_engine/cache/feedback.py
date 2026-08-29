"""Compression feedback loop — tune aggressiveness per source (headroom-inspired)."""

from __future__ import annotations

from collections import defaultdict


class CompressionFeedback:
    """Track compression outcomes per source/tool and suggest aggressiveness."""

    def __init__(self) -> None:
        self._attempts: dict[str, int] = defaultdict(int)
        self._successes: dict[str, int] = defaultdict(int)
        self._ratios: dict[str, list[float]] = defaultdict(list)

    def record(self, source: str, *, compressed: bool, ratio: float = 0.0) -> None:
        key = source or "unknown"
        self._attempts[key] += 1
        if compressed and ratio > 0:
            self._successes[key] += 1
            self._ratios[key].append(ratio)
            if len(self._ratios[key]) > 50:
                self._ratios[key] = self._ratios[key][-50:]

    def suggested_aggressiveness(self, source: str, base: float) -> float:
        """Adjust base aggressiveness: increase if compression works well, decrease if not."""
        key = source or "unknown"
        attempts = self._attempts.get(key, 0)
        if attempts < 3:
            return base
        success_rate = self._successes.get(key, 0) / attempts
        avg_ratio = sum(self._ratios[key]) / len(self._ratios[key]) if self._ratios[key] else 0

        if success_rate > 0.7 and avg_ratio > 0.3:
            return min(1.0, base + 0.15)
        if success_rate < 0.2:
            return max(0.1, base - 0.2)
        return base

    def stats(self) -> dict:
        return {
            source: {
                "attempts": self._attempts[source],
                "successes": self._successes[source],
                "avg_ratio": sum(self._ratios[source]) / len(self._ratios[source]) if self._ratios[source] else 0,
            }
            for source in self._attempts
        }
