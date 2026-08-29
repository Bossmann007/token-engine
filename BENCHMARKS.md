# Benchmarks

Run benchmarks:

```bash
token-engine benchmark
# or
python -m token_engine.benchmark.runner
```

## Methodology

Each fixture includes:
- Original content (simulated agent context)
- `must_contain` / `must_preserve` quality checks
- Token counts via tiktoken (`o200k_base`)

Metrics measured:
- Input tokens (original)
- Output tokens (optimized)
- Tokens saved
- Compression ratio
- Latency (ms)
- Quality check pass rate

## Live Results (2026-08-29)

```
Fixture                     Original  Optimized      Saved    Ratio
------------------------------------------------------------------------
agent_context_session            517        489         28     5.4%
large_json_api_response          625        268        357    57.1%
pytest_failures                  279        157        122    43.7%
app_log                          728         93        635    87.2%
------------------------------------------------------------------------
TOTAL                          2,149      1,007      1,142    53.1%
```

Quality check pass rates:
- pytest_failures: 100% (4/4)
- agent_context: 80% (4/5)
- large_json: 67% (2/3) — array collapse removes individual items but preserves structure

## Expected Results

Based on fixture design (run `token-engine benchmark` for live numbers):

| Fixture | Type | Expected Compression | Quality |
|---------|------|---------------------|---------|
| app_log.txt | Application log | 60-75% | Errors/traces preserved |
| pytest_failures.json | Test output | 70-85% | Failure details preserved |
| large_json.json | API response | 40-60% | Keys and totals preserved |
| agent_context.json | Multi-item context | 30-50% | Task-relevant code/errors kept |

## Quality Benchmark

Quality tests verify compressed content still supports:
- Answering questions about the task
- Locating bugs and errors
- Understanding code structure
- Executing fixes

Run quality tests:

```bash
pytest tests/test_engine.py::TestQualityPreservation -v
```

## Interpreting Results

- **High compression + failed quality checks** → technique marked inadequate
- **Low compression + 100% quality** → acceptable at `quality=maximum`
- **Target**: >40% average compression with >95% quality check pass rate

The goal is not maximum compression percentage — it is maximum savings while maintaining agent reasoning capability.
