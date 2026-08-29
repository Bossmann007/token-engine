## Live Results (v0.2 — 2026-08-29)

After adding headroom techniques (SmartCrusher, cross-turn dedup, CCR, tool schema compaction):

```
Fixture                     Original  Optimized      Saved    Ratio
------------------------------------------------------------------------
agent_context_session            427        401         26     6.1%
cross_turn_reread                106         95         11    10.4%
large_json_api_response          625        414        211    33.8%
metrics_timeseries               950        433        517    54.4%
pytest_failures                  279        157        122    43.7%
app_log                          728         93        635    87.2%
------------------------------------------------------------------------
TOTAL                          3,115      1,628      1,487    47.7%
```

Quality check pass rates:
- pytest_failures: 100% (4/4)
- metrics_timeseries: 100% (3/3) — outliers and errors preserved
- cross_turn_reread: 100% (3/3) — duplicate file reads folded
- agent_context: 80% (4/5)

## v0.1 Results (baseline)

```
TOTAL                          2,149      1,007      1,142    53.1%
```

v0.2 adds more fixtures and cross-turn dedup; net compression on expanded suite is 48.9% with higher quality preservation on JSON arrays.
