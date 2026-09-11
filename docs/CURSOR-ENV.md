# CURSOR-ENV — My Ultimate Cursor Environment

Phases 1–29 implemented. Full docs: [cursor-kit](https://github.com/Bossmann007/cursor-kit) (`~/cursor-kit`).

## Stack

| Component | Path |
|-----------|------|
| Global config | `~/.cursor/` |
| Template kit | `~/cursor-kit/` ([repo](https://github.com/Bossmann007/cursor-kit)) |
| Compression | this repo — token-engine MCP + API |
| Memory | AGENTS.md + Continual Learning plugin |
| Task state | `.cursor/state/checkpoint.json` |
| Orchestrator | `/setup-project` skill in cursor-kit |

## Docs map

| Topic | Doc |
|-------|-----|
| **Onboarding (start here)** | [cursor-kit playbook](https://github.com/Bossmann007/cursor-kit/blob/master/docs/02-playbook-onboarding.md) |
| Overview / pillars | [cursor-kit/docs/00-overview.md](https://github.com/Bossmann007/cursor-kit/blob/master/docs/00-overview.md) |
| Architecture | [cursor-kit/docs/ARCHITECTURE.md](https://github.com/Bossmann007/cursor-kit/blob/master/docs/ARCHITECTURE.md) |
| Memory | [cursor-kit/docs/MEMORY.md](https://github.com/Bossmann007/cursor-kit/blob/master/docs/MEMORY.md) |
| Project brain | [cursor-kit/docs/PROJECT-BRAIN.md](https://github.com/Bossmann007/cursor-kit/blob/master/docs/PROJECT-BRAIN.md) |
| Context | [cursor-kit/docs/CONTEXT.md](https://github.com/Bossmann007/cursor-kit/blob/master/docs/CONTEXT.md) |
| Workflows | [cursor-kit/docs/WORKFLOWS.md](https://github.com/Bossmann007/cursor-kit/blob/master/docs/WORKFLOWS.md) |
| Migration | [cursor-kit/docs/MIGRATION.md](https://github.com/Bossmann007/cursor-kit/blob/master/docs/MIGRATION.md) |
| Token compression | [CURSOR.md](CURSOR.md), [API.md](API.md) |

## Hooks (global)

Prefer kit sync into `~/.cursor/hooks` (not machine-specific paths in this repo):

sessionStart → token-engine + checkpoint inject  
postToolUse → compress large Shell/Read  
postToolUseFailure → failures.jsonl  
afterFileEdit → format + track files  
stop → merge session → checkpoint  

```bash
~/cursor-kit/sync-hooks.sh    # macOS / Linux
# Windows: ~\cursor-kit\sync-hooks.ps1
```

## New project

```bash
# Preferred
# In Cursor: /setup-project

# Manual
~/cursor-kit/install.sh                 # macOS / Linux
# Windows: ~\cursor-kit\install.ps1
```

## Tests

```bash
python -m unittest discover -s ~/cursor-kit/tests
token-engine benchmark --check-baseline
pytest
```
