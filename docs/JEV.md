# Jev (TypeSafe) tool routing

## Critical Cursor limitation

Cursor injects **all enabled MCP tool schemas** into the model context before the agent runs. Adding a consultative MCP tool such as `token_engine_route_tool` does **not** remove those schemas. Do not count that as end-to-end schema savings.

Real schema reduction requires one of:

1. **Harness ownership** — your code builds the prompt and only inserts a shortlist / lazy schema (Token Engine `lazy_tool_catalog` + `route_tool`).
2. **MCP gateway** — a meta-server exposes `search_tools` / `get_tool_schema` / `call_tool` and keeps downstream tools out of Cursor. Not shipped as a production gateway in this change; foundations only via Python `ToolRouter` + existing lazy catalog.

`token_engine_compact_tools` helps when **you** feed compacted schemas into a prompt you control. Inside stock Cursor MCP, schemas are already present.

## What was implemented

Opt-in Python router (`token_engine.jev`):

1. Redact / minimize intent (no secrets in config; `TYPESAFE_API_KEY` from env only).
2. BM25 shortlist (reuses `BM25Ranker`).
3. Optional Jev `Choice` over the shortlist only (not full catalog).
4. Confidence gates by risk tier; **destructive never auto-executes**.
5. Selection is separated from execution (`allow_execute` is advisory; no shell dispatch).
6. Fail-closed: disabled by default; skips Jev when catalog small or expected savings below threshold; circuit breaker + BM25 fallback.

```bash
pip install -e ".[jev]"   # optional SDK; HTTP client works without it
export TYPESAFE_API_KEY=...  # never commit

token-engine route-tool tools.json --intent "search auth middleware"
token-engine route-tool tools.json --intent "..." --enable-jev --json
```

Config flags (all default safe / off for network): see `enable_jev_router` and `jev_*` in `EngineConfig` / `config/token-engine.defaults.json`.

## Privacy

TypeSafe states they do not train on user data; zero retention is an enterprise feature. Token Engine still minimizes payloads regardless.

## Rollback

Set `enable_jev_router: false` (default). Remove `[jev]` extra. No default behavior change when disabled.
