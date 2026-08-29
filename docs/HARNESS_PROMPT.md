# Harness Prompt — Token Engine + Hermes + Claude

Use this prompt in a **new agent session** (Cursor/Claude/Hermes) to build the personal harness.
Copy everything inside the fenced block below.

---

```
You are building Enzo Bossmann's personal AI harness on Windows 11.

## Goal

Wire **token-engine** (deterministic compression) into **Hermes** (multi-channel agent) and **Claude Code** (dev loop), replacing ad-hoc compression with a single stack:

- **Input compression:** token-engine `POST /optimize-context` + MCP `caveman_compress` / `token_engine_compress_session`
- **Shell output:** rtk hook (already in `~/.claude/settings.json` PreToolUse:Bash)
- **Code exploration:** codebase-memory MCP (graph first, never Read full files)
- **Output style:** ponytail + caveman rules (behavioral, not engine)
- **Orchestrator:** Hermes `context_engine` plugin slot

Target: before every LLM call, context tokens drop 40–60% with quality ≥95% on benchmark fixtures.

## Repos & paths (verified on this machine)

| Component | Path |
|-----------|------|
| token-engine (library + API + MCP) | `C:\Users\enzo.bossmann\token-engine` |
| Hermes install + config | `C:\Users\enzo.bossmann\AppData\Local\hermes` |
| Hermes agent source | `C:\Users\enzo.bossmann\AppData\Local\hermes\hermes-agent` |
| Claude settings + hooks | `C:\Users\enzo.bossmann\.claude\settings.json` |
| Obsidian vault / harness docs | `C:\Users\enzo.bossmann\OneDrive\Mafioso` |
| Token optimization corpus | `Mafioso/60 - Ferramentas e Prompts/References/Token Optimization.md` |
| Harness primer / smoke tasks | `Mafioso/00 - Home/Primer.md`, `Mafioso/ops/TASKS.md` |

## Existing infrastructure (do NOT reinvent)

### token-engine (Python, shipped)

- CLI: `token-engine serve` → REST on `http://127.0.0.1:8741`
- Endpoints: `GET /health`, `POST /optimize`, `POST /optimize-context`
- Python client: `from token_engine.harness import HarnessClient`
- MCP tools: `caveman_compress`, `token_engine_compress_session`, `token_engine_compact_tools`, `caveman_stats`
- Cursor hooks (project): `.cursor/hooks.json` — sessionStart reminder + postToolUse compress
- Config defaults: `config/token-engine.defaults.json`
- Benchmark gate: `token-engine benchmark --check-baseline` (60%+ total, session 40%+, quality 100%)

### Hermes (config.yaml)

```yaml
compression:
  enabled: true
  threshold: 0.5          # fire when context ~50% of window
  target_ratio: 0.2       # aim to leave ~20% headroom
  protect_last_n: 20
  protect_first_n: 3
  proactive_prune_min_result_chars: 8000
```

- Context engine plugin API: `hermes-agent/agent/context_engine.py`
- Compression orchestration: `hermes-agent/agent/conversation_compression.py`
- Plugin dir pattern: `plugins/context_engine/<name>/`
- Built-in toolset includes `context_engine` (cli platform)
- Model default: `nemotron-3.5-lightning-free` via opencode-free

### Claude Code

- `~/.claude/settings.json`: rtk `PreToolUse:Bash` hook already active
- ponytail plugin enabled
- caveman referenced in Mafioso skill map but not always enabled in Claude

### Mafioso vault lessons (must respect)

1. **Mount check before vault writes** — `findmnt` must show `fuse.rclone` on OneDrive; absent mount ≠ empty vault (see Primer.md 2026-07-31)
2. **4 compression layers stack, same layer competes** (Token Optimization.md): rtk (shell) + token-engine (input) + caveman (output) + ponytail (codegen)
3. **Harness smoke** was 13/13 on Linux; Windows needs equivalent `harness-smoke.ps1`
4. **MedOS harness** is a separate vertical (LGPD) — out of scope unless explicitly requested

## Architecture to implement

```
┌─────────────────────────────────────────────────────────────┐
│ Hermes AIAgent / conversation_loop                          │
│   before each provider call:                                │
│     1. map messages[] → ContentItem[]                     │
│     2. task_query = last user message (300 chars)           │
│     3. HarnessClient.optimize_messages(...)               │
│     4. replace history with optimized content             │
│   on tool result > 1500 chars:                              │
│     caveman_compress (in-process or HTTP)                   │
└─────────────────────────────────────────────────────────────┘
         │ HTTP fallback              │ in-process
         ▼                            ▼
   token-engine serve :8741      TokenEngine.optimize_context()
```

