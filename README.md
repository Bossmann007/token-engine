# Token Engine

**Ultimate LLM Token Optimization Engine** — fast, accurate, model-agnostic context compression for AI agents and harnesses.

Token Engine analyzes, ranks, and compresses LLM context while preserving critical information: errors, stack traces, code structure, API contracts, and task-relevant content.

## Quick Start

```bash
pip install -e ".[dev,api]"

# Optimize a file
token-engine optimize benchmarks/fixtures/app_log.txt

# Optimize agent context (JSON)
token-engine optimize-context benchmarks/fixtures/agent_context.json --task "authentication bug"

# Analyze token usage
token-engine analyze benchmarks/fixtures/

# Run benchmarks
token-engine benchmark

# Start API server
uvicorn token_engine.api.server:app --host 0.0.0.0 --port 8741
```

## Features

- **Token Analyzer** — tokens per file/message/tool, redundancy detection, relevance tiers
- **Context Optimizer** — CRITICAL → DISCARDABLE classification with BM25 ranking
- **Compression Engine** — JSON, logs, code, diffs, tool outputs (git, pytest, grep, npm)
- **Deduplication** — cross-item and within-text duplicate detection
- **Smart Cache** — TTL, dependency tracking, file invalidation
- **Token Budget** — `max_tokens`, `target_tokens`, quality levels (maximum/balanced/economy)
- **Adaptive Compression** — aggressiveness scales with content type and task complexity
- **Quality Preservation** — fail-closed: never replace content unless smaller AND critical info kept
- **Provider Agnostic** — OpenAI, Anthropic, Google adapters via tiktoken
- **Plugin Architecture** — extensible compressors, tokenizers, rankers, caches
- **CLI + REST API** — for harness integration

## Architecture

```
                    TOKEN ENGINE
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
   Tokenizer        Analyzer         Compressor
        │                │                │
        └────────────────┼────────────────┘
                         ▼
                  Optimization Engine
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       Cache          Ranking        Filtering
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                   Optimized Context
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for details.

## Inspiration

Built by analyzing 9 open-source token optimization projects:

| Project | Concepts Adopted |
|---------|-----------------|
| [caveman](https://github.com/JuliusBrussee/caveman) | Type detection, fail-closed compression, BM25 packing, line-number gutter stripping |
| [rtk](https://github.com/rtk-ai/rtk) | Command output filters, truncation caps, error priority |
| [context-mode](https://github.com/mksglu/context-mode) | FTS5/BM25 continuity, sandbox philosophy |
| [claude-token-optimizer](https://github.com/nadimtuhin/claude-token-optimizer) | Startup doc hygiene patterns |
| [token-optimizer](https://github.com/alexgreensh/token-optimizer) | Read-cache/delta, structure maps, char/token heuristic |
| [token-optimizer-mcp](https://github.com/ooples/token-optimizer-mcp) | Knowledge retention concepts (phase 2) |
| [claude-context](https://github.com/zilliztech/claude-context) | AST-aware chunking philosophy |
| [claude-token-efficient](https://github.com/drona23/claude-token-efficient) | Minimal output rules (opt-in only) |
| [token-savior](https://github.com/Mibayy/token-savior) | Structural symbol navigation, PreToolUse bash rewrite |

See [ALGORITHMS.md](ALGORITHMS.md) for technique selection rationale.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — system design
- [ALGORITHMS.md](ALGORITHMS.md) — algorithms and rejected approaches
- [BENCHMARKS.md](BENCHMARKS.md) — benchmark results
- [API.md](API.md) — REST API reference
- [CONFIGURATION.md](CONFIGURATION.md) — config options

## License

MIT
