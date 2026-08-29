# My Ultimate Cursor Environment

Cursor-only dev stack. Hermes and Claude Code are **not** runtime dependencies.

## Layers

| Layer | Where |
|-------|--------|
| Global rules | `~/.cursor/rules/` — ponytail, caveman, token-engine, cbm-first, session-continuity, core |
| Global MCP | `~/.cursor/mcp.json` — context7, token-engine, codebase-memory, notion |
| Global hooks | `~/.cursor/hooks.json` — session reminder, compress large outputs, black/ruff |
| This repo | token-engine MCP + rules + benchmark |
| Template kit | `~/cursor-kit` — bootstrap new projects |

## Before each session

1. Reload Cursor window if MCP changed
2. Optional: `token-engine serve` for REST harness on `:8741`
3. Agent reads `.cursor/state/checkpoint.json` on **continue** / **retomar**

## Compression workflow

```
tool output >1.5k chars  →  caveman_compress (MCP)
multi-item context       →  token_engine_compress_session
code exploration         →  codebase-memory search_graph (not full Read)
```

Hooks auto-remind on sessionStart; postToolUse adds compression notice for large Shell/Read.

## Memory (not token-engine)

| File | Role |
|------|------|
| `AGENTS.md` | Durable prefs — Continual Learning plugin |
| `PROJECT.md` | Stack, commands, decisions |
| `.cursor/state/checkpoint.json` | Current task — resume |
| `.cursor/state/failures.jsonl` | Lessons from failed approaches |

Never store secrets in memory files.

## New project bootstrap

```powershell
Copy-Item "$env:USERPROFILE\cursor-kit\AGENTS.md.template" .\AGENTS.md
Copy-Item "$env:USERPROFILE\cursor-kit\PROJECT.md.template" .\PROJECT.md
New-Item -ItemType Directory -Force .cursor\state
Copy-Item "$env:USERPROFILE\cursor-kit\state\checkpoint.json.example" .cursor\state\checkpoint.json
```

See `~/cursor-kit/README.md`.

## Iterative loops

- **Default:** superpowers plugin (plans, TDD, debug)
- **Optional:** ralph-loop for long autonomous runs
- **Skip:** OMH/Hermes pipeline (redundant)

## Observability

`caveman_stats` on demand only — minimal token cost.

## Benchmark

```bash
token-engine benchmark --check-baseline
```

Target: quality 100%; compression ratio improves over time.
