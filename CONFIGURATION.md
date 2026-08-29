# Configuration

## EngineConfig

```python
from token_engine import EngineConfig, QualityLevel

config = EngineConfig(
    # Provider
    provider="openai",          # openai | anthropic | google | local
    model="gpt-4o",

    # Token budget
    max_tokens=128000,          # hard ceiling
    target_tokens=32000,        # optimization target
    budget_usd=1.0,             # optional cost budget

    # Quality
    quality_level=QualityLevel.BALANCED,  # maximum | balanced | economy
    compression_level=None,     # override: none | light | moderate | aggressive

    # Features
    enable_deduplication=True,
    enable_cache=True,
    enable_code_aware=True,
    enable_tool_output_compression=True,
    fail_closed=True,

    # Cache
    cache_ttl_seconds=3600,
    cache_max_entries=10000,

    # Task context
    task_query="implement feature X",
    task_complexity="medium",   # simple | medium | complex

    # Cost estimation (USD per 1M tokens)
    input_cost_per_million=2.50,
    output_cost_per_million=10.00,
)
```

## Quality Levels

| Level | Compression | Use Case |
|-------|------------|----------|
| `maximum` | Light (25%) | Complex tasks, debugging, architecture decisions |
| `balanced` | Moderate (55%) | Default agent work |
| `economy` | Aggressive (85%) | Large tool outputs, log dumps |

## JSON Config File

```json
{
  "provider": "anthropic",
  "model": "claude-3-5-sonnet",
  "quality_level": "balanced",
  "target_tokens": 8000,
  "task_query": "refactor auth module",
  "enable_deduplication": true,
  "fail_closed": true
}
```

Load:

```python
engine = TokenEngine.from_config_file("token-engine.json")
```

## Context Item Metadata

Enhance relevance scoring via item metadata:

```json
{
  "id": "error_log",
  "content": "...",
  "metadata": {
    "is_error": true,
    "is_stack_trace": true,
    "content_role": "api_contract",
    "recency_score": 0.95,
    "is_duplicate": false
  }
}
```

## Provider Adapters

Token counting uses tiktoken encodings mapped per model:

| Provider | Models | Encoding |
|----------|--------|----------|
| OpenAI | gpt-4o, o1, o3-mini | o200k_base |
| OpenAI | gpt-4, gpt-3.5-turbo | cl100k_base |
| Anthropic | claude-* | cl100k_base (approximate) |
| Google | gemini-* | cl100k_base (approximate) |

For fast hooks without tiktoken overhead, use `create_tokenizer(use_estimate=True)`.

## Environment Variables

No required environment variables. Optional:

- `TOKEN_ENGINE_QUALITY` — default quality level
- `TOKEN_ENGINE_PROVIDER` — default provider
- `TOKEN_ENGINE_MODEL` — default model
