"""FastAPI server for programmatic access."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from token_engine.core.config import EngineConfig, QualityLevel
from token_engine.core.engine import TokenEngine
from token_engine.core.types import ContentItem, ContentType

app = FastAPI(
    title="Token Engine API",
    description="LLM Token Optimization Engine — model-agnostic context compression",
    version="0.1.0",
)


class OptimizeRequest(BaseModel):
    content: str
    content_type: str = ""
    quality: str = "balanced"
    task_query: str = ""
    max_tokens: int | None = None
    target_tokens: int | None = None


class ContextItemRequest(BaseModel):
    id: str
    content: str
    content_type: str = "unknown"
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class OptimizeContextRequest(BaseModel):
    items: list[ContextItemRequest]
    quality: str = "balanced"
    task_query: str = ""
    max_tokens: int | None = None
    target_tokens: int | None = None


class AnalyzeRequest(BaseModel):
    content: str


def _engine_from_request(quality: str, task_query: str = "", max_tokens: int | None = None, target_tokens: int | None = None) -> TokenEngine:
    config = EngineConfig(
        quality_level=QualityLevel(quality),
        task_query=task_query,
        max_tokens=max_tokens,
        target_tokens=target_tokens,
    )
    return TokenEngine(config)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/optimize")
def optimize(req: OptimizeRequest) -> dict[str, Any]:
    engine = _engine_from_request(req.quality, req.task_query, req.max_tokens, req.target_tokens)
    result = engine.optimize(req.content, content_type=req.content_type)
    return _result_to_dict(result)


@app.post("/optimize-context")
def optimize_context(req: OptimizeContextRequest) -> dict[str, Any]:
    engine = _engine_from_request(req.quality, req.task_query, req.max_tokens, req.target_tokens)
    items = [
        ContentItem(
            id=item.id,
            content=item.content,
            content_type=ContentType(item.content_type) if item.content_type != "unknown" else ContentType.UNKNOWN,
            source=item.source,
            metadata=item.metadata,
        )
        for item in req.items
    ]
    result = engine.optimize_context(items)
    return _result_to_dict(result)


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    engine = TokenEngine()
    result = engine.analyze(req.content)
    report = result.analysis
    return {
        "total_tokens": report.total_tokens if report else 0,
        "metrics": {
            "by_source": report.metrics.tokens_by_source if report else {},
            "by_type": report.metrics.tokens_by_type if report else {},
            "redundant": report.metrics.redundant_tokens if report else 0,
            "critical": report.metrics.critical_tokens if report else 0,
        } if report else {},
        "recommendations": report.recommendations if report else [],
    }


@app.post("/compact-tools")
def compact_tools_endpoint(req: dict) -> dict[str, Any]:
    engine = TokenEngine()
    tools = req.get("tools", [])
    compacted, stats = engine.compact_tool_schemas(tools)
    return {"tools": compacted, "stats": stats}


@app.post("/retrieve-ccr")
def retrieve_ccr(req: dict) -> dict[str, str | None]:
    engine = TokenEngine()
    handle = req.get("handle", "")
    content = engine.retrieve_compressed(handle)
    return {"content": content}


@app.post("/count-tokens")
def count_tokens(req: AnalyzeRequest) -> dict[str, int]:
    engine = TokenEngine()
    return {"tokens": engine.count_tokens(req.content)}


def _result_to_dict(result) -> dict[str, Any]:
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
    if result.analysis:
        out["analysis"] = {
            "total_tokens": result.analysis.total_tokens,
            "recommendations": result.analysis.recommendations,
        }
    return out
