# Security notes

## Python subprocess runner (`token_engine_run_python`)

**Not a sandbox.** Default: `enable_sandbox_execute=false`.

When enabled it runs `python -I -c` with a scrubbed environment, timeout, output/code size caps, and best-effort POSIX resource limits. It does **not** isolate filesystem or network. Treat enabling it as accepting host process risk.

MCP tools:
- `token_engine_run_python` — gated; rejects when `enable_sandbox_execute=false`

## Jev (TypeSafe)

Opt-in (`enable_jev_router=false`). Sends only minimized, redacted intent + shortlist metadata. Local risk policy always wins over model confidence. Destructive tools never get `allow_execute=True`.

## Architecture A vs B (schema tokens)

| Mode | Schema savings |
|------|----------------|
| **A Advisory** (Cursor MCP already injected schemas) | Estimated shortlist savings are **not** realized retroactively (`schema_reduction_realized=0`) |
| **B MCP gateway** | Would keep full catalog off the main context — **not shipped**; design only until Cursor contract is proven |

## RTK

Python filters in-repo are RTK-**inspired**. Official `rtk` binary is optional (user install + Cursor `preToolUse`). Token Engine does not auto-install it.
