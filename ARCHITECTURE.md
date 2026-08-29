# Architecture

## Overview

Token Engine is a modular, provider-agnostic library designed for integration into AI Harnesses. It separates **core logic** from **provider adapters** and uses a plugin registry for extensibility.

## Modules

### Core (`token_engine.core`)

| Component | Responsibility |
|-----------|---------------|
| `EngineConfig` | Token budget, quality levels, feature flags |
| `TokenEngine` | Public facade — optimize, analyze, count |
| `types` | `ContentItem`, `RelevanceTier`, metrics dataclasses |
| `registry` | Plugin registration for compressors, tokenizers, rankers |

### Tokenizer (`token_engine.tokenizer`)

- **TiktokenTokenizer** — accurate BPE counting (default)
- **CharEstimateTokenizer** — fast fallback (~3.3 chars/token)
- Provider adapters map models to encodings (OpenAI `o200k_base`, Anthropic approximate via `cl100k_base`)

### Analyzer (`token_engine.analyzer`)

- Token counts by source, type, message
- Redundancy detection via content hashing
- Relevance tier assignment (CRITICAL → DISCARDABLE)
- Recommendations for compression opportunities

### Compressor (`token_engine.compressor`)

Content-type routed compression pipeline:

```
detect_content_type()
       │
       ├── JSONCompressor
       ├── LogCompressor
       ├── CodeCompressor
       ├── DiffCompressor
       └── ToolOutputCompressor
              ├── git, pytest, grep, ls, npm
              └── falls back to LogCompressor
```

**Fail-closed rule**: if compressed output is not smaller in tokens, pass original through unchanged.

### Optimizer (`token_engine.optimizer`)

1. **Analyze** all items → assign tiers
2. **Deduplicate** cross-item duplicates → mark REDUNDANT
3. **Filter** under token budget (always keep CRITICAL)
4. **Rank** remaining with BM25 + recency + error boost
5. **Compress** each item with adaptive aggressiveness

### Cache (`token_engine.cache`)

- In-memory store with TTL
- Dependency tracking (invalidate on file change)
- Used for compression results and analysis

## Data Flow

```
Input (text | ContentItem[] | JSON context file)
  → Tokenizer.count() per item
  → Analyzer.analyze_items() → tiers, duplicates, metrics
  → ContextFilter.select_items() → budget-aware selection
  → Compressor chain per item (with cache lookup)
  → OptimizationResult { content, stats, analysis }
```

## Plugin Architecture

Register custom compressors via `compressor_registry`:

```python
from token_engine.core.registry import compressor_registry
from token_engine.compressor.base import Compressor

class MyCompressor(Compressor):
    ...

compressor_registry.register("my_compressor", MyCompressor(), priority=0)
```

## Integration Points for AI Harness

1. **Pre-context hook** — call `engine.optimize_context(items)` before LLM request
2. **Post-tool hook** — call `engine.optimize(tool_output, content_type="tool_output")`
3. **Budget enforcement** — set `target_tokens` based on model window
4. **Cache invalidation** — call `cache.invalidate_path()` on file writes

## Design Principles

1. **Quality first** — never drop errors, stack traces, or task-critical code
2. **Fail-closed** — no compression unless provably smaller
3. **Deterministic** — same input → same output (no LLM calls in core)
4. **Fast** — pure Python + tiktoken, sub-100ms for typical agent contexts
5. **Extensible** — plugins without core modification

## Rejected Architectures

| Approach | Source | Why Rejected |
|----------|--------|--------------|
| Proxy intercept | caveman | Adds latency hop; harness can call engine directly |
| Hard deny native tools | token-optimizer-mcp | Fragile; harness controls tool routing |
| LLM summarization in core | various | Non-deterministic, adds cost/latency |
| Embedding RAG as default | claude-context | Different problem; optional future module |
