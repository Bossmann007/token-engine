"""Hierarchical tool routing: BM25 shortlist → optional Jev Choice → validate."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from token_engine.core.config import EngineConfig
from token_engine.core.types import ContentItem, ContentType
from token_engine.jev.circuit import CircuitBreaker
from token_engine.jev.client import (
    HttpJevClient,
    JevClient,
    JevUnavailableError,
    parse_choice_answer,
    try_typesafe_sdk_client,
)
from token_engine.jev.redact import minimize_intent
from token_engine.jev.types import RiskTier, infer_risk_tier
from token_engine.optimizer.ranking import BM25Ranker
from token_engine.tokenizer.base import Tokenizer
from token_engine.tokenizer.tiktoken_tokenizer import TiktokenTokenizer


@dataclass
class ToolRouteResult:
    tool_name: str | None
    confidence: float
    risk_tier: RiskTier
    source: str  # bm25 | jev | fallback | skipped | blocked
    candidates: list[str] = field(default_factory=list)
    jev_input_tokens: int = 0
    jev_output_tokens: int = 0
    estimated_catalog_tokens_full: int = 0
    estimated_catalog_tokens_shortlist: int = 0
    estimated_net_savings: int = 0
    used_jev: bool = False
    reason: str = ""
    allow_execute: bool = False


class ToolRouter:
    """Route an intent to one catalog tool. Fail-closed; Jev opt-in only."""

    def __init__(
        self,
        config: EngineConfig | None = None,
        *,
        client: JevClient | None = None,
        counter: Tokenizer | None = None,
    ) -> None:
        self._config = config or EngineConfig.default()
        self._client = client
        self._counter = counter or TiktokenTokenizer(self._config.encoding)
        self._ranker = BM25Ranker()
        self._circuit = CircuitBreaker()
        self._cache: dict[str, tuple[float, ToolRouteResult]] = {}

    def route(
        self,
        intent: str,
        tools: list[dict[str, Any]],
        *,
        allowlist: set[str] | None = None,
        denylist: set[str] | None = None,
    ) -> ToolRouteResult:
        catalog = self._filter_catalog(tools, allowlist=allowlist, denylist=denylist)
        full_tok = self._catalog_tokens(catalog)
        if not catalog:
            return ToolRouteResult(
                tool_name=None,
                confidence=0.0,
                risk_tier=RiskTier.READ,
                source="skipped",
                estimated_catalog_tokens_full=full_tok,
                reason="empty catalog",
            )

        cache_key = self._cache_key(intent, catalog)
        cached = self._cache_get(cache_key)
        if cached is not None:
            cached.reason = (cached.reason + "; cache_hit").strip("; ")
            return cached

        shortlist = self._bm25_shortlist(intent, catalog, self._config.jev_max_candidates)
        short_tok = self._catalog_tokens(shortlist)
        net = max(0, full_tok - short_tok)
        names = [str(t.get("name", "")) for t in shortlist if t.get("name")]

        if not names:
            return ToolRouteResult(
                tool_name=None,
                confidence=0.0,
                risk_tier=RiskTier.READ,
                source="skipped",
                estimated_catalog_tokens_full=full_tok,
                estimated_catalog_tokens_shortlist=short_tok,
                reason="no bm25 candidates",
            )

        top = names[0]
        top_meta = next((t for t in shortlist if t.get("name") == top), {})
        risk = infer_risk_tier(top, metadata=top_meta if isinstance(top_meta, dict) else None)
        bm25_result = ToolRouteResult(
            tool_name=top,
            confidence=0.0,
            risk_tier=risk,
            source="bm25",
            candidates=names,
            estimated_catalog_tokens_full=full_tok,
            estimated_catalog_tokens_shortlist=short_tok,
            estimated_net_savings=net,
            allow_execute=False,
            reason="local bm25 shortlist",
        )

        if not self._should_use_jev(catalog, net):
            self._cache_put(cache_key, bm25_result)
            return bm25_result

        jev_result = self._jev_pick(intent, shortlist, names, full_tok, short_tok, net)
        self._cache_put(cache_key, jev_result)
        return jev_result

    def _should_use_jev(self, catalog: list[dict[str, Any]], net_savings: int) -> bool:
        cfg = self._config
        if not cfg.enable_jev_router:
            return False
        if len(catalog) < cfg.jev_min_catalog_tools:
            return False
        if net_savings < cfg.jev_min_expected_token_savings:
            return False
        if not self._circuit.allow():
            return False
        return True

    def _jev_pick(
        self,
        intent: str,
        shortlist: list[dict[str, Any]],
        names: list[str],
        full_tok: int,
        short_tok: int,
        net: int,
    ) -> ToolRouteResult:
        state = minimize_intent(
            intent,
            max_chars=min(500, self._config.jev_max_input_tokens * 4),
            redact=self._config.jev_redact_secrets and self._config.jev_data_minimization,
        )
        criteria = {
            n: (next((str(t.get("description", "") or "")[:80] for t in shortlist if t.get("name") == n), None) or None)
            for n in names
        }
        criteria["__none__"] = "Intent does not match any listed tool or is underspecified"
        questions = {
            "tool": {
                "type": "choice",
                "instructions": "Which tool best matches the user intent? Prefer __none__ if unclear.",
                "criteria": criteria,
            }
        }
        client = self._resolve_client()
        try:
            raw = client.evaluate(
                state,
                questions,
                model=self._config.jev_model,
                timeout_seconds=self._config.jev_timeout_seconds,
            )
            self._circuit.record_success()
        except JevUnavailableError as exc:
            self._circuit.record_failure()
            fallback = self._config.jev_fallback_mode
            if fallback == "bm25" and names:
                return ToolRouteResult(
                    tool_name=names[0],
                    confidence=0.0,
                    risk_tier=infer_risk_tier(names[0]),
                    source="fallback",
                    candidates=names,
                    estimated_catalog_tokens_full=full_tok,
                    estimated_catalog_tokens_shortlist=short_tok,
                    estimated_net_savings=net,
                    reason=f"jev unavailable: {exc}",
                    allow_execute=False,
                )
            return ToolRouteResult(
                tool_name=None,
                confidence=0.0,
                risk_tier=RiskTier.READ,
                source="fallback",
                candidates=names,
                estimated_catalog_tokens_full=full_tok,
                estimated_catalog_tokens_shortlist=short_tok,
                estimated_net_savings=net,
                reason=f"jev unavailable: {exc}",
            )

        answer = parse_choice_answer(raw.answers.get("tool"))
        if answer is None or answer.choice == "__none__" or answer.choice not in names:
            return ToolRouteResult(
                tool_name=None if self._config.jev_fallback_mode == "none" else names[0],
                confidence=float(answer.confidence) if answer else 0.0,
                risk_tier=infer_risk_tier(names[0]) if names else RiskTier.READ,
                source="jev" if answer and answer.choice == "__none__" else "fallback",
                candidates=names,
                jev_input_tokens=raw.usage_input_tokens,
                jev_output_tokens=raw.usage_output_tokens,
                estimated_catalog_tokens_full=full_tok,
                estimated_catalog_tokens_shortlist=short_tok,
                estimated_net_savings=max(0, net - raw.usage_input_tokens - raw.usage_output_tokens),
                used_jev=True,
                reason="low confidence or invalid/none choice",
                allow_execute=False,
            )

        risk = infer_risk_tier(answer.choice)
        threshold = self._threshold_for(risk)
        allow = answer.confidence >= threshold and risk != RiskTier.DESTRUCTIVE
        return ToolRouteResult(
            tool_name=answer.choice,
            confidence=answer.confidence,
            risk_tier=risk,
            source="jev",
            candidates=names,
            jev_input_tokens=raw.usage_input_tokens,
            jev_output_tokens=raw.usage_output_tokens,
            estimated_catalog_tokens_full=full_tok,
            estimated_catalog_tokens_shortlist=short_tok,
            estimated_net_savings=max(0, net - raw.usage_input_tokens - raw.usage_output_tokens),
            used_jev=True,
            reason="jev choice",
            allow_execute=allow,
        )

    def _threshold_for(self, risk: RiskTier) -> float:
        if risk == RiskTier.DESTRUCTIVE:
            return self._config.jev_min_confidence_destructive
        if risk == RiskTier.WRITE:
            return self._config.jev_min_confidence_write
        return self._config.jev_min_confidence_read

    def _resolve_client(self) -> JevClient:
        if self._client is not None:
            return self._client
        sdk = try_typesafe_sdk_client()
        if sdk is not None:
            return sdk
        return HttpJevClient()

    def _bm25_shortlist(
        self, intent: str, tools: list[dict[str, Any]], k: int
    ) -> list[dict[str, Any]]:
        items: list[ContentItem] = []
        for i, tool in enumerate(tools):
            name = str(tool.get("name", ""))
            desc = str(tool.get("description", "") or "")
            items.append(
                ContentItem(
                    id=f"tool-{i}",
                    content=f"{name} {desc}",
                    content_type=ContentType.TEXT,
                )
            )
        ranked = self._ranker.score_items(items, intent)
        out: list[dict[str, Any]] = []
        for item, _score in ranked[: max(1, k)]:
            idx = int(item.id.split("-", 1)[1])
            out.append(tools[idx])
        return out

    def _filter_catalog(
        self,
        tools: list[dict[str, Any]],
        *,
        allowlist: set[str] | None,
        denylist: set[str] | None,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        deny = denylist or set()
        for tool in tools:
            name = str(tool.get("name", ""))
            if not name or name in deny:
                continue
            if allowlist is not None and name not in allowlist:
                continue
            # Strip injection-heavy description noise for ranking; keep short label.
            safe = dict(tool)
            desc = str(safe.get("description", "") or "")
            if "ignore previous" in desc.lower() or "system prompt" in desc.lower():
                safe["description"] = name
            out.append(safe)
        return out

    def _catalog_tokens(self, tools: list[dict[str, Any]]) -> int:
        return self._counter.count(json.dumps(tools, ensure_ascii=False))

    def _cache_key(self, intent: str, tools: list[dict[str, Any]]) -> str:
        blob = json.dumps(
            {"intent": minimize_intent(intent, redact=True), "names": [t.get("name") for t in tools]},
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:24]

    def _cache_get(self, key: str) -> ToolRouteResult | None:
        hit = self._cache.get(key)
        if not hit:
            return None
        ts, result = hit
        if time.monotonic() - ts > self._config.jev_cache_ttl_seconds:
            self._cache.pop(key, None)
            return None
        return ToolRouteResult(**result.__dict__)

    def _cache_put(self, key: str, result: ToolRouteResult) -> None:
        self._cache[key] = (time.monotonic(), result)
