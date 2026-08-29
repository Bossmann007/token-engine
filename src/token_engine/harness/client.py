"""HTTP/in-process harness client for POST /optimize-context."""

from __future__ import annotations

from typing import Any

from token_engine.core.config import EngineConfig
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType, OptimizationResult


class HarnessClient:
    """Call Token Engine before each LLM turn (API first, in-process fallback)."""

    DEFAULT_URL = "http://127.0.0.1:8741"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        config: EngineConfig | None = None,
        prefer_api: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or self.DEFAULT_URL).rstrip("/")
        self._config = config or EngineConfig.default()
        self._prefer_api = prefer_api
        self._timeout = timeout
        self._engine = TokenEngine(self._config)

    def optimize_context(
        self,
        items: list[dict[str, Any] | ContentItem],
        *,
        task_query: str = "",
        quality: str | None = None,
        max_tokens: int | None = None,
        target_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Optimize context items; returns API-shaped dict with content + stats."""
        normalized = [self._as_item(i, idx) for idx, i in enumerate(items)]
        payload = {
            "items": [self._item_payload(i) for i in normalized],
            "quality": quality or self._config.quality_level.value,
            "task_query": task_query or self._config.task_query,
            "max_tokens": max_tokens if max_tokens is not None else self._config.max_tokens,
            "target_tokens": target_tokens if target_tokens is not None else self._config.target_tokens,
        }
        if self._prefer_api and self._api_available():
            return self._post("/optimize-context", payload)
        return self._result_dict(self._engine.optimize_context(normalized))

    def optimize_messages(
        self,
        messages: list[dict[str, str]],
        *,
        task_query: str = "",
        quality: str | None = None,
        max_tokens: int | None = None,
        target_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Chat harness helper — list of {role, content} dicts."""
        items = [
            ContentItem(
                id=f"msg_{idx}",
                content=msg["content"],
                content_type=ContentType.MESSAGE,
                source=msg.get("role", "user"),
                metadata={"content_role": msg.get("role", "user")},
            )
            for idx, msg in enumerate(messages)
        ]
        if not task_query:
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    task_query = msg["content"][:300]
                    break
        return self.optimize_context(
            items,
            task_query=task_query,
            quality=quality,
            max_tokens=max_tokens,
            target_tokens=target_tokens,
        )

    def health(self) -> dict[str, Any]:
        if self._api_available():
            return self._get("/health")
        return {"status": "ok", "mode": "in-process"}

    def _api_available(self) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=min(self._timeout, 1.0))
            return response.status_code == 200
        except Exception:
            return False

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        response = httpx.post(
            f"{self.base_url}{path}",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

    def _get(self, path: str) -> dict[str, Any]:
        import httpx

        response = httpx.get(f"{self.base_url}{path}", timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _as_item(raw: dict[str, Any] | ContentItem, idx: int) -> ContentItem:
        if isinstance(raw, ContentItem):
            return raw
        content_type = raw.get("content_type", "unknown")
        return ContentItem(
            id=raw.get("id", f"item_{idx}"),
            content=raw["content"],
            content_type=ContentType(content_type) if content_type != "unknown" else ContentType.UNKNOWN,
            source=raw.get("source", ""),
            metadata=dict(raw.get("metadata") or {}),
        )

    @staticmethod
    def _item_payload(item: ContentItem) -> dict[str, Any]:
        ct = item.content_type.value if isinstance(item.content_type, ContentType) else str(item.content_type)
        return {
            "id": item.id,
            "content": item.content,
            "content_type": ct,
            "source": item.source,
            "metadata": item.metadata,
        }

    @staticmethod
    def _result_dict(result: OptimizationResult) -> dict[str, Any]:
        out: dict[str, Any] = {"content": result.content}
        if result.stats:
            out["stats"] = {
                "original_tokens": result.stats.original_tokens,
                "optimized_tokens": result.stats.optimized_tokens,
                "tokens_saved": result.stats.tokens_saved,
                "compression_ratio": result.stats.compression_ratio,
                "strategy": result.stats.strategy,
                "latency_ms": result.stats.latency_ms,
            }
        if result.metadata:
            out["metadata"] = result.metadata
        return out
