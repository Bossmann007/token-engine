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
| `token_engine_run_python` | Gated subprocess runner (**not a sandbox**); disabled unless `enable_sandbox_execute=true` |
| `token_engine_compact_tools` | Reduce MCP tool schema bloat (mcp-compressor) |

### MCP stack (default in `.cursor/mcp.json`)

| Server | Role |
|--------|------|
| **token-engine** | Compression, schema compaction, optional gated Python runner |
| **codebase-memory** | Structural code graph queries (CBM) |

Optional: wrap bloated MCPs with `mcp-compressor` — see `.cursor/mcp-compressor.example.json`

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
| Skills | `.cursor/rules/` (always-on) + user/plugin skills |

Cursor **does** support hooks (including third-party `preToolUse` integrations such as [RTK’s Cursor hook](https://github.com/rtk-ai/rtk/tree/master/hooks/cursor)). Token Engine’s default path still uses MCP tools + rules so compression works without installing RTK globally. Optional RTK install/check: `token-engine rtk-check` (see [RTK.md](RTK.md)).

## Live efficiency checklist (verified 2026-09-17)

Run anytime after Cursor reload:

```bash
token-engine rtk-check --json
echo '{"tool_name":"Shell","tool_input":{"command":"git status"}}' | rtk hook cursor
python scripts/marker_test_mcp_hook.py
token-engine optimize benchmarks/fixtures/app_log.txt
```

**Verified on this Mac:**

| Check | Result |
|-------|--------|
| Official RTK | 0.49.0 at `/opt/homebrew/bin/rtk`; `jq` present |
| `preToolUse` Shell | rewrites `git status` → `rtk git status` |
| Python RTK filters | 22 detectors / 22 compressors (`enable_rtk_filters=true`) |
| MCP compress marker | PASS (`1925→72` chars via hook rewrite) |
| Global hooks sync | `~/.cursor/hooks/compress-*.py` matched to repo |
| MCP `caveman_compress` | live smoke OK (log ≈75% on sample) |
| codebase-memory | indexed; use `search_graph` not full Read |
| Main corpus gross | **91.9%** (floors OK; practical plateau under quality invariants) |
| Holdout `adv_*` | ~61.1% (stress, not marketing) |
| Net (`measure_corpus`, minus omit/CCR overhead) | **~90.0%** |
| Keep **OFF** | `enable_jev_router`, `enable_sandbox_execute` |

**Trust:** 90% is reproducible on the main fixture corpus. It is **not** Cursor bill reduction. Real savings = RTK before Shell + CBM instead of fat Reads + compress before reasoning.


## Attribution

- Ponytail behavior adapted from [dietrichgebert/ponytail](https://github.com/dietrichgebert/ponytail) (MIT)
- Caveman output style adapted from [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) (MIT skill)
- Compression engine: Token Engine (this repo)
