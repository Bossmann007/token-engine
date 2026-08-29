"""Relevance ranking and BM25-inspired scoring (caveman contextwindow-inspired)."""

from __future__ import annotations

import math
import re
import time
from collections import Counter

from token_engine.core.types import ContentItem, RelevanceTier


STOPWORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might must can could of in to for on with at by from as into "
    "through during before after and or but not no nor so yet both either neither "
    "each every all any few more most other some such than too very just also".split()
)


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"\b\w+\b", text) if w.lower() not in STOPWORDS and len(w) > 1]


class BM25Ranker:
    """Lexical relevance ranking for context selection."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b

    def score_items(self, items: list[ContentItem], query: str) -> list[tuple[ContentItem, float]]:
        if not query.strip():
            return [(item, self._recency_score(item)) for item in items]

        query_terms = _tokenize(query)
        if not query_terms:
            return [(item, 0.0) for item in items]

        doc_terms = [_tokenize(item.content) for item in items]
        avg_dl = sum(len(d) for d in doc_terms) / max(len(doc_terms), 1)
        N = len(items)

        # Document frequency
        df: Counter[str] = Counter()
        for terms in doc_terms:
            for t in set(terms):
                df[t] += 1

        scores: list[tuple[ContentItem, float]] = []
        for item, terms in zip(items, doc_terms):
            dl = len(terms)
            tf = Counter(terms)
            score = 0.0
            for term in query_terms:
                if term not in tf:
                    continue
                idf = math.log((N - df[term] + 0.5) / (df[term] + 0.5) + 1)
                tf_val = tf[term]
                denom = tf_val + self._k1 * (1 - self._b + self._b * dl / avg_dl)
                score += idf * (tf_val * (self._k1 + 1)) / denom

            # Boosts
            score += self._recency_score(item)
            score += self._tier_boost(item)
            score += self._error_boost(item)

            scores.append((item, score))

        scores.sort(key=lambda x: -x[1])
        return scores

    def _recency_score(self, item: ContentItem) -> float:
        if item.timestamp is None:
            return 0.0
        age_hours = (time.time() - item.timestamp) / 3600
        half_life = 24.0
        return math.exp(-0.693 * age_hours / half_life)

    def _tier_boost(self, item: ContentItem) -> float:
        boosts = {
            RelevanceTier.CRITICAL: 10.0,
            RelevanceTier.HIGH: 3.0,
            RelevanceTier.MEDIUM: 0.0,
            RelevanceTier.LOW: -2.0,
            RelevanceTier.REDUNDANT: -5.0,
            RelevanceTier.DISCARDABLE: -10.0,
        }
        return boosts.get(item.tier, 0.0)

    def _error_boost(self, item: ContentItem) -> float:
        if re.search(r"(error|exception|traceback|failed)", item.content, re.IGNORECASE):
            return 5.0
        return 0.0
