"""Net compression accounting — gross vs economia_liquida."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from token_engine.benchmark.runner import BenchmarkRunner
from token_engine.core.config import EngineConfig, QualityLevel
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType
from token_engine.tokenizer.tiktoken_tokenizer import create_tokenizer

_CCR_RE = re.compile(r"<<ccr:[^>]+>>")
_OMIT_RE = re.compile(r"^(?:OMIT|O):.*$", re.M)
_HEADER_RE = re.compile(r"^\[(?:input\|)?[^\]]+\]\s*", re.M)


@dataclass
class NetMetrics:
    quality: str
    original_tokens: int
    compressed_tokens: int
    overhead_tokens: int
    ccr_marker_tokens: int
    gross_ratio: float
    net_ratio: float
    latency_ms: float
    fixture_count: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def tokens_saved_gross(self) -> int:
        return self.original_tokens - self.compressed_tokens

    @property
    def tokens_saved_net(self) -> int:
        return self.original_tokens - self.compressed_tokens - self.overhead_tokens


def _overhead_in(text: str, tokenizer) -> tuple[int, int]:
    ccr = _CCR_RE.findall(text)
    ccr_tok = sum(tokenizer.count(m) for m in ccr)
    omit = _OMIT_RE.findall(text)
    omit_tok = sum(tokenizer.count(m) for m in omit)
    # structural labels T:/E:/CODE: are small; count omit+ccr as recoverable/overhead
    return omit_tok + ccr_tok, ccr_tok


def measure_corpus(
    fixtures_dir: Path,
    *,
    quality: QualityLevel = QualityLevel.BALANCED,
) -> NetMetrics:
    tokenizer = create_tokenizer("o200k_base")
    cfg = EngineConfig(quality_level=quality)
    engine = TokenEngine(cfg)
    runner = BenchmarkRunner(cfg)

    original = 0
    compressed = 0
    overhead = 0
    ccr_tok = 0
    latency = 0.0
    n = 0

    for path in sorted(fixtures_dir.glob("*.json")):
        data = __import__("json").loads(path.read_text(encoding="utf-8"))
        if "items" not in data and "content" not in data:
            continue
        start = time.perf_counter()
        if "items" in data:
            items = [
                ContentItem(**{**it, "content_type": ContentType(it.get("content_type", "unknown"))})
                for it in data["items"]
            ]
            result = engine.optimize_context(items)
        else:
            result = engine.optimize(data.get("content", ""), content_type=data.get("content_type", ""))
        latency += (time.perf_counter() - start) * 1000
        stats = result.stats
        if not stats:
            continue
        original += stats.original_tokens
        compressed += stats.optimized_tokens
        oh, ccr = _overhead_in(result.content, tokenizer)
        overhead += oh
        ccr_tok += ccr
        n += 1

    for path in sorted(fixtures_dir.glob("*.txt")):
        start = time.perf_counter()
        result = engine.optimize(path.read_text(encoding="utf-8"))
        latency += (time.perf_counter() - start) * 1000
        stats = result.stats
        if not stats:
            continue
        original += stats.original_tokens
        compressed += stats.optimized_tokens
        oh, ccr = _overhead_in(result.content, tokenizer)
        overhead += oh
        ccr_tok += ccr
        n += 1

    gross = (original - compressed) / original if original else 0.0
    # Economia líquida: gross savings minus omit/CCR marker tokens still sitting in the prompt.
    # Jev / reprocess costs stay 0 until instrumented.
    net = (original - compressed - overhead) / original if original else 0.0

    # Verify floors still hold under this quality
    results = runner.run_all(fixtures_dir)
    failures = runner.check_baseline(results, fixtures_dir.parent / "baseline.json")

    return NetMetrics(
        quality=quality.value,
        original_tokens=original,
        compressed_tokens=compressed,
        overhead_tokens=overhead,
        ccr_marker_tokens=ccr_tok,
        gross_ratio=gross,
        net_ratio=net,
        latency_ms=latency,
        fixture_count=n,
        notes=(failures[:5] if failures else ["floors_ok"]),
    )
