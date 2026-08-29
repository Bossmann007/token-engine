"""Token and content analyzer."""

from __future__ import annotations

import re
from collections import Counter

from token_engine.core.types import (
    AnalysisReport,
    ContentItem,
    ContentType,
    RelevanceTier,
    TokenMetrics,
)
from token_engine.compressor.detect import detect_content_type
from token_engine.compressor.deduplicator import Deduplicator
from token_engine.tokenizer.base import Tokenizer


class TokenAnalyzer:
    """Analyze content for token usage, redundancy, and relevance signals."""

    CRITICAL_KEYWORDS = re.compile(
        r"(error|exception|traceback|failed|panic|security|password|secret|api[_-]?key|"
        r"stack trace|assertion|critical|fatal|vulnerability|CVE-\d+)",
        re.IGNORECASE,
    )
    OBSOLETE_KEYWORDS = re.compile(
        r"(deprecated|legacy|old version|no longer used|TODO: remove|FIXME)",
        re.IGNORECASE,
    )

    def __init__(self, tokenizer: Tokenizer) -> None:
        self._tokenizer = tokenizer
        self._dedup = Deduplicator()

    def analyze_items(self, items: list[ContentItem], *, task_query: str = "") -> AnalysisReport:
        metrics = TokenMetrics()
        recommendations: list[str] = []

        for item in items:
            if item.token_count == 0:
                item.token_count = self._tokenizer.count(item.content)
            if item.content_type == ContentType.UNKNOWN:
                item.content_type = detect_content_type(item.content, item.metadata.get("hint", ""))

            metrics.total_tokens += item.token_count
            metrics.tokens_by_source[item.source or "unknown"] = (
                metrics.tokens_by_source.get(item.source or "unknown", 0) + item.token_count
            )
            metrics.tokens_by_type[item.content_type.value] = (
                metrics.tokens_by_type.get(item.content_type.value, 0) + item.token_count
            )

            item.tier = self._score_relevance(item, task_query)

            if item.tier == RelevanceTier.CRITICAL:
                metrics.critical_tokens += item.token_count
            elif item.tier in (RelevanceTier.REDUNDANT, RelevanceTier.DISCARDABLE):
                metrics.discardable_tokens += item.token_count

        dup_pairs = self._dedup.find_duplicates_among_items([(i.id, i.content) for i in items])
        if dup_pairs:
            dup_tokens = sum(
                next(i.token_count for i in items if i.id == dup_id)
                for _, dup_id in dup_pairs
            )
            metrics.redundant_tokens = dup_tokens
            recommendations.append(f"Remove {len(dup_pairs)} duplicate item(s) (~{dup_tokens} tokens)")

        large_items = [i for i in items if i.token_count > 2000]
        if large_items:
            recommendations.append(
                f"Compress {len(large_items)} large item(s): {', '.join(i.id for i in large_items[:5])}"
            )

        low_relevance = [i for i in items if i.tier in (RelevanceTier.LOW, RelevanceTier.DISCARDABLE)]
        if low_relevance:
            recommendations.append(
                f"Consider dropping {len(low_relevance)} low-relevance items (~{sum(i.token_count for i in low_relevance)} tokens)"
            )

        return AnalysisReport(
            metrics=metrics,
            items=items,
            duplicates=dup_pairs,
            recommendations=recommendations,
        )

    def analyze_text(self, text: str, *, source: str = "text") -> AnalysisReport:
        item = ContentItem(id=source, content=text, source=source)
        return self.analyze_items([item])

    def analyze_directory_summary(self, files: dict[str, str]) -> AnalysisReport:
        items = [
            ContentItem(id=path, content=content, source=path, metadata={"path": path})
            for path, content in files.items()
        ]
        return self.analyze_items(items)

    def _score_relevance(self, item: ContentItem, task_query: str) -> RelevanceTier:
        content = item.content
        meta = item.metadata

        # Critical signals
        if self.CRITICAL_KEYWORDS.search(content):
            return RelevanceTier.CRITICAL

        if meta.get("is_error") or meta.get("is_stack_trace"):
            return RelevanceTier.CRITICAL

        if meta.get("content_role") in ("system", "instruction", "api_contract"):
            return RelevanceTier.CRITICAL

        # Task query relevance (simple BM25-like term overlap)
        if task_query:
            query_terms = set(task_query.lower().split())
            content_terms = set(content.lower().split())
            overlap = len(query_terms & content_terms) / max(len(query_terms), 1)
            if overlap > 0.5:
                return RelevanceTier.HIGH
            if overlap > 0.2:
                return RelevanceTier.MEDIUM

        # Recency boost
        if meta.get("recency_score", 0) > 0.8:
            return RelevanceTier.HIGH

        # Obsolete content
        if self.OBSOLETE_KEYWORDS.search(content):
            return RelevanceTier.DISCARDABLE

        # Size-based heuristics for tool outputs
        if item.content_type in (ContentType.LOG, ContentType.TERMINAL) and item.token_count > 3000:
            if not self.CRITICAL_KEYWORDS.search(content):
                return RelevanceTier.LOW

        # Redundant if marked
        if meta.get("is_duplicate"):
            return RelevanceTier.REDUNDANT

        return RelevanceTier.MEDIUM
