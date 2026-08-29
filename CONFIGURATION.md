# Configuration

## Default stack (all features ON)

Load `config/token-engine.defaults.json` or:

```python
from token_engine import TokenEngine
engine = TokenEngine.default()  # full stack enabled
```

| Feature | Flag | Default | Source |
|---------|------|---------|--------|
| Live-zone (no drop) | `live_zone_mode` | **true** | headroom |
| Cross-turn dedup | `enable_cross_turn_dedup` | true | headroom |
| SmartCrusher | `enable_smart_crusher` | true | headroom |
| CCR recovery | `enable_ccr` | true | headroom/caveman |
| Log template mining | `enable_log_template_mining` | true | slimctx |
| TOON encoding | `enable_toon_encoding` | true | caveman/kompact |
| Read delta | `enable_read_delta` | true | TokenDamper |
| Knapsack selection | `enable_knapsack_selection` | true | TokenDamper |
| Stale read prune | `enable_read_lifecycle` | true | headroom |
| Compression feedback | `enable_compression_feedback` | true | headroom |
| Cache aligner | `enable_cache_aligner` | true | headroom |
| Sandbox execute | `enable_sandbox_execute` | true | context-mode |
| Tool schema compaction | `enable_tool_schema_compaction` | true | mcp-compressor |

Token counting default: `o200k_base` (modern BPE; override via `encoding`).

## EngineConfig

```python
from token_engine import EngineConfig, QualityLevel

config = EngineConfig(
    # Token counting (tiktoken encoding)
    encoding="o200k_base",      # or cl100k_base for older BPE models

    # Token budget
    max_tokens=128000,          # hard ceiling
    target_tokens=32000,        # optimization target
    budget_usd=1.0,             # optional cost budget

    # Quality
    quality_level=QualityLevel.BALANCED,  # maximum | balanced | economy
    compression_level=None,     # override: none | light | moderate | aggressive

    # Features
    enable_deduplication=True,
    enable_cross_turn_dedup=True,
    enable_smart_crusher=True,
    enable_ccr=True,
    enable_tool_schema_compaction=True,
    live_zone_mode=False,
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
  "encoding": "o200k_base",
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

## Tokenizer

Token counting uses [tiktoken](https://github.com/openai/tiktoken) encodings directly — no provider or model coupling:

| Encoding | Typical use |
|----------|-------------|
| `o200k_base` | Default; modern multimodal / reasoning models |
| `cl100k_base` | GPT-4 era and many approximate counts |
| `p50k_base` / `r50k_base` | Legacy OpenAI models |

For fast hooks without tiktoken overhead, use `create_tokenizer(use_estimate=True)`.

## Environment Variables

No required environment variables. Optional:

- `TOKEN_ENGINE_QUALITY` — default quality level
- `TOKEN_ENGINE_ENCODING` — default tiktoken encoding
