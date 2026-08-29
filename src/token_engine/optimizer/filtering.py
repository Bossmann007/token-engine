"""Context filtering and selection under token budget."""

from __future__ import annotations

from token_engine.core.types import ContentItem, RelevanceTier
from token_engine.optimizer.knapsack import knapsack_select
from token_engine.optimizer.ranking import BM25Ranker
from token_engine.tokenizer.base import Tokenizer


class ContextFilter:
    """Decide what enters the optimized context."""

    TIER_PRIORITY = {
        RelevanceTier.CRITICAL: 0,
        RelevanceTier.HIGH: 1,
        RelevanceTier.MEDIUM: 2,
        RelevanceTier.LOW: 3,
        RelevanceTier.REDUNDANT: 4,
        RelevanceTier.DISCARDABLE: 5,
    }

    def __init__(self, tokenizer: Tokenizer) -> None:
        self._tokenizer = tokenizer
        self._ranker = BM25Ranker()

    def select_items(
        self,
        items: list[ContentItem],
        *,
        max_tokens: int | None = None,
        target_tokens: int | None = None,
        task_query: str = "",
        drop_redundant: bool = True,
        use_knapsack: bool = True,
    ) -> list[ContentItem]:
        budget = target_tokens or max_tokens
        if budget is None:
            return items

        if drop_redundant:
            items = [i for i in items if i.tier not in (RelevanceTier.REDUNDANT, RelevanceTier.DISCARDABLE)]

        if use_knapsack:
            ranked = self._ranker.score_items(items, task_query)
            scores = {item.id: score for item, score in ranked}
            return knapsack_select(items, budget, scores)

        # Fallback: greedy by tier + BM25
        critical = [i for i in items if i.tier == RelevanceTier.CRITICAL]
        rest = [i for i in items if i.tier != RelevanceTier.CRITICAL]
        ranked = self._ranker.score_items(rest, task_query)
        selected = list(critical)
        used_tokens = sum(i.token_count for i in critical)
        for item, _score in ranked:
            if used_tokens + item.token_count <= budget:
                selected.append(item)
                used_tokens += item.token_count
        id_order = {item.id: idx for idx, item in enumerate(items)}
        selected.sort(key=lambda i: (self.TIER_PRIORITY.get(i.tier, 99), id_order.get(i.id, 999)))
        return selected
