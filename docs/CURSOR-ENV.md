# CURSOR-ENV — My Ultimate Cursor Environment

Phases 1–29 implemented. See `~/cursor-kit/` for full docs.

## Stack

| Component | Path |
|-----------|------|
| Global config | `~/.cursor/` |
| Template kit | `~/cursor-kit/` |
| Compression | `token-engine` MCP + API |
| Memory | AGENTS.md + Continual Learning plugin |
| Task state | `.cursor/state/checkpoint.json` |

## Docs map

| Phase | Doc |
|-------|-----|
| Architecture | `~/cursor-kit/docs/ARCHITECTURE.md` |
| Memory | `~/cursor-kit/docs/MEMORY.md` |
| Project brain | `~/cursor-kit/docs/PROJECT-BRAIN.md` |
| Context | `~/cursor-kit/docs/CONTEXT.md` |
| Workflows | `~/cursor-kit/docs/WORKFLOWS.md` |
| Migration | `~/cursor-kit/docs/MIGRATION.md` |
| Token compression | `docs/CURSOR.md`, `docs/API.md` |

## Hooks (global)

sessionStart → token-engine + checkpoint inject  
postToolUse → compress large Shell/Read  
postToolUseFailure → failures.jsonl  
afterFileEdit → format + track files  
stop → merge session → checkpoint  

## New project

```powershell
~\cursor-kit\install.ps1
```

## Tests

```powershell
python -m unittest discover -s "$env:USERPROFILE\cursor-kit\tests"
token-engine benchmark --check-baseline
pytest
```
