# API Reference

## REST API

Start server:

```bash
uvicorn token_engine.api.server:app --host 0.0.0.0 --port 8741
```

### `GET /health`

Returns service status.

### `POST /optimize`

Optimize single text content.

```json
{
  "content": "large log output...",
  "content_type": "log",
  "quality": "balanced",
  "task_query": "fix authentication bug",
  "max_tokens": 8000,
  "target_tokens": 4000
}
```

Response:

```json
{
  "content": "optimized output...",
  "stats": {
    "original_tokens": 5000,
    "optimized_tokens": 1200,
    "tokens_saved": 3800,
    "compression_ratio": 0.76,
    "strategy": "context_optimizer",
    "latency_ms": 45.2
  }
}
```

### `POST /optimize-context`

Optimize multiple context items.

```json
{
  "items": [
    {"id": "msg1", "content": "...", "content_type": "message", "source": "user"},
    {"id": "log1", "content": "...", "content_type": "log", "source": "pytest"}
  ],
  "quality": "balanced",
  "task_query": "fix login bug",
  "target_tokens": 4000
}
```

### `POST /analyze`

Analyze token usage without compression.

```json
{"content": "text to analyze..."}
```

### `POST /count-tokens`

Quick token count.

```json
{"content": "hello world"}
```

## Python API

```python
from token_engine import TokenEngine, EngineConfig, QualityLevel
from token_engine.core.types import ContentItem, ContentType

config = EngineConfig(
    quality_level=QualityLevel.BALANCED,
    target_tokens=4000,
    task_query="fix auth bug",
    provider="openai",
    model="gpt-4o",
)

engine = TokenEngine(config)

# Single text
result = engine.optimize(large_log_text, content_type="log")
print(result.stats.tokens_saved)

# Context items
items = [
    ContentItem(id="code", content=source_code, content_type=ContentType.CODE),
    ContentItem(id="test", content=test_output, content_type=ContentType.LOG),
]
result = engine.optimize_context(items)

# Analyze project
result = engine.analyze_project("./src")

# Token count and cost
tokens = engine.count_tokens(text)
cost = engine.estimate_cost(input_tokens=tokens)
```

## CLI

| Command | Description |
|---------|-------------|
| `token-engine optimize <file>` | Optimize a text file |
| `token-engine optimize-context <json>` | Optimize JSON context |
| `token-engine analyze <path>` | Analyze file or directory |
| `token-engine benchmark` | Run benchmarks |
| `token-engine stats <file>` | Token count and cost estimate |

Options: `--quality maximum|balanced|economy`, `--max-tokens N`, `--target-tokens N`, `--task "query"`
