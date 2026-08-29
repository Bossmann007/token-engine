# PROJECT.md — token-engine

## Stack

- Python 3.14, FastAPI/uvicorn (API), MCP server
- tiktoken for counting, pure-Python compressors

## Commands

```bash
pip install -e ".[cursor,dev]"
token-engine serve          # REST :8741
token-engine benchmark --check-baseline
pytest
```

## Architecture

Modular compression library: analyzer → optimizer (knapsack + BM25) → content-type compressors. MCP exposes caveman_* tools. HarnessClient for pre-LLM context optimization.

## MCP (this repo)

Project `.cursor/mcp.json` mirrors global — token-engine + codebase-memory.

## Conventions

- Fail-closed compression (never expand output)
- ponytail + cbm-first rules
- Benchmark gate before claiming compression improvements

## Decisions

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-08 | Cursor-only env | Drop Hermes/Claude dev dependency |
| 2026-08 | Global token-engine MCP | All projects benefit from compression |

## Current work

See `.cursor/state/checkpoint.json`.
