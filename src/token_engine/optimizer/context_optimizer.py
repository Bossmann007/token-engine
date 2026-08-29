"""Context optimizer — orchestrates analysis, ranking, compression."""

from __future__ import annotations

import time

from token_engine.analyzer.analyzer import TokenAnalyzer
from token_engine.cache.cache import SmartCache
from token_engine.ccr.store import CCRStore
from token_engine.compressor.base import Compressor
from token_engine.compressor.code_compressor import CodeCompressor
from token_engine.compressor.cross_turn_dedup import DedupBlock, dedup_blocks
from token_engine.compressor.deduplicator import Deduplicator
from token_engine.compressor.detect import detect_content_type
from token_engine.compressor.diff_compressor import DiffCompressor
from token_engine.compressor.json_compressor import JSONCompressor
from token_engine.compressor.log_compressor import LogCompressor
from token_engine.compressor.smart_crusher import SmartCrusher
from token_engine.compressor.tool_output_compressor import ToolOutputCompressor
from token_engine.compressor.tool_schema_compactor import ToolSchemaCompactor
from token_engine.core.config import EngineConfig
from token_engine.core.types import (
    AnalysisReport,
    CompressionStats,
    ContentItem,
    ContentType,
    OptimizationResult,
    RelevanceTier,
)
from token_engine.optimizer.filtering import ContextFilter
from token_engine.optimizer.ranking import BM25Ranker
from token_engine.tokenizer.base import Tokenizer


