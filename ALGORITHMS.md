# Algorithms — Full Repository Audit (15 repos + 7 discovered)

## Repositories Analyzed

### Original 9
| Repo | Primary Contribution |
|------|---------------------|
| [caveman](https://github.com/JuliusBrussee/caveman) | Type-detect compression, CCR, BM25 packing, fail-closed |
| [rtk](https://github.com/rtk-ai/rtk) | 100+ bash output filters, truncation caps |
| [context-mode](https://github.com/mksglu/context-mode) | Sandbox execute, FTS5 continuity |
| [claude-token-optimizer](https://github.com/nadimtuhin/claude-token-optimizer) | Startup doc hygiene |
| [token-optimizer](https://github.com/alexgreensh/token-optimizer) | Multi-surface hooks, read-cache, structure maps |
| [token-optimizer-mcp](https://github.com/ooples/token-optimizer-mcp) | Hard deny + knowledge graph |
| [claude-context](https://github.com/zilliztech/claude-context) | Semantic vector codebase search |
| [claude-token-efficient](https://github.com/drona23/claude-token-efficient) | Output brevity rules |
| [token-savior](https://github.com/Mibayy/token-savior) | Structural symbol navigation MCP |

### Additional 3 (user-provided)
| Repo | Primary Contribution | Adopted in v0.2 |
|------|---------------------|-----------------|
| [headroom](https://github.com/headroomlabs-ai/headroom) | SmartCrusher, CCR, cross-turn dedup, tool schema compaction, live-zone | **Yes — core** |
| [ponytail](https://github.com/dietrichgebert/ponytail) | Behavioral YAGNI steering (output-side) | **No** — agent skill layer |
| [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) | Structural graph queries, compact tree output | **Partial** — integration pattern |

### Discovered via search (7 additional)
| Repo | Technique | Adopted |
|------|-----------|---------|
| [kompact](https://github.com/npow/kompact) | TF-IDF proxy pipeline, TOON encoding | Patterns only |
| [SuperCompress](https://github.com/Supercompress/Supercompress) | Query-aware block scoring | Query param in SmartCrusher |
| [TokenDamper](https://github.com/Epichlo/TokenDamper) | Knapsack planning, Myers diff | Phase 2 |
| [slimctx](https://github.com/omkar9854/token_optimizer) | Log template mining, reversible transforms | Phase 2 |
| [mcp-compressor](https://github.com/atlassian-labs/mcp-compressor) | On-demand tool schema lookup | Inspiration for compaction |
| [mcp-sophon](https://github.com/lacausecrypto/mcp-sophon) | Deterministic Rust compressors | Reference architecture |
| [context-compress](https://github.com/Open330/context-compress) | Index-backed search + wrap CLI | Complementary upstream |

## Updated Comparison Matrix (15 repos)

| Technique | Best Source | Quality | Economy | Latency | Adopted v0.2 |
|-----------|------------|---------|---------|---------|--------------|
| Statistical JSON crushing | headroom SmartCrusher | 9 | 9 | 8 | **Yes** |
| CCR reversible compression | headroom / caveman | 10 | 9 | 9 | **Yes** |
| Cross-turn verbatim dedup | headroom | 10 | 8 | 10 | **Yes** |
| Tool schema compaction | headroom / mcp-compressor | 9 | 9 | 10 | **Yes** |
| Live-zone-only (no drop) | headroom | 10 | 7 | 10 | **Yes** (config) |
| Query-aware compression | SuperCompress / headroom | 9 | 9 | 8 | **Yes** |
| Structural code graph | codebase-memory-mcp | 9 | 10 | 9 | Phase 2 (MCP bridge) |
| Compact tree output | codebase-memory-mcp | 8 | 8 | 10 | Pattern adopted |
| Behavioral output reduction | ponytail | 7 | 6 | 10 | **No** (skill layer) |
| Knapsack token budgeting | TokenDamper | 8 | 8 | 7 | Phase 2 |
| Log template mining | slimctx | 8 | 9 | 9 | Phase 2 |
| MCP on-demand schemas | mcp-compressor | 8 | 9 | 8 | Partial (compaction) |
| Proxy intercept | kompact / headroom | 8 | 9 | 7 | **No** (library only) |
| ML compression (Kompress) | headroom | 7 | 8 | 4 | **No** (defer) |
| Embedding RAG | claude-context | 8 | 7 | 5 | Phase 2 optional |

## New in v0.2

### SmartCrusher (`compressor/smart_crusher.py`)
- Statistical row selection for JSON arrays
- Preserves: errors, outliers (z-score > 2), first/last rows, query-relevant rows
- Constant field factoring (hoist shared values)
- Inspired by headroom `smart_crusher.py` (Rust); Python implementation

### CCR Store (`ccr/store.py`)
- Reversible compression with `<<ccr:handle>>` markers
- Retrieve API for harness integration
- Inspired by headroom + caveman CCR

### Cross-Turn Dedup (`compressor/cross_turn_dedup.py`)
- Prefix-monotonic verbatim back-references
- Line-number-aware renumbering folds
- Inspired by headroom `cross_turn_dedup.py`

### Tool Schema Compactor (`compressor/tool_schema_compactor.py`)
- Strip JSON Schema annotation keys
- Truncate descriptions to first sentence
- Remove self-explanatory param descriptions
- Inspired by headroom `tool_schema_compaction.py` + Atlassian mcp-compressor

### Live-Zone Mode (`config.live_zone_mode`)
- Compress all items, never drop messages
- Preserves provider cache prefix stability
- Inspired by headroom live-zone architecture

## Rejected (unchanged + new)

| Technique | Source | Why |
|-----------|--------|-----|
| Ponytail behavioral ladder | ponytail | Output steering ≠ compression engine |
| Full CBM indexing in Python | codebase-memory-mcp | 200K LOC C; integrate via MCP externally |
| Headroom HTTP proxy | headroom | Out of scope for library |
| ML Kompress path | headroom | ONNX latency, non-deterministic |
| LLM summarization | various | Non-deterministic, adds cost |

## Integration with codebase-memory-mcp (Phase 2)

Recommended pattern for AI Harness:
```
1. Agent calls codebase-memory-mcp search_graph (structural, ~3K tokens)
2. Instead of Read full files, get symbol snippets
3. Pass snippets to token-engine optimize_context()
4. CCR handles any aggressive compression with recovery
```

Expected combined savings: 90%+ on exploration workloads (CBM upstream) + 50%+ on tool outputs (engine downstream).
