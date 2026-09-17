"""Hierarchical tool routing: BM25 shortlist → optional Jev Choice → validate."""

from __future__ import annotations

import hashlib
import json
import threading
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
from token_engine.jev.redact import minimize_intent, redact_secrets
from token_engine.jev.types import RiskTier, infer_risk_tier
from token_engine.optimizer.ranking import BM25Ranker
from token_engine.tokenizer.base import Tokenizer
from token_engine.tokenizer.tiktoken_tokenizer import TiktokenTokenizer

POLICY_VERSION = "jev-router-v2"
RESERVED_NAMES = frozenset({"__none__", ""})


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
    # Honest accounting: schema reduction is only real if the main model never saw full catalog
    schema_reduction_estimated: int = 0
    schema_reduction_realized: int = 0  # 0 in advisory/Cursor mode
    used_jev: bool = False
    reason: str = ""
    allow_execute: bool = False
    cache_hit: bool = False


class ToolRouter:
    """Route an intent to one catalog tool. Fail-closed; Jev opt-in only."""

    def __init__(
        self,
        config: EngineConfig | None = None,
        *,
        client: JevClient | None = None,
        counter: Tokenizer | None = None,
        advisory_mode: bool = True,
    ) -> None:
        self._config = config or EngineConfig.default()
        self._client = client
        self._counter = counter or TiktokenTokenizer(self._config.encoding)
        self._ranker = BM25Ranker()
        self._circuit = CircuitBreaker()
        self._cache: dict[str, tuple[float, ToolRouteResult]] = {}
        self._lock = threading.RLock()
        self._advisory_mode = advisory_mode
        self._cache_hits = 0
        self._cache_misses = 0
        self._config_fp = self._fingerprint_config(self._config)

    @property
    def cache_stats(self) -> dict[str, int]:
        return {"hits": self._cache_hits, "misses": self._cache_misses, "size": len(self._cache)}

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def route(
        self,
        intent: str,
        tools: list[dict[str, Any]],
        *,
        allowlist: set[str] | None = None,
        denylist: set[str] | None = None,
    ) -> ToolRouteResult:
        catalog, dupes = self._filter_catalog(tools, allowlist=allowlist, denylist=denylist)
        full_tok = self._catalog_tokens(catalog)
        if dupes:
            return ToolRouteResult(
                tool_name=None,
                confidence=0.0,
                risk_tier=RiskTier.READ,
                source="blocked",
                estimated_catalog_tokens_full=full_tok,
                reason=f"duplicate tool names: {sorted(dupes)[:8]}",
                allow_execute=False,
            )
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
        with self._lock:
            cached = self._cache_get(cache_key)
            if cached is not None:
                self._cache_hits += 1
                cached.cache_hit = True
                cached.reason = (cached.reason + "; cache_hit").strip("; ")
                return cached
            self._cache_misses += 1

        shortlist = self._bm25_shortlist(intent, catalog, self._config.jev_max_candidates)
        short_tok = self._catalog_tokens(shortlist)
        net = max(0, full_tok - short_tok)
        by_name = {str(t.get("name")): t for t in shortlist if t.get("name")}
        names = list(by_name.keys())

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
        risk = self._risk_for_tool(top, by_name[top])
        bm25_result = self._finalize_result(
            tool_name=top,
            confidence=0.0,
            risk=risk,
            source="bm25",
            candidates=names,
            full_tok=full_tok,
            short_tok=short_tok,
            net=net,
            reason="local bm25 shortlist",
            used_jev=False,
        )

        if not self._should_use_jev(catalog, net):
            self._cache_put(cache_key, bm25_result)
            return bm25_result

        jev_result = self._jev_pick(intent, by_name, names, full_tok, short_tok, net)
        # Do not cache fallback/error paths — circuit breaker and retries must see failures
        if jev_result.source in {"bm25", "jev"} and jev_result.tool_name is not None:
            self._cache_put(cache_key, jev_result)
        return jev_result

    def _risk_for_tool(self, name: str, meta: dict[str, Any]) -> RiskTier:
        """Explicit catalog risk_tier wins; infer only when absent; invalid → destructive."""
        explicit = meta.get("risk_tier")
        if explicit is None and isinstance(meta.get("metadata"), dict):
            explicit = meta["metadata"].get("risk_tier")
        if explicit is None:
            return infer_risk_tier(name, metadata=meta)
        text = str(explicit).lower().strip()
        try:
            return RiskTier(text)
        except ValueError:
            return RiskTier.DESTRUCTIVE

    def _finalize_result(
        self,
        *,
        tool_name: str | None,
        confidence: float,
        risk: RiskTier,
        source: str,
        candidates: list[str],
        full_tok: int,
        short_tok: int,
        net: int,
        reason: str,
        used_jev: bool,
        jev_in: int = 0,
        jev_out: int = 0,
    ) -> ToolRouteResult:
        allow = False
        if tool_name and risk != RiskTier.DESTRUCTIVE:
            allow = confidence >= self._threshold_for(risk) and used_jev
        # BM25 never auto-executes
        if source == "bm25":
            allow = False
        realized = 0 if self._advisory_mode else max(0, net - jev_in - jev_out)
        return ToolRouteResult(
            tool_name=tool_name,
            confidence=confidence,
            risk_tier=risk,
            source=source,
            candidates=candidates,
            jev_input_tokens=jev_in,
            jev_output_tokens=jev_out,
            estimated_catalog_tokens_full=full_tok,
            estimated_catalog_tokens_shortlist=short_tok,
            estimated_net_savings=max(0, net - jev_in - jev_out),
            schema_reduction_estimated=net,
            schema_reduction_realized=realized,
            used_jev=used_jev,
            reason=reason,
            allow_execute=allow and risk != RiskTier.DESTRUCTIVE,
        )

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
        by_name: dict[str, dict[str, Any]],
        names: list[str],
        full_tok: int,
        short_tok: int,
        net: int,
    ) -> ToolRouteResult:
        state = minimize_intent(
            intent,
            max_chars=max(64, min(2000, int(self._config.jev_max_input_tokens) * 4)),
            redact=self._config.jev_redact_secrets and self._config.jev_data_minimization,
        )
        criteria: dict[str, str | None] = {}
        for n in names:
            raw_desc = str(by_name[n].get("description", "") or "")[:80]
            # Descriptions are untrusted; redact before leaving the machine
            desc = redact_secrets(raw_desc) if self._config.jev_redact_secrets else raw_desc
            criteria[n] = desc or None
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
            if self._config.jev_fallback_mode == "bm25" and names:
                top = names[0]
                return self._finalize_result(
                    tool_name=top,
                    confidence=0.0,
                    risk=self._risk_for_tool(top, by_name[top]),
                    source="fallback",
                    candidates=names,
                    full_tok=full_tok,
                    short_tok=short_tok,
                    net=net,
                    reason=f"jev unavailable: {type(exc).__name__}",
                    used_jev=False,
                )
            return self._finalize_result(
                tool_name=None,
                confidence=0.0,
                risk=RiskTier.READ,
                source="fallback",
                candidates=names,
                full_tok=full_tok,
                short_tok=short_tok,
                net=net,
                reason=f"jev unavailable: {type(exc).__name__}",
                used_jev=False,
            )

        answer = parse_choice_answer(raw.answers.get("tool"))
        choice = answer.choice if answer else None
        if (
            answer is None
            or choice is None
            or choice in RESERVED_NAMES
            or choice == "__none__"
            or choice not in by_name
        ):
            if choice == "__none__" or self._config.jev_fallback_mode == "none":
                return self._finalize_result(
                    tool_name=None,
                    confidence=float(answer.confidence) if answer else 0.0,
                    risk=RiskTier.READ,
                    source="jev",
                    candidates=names,
                    full_tok=full_tok,
                    short_tok=short_tok,
                    net=net,
                    reason="none or invalid choice",
                    used_jev=True,
                    jev_in=raw.usage_input_tokens,
                    jev_out=raw.usage_output_tokens,
                )
            top = names[0]
            return self._finalize_result(
                tool_name=top,
                confidence=0.0,
                risk=self._risk_for_tool(top, by_name[top]),
                source="fallback",
                candidates=names,
                full_tok=full_tok,
                short_tok=short_tok,
                net=net,
                reason="invalid jev choice; bm25 fallback",
                used_jev=True,
                jev_in=raw.usage_input_tokens,
                jev_out=raw.usage_output_tokens,
            )

        meta = by_name[choice]
        risk = self._risk_for_tool(choice, meta)
        return self._finalize_result(
            tool_name=choice,
            confidence=answer.confidence,
            risk=risk,
            source="jev",
            candidates=names,
            full_tok=full_tok,
            short_tok=short_tok,
            net=net,
            reason="jev choice",
            used_jev=True,
            jev_in=raw.usage_input_tokens,
            jev_out=raw.usage_output_tokens,
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
            desc = str(tool.get("description", "") or "")[:200]
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
    ) -> tuple[list[dict[str, Any]], set[str]]:
        out: list[dict[str, Any]] = []
        deny = denylist or set()
        seen: set[str] = set()
        dupes: set[str] = set()
        for tool in tools:
            name = str(tool.get("name", ""))
            if not name or name in RESERVED_NAMES or name in deny:
                continue
            if allowlist is not None and name not in allowlist:
                continue
            if name in seen:
                dupes.add(name)
                continue
            seen.add(name)
            safe = dict(tool)
            desc = str(safe.get("description", "") or "")
            # Treat descriptions as untrusted data: hard truncate (not phrase filters alone)
            if len(desc) > 240:
                safe["description"] = desc[:240]
            out.append(safe)
        if dupes:
            # Remove first occurrences too — ambiguous catalog is unsafe
            out = [t for t in out if str(t.get("name")) not in dupes]
        return out, dupes

    def _catalog_tokens(self, tools: list[dict[str, Any]]) -> int:
        return self._counter.count(json.dumps(tools, ensure_ascii=False))

    @staticmethod
    def _fingerprint_config(cfg: EngineConfig) -> str:
        payload = {
            "enable": cfg.enable_jev_router,
            "model": cfg.jev_model,
            "max_cand": cfg.jev_max_candidates,
            "read": cfg.jev_min_confidence_read,
            "write": cfg.jev_min_confidence_write,
            "dest": cfg.jev_min_confidence_destructive,
            "fallback": cfg.jev_fallback_mode,
            "min_tools": cfg.jev_min_catalog_tools,
            "min_save": cfg.jev_min_expected_token_savings,
            "ttl": cfg.jev_cache_ttl_seconds,
            "policy": POLICY_VERSION,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]

    def _tool_fingerprint(self, tool: dict[str, Any]) -> str:
        schema = tool.get("inputSchema") or tool.get("parameters") or {}
        risk = tool.get("risk_tier")
        if risk is None and isinstance(tool.get("metadata"), dict):
            risk = tool["metadata"].get("risk_tier")
        blob = {
            "n": tool.get("name"),
            "d": str(tool.get("description", "") or "")[:240],
            "r": risk,
            "s": hashlib.sha256(
                json.dumps(schema, sort_keys=True, default=str).encode()
            ).hexdigest()[:16],
        }
        return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()[:16]

    def _cache_key(self, intent: str, tools: list[dict[str, Any]]) -> str:
        blob = {
            "intent": minimize_intent(intent, redact=True),
            "tools": [self._tool_fingerprint(t) for t in tools],
            "cfg": self._config_fp,
            "policy": POLICY_VERSION,
            "advisory": self._advisory_mode,
        }
        return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()[:32]

    def _cache_get(self, key: str) -> ToolRouteResult | None:
        hit = self._cache.get(key)
        if not hit:
            return None
        ts, result = hit
        ttl = self._config.jev_cache_ttl_seconds
        if ttl == 0:
            self._cache.pop(key, None)
            return None
        if time.monotonic() - ts > ttl:
            self._cache.pop(key, None)
            return None
        return ToolRouteResult(**result.__dict__)

    def _cache_put(self, key: str, result: ToolRouteResult) -> None:
        ttl = self._config.jev_cache_ttl_seconds
        if ttl == 0:
            return
        with self._lock:
            self._cache[key] = (time.monotonic(), result)
            max_entries = 256
            while len(self._cache) > max_entries:
                self._cache.pop(next(iter(self._cache)))