### Deliverables (in order)

**D1 — Windows service wrapper**
- `scripts/start-token-engine.ps1`: venv activate, `token-engine serve`, health poll
- Optional: Task Scheduler entry @ logon

**D2 — Hermes context engine plugin `token_engine`**
- Location: `%LOCALAPPDATA%\hermes\plugins\context_engine\token_engine\` OR fork patch in `hermes-agent`
- Implement `ContextEngine` subclass:
  - `should_compress()`: delegate to Hermes threshold OR token count from `HarnessClient`
  - `compress()`: call `HarnessClient.optimize_messages(history, task_query=...)`, return compressed messages
  - `emit_automatic_compaction_status = True`
- Register in `config.yaml`: `context.engine: token_engine` (or hybrid: try token-engine first, fallback built-in summarizer)

**D3 — Message mapping spec**

Map Hermes/OpenAI-style messages to token-engine items:

| Hermes role | ContentItem |
|-------------|-------------|
| system | `content_type=message`, `source=system`, `metadata.content_role=instruction` |
| user | `source=user` |
| assistant | `source=assistant` |
| tool / tool_result | `content_type=tool_output`, preserve `tool_call_id` in metadata |
| file read injection | `content_type=code`, `source=<path>` |

Always pass `task_query` = latest user turn text.

**D4 — Tool output path**
- Hook Hermes post-tool callback (mirror `.cursor/hooks/compress-tool-output.py`)
- If result chars > 1500: compress with `engine.optimize(text, content_type="tool_output")`
- Store CCR handle in metadata for `caveman_retrieve`

**D5 — Smoke test `harness-smoke.ps1`**
Checks:
1. `curl http://127.0.0.1:8741/health` → ok
2. `token-engine benchmark --check-baseline` → pass
3. One `optimize-context` round-trip with fixture `benchmarks/fixtures/large_agent_session.json`
4. OneDrive mount present if vault path used (Windows: `Get-Process rclone` + junction check)
5. Hermes `compression.enabled` still true after plugin install

**D6 — Metrics dashboard (minimal)**
- Extend `caveman_stats` consumption in a `harness-status.ps1` printing: session ratio, resist_compression sources, benchmark total vs reference 82%

## Constraints

- **No LLM summarization** for compression (deterministic only — token-engine philosophy)
- **live_zone_mode=true**: never drop messages; stub instead (knapsack)
- **fail_closed=true**: if compression doesn't save ≥3%, keep original
- **Quality gates**: run benchmark before declaring done; do not lower `must_contain` checks to pass
- **Secrets**: never commit `.env`, `auth.json`, whatsapp session creds from hermes
- **Windows paths** in scripts; PowerShell 7+ compatible

## Reference code (token-engine)

Harness client usage:

```python
from token_engine.harness import HarnessClient

client = HarnessClient()  # tries :8741, falls back in-process
out = client.optimize_messages(
    messages=[{"role": "user", "content": "fix users.py delete_user bug"}, ...],
    task_query="fix users.py delete_user bug",
    quality="balanced",
)
optimized_text = out["content"]
stats = out.get("stats", {})
```

Hermes integration point (read first):
- `hermes-agent/agent/context_engine.py` — plugin ABC
- `hermes-agent/agent/conversation_compression.py` — `compress_context()` flow
- Search `context.engine` in hermes codebase for registration

## Success criteria

| Metric | Floor | Stretch (reference) |
|--------|-------|---------------------|
| Benchmark total | ≥58% | 82% (needs CBM upstream + large sessions) |
| Benchmark session | ≥40% | 80% |
| Quality checks | 100% | 100% |
| Hermes turn latency overhead | <200ms | <80ms |
| Smoke script | 5/5 green | CI on push |

## Work plan

1. Read Hermes `context_engine.py` + `conversation_compression.py` (first 200 lines each)
2. Scaffold plugin with in-process `HarnessClient(prefer_api=True)`
3. Wire `compress()` path; test with one manual Hermes session
4. Add smoke script + document in `Mafioso/00 - Home/Primer.md` harness row
5. Run `token-engine benchmark --check-baseline` after any engine change

Start with D1+D2. Show me the plugin file tree before editing Hermes core.
```

---

## Quick start (after harness exists)

```powershell
cd C:\Users\enzo.bossmann\token-engine
.\.venv\Scripts\token-engine.exe serve
# separate terminal:
.\scripts\harness-smoke.ps1
```
