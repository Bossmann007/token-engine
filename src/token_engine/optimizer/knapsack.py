"""0/1 Knapsack context selection under token budget (TokenDamper-inspired)."""

from __future__ import annotations

from token_engine.core.types import ContentItem, RelevanceTier


def knapsack_select(
    items: list[ContentItem],
    budget: int,
    scores: dict[str, float] | None = None,
) -> list[ContentItem]:
    """Select items maximizing value density under token budget.

    CRITICAL items are always included (pinned). Uses DP knapsack on the rest.
    """
    if budget <= 0:
        return [i for i in items if i.tier == RelevanceTier.CRITICAL]

    pinned = [i for i in items if i.tier == RelevanceTier.CRITICAL]
    pinned_tokens = sum(i.token_count for i in pinned)
    remaining_budget = max(0, budget - pinned_tokens)

    candidates = [
        i for i in items
        if i.tier != RelevanceTier.CRITICAL
        and i.tier not in (RelevanceTier.REDUNDANT, RelevanceTier.DISCARDABLE)
    ]

    if not candidates or remaining_budget <= 0:
        return pinned

    # Value = relevance score / tokens (density)
    scored: list[tuple[ContentItem, float, int]] = []
    for item in candidates:
        value = (scores or {}).get(item.id, _default_value(item))
        weight = max(1, item.token_count)
        scored.append((item, value, weight))

    n = len(scored)
    # Cap weights for DP table size
    max_w = remaining_budget
    if max_w > 50_000:
        # Greedy fallback for huge budgets
        return _greedy_select(pinned, scored, remaining_budget)

    # DP: dp[w] = max value achievable with weight w
    dp = [0.0] * (max_w + 1)
    choice: list[list[bool | None]] = [[None] * (max_w + 1) for _ in range(n)]

    for i, (item, value, weight) in enumerate(scored):
        for w in range(max_w, weight - 1, -1):
            if dp[w - weight] + value > dp[w]:
                dp[w] = dp[w - weight] + value
                choice[i][w] = True

    # Backtrack
    selected_ids: set[str] = {i.id for i in pinned}
    w = max_w
    for i in range(n - 1, -1, -1):
        if choice[i][w]:
            item, _, weight = scored[i]
            selected_ids.add(item.id)
            w -= weight

    id_order = {item.id: idx for idx, item in enumerate(items)}
    return sorted(
        [i for i in items if i.id in selected_ids],
        key=lambda i: id_order.get(i.id, 999),
    )


def _default_value(item: ContentItem) -> float:
    tier_values = {
        RelevanceTier.CRITICAL: 1000.0,
        RelevanceTier.HIGH: 10.0,
        RelevanceTier.MEDIUM: 3.0,
        RelevanceTier.LOW: 1.0,
        RelevanceTier.REDUNDANT: 0.0,
        RelevanceTier.DISCARDABLE: 0.0,
    }
    return tier_values.get(item.tier, 1.0)


def _greedy_select(
    pinned: list[ContentItem],
    scored: list[tuple[ContentItem, float, int]],
    budget: int,
) -> list[ContentItem]:
    ranked = sorted(scored, key=lambda x: -x[1] / max(1, x[2]))
    selected = list(pinned)
    used = sum(i.token_count for i in pinned)
    for item, _, weight in ranked:
        if used + weight <= budget:
            selected.append(item)
            used += weight
    return selected
