<!-- ENZO-PORTFOLIO-BRAND -->
<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:111111,100:7751FF&height=165&section=header&text=Token%20Engine&fontSize=42&fontColor=ffffff&animation=fadeIn&fontAlignY=35&desc=Context%20optimization%20for%20AI%20agents%20with%20fail-closed%20checks.&descAlignY=57&descSize=14" alt="Token Engine" />
</p>

<p align="center"><strong>Python · MCP · LLMs</strong></p>

---

# Token Engine

<p align="center">
  <strong>Ultimate LLM Token Optimization Engine</strong><br>
  Fast · accurate · model-agnostic · Cursor-native
</p>

<p align="center">
  <a href="https://github.com/Bossmann007/token-engine">token-engine</a> ·
  <a href="https://github.com/Bossmann007/cursor-kit">cursor-kit</a> ·
  <a href="docs/CURSOR-ENV.md">Cursor env</a>
</p>

---

Compress agent context while preserving errors, stack traces, and task-critical code.  
Built for **Cursor** + MCP. Live path: official RTK on Shell + compress hooks/MCP + codebase-memory. Keep Jev/sandbox **off** in Cursor (see [JEV.md](docs/JEV.md)).

## Cursor Integration

**Ponytail + Caveman + Token Engine + codebase-memory** — see [docs/CURSOR.md](docs/CURSOR.md) and [docs/CURSOR-ENV.md](docs/CURSOR-ENV.md).

Per-repo bootstrap of the full stack: [`/setup-project`](https://github.com/Bossmann007/cursor-kit) in cursor-kit.

```bash
pip install -e ".[cursor,dev]"
token-engine cursor-setup
token-engine benchmark --check-baseline
```

## Install

### macOS / Linux

```bash
git clone https://github.com/Bossmann007/token-engine.git
cd token-engine
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[cursor,dev]"
```

Optional symlink used by this machine’s Cursor env:

```bash
ln -sfn "$PWD" ~/token-engine
```

### Windows

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

Main-corpus benchmark (balanced, 2026-09-17) — see [BENCHMARKS.md](docs/BENCHMARKS.md):

```
Fixture                 Original  Optimized   Ratio
────────────────────────────────────────────────────
TOTAL                      6,293        510   91.9%
Net (minus omit/CCR overhead)                 ~90.0%
Holdout adv_* (stress only)                   ~61.1%
```

Fixture % ≠ Cursor bill. Real savings = RTK-before-Shell + compress before reasoning + CBM instead of fat Reads.

## Features

| Module | What it does |
|--------|----------------|
| **Analyzer** | Token tiers, redundancy, relevance scoring |
| **Optimizer** | BM25 rank + hybrid knapsack (live-zone) |
| **Compressors** | Session semantic (T/E/C/O), JSON, logs, code, diffs, pytest/git/npm/RTK |
| **MCP** | `caveman_compress`, session compress, schema compact |
| **Harness** | `POST /optimize-context` before each LLM turn |
| **Jev** | Opt-in tool shortlist for harnesses only — off in Cursor |

Fail-closed: never replaces content unless provably smaller **and** quality checks pass.

## Documentation

| Doc | Topic |
|-----|-------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design |
| [ALGORITHMS.md](docs/ALGORITHMS.md) | Techniques + rejected approaches |
| [API.md](docs/API.md) | REST endpoints |
| [CURSOR.md](docs/CURSOR.md) | Cursor MCP + live efficiency checklist |
| [CURSOR-ENV.md](docs/CURSOR-ENV.md) | Ultimate Cursor Environment |
| [BENCHMARKS.md](docs/BENCHMARKS.md) | Live numbers + baseline gates |
| [RTK.md](docs/RTK.md) | Python RTK filters + optional official binary |
| [JEV.md](docs/JEV.md) | Opt-in TypeSafe Jev tool routing (harness) |
| [SECURITY.md](docs/SECURITY.md) | Executor limits, Jev privacy, architecture honesty |
| [cursor-kit](https://github.com/Bossmann007/cursor-kit) | Templates, hooks, `/setup-project` |

## License

MIT

<!-- ENZO-PORTFOLIO-BRAND-FOOTER -->
<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:111111,100:7751FF&height=85&section=footer" alt="Footer" />
</p>