class ContextOptimizer:
    """Main context optimization pipeline."""

    def __init__(self, config: EngineConfig, tokenizer: Tokenizer) -> None:
        self._config = config
        self._tokenizer = tokenizer
        self._analyzer = TokenAnalyzer(tokenizer)
        self._filter = ContextFilter(tokenizer)
        self._ranker = BM25Ranker()
        self._dedup = Deduplicator()
        self._cache = SmartCache(config.cache_ttl_seconds, config.cache_max_entries) if config.enable_cache else None
        self._ccr = CCRStore(config.ccr_ttl_seconds) if config.enable_ccr else None
        self._tool_schema = ToolSchemaCompactor(
            desc_max_chars=config.tool_desc_max_chars,
            strip_semantic=config.tool_desc_strip_semantic,
        ) if config.enable_tool_schema_compaction else None
        self._compressors = self._build_compressors()

    def _build_compressors(self) -> list[Compressor]:
        compressors: list[Compressor] = []
        if self._config.enable_smart_crusher:
            compressors.append(SmartCrusher())
        compressors.extend([
            JSONCompressor(),
            LogCompressor(),
            CodeCompressor(),
            DiffCompressor(),
            ToolOutputCompressor(),
        ])
        return compressors

    def optimize_items(self, items: list[ContentItem]) -> OptimizationResult:
        start = time.perf_counter()
        cache_hits = 0
        aggressiveness = self._config.compression_aggressiveness()

        # Cross-turn dedup (headroom-style, prefix-monotonic)
        if self._config.enable_cross_turn_dedup and len(items) > 1:
            blocks = [DedupBlock(text=item.content, turn=i) for i, item in enumerate(items)]
            deduped_blocks, cross_stats = dedup_blocks(blocks)
            for item, block in zip(items, deduped_blocks):
                item.content = block.text
                item.token_count = self._tokenizer.count(item.content)
            cross_stats  # available in metadata below

        # Analyze
        analysis = self._analyzer.analyze_items(items, task_query=self._config.task_query)

        # Mark cross-item duplicates
        for id_a, id_b in analysis.duplicates:
            for item in items:
                if item.id == id_b:
                    item.tier = RelevanceTier.REDUNDANT
                    item.metadata["is_duplicate"] = True

        # Filter under budget (skip dropping in live_zone_mode)
        if self._config.live_zone_mode:
            selected = items
        else:
            selected = self._filter.select_items(
                items,
                max_tokens=self._config.max_tokens,
                target_tokens=self._config.target_tokens,
                task_query=self._config.task_query,
            )

        # Compress each selected item
        optimized_items: list[ContentItem] = []
        for item in selected:
            compressed_item, hit = self._compress_item(item, aggressiveness)
            if hit:
                cache_hits += 1
            optimized_items.append(compressed_item)

        # Build output
        output_parts = []
        for item in optimized_items:
            header = f"<!-- {item.id} [{item.tier.value}] -->"
            output_parts.append(f"{header}\n{item.content}")

        output = "\n\n---\n\n".join(output_parts)

        original_tokens = sum(i.token_count for i in items)
        optimized_tokens = self._tokenizer.count(output)
        latency_ms = (time.perf_counter() - start) * 1000

        stats = CompressionStats.compute(
            "", output,
            original_tokens, optimized_tokens,
            strategy="context_optimizer",
            lossless=False,
            latency_ms=latency_ms,
        )

        return OptimizationResult(
            content=output,
            items=optimized_items,
            stats=stats,
            analysis=analysis,
            cache_hits=cache_hits,
            metadata={
                "items_in": len(items),
                "items_out": len(optimized_items),
                "live_zone_mode": self._config.live_zone_mode,
            },
        )

    def optimize_text(self, text: str, *, content_type: str = "") -> OptimizationResult:
        hint = content_type or ""
        ct = detect_content_type(text, hint)
        item = ContentItem(
            id="input",
            content=text,
            content_type=ct,
            token_count=self._tokenizer.count(text),
        )
        return self.optimize_items([item])

    def compact_tool_schemas(self, tools: list[dict]) -> tuple[list[dict], dict]:
        """Compact MCP tool definitions to reduce token bloat."""
        if not self._tool_schema:
            return tools, {}
        return self._tool_schema.compact_tools(tools)

    def _compress_item(self, item: ContentItem, aggressiveness: float) -> tuple[ContentItem, bool]:
        cache_hit = False
        original_token_count = item.token_count

        if self._cache:
            cache_key = SmartCache.make_key("compress", item.id, str(aggressiveness), item.content[:200])
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached, True

        content = item.content
        strategy = "passthrough"
        ccr_handle: str | None = None

        # Deduplication within item
        if self._config.enable_deduplication:
            dedup = self._dedup.deduplicate_text(content)
            if dedup.duplicates_removed > 0:
                content = dedup.content

        # Tool output first when detectable
        tool_comp = self._compressors[-1]
        if self._config.enable_tool_output_compression:
            tool_result = tool_comp.compress(content, aggressiveness=aggressiveness, query=self._config.task_query)
            if tool_result.compressed and tool_result.strategy != "tool_output":
                content = tool_result.content
                strategy = tool_result.strategy

        if strategy == "passthrough":
            for compressor in self._compressors:
                if compressor.can_handle(item.content_type):
                    result = compressor.compress(content, aggressiveness=aggressiveness, query=self._config.task_query)
                    if result.compressed:
                        content = result.content
                        strategy = result.strategy
                        break

        # CCR: store original if lossy compression applied with significant savings
        new_tokens = self._tokenizer.count(content)
        chars_saved = len(item.content) - len(content)
        token_saved = original_token_count - new_tokens
        if (
            self._ccr
            and strategy != "passthrough"
            and token_saved > 50
            and chars_saved > 200
        ):
            ccr_handle = self._ccr.store(item.content, metadata={"strategy": strategy, "item_id": item.id})
            marker = self._ccr.marker(ccr_handle, chars_dropped=chars_saved)
            content = f"{content}\n\n{marker}"

        # Fail-closed: only use if smaller
        new_tokens = self._tokenizer.count(content)
        if self._config.fail_closed and new_tokens >= original_token_count:
            content = item.content
            new_tokens = original_token_count
            strategy = "passthrough"
            ccr_handle = None

        metadata = {**item.metadata, "compression_strategy": strategy}
        if ccr_handle:
            metadata["ccr_handle"] = ccr_handle

        optimized = ContentItem(
            id=item.id,
            content=content,
            content_type=item.content_type,
            source=item.source,
            metadata=metadata,
            tier=item.tier,
            token_count=new_tokens,
            dependencies=item.dependencies,
            timestamp=item.timestamp,
        )

        if self._cache:
            deps = set(item.dependencies)
            if item.source:
                deps.add(item.source)
            self._cache.set(cache_key, optimized, dependencies=deps)

        return optimized, cache_hit

    def retrieve_ccr(self, handle: str) -> str | None:
        if not self._ccr:
            return None
        return self._ccr.retrieve(handle)

    def analyze(self, items: list[ContentItem]) -> AnalysisReport:
        return self._analyzer.analyze_items(items, task_query=self._config.task_query)

    @property
    def cache_stats(self) -> dict:
        return self._cache.stats if self._cache else {}
