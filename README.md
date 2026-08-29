# Token Engine

**Ultimate LLM Token Optimization Engine** — fast, accurate, model-agnostic context compression for AI agents and harnesses.

Token Engine analyzes, ranks, and compresses LLM context while preserving critical information: errors, stack traces, code structure, API contracts, and task-relevant content.

## Cursor Integration

**Ponytail + Caveman + Token Engine** ready for Cursor. See [docs/CURSOR.md](docs/CURSOR.md).

```bash
pip install -e ".[cursor,dev]"
token-engine cursor-setup
```

Rules auto-apply from `.cursor/rules/`. MCP server in `.cursor/mcp.json`.

## Install

### Windows

```powershell
git clone https://github.com/Bossmann007/token-engine.git
cd token-engine
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\install-windows.ps1 -SkipClone
```

### Any OS

```bash
git clone https://github.com/Bossmann007/token-engine.git
cd token-engine
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[cursor,dev]"
token-engine cursor-setup
```

## Quick Start

```bash
pip install -e ".[dev,api]"

# Optimize a file
token-engine optimize benchmarks/fixtures/app_log.txt

# Optimize agent context (JSON)
token-engine optimize-context benchmarks/fixtures/agent_context.json --task "authentication bug"

# Compact MCP tool schemas (70-90% savings on tool bloat)
token-engine compact-tools tools.json

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

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Inspiration

Built by analyzing **15 open-source projects** (+ 7 discovered via search):

| Project | Concepts Adopted |
|---------|-----------------|
| [caveman](https://github.com/JuliusBrussee/caveman) | Type detection, fail-closed compression, BM25 packing |
| [headroom](https://github.com/headroomlabs-ai/headroom) | **SmartCrusher, CCR, cross-turn dedup, tool schema compaction, live-zone** |
| [rtk](https://github.com/rtk-ai/rtk) | Command output filters, truncation caps |
| [context-mode](https://github.com/mksglu/context-mode) | FTS5/BM25 continuity, sandbox philosophy |
| [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) | Structural graph queries (integration pattern) |
| [mcp-compressor](https://github.com/atlassian-labs/mcp-compressor) | MCP tool schema bloat reduction |
| [token-optimizer](https://github.com/alexgreensh/token-optimizer) | Read-cache/delta, structure maps |
| [token-savior](https://github.com/Mibayy/token-savior) | Structural symbol navigation |
| [SuperCompress](https://github.com/Supercompress/Supercompress) | Query-aware block scoring |
| [ponytail](https://github.com/dietrichgebert/ponytail) | Evaluated — behavioral layer, not adopted in engine |

See [docs/ALGORITHMS.md](docs/ALGORITHMS.md) for technique selection rationale.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design
- [docs/ALGORITHMS.md](docs/ALGORITHMS.md) — algorithms and rejected approaches
- [docs/BENCHMARKS.md](docs/BENCHMARKS.md) — benchmark results
- [docs/API.md](docs/API.md) — REST API reference
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — config options
- [docs/CURSOR.md](docs/CURSOR.md) — Cursor + MCP setup

## License

MIT
