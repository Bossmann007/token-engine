# RTK integration

## What Token Engine does today

Token Engine ships **Python reimplementations** of a subset of [RTK](https://github.com/rtk-ai/rtk) bash/tool output filters (`src/token_engine/compressor/rtk_filters.py`).

- Controlled by `enable_rtk_filters` (default **true**).
- `ContextOptimizer` passes the flag into `ToolOutputCompressor(enable_rtk=...)`.
- This is **not** a subprocess call to the official `rtk` binary.
- Detector count is on the order of ~20 tools (far fewer than RTK’s 100+ commands).

Official RTK savings claims apply to **shell/tool stdout**, measured roughly as `bytes/4`. That is not the same as total LLM bill reduction.

## Hybrid strategy (recommended)

| Layer | Role |
|-------|------|
| Token Engine Python filters | Always-on fallback; no install; used by MCP/`caveman_compress` |
| Official RTK binary (optional) | Best coverage for shell wrappers when you install it yourself |
| RTK Cursor `preToolUse` hook (optional) | Rewrites shell commands before execution — **user installs**; Token Engine never writes `~/.cursor` |
| Token Engine `postToolUse` MCP prototype | `hooks/compress-mcp-output.py` — fail-open; only useful if Cursor accepts `updated_mcp_tool_output` for MCP tools |

**Shell/Read advisory compress** (ask the model to call `caveman_compress` after the fact) is usually a **net loss**: raw output is already in context, and echoing it into another tool costs output tokens. Prefer RTK for Shell and the MCP rewrite hook for MCP outputs.

Local marker harness (proves hook rewrite, not live Cursor application):

```bash
python scripts/marker_test_mcp_hook.py
```

Check local status:

```bash
token-engine rtk-check
```

Install RTK separately (examples):

```bash
brew install rtk
# or
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
```

Cursor hook docs: https://github.com/rtk-ai/rtk/tree/master/hooks/cursor (requires `rtk >= 0.23.0` and `jq`).

## Verified on this machine (2026-09-17)

- Homebrew `rtk` **0.49.0** at `/opt/homebrew/bin/rtk` (≥ 0.23.0 required for Cursor hook).
- `~/.cursor/hooks.json` already has `preToolUse` → `rtk hook cursor` (matcher `Shell`).
- Local probe: `git status` rewrites to `rtk git …` with `permission` + `updated_input`.
- Marker harness: `python scripts/marker_test_mcp_hook.py` → PASS.
- Do **not** run bare `rtk init -g` here if you want Cursor-only — that dry-run also targets `~/.claude`. Prefer `rtk init -g --agent cursor --hook-only` when reinstalling.
- **Note:** if `~/.cursor/hooks/compress-*.py` drifts from the repo copy, re-sync manually (agent may ask approval to write `~/.cursor`).

Uninstall Cursor RTK hook only:

```bash
rtk init -g --agent cursor --uninstall
```


Cursor **does** support hooks. Token Engine’s default path still uses MCP tools + rules because that works without a global RTK install. Prefer RTK’s official Cursor hook when you want command-level rewriting; keep Token Engine for content-type compression, sessions, schemas, and CCR.
