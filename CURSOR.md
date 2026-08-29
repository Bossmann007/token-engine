# Cursor Integration — Ponytail + Caveman + Token Engine

This project is configured for **Cursor** with three complementary layers:

| Layer | What | Where |
|-------|------|-------|
| **Ponytail** | Minimal code — YAGNI, stdlib first, shortest diff | `.cursor/rules/ponytail.mdc` |
| **Caveman** | Terse output — ~65% fewer response tokens | `.cursor/rules/caveman.mdc` |
| **Token Engine** | Compress tool outputs — logs, JSON, tests | MCP `token-engine` |

## Quick Start

```bash
pip install -e ".[cursor,dev]"

# Verify setup
token-engine cursor-setup

# Test compression
token-engine optimize benchmarks/fixtures/app_log.txt
```

## Enable MCP in Cursor

1. Open this project in Cursor
2. The file `.cursor/mcp.json` registers the `token-engine` MCP server
3. Go to **Cursor Settings → MCP** and ensure `token-engine` is enabled
4. Reload window if needed

MCP tools available to the agent:

| Tool | Purpose |
|------|---------|
| `caveman_compress` | Compress large tool output before keeping in context |
| `caveman_retrieve` | Recover original bytes from `recovery_handle` |
| `caveman_stats` | Session compression statistics |
| `token_engine_analyze` | Token analysis + recommendations |
| `token_engine_compact_tools` | Reduce MCP tool schema bloat |

## How the behaviors work together

```
User task
    │
    ▼
Ponytail rule ──► write minimum code, reuse existing, stdlib first
    │
    ▼
Agent runs tools (bash, read, grep)
    │
    ▼
Token Engine MCP ──► caveman_compress on large outputs
    │
    ▼
Caveman rule ──► terse responses, no tool narration, no fluff
    │
    ▼
User sees: less code, less prose, fewer tokens
```

## Ponytail intensity

Say in chat:
- `ponytail lite` — suggest lazier alternatives
- `ponytail full` — default, ladder enforced
- `ponytail ultra` — YAGNI extremist
- `stop ponytail` — disable

## Caveman intensity

- `caveman lite` — professional tight
- `caveman full` — default terse
- `caveman ultra` — maximum compression
- `stop caveman` — normal prose

## Migrating from Hermes / Claude Code

| Hermes / Claude | Cursor equivalent |
|-----------------|-------------------|
| bash_compress hook | `caveman_compress` MCP tool |
| CLAUDE.md rules | `.cursor/rules/*.mdc` |
| MCP servers | `.cursor/mcp.json` |
| Skills | `.cursor/rules/` (always-on) |

No hooks in Cursor — the agent calls MCP tools directly when rules instruct it.

## Manual MCP test

```bash
PYTHONPATH=src python3 -m token_engine.mcp.server
# (stdio server — Cursor manages this automatically)
```

## Attribution

- Ponytail behavior adapted from [dietrichgebert/ponytail](https://github.com/dietrichgebert/ponytail) (MIT)
- Caveman output style adapted from [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) (MIT skill)
- Compression engine: Token Engine (this repo)
