"""Token accounting for tool catalog strategies (local; mock Jev)."""

from __future__ import annotations

import json
from typing import Any

from token_engine.core.config import EngineConfig
from token_engine.core.engine import TokenEngine
from token_engine.jev.router import ToolRouter
from token_engine.jev.types import JevEvaluateResult
from token_engine.tokenizer.tiktoken_tokenizer import TiktokenTokenizer


def _catalog(n: int) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for i in range(n):
        tools.append({
            "name": f"tool_{i:03d}",
            "description": f"Tool number {i} performs action family {i % 7} with detailed docs " + ("word " * 20),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "free text"},
                    "mode": {"type": "string", "enum": ["a", "b", "c"]},
                },
                "required": ["query"],
            },
        })
    return tools


class MockJev:
    def evaluate(self, state, questions, *, model, timeout_seconds):
        opts = list((questions.get("tool") or {}).get("criteria") or {})
        pick = next((o for o in opts if o != "__none__"), "__none__")
        return JevEvaluateResult(
            answers={"tool": {"choice": pick, "confidence": 0.88, "probabilities": {pick: 0.88}}},
            usage_input_tokens=55,
            usage_output_tokens=10,
            model=model,
        )


def test_catalog_token_strategies_scale():
    tok = TiktokenTokenizer()
    engine = TokenEngine()
    rows = []
    for n in (20, 50, 100):
        tools = _catalog(n)
        full = tok.count(json.dumps(tools))
        compacted, _ = engine.compact_tool_schemas(tools)
        compact_tok = tok.count(json.dumps(compacted))
        catalog, _sid, _stats = engine.lazy_tool_catalog(tools, level="medium")
        lazy_tok = tok.count(catalog)
        cfg = EngineConfig(
            enable_jev_router=True,
            jev_min_catalog_tools=10,
            jev_min_expected_token_savings=0,
            jev_max_candidates=8,
        )
        routed = ToolRouter(cfg, client=MockJev(), counter=tok).route(
            "run tool family 3 search query", tools
        )
        combined = routed.estimated_catalog_tokens_shortlist + routed.jev_input_tokens + routed.jev_output_tokens
        rows.append({
            "n": n,
            "full": full,
            "compact": compact_tok,
            "lazy": lazy_tok,
            "bm25_shortlist": routed.estimated_catalog_tokens_shortlist,
            "jev_overhead": routed.jev_input_tokens + routed.jev_output_tokens,
            "combined_shortlist_plus_jev": combined,
        })
        assert compact_tok <= full
        assert lazy_tok < full
        assert routed.estimated_catalog_tokens_shortlist < full
        # Net vs full catalog must beat Jev overhead on these fixtures
        assert combined < full

    # Sanity: larger catalogs cost more full tokens
    assert rows[-1]["full"] > rows[0]["full"]
