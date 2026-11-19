# Benchmarks

## Live Results (2026-09-17 — balanced, main corpus)

Main fixtures only (`adv_*` holdout excluded from tuning and from this TOTAL).

```
Fixture                         Original  Optimized  Ratio
------------------------------------------------------------
agent_context_session                517         46  91.1%
app_log                              728         28  96.2%
cargo_build                          246         23  90.7%
cross_turn_reread                    160         29  81.9%
docker_build                         203         17  91.6%
git_status                           136         25  81.6%
hybrid_knapsack_session              635         46  92.8%
jest_failures                        101         22  78.2%
large_agent_session                  403         40  90.1%
large_json_api_response              625         26  95.8%
metrics_timeseries                   950         27  97.2%
npm_install                          228         23  89.9%
pnpm_install                         103         12  88.3%
pytest_failures                      279         18  93.5%
read_delta_session                   190         33  82.6%
session_reread_chain                 273         40  85.3%
session_unrelated_reads              201         41  79.6%
vite_build                           315         14  95.6%
------------------------------------------------------------
TOTAL                               6293        510  91.9%
```

- Gross (main): **91.9%**
- Net (main, subtracts omit/CCR overhead): **91.4%** (6,293 → 510 tok, overhead 32 tok)
- Holdout `adv_*` (3 fixtures, 283 → 110 tok): gross **61.1%**, net **59.7%** (stress only; not used to tune)
- Earlier docs quoted ~90.0% net: that was main + `adv_*` combined (21 fixtures), not main alone.

Floors in `benchmarks/baseline.json`: current ratio minus 5 pp, rounded down (total floor 86%). Fixtures in the `holdout` list of `corpus_split.json` keep their older floors so holdout peaks never raise CI floors.

**Trust note:** fixture % ≠ Cursor bill. Real live savings = RTK-before-Shell + compress hooks/MCP + codebase-memory instead of fat Reads. Keep Jev/sandbox OFF on Cursor.

Reproduce:

```bash
token-engine benchmark --check-baseline --net
pytest tests/test_benchmark_baseline.py tests/test_net_metrics.py
```

## Historical (v0.2 — 2026-08-29)

Early expanded suite ~47.7% total before session-semantic + denser RTK/log/JSON paths. Kept for trend only.
