"""Benchmark runner and quality tests."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from token_engine.core.config import EngineConfig
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType


@dataclass
class BenchmarkResult:
    name: str
    original_tokens: int
    optimized_tokens: int
    tokens_saved: int
    compression_ratio: float
    latency_ms: float
    strategy: str
    quality_checks: dict[str, bool] = field(default_factory=dict)
    quality_score: float = 0.0
    category: str = "other"


class BenchmarkRunner:
    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        self.engine = TokenEngine(self.config)

    def run_all(self, fixtures_dir: Path) -> list[BenchmarkResult]:
        results: list[BenchmarkResult] = []
        if not fixtures_dir.exists():
            return results

        for path in sorted(fixtures_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if "items" not in data and "content" not in data:
                continue
            results.append(self.run_fixture(path))
        for path in sorted(fixtures_dir.glob("*.txt")):
            results.append(self.run_text_fixture(path))

        return results

    def run_fixture(self, path: Path) -> BenchmarkResult:
        data = json.loads(path.read_text(encoding="utf-8"))
        name = data.get("name", path.stem)
        fixture_config = self.config
        if override := data.get("config"):
            merged = {**self.config.model_dump(), **override}
            fixture_config = EngineConfig.from_dict(merged)
        engine = TokenEngine(fixture_config) if fixture_config is not self.config else self.engine

        if "items" in data:
            items = [ContentItem(**{**item, "content_type": ContentType(item.get("content_type", "unknown"))}) for item in data["items"]]
            start = time.perf_counter()
            result = engine.optimize_context(items)
            latency = (time.perf_counter() - start) * 1000
        else:
            text = data.get("content", "")
            start = time.perf_counter()
            result = self.engine.optimize(text, content_type=data.get("content_type", ""))
            latency = (time.perf_counter() - start) * 1000

        stats = result.stats
        quality_checks = self._quality_checks(data, result.content)

        return BenchmarkResult(
            name=name,
            original_tokens=stats.original_tokens if stats else 0,
            optimized_tokens=stats.optimized_tokens if stats else 0,
            tokens_saved=stats.tokens_saved if stats else 0,
            compression_ratio=stats.compression_ratio if stats else 0.0,
            latency_ms=latency,
            strategy=stats.strategy if stats else "unknown",
            quality_checks=quality_checks,
            quality_score=sum(quality_checks.values()) / max(len(quality_checks), 1),
            category=self._fixture_category(name, path),
        )

    def run_text_fixture(self, path: Path) -> BenchmarkResult:
        text = path.read_text(encoding="utf-8")
        hint = "tool_output" if path.stem in {
            "npm_install", "jest_failures", "pnpm_install", "vite_build",
            "docker_build", "cargo_build", "app_log", "git_status",
        } else ""
        start = time.perf_counter()
        result = self.engine.optimize(text, content_type=hint)
        latency = (time.perf_counter() - start) * 1000
        stats = result.stats
        checks_meta = self._load_checks(path)
        quality_checks = self._quality_checks(checks_meta, result.content) if checks_meta else {}

        return BenchmarkResult(
            name=path.stem,
            original_tokens=stats.original_tokens if stats else 0,
            optimized_tokens=stats.optimized_tokens if stats else 0,
            tokens_saved=stats.tokens_saved if stats else 0,
            compression_ratio=stats.compression_ratio if stats else 0.0,
            latency_ms=latency,
            strategy=stats.strategy if stats else "unknown",
            quality_checks=quality_checks,
            quality_score=sum(quality_checks.values()) / max(len(quality_checks), 1),
            category=self._fixture_category(path.stem, path),
        )

    @staticmethod
    def _load_checks(path: Path) -> dict:
        checks_path = path.with_name(f"{path.stem}.checks.json")
        if not checks_path.exists():
            return {}
        return json.loads(checks_path.read_text(encoding="utf-8"))

    def _quality_checks(self, fixture: dict, optimized: str) -> dict[str, bool]:
        checks: dict[str, bool] = {}
        must_contain = fixture.get("must_contain", [])
        for term in must_contain:
            checks[f"contains:{term[:30]}"] = term.lower() in optimized.lower()

        must_not_lose = fixture.get("must_preserve", [])
        for term in must_not_lose:
            normalized_term = re.sub(r"\s+", "", term)
            normalized_out = re.sub(r"\s+", "", optimized)
            checks[f"preserve:{term[:30]}"] = term in optimized or normalized_term in normalized_out

        for pattern in fixture.get("must_match", []):
            checks[f"match:{pattern[:30]}"] = bool(re.search(pattern, optimized))

        return checks

    @staticmethod
    def _fixture_category(name: str, path: Path) -> str:
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if cat := data.get("category"):
                    return cat
                if "items" in data:
                    return "session"
                return "blob"
            except json.JSONDecodeError:
                return "blob"
        stem = path.stem
        if stem in {"app_log"}:
            return "log"
        if stem in {"large_json", "metrics_timeseries"} or "json" in stem:
            return "json"
        return "tool_output"

    def print_report(self, results: list[BenchmarkResult]) -> None:
        if not results:
            print("No benchmark fixtures found.")
            return

        total_orig = sum(r.original_tokens for r in results)
        total_opt = sum(r.optimized_tokens for r in results)
        total_saved = total_orig - total_opt
        ratio = total_saved / total_orig if total_orig else 0

        print("=" * 72)
        print("TOKEN ENGINE BENCHMARK REPORT")
        print("=" * 72)
        print(f"{'Fixture':<25} {'Original':>10} {'Optimized':>10} {'Saved':>10} {'Ratio':>8} {'ms':>8}")
        print("-" * 72)

        for r in results:
            print(
                f"{r.name:<25} {r.original_tokens:>10,} {r.optimized_tokens:>10,} "
                f"{r.tokens_saved:>10,} {r.compression_ratio * 100:>7.1f}% {r.latency_ms:>7.1f}"
            )
            if r.quality_checks:
                passed = sum(r.quality_checks.values())
                total = len(r.quality_checks)
                print(f"  Quality: {passed}/{total} checks passed ({r.quality_score * 100:.0f}%)")

        print("-" * 72)
        print(f"{'TOTAL':<25} {total_orig:>10,} {total_opt:>10,} {total_saved:>10,} {ratio * 100:>7.1f}%")
        print("=" * 72)

        categories: dict[str, list[BenchmarkResult]] = {}
        for r in results:
            cat = getattr(r, "category", "other")
            categories.setdefault(cat, []).append(r)
        if len(categories) > 1:
            print("\nBY CATEGORY:")
            for cat, cat_results in sorted(categories.items()):
                co = sum(x.original_tokens for x in cat_results)
                cs = sum(x.tokens_saved for x in cat_results)
                cr = cs / co if co else 0
                print(f"  {cat:<12} {cr * 100:5.1f}%  ({len(cat_results)} fixtures)")

        heavy = sorted(results, key=lambda r: r.optimized_tokens, reverse=True)[:5]
        if heavy:
            print("\nTOP TOKEN CONSUMERS (post-optimize):")
            for r in heavy:
                print(f"  {r.name:<22} {r.optimized_tokens:>6,} tok  ({r.compression_ratio * 100:.1f}% saved)")

    def check_baseline(self, results: list[BenchmarkResult], baseline_path: Path) -> list[str]:
        """Return list of regression messages; empty if all thresholds met."""
        if not baseline_path.exists():
            return [f"baseline file not found: {baseline_path}"]

        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        failures: list[str] = []

        total_orig = sum(r.original_tokens for r in results)
        total_saved = sum(r.tokens_saved for r in results)
        total_ratio = total_saved / total_orig if total_orig else 0.0
        min_total = baseline.get("minimum_total_ratio", 0.0)
        if total_ratio < min_total:
            failures.append(
                f"TOTAL ratio {total_ratio * 100:.1f}% below baseline {min_total * 100:.1f}%"
            )

        min_quality = baseline.get("minimum_quality_score")
        for result in results:
            if not result.quality_checks or min_quality is None:
                continue
            if result.quality_score < min_quality:
                failures.append(
                    f"{result.name}: quality {result.quality_score * 100:.0f}% "
                    f"below {min_quality * 100:.0f}%"
                )

        fixture_floor = baseline.get("fixtures", {})
        category_floor = baseline.get("categories", {})
        cat_totals: dict[str, tuple[int, int]] = {}
        for result in results:
            cat = result.category
            orig, saved = cat_totals.get(cat, (0, 0))
            cat_totals[cat] = (orig + result.original_tokens, saved + result.tokens_saved)
        for cat, (orig, saved) in cat_totals.items():
            floor = category_floor.get(cat)
            if floor is None or orig == 0:
                continue
            cat_ratio = saved / orig
            if cat_ratio < floor:
                failures.append(
                    f"category {cat}: {cat_ratio * 100:.1f}% below floor {floor * 100:.1f}%"
                )

        for result in results:
            floor = fixture_floor.get(result.name)
            if floor is None:
                continue
            if result.compression_ratio < floor:
                failures.append(
                    f"{result.name}: {result.compression_ratio * 100:.1f}% "
                    f"below floor {floor * 100:.1f}%"
                )

        return failures
