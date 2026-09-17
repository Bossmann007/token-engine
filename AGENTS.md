# AGENTS.md

## Learned User Preferences

- Cursor-only dev environment — Hermes and Claude Code are reference only, not runtime
- macOS primary (darwin); Windows install script still available
- Prefer minimal tokens: caveman_stats on demand, no always-on observability dashboards
- Autonomous after architecture OK — do not re-confirm every step; still ask before commit/push, `~/.cursor` edits, credentials, or paid APIs
- ponytail + caveman rules apply globally to all projects
- Critically evaluate large prompts: implement only what is viable, safe, measurable, and non-decorative; prefer a better design when the ask conflicts with reality
- Prefer honest token accounting (estimate vs realized); do not claim Cursor MCP schema savings when schemas were already injected
- Portuguese OK in chat; keep code, paths, and file contents in English unless the project is PT-first

## Learned Workspace Facts

- token-engine lives at `~/token-engine` → `~/.cursor/repos/token-engine` ([GitHub](https://github.com/Bossmann007/token-engine))
- Global MCP: context7, token-engine, codebase-memory, notion (OAuth)
- cursor-kit at `~/cursor-kit` → `~/.cursor/repos/cursor-kit` ([GitHub](https://github.com/Bossmann007/cursor-kit))
- Skills: mattpocock/skills + find-skills in `~/.cursor/skills/`; book rules in `~/.cursor/rules/books/`
- Pair with `/setup-project` from cursor-kit for per-repo bootstrap
- Issue tracker: GitHub Issues via `gh`; domain layout single-context (`docs/agents/`)
- Official RTK is optional (Homebrew/`rtk`); Cursor Shell uses `preToolUse` → `rtk hook cursor`; in-repo `rtk_filters` are a Python subset, not the binary
- Jev/TypeSafe router is opt-in (`enable_jev_router` default false); Python subprocess runner is gated (`enable_sandbox_execute` default false) and is not a real sandbox
- Integration honesty docs: `docs/RTK.md`, `docs/JEV.md`, `docs/SECURITY.md`

## Agent skills

### Issue tracker

GitHub Issues via `gh` CLI ([Bossmann007/token-engine](https://github.com/Bossmann007/token-engine)). See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: root `CONTEXT.md` + `docs/adr/` (created lazily by domain-modeling). See `docs/agents/domain.md`.
