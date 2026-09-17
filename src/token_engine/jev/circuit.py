"""Simple circuit breaker for external Jev calls."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    reset_seconds: float = 60.0
    _failures: int = 0
    _opened_at: float | None = None
    _history: list[float] = field(default_factory=list)

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.monotonic() - self._opened_at >= self.reset_seconds:
            self._opened_at = None
            self._failures = 0
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()

    @property
    def open(self) -> bool:
        return not self.allow()
