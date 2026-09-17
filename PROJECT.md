# PROJECT.md — token-engine

## Stack

- Python 3.12+ (venv), FastAPI/uvicorn (API), MCP server
- tiktoken for counting, pure-Python compressors
- Pairs with [cursor-kit](https://github.com/Bossmann007/cursor-kit) for Cursor env / `/setup-project`

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
| 2026-09-17 | GitHub Issues as agent issue tracker | Matt Pocock skills use `gh`; repo is Bossmann007/token-engine |
| 2026-09-17 | Jev router opt-in only; no advisory MCP route tool | Cursor already injects MCP schemas; Jev helps harness/shortlist paths, not decorative MCP |
| 2026-09-17 | Keep Python RTK filters + optional official binary | No hard `rtk` dependency; honor enable flag; document Cursor hooks |
| 2026-09-17 | `enable_sandbox_execute` default false; not a real jail | Subprocess runner only; MCP rejects when disabled |
| 2026-09-17 | 82% is milestone not ceiling; maximize net economia_liquida | User objective; quality/safety constraints dominate raw % |
| 2026-09-17 | SessionSemanticCompactor default on; fail-closed vs legacy join | Top remaining tokens were session filler + header overhead |
| 2026-09-17 | Practical corpus ceiling ~91.9% gross / ~90.0% net under quality floors | Further densify cuts required strings; net subtracts omit/CCR overhead; live savings = RTK+CBM+compress not fixture %; Jev OFF on Cursor |


## Current work

See `.cursor/state/checkpoint.json`.
