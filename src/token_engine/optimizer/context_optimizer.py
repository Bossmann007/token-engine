"""Context optimizer — full pipeline with all integrated techniques."""

from __future__ import annotations

import time

from token_engine.analyzer.analyzer import TokenAnalyzer
from token_engine.analyzer.cache_aligner import detect_volatile_content
from token_engine.cache.cache import SmartCache
from token_engine.cache.feedback import CompressionFeedback
from token_engine.ccr.store import CCRStore
from token_engine.compressor.base import Compressor, CompressResult
from token_engine.compressor.cbm_bridge import collapse_large_reads_to_cbm
from token_engine.compressor.code_compressor import CodeCompressor
from token_engine.compressor.context_helpers import (
    collapse_duplicate_items,
    collapse_grep_into_reads,
    collapse_low_relevance_reads,
    collapse_obsolete_items,
    collapse_stale_reads,
    collapse_superseded_reads,
    knapsack_stub,
    strip_line_gutters,
)
from token_engine.compressor.content_router import route_and_join
from token_engine.compressor.cross_turn_dedup import DedupBlock, dedup_blocks
from token_engine.compressor.deduplicator import Deduplicator
from token_engine.compressor.detect import detect_content_type
from token_engine.compressor.diff_compressor import DiffCompressor
from token_engine.compressor.json_compressor import JSONCompressor
from token_engine.compressor.log_compressor import LogCompressor
from token_engine.compressor.read_delta import ReadDelta
from token_engine.compressor.smart_crusher import SmartCrusher
from token_engine.compressor.toon_encoder import ToonEncoder
from token_engine.compressor.tool_output_compressor import ToolOutputCompressor
from token_engine.compressor.tool_schema_compactor import LazyToolRegistry, ToolSchemaCompactor
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
from token_engine.optimizer.read_lifecycle import prune_stale_reads
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
        self._read_delta = ReadDelta() if config.enable_read_delta else None
        self._feedback = CompressionFeedback() if config.enable_compression_feedback else None
        self._cache = SmartCache(config.cache_ttl_seconds, config.cache_max_entries) if config.enable_cache else None
        self._ccr = CCRStore(config.ccr_ttl_seconds) if config.enable_ccr else None
        self._tool_schema = ToolSchemaCompactor(
            desc_max_chars=config.tool_desc_max_chars,
            strip_semantic=config.tool_desc_strip_semantic,
        ) if config.enable_tool_schema_compaction else None
        self._compressors = self._build_compressors()

    def _build_compressors(self) -> list[Compressor]:
        compressors: list[Compressor] = []
        if self._config.enable_toon_encoding:
            compressors.append(ToonEncoder())
        if self._config.enable_smart_crusher:
            compressors.append(SmartCrusher())
        compressors.extend([
            JSONCompressor(),
            LogCompressor(),
            CodeCompressor(),
            DiffCompressor(),
            ToolOutputCompressor(enable_rtk=self._config.enable_rtk_filters),
        ])
        return compressors

    def optimize_items(self, items: list[ContentItem]) -> OptimizationResult:
        start = time.perf_counter()
        if self._read_delta:
            self._read_delta.reset()
        cache_hits = 0
        base_aggressiveness = self._config.compression_aggressiveness()
        cache_warnings: list[dict] = []
        task_query = self._config.task_query or self._infer_task_query(items)

        for item in items:
            if item.token_count <= 0:
                item.token_count = self._tokenizer.count(item.content)
        original_tokens = sum(i.token_count for i in items)

        # Strip read-tool line gutters early (token-savior / caveman)
        for item in items:
            if item.content_type in (ContentType.CODE, ContentType.TEXT):
                stripped, changed = strip_line_gutters(item.content)
                if changed:
                    item.content = stripped
                    item.token_count = self._tokenizer.count(item.content)
                    item.metadata["gutter_stripped"] = True

        if self._config.enable_cbm_bridge:
            session_code_tokens = sum(
                i.token_count for i in items if i.content_type in (ContentType.CODE, ContentType.TEXT)
            )
            collapse_large_reads_to_cbm(
                items,
                task_query=task_query,
                min_lines=self._config.cbm_min_lines,
                min_chars=self._config.cbm_min_chars,
                session_code_tokens=session_code_tokens,
                session_min_lines=self._config.cbm_min_lines_session,
                session_min_chars=self._config.cbm_min_chars_session,
                session_code_threshold=self._config.cbm_session_code_threshold,
                collapse_irrelevant=self._config.cbm_collapse_irrelevant,
            )
            for item in items:
                if item.metadata.get("cbm_collapsed"):
                    item.token_count = self._tokenizer.count(item.content)

        # Collapse grep hits covered by earlier reads (token-optimizer read-cache)
        collapse_grep_into_reads(items)

        # Read delta on file re-reads (before verbatim dedup — Myers diff wins on edits)
        if self._read_delta:
            for item in items:
                path = item.source or item.metadata.get("path", "")
                if path and item.content_type in (ContentType.CODE, ContentType.TEXT):
                    delta = self._read_delta.process(path, item.content)
                    if delta.is_delta and delta.strategy != "passthrough":
                        item.content = delta.content
                        item.token_count = self._tokenizer.count(item.content)
                        item.metadata["read_delta"] = delta.strategy

            collapsed_reads = collapse_superseded_reads(items)
            if collapsed_reads:
                for item in items:
                    if item.metadata.get("read_superseded_by_delta"):
                        item.token_count = self._tokenizer.count(item.content)

        # Cross-turn dedup on remaining verbatim repeats
        if self._config.enable_cross_turn_dedup and len(items) > 1:
            blocks = [DedupBlock(text=item.content, turn=i) for i, item in enumerate(items)]
            deduped_blocks, _ = dedup_blocks(blocks)
            for item, block in zip(items, deduped_blocks):
                item.content = block.text
                item.token_count = self._tokenizer.count(item.content)

        # Stale read pruning
        if self._config.enable_read_lifecycle:
            items = prune_stale_reads(items)
            if self._config.live_zone_mode:
                collapse_stale_reads(items)
                for item in items:
                    if item.metadata.get("stale_read_stub"):
                        item.token_count = self._tokenizer.count(item.content)

        analysis = self._analyzer.analyze_items(items, task_query=task_query)
        bm25_scores = {
            item.id: score for item, score in self._ranker.score_items(items, task_query)
        }

        if analysis.duplicates:
            collapse_duplicate_items(items, analysis.duplicates)

        collapse_obsolete_items(items)
        if self._config.enable_proactive_low_tier_collapse:
            collapse_low_relevance_reads(items, task_query=task_query, bm25_scores=bm25_scores)
        for item in items:
            item.token_count = self._tokenizer.count(item.content)

        for id_a, id_b in analysis.duplicates:
            for item in items:
                if item.id == id_b:
                    item.tier = RelevanceTier.REDUNDANT
                    item.metadata["is_duplicate"] = True

        selected = self._select_items(items, task_query)
        knapsack_dropped = sum(1 for i in selected if i.metadata.get("knapsack_dropped"))
        orig_tokens_map = {item.id: item.token_count for item in selected}

        optimized_items: list[ContentItem] = []
        for item in selected:
            agg = self._aggressiveness_for_item(item, base_aggressiveness, bm25_scores.get(item.id, 0.0))
            if self._feedback:
                agg = self._feedback.suggested_aggressiveness(item.source, agg)
            compressed_item, hit = self._compress_item(item, agg, task_query=task_query)
            if hit:
                cache_hits += 1
            optimized_items.append(compressed_item)

        if self._config.enable_cache_aligner:
            for item in optimized_items:
                cache_warnings.extend(detect_volatile_content(item.content))

        output_parts = []
        for item, orig in zip(optimized_items, selected, strict=True):
            output_parts.append(self._format_output_item(item, original_tokens=orig_tokens_map.get(orig.id)))

        output = "\n\n".join(output_parts)
        optimized_tokens = self._tokenizer.count(output)
        latency_ms = (time.perf_counter() - start) * 1000

        stats = CompressionStats.compute(
            "", output, original_tokens, optimized_tokens,
            strategy="context_optimizer", lossless=False, latency_ms=latency_ms,
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
                "knapsack_dropped": knapsack_dropped,
                "cache_warnings": cache_warnings[:10],
                "feedback": self._feedback.stats() if self._feedback else {},
            },
        )

    def optimize_text(self, text: str, *, content_type: str = "") -> OptimizationResult:
        ct = detect_content_type(text, content_type or "")
        item = ContentItem(id="input", content=text, content_type=ct, token_count=self._tokenizer.count(text))
        return self.optimize_items([item])

    def compact_tool_schemas(self, tools: list[dict]) -> tuple[list[dict], dict]:
        if not self._tool_schema:
            return tools, {"tools": len(tools), "skipped": True}
        return self._tool_schema.compact_tools(tools)

    def lazy_tool_catalog(
        self,
        tools: list[dict],
        *,
        level: str | None = None,
    ) -> tuple[str, str, dict]:
        if not self._tool_schema:
            session_id = LazyToolRegistry.store(tools)
            catalog = "\n".join(t.get("name", "?") for t in tools)
            return catalog, session_id, {"tools": len(tools), "skipped": True}
        lvl = level or self._config.lazy_schema_default_level
        return self._tool_schema.lazy_catalog(tools, level=lvl)

    def get_lazy_tool_schema(self, session_id: str, tool_name: str) -> tuple[dict | None, dict]:
        if not self._tool_schema:
            raw = LazyToolRegistry.get(session_id, tool_name)
            return ({"tool": raw} if raw else None), {"session_id": session_id}
        return self._tool_schema.get_lazy_schema(session_id, tool_name)

    def _compress_item(
        self,
        item: ContentItem,
        aggressiveness: float,
        *,
        task_query: str = "",
    ) -> tuple[ContentItem, bool]:
        cache_hit = False
        original_token_count = item.token_count

        if item.metadata.get("read_delta") or item.metadata.get("read_superseded_by_delta"):
            return item, False
        if item.metadata.get("stale_read_stub"):
            return item, False

        if self._cache:
            cache_key = SmartCache.make_key("compress", item.id, str(aggressiveness), item.content[:200])
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached, True

        content = item.content
        strategy = "passthrough"

        if self._config.enable_deduplication:
            dedup = self._dedup.deduplicate_text(content)
            if dedup.duplicates_removed > 0:
                content = dedup.content

        tool_comp = self._compressors[-1]
        if self._config.enable_tool_output_compression:
            tool_result = tool_comp.compress(content, aggressiveness=aggressiveness, query=task_query)
            if tool_result.compressed and tool_result.strategy != "tool_output":
                content = tool_result.content
                strategy = tool_result.strategy

        if strategy == "passthrough":
            routed = self._compress_with_router(content, item.content_type, aggressiveness, task_query)
            if routed.compressed:
                content = routed.content
                strategy = routed.strategy

        new_tokens = self._tokenizer.count(content)
        chars_saved = len(item.content) - len(content)
        token_saved = original_token_count - new_tokens
        ccr_handle = None

        ccr_min_tokens = self._config.ccr_min_token_saved
        if item.tier == RelevanceTier.CRITICAL:
            ccr_min_tokens = self._config.ccr_min_token_saved_critical

        if (
            self._ccr
            and strategy != "passthrough"
            and chars_saved >= self._config.ccr_min_chars_saved
            and token_saved >= ccr_min_tokens
        ):
            handle = self._ccr.store(item.content, metadata={"strategy": strategy, "item_id": item.id})
            marker = self._ccr.marker(handle, chars_dropped=chars_saved)
            marked = f"{content}\n{marker}"
            if self._tokenizer.count(marked) < original_token_count:
                content = marked
                ccr_handle = handle

        if self._config.fail_closed:
            saved_ratio = token_saved / original_token_count if original_token_count else 0
            if new_tokens >= original_token_count or saved_ratio < self._config.fail_closed_min_ratio:
                content = item.content
                new_tokens = original_token_count
                strategy = "passthrough"
                ccr_handle = None
                token_saved = 0

        if self._feedback:
            ratio = token_saved / original_token_count if original_token_count else 0
            self._feedback.record(item.source, compressed=strategy != "passthrough", ratio=ratio)

        metadata = {**item.metadata, "compression_strategy": strategy}
        if ccr_handle:
            metadata["ccr_handle"] = ccr_handle

        optimized = ContentItem(
            id=item.id, content=content, content_type=item.content_type,
            source=item.source, metadata=metadata, tier=item.tier,
            token_count=new_tokens, dependencies=item.dependencies, timestamp=item.timestamp,
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
        return self._ccr.retrieve(handle.removeprefix("ccr_"))

    def analyze(self, items: list[ContentItem]) -> AnalysisReport:
        return self._analyzer.analyze_items(items, task_query=self._config.task_query)

    def _select_items(self, items: list[ContentItem], task_query: str) -> list[ContentItem]:
        if not self._config.live_zone_mode:
            return self._filter.select_items(
                items,
                max_tokens=self._config.max_tokens,
                target_tokens=self._config.target_tokens,
                task_query=task_query,
                use_knapsack=self._config.enable_knapsack_selection,
            )

        if not self._config.enable_hybrid_knapsack:
            return items

        budget = self._config.target_tokens or self._config.max_tokens
        if budget is None:
            return items

        total = sum(i.token_count for i in items)
        threshold_ratio = self._config.knapsack_budget_threshold
        if len(items) >= self._config.knapsack_large_session_items:
            threshold_ratio = self._config.knapsack_large_session_threshold
        threshold = int(budget * threshold_ratio)
        small_session = (
            len(items) >= self._config.knapsack_small_session_items
            and total >= int(budget * self._config.knapsack_small_session_threshold)
        )
        if total <= threshold and not small_session:
            return items

        if small_session and total <= threshold:
            target = int(total * 0.72)
        else:
            target = int(budget * self._config.hybrid_knapsack_target_ratio)
        kept = self._filter.select_items(
            items,
            max_tokens=self._config.max_tokens,
            target_tokens=target,
            task_query=task_query,
            use_knapsack=True,
            drop_redundant=True,
        )
        kept_ids = {i.id for i in kept}
        selected: list[ContentItem] = []
        for item in items:
            if item.id in kept_ids:
                selected.append(item)
            else:
                stub = knapsack_stub(item)
                stub.token_count = self._tokenizer.count(stub.content)
                selected.append(stub)
        return selected

    def _compress_with_router(
        self,
        content: str,
        content_type: ContentType,
        aggressiveness: float,
        task_query: str,
    ) -> CompressResult:
        def pick_best(text: str, ct: ContentType) -> CompressResult:
            best: CompressResult | None = None
            for compressor in self._compressors:
                if compressor.can_handle(ct):
                    kwargs: dict = {"aggressiveness": aggressiveness, "query": task_query}
                    if isinstance(compressor, LogCompressor):
                        kwargs["use_template_mining"] = self._config.enable_log_template_mining
                        if aggressiveness >= 0.75:
                            kwargs["use_template_mining"] = True
                    if isinstance(compressor, CodeCompressor):
                        kwargs["min_chars"] = (
                            self._config.query_slice_min_chars_session
                            if task_query
                            else self._config.query_slice_min_chars
                        )
                    result = compressor.compress(text, **kwargs)
                    if result.compressed and (
                        best is None or len(result.content) < len(best.content)
                    ):
                        best = result
            return best or CompressResult(content=text, strategy="passthrough", compressed=False)

        if self._config.enable_content_router and len(content) > 400:

            def route_fn(text: str, **kwargs: object) -> CompressResult:
                ct = kwargs.get("content_type") if isinstance(kwargs.get("content_type"), ContentType) else detect_content_type(text)
                return pick_best(text, ct)

            routed, strategies = route_and_join(
                content, route_fn, aggressiveness=aggressiveness, query=task_query,
            )
            if len(routed) < len(content):
                return CompressResult(
                    content=routed, strategy="content_router:" + "+".join(strategies[:3]), compressed=True,
                )
        return pick_best(content, content_type)

    def _aggressiveness_for_item(
        self, item: ContentItem, base: float, bm25_score: float,
    ) -> float:
        tier_map = {
            RelevanceTier.CRITICAL: 0.25,
            RelevanceTier.HIGH: base,
            RelevanceTier.MEDIUM: base,
            RelevanceTier.LOW: min(0.85, base + 0.25),
            RelevanceTier.REDUNDANT: 0.9,
            RelevanceTier.DISCARDABLE: 0.95,
        }
        agg = tier_map.get(item.tier, base)
        if bm25_score < 0.1 and item.tier not in (RelevanceTier.CRITICAL, RelevanceTier.HIGH):
            agg = min(0.95, agg + 0.15)
        elif bm25_score > 0.5:
            agg = max(0.15, agg - 0.1)
        return agg

    def _format_output_item(self, item: ContentItem, *, original_tokens: int | None = None) -> str:
        if item.metadata.get("low_relevance_stub"):
            return item.content
        if item.content_type == ContentType.MESSAGE and (item.source in ("user", "system") or item.metadata.get("content_role") in ("user", "system", "instruction")):
            return item.content

        saved = (original_tokens or 0) - item.token_count
        header = item.id
        if (
            self._config.show_token_savings_in_headers
            and original_tokens
            and saved >= self._config.header_min_saved_tokens
            and original_tokens >= self._config.header_min_original_tokens
        ):
            header = f"{item.id}|{original_tokens}→{item.token_count}tok"
        if self._config.compact_output_headers:
            if self._use_inline_header(item.content, item):
                return f"[{header}] {item.content}"
            return f"[{header}]\n{item.content}"
        if self._use_inline_header(item.content, item):
            return f"<!-- {header} --> {item.content}"
        return f"<!-- {header} -->\n{item.content}"

    @staticmethod
    def _use_inline_header(content: str, item: ContentItem) -> bool:
        if item.metadata.get("knapsack_dropped") or item.metadata.get("grep_collapsed"):
            return True
        stripped = content.strip()
        if not stripped:
            return True
        if stripped.startswith("[") and (
            "same as msg" in stripped
            or stripped.startswith("[CBM:")
            or stripped.startswith("[dropped:")
            or stripped.startswith("[grep:")
            or stripped.startswith("[subset read:")
            or stripped.startswith("[unchanged:")
            or stripped.startswith("[first read:")
            or stripped.startswith("[DELTA ")
            or stripped.startswith("[irrelevant read:")
            or stripped.startswith("[obsolete note:")
            or stripped.startswith("[stale read:")
        ):
            return True
        return "\n" not in stripped and len(stripped) <= 120

    @staticmethod
    def _infer_task_query(items: list[ContentItem]) -> str:
        for item in items:
            if item.source == "user" or item.metadata.get("content_role") == "user":
                return item.content[:300]
        return ""

    @property
    def cache_stats(self) -> dict:
        return self._cache.stats if self._cache else {}

    @property
    def feedback_stats(self) -> dict:
        return self._feedback.stats() if self._feedback else {}
