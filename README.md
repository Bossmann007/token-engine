# Token Engine

<p align="center">
  <strong>Ultimate LLM Token Optimization Engine</strong><br>
  Fast · accurate · model-agnostic · Cursor-native
</p>

<p align="center">
  <a href="https://github.com/Bossmann007/token-engine">token-engine</a> ·
  <a href="docs/CURSOR-ENV.md">Cursor env</a>
</p>

---

Compress agent context while preserving errors, stack traces, and task-critical code.  
Built for **Cursor** + MCP  

## Cursor Integration

**Ponytail + Caveman + Token Engine + codebase-memory** — see [docs/CURSOR.md](docs/CURSOR.md) and [docs/CURSOR-ENV.md](docs/CURSOR-ENV.md).

```bash
pip install -e ".[cursor,dev]"
token-engine cursor-setup
token-engine benchmark --check-baseline
```

## Install (Windows)

```powershell
git clone https://github.com/Bossmann007/token-engine.git
cd token-engine
.\scripts\install-windows.ps1 -SkipClone
```

## Quick Start

```bash
token-engine optimize benchmarks/fixtures/app_log.txt
token-engine optimize-context benchmarks/fixtures/agent_context.json --task "auth bug"
token-engine benchmark --check-baseline
token-engine serve   # REST on :8741
```

Example benchmark output:

```
╔══════════════════════════════════════════════════════════╗
║                      Token Engine                        ║
║                     Benchmark Report                     ║
╚══════════════════════════════════════════════════════════╝
Fixture                 Original     Saved   Ratio  Bar
────────────────────────────────────────────────────────
app_log                    1,234       890   72.1%  ███████████░░░░░
```

## Features

| Module | What it does |
|--------|----------------|
| **Analyzer** | Token tiers, redundancy, relevance scoring |
| **Optimizer** | BM25 rank + knapsack budget |
| **Compressors** | JSON, logs, code, diffs, pytest/git/npm output |
| **MCP** | `caveman_compress`, session compress, schema compact |
| **Harness** | `POST /optimize-context` before each LLM turn |

Fail-closed: never replaces content unless provably smaller **and** quality checks pass.

## Documentation

| Doc | Topic |
|-----|-------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design |
| [ALGORITHMS.md](docs/ALGORITHMS.md) | Techniques + rejected approaches |
| [API.md](docs/API.md) | REST endpoints |
| [CURSOR-ENV.md](docs/CURSOR-ENV.md) | Ultimate Cursor Environment |
| [BENCHMARKS.md](docs/BENCHMARKS.md) | Baseline gates |

## License

MIT
