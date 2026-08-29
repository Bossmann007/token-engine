# Algorithms

## Technique Selection

After analyzing 9 repositories, these techniques were **selected**, **adapted**, or **rejected**.

## Adopted Techniques

### 1. Content-Type Detection + Routed Compression
**Source**: caveman `engine/detect.go`

Strict detection order: JSON → diff → log → terminal → search → config → code → text.

Each type gets a specialized compressor. Avoids one-size-fits-all damage.

### 2. Fail-Closed Compression
**Source**: caveman `engine/engine.go`

Only apply compression when output token count is strictly less than input. Prevents silent quality regression.

### 3. Log Error/Stack Trace Preservation
**Sources**: caveman, rtk

- CRITICAL patterns never dropped (Traceback, panic, AssertionError)
- INFO/DEBUG collapsed aggressively
- Repeated lines deduplicated with counts

### 4. Code Structural Compression
**Sources**: caveman `code_listing.go`, token-savior annotators

- Strip line-number gutters (`123| code`)
- Preserve imports and signatures
- Elide function bodies with markers
- Only at moderate+ aggressiveness

### 5. Tool Output Compactors
**Sources**: rtk, token-optimizer `bash_compress.py`

Per-tool handlers:
- **git**: branch + file lists, not full diff
- **pytest**: failures + summary, not passed tests
- **grep**: group by file, cap matches
- **npm**: errors + summary
- **ls**: cap entries

### 6. BM25 Relevance Ranking
**Source**: caveman `contextwindow.Pack()`

Lexical BM25 with boosts:
- Recency (24h half-life)
- Error content (+5.0)
- Tier priority (CRITICAL +10.0)

### 7. Cross-Item Deduplication
**Source**: token-optimizer read-cache concept

SHA-256 hash of normalized content. Duplicates marked REDUNDANT and dropped from selection.

### 8. Smart Cache with Dependency Invalidation
**Source**: token-optimizer-mcp cache-engine

Cache compression results keyed by content hash + aggressiveness. Invalidate when dependency files change.

### 9. Token Budget Filtering
**Source**: caveman context window

Always include CRITICAL tier. Fill remaining budget by BM25 rank.

### 10. Adaptive Aggressiveness
**Mapping**:
- `quality=maximum` → 0.25 aggressiveness
- `quality=balanced` → 0.55
- `quality=economy` → 0.85

Large tool outputs auto-route to tool compressor regardless.

## Rejected Techniques

| Technique | Source | Reason |
|-----------|--------|--------|
| PostToolUse-only compaction | token-savior | Doesn't reduce current-turn tokens |
| Output brevity prompts | claude-token-efficient | Quality risk; adds input overhead every turn |
| Caveman-speak skill | caveman | Reduces reasoning clarity |
| Hard deny Read/Grep | token-optimizer-mcp | Too fragile for generic harness |
| bytes/4 as sole metric | rtk | Inaccurate for gating decisions |
| LLM summarization | various | Non-deterministic, adds cost |
| Embedding RAG default | claude-context | Index cost; different problem class |
| Pixel/skills-as-image | caveman | Model-dependent economics |
| Full 65+ MCP tool surface | token-optimizer-mcp | Complexity without proportional gain |
| Lossy compress without recovery | various | Violates quality-first priority |

## Comparison Matrix

| Technique | Best Source | Quality | Economy | Latency | Complexity | Adopted |
|-----------|------------|---------|---------|---------|------------|---------|
| Prompt compression | claude-token-optimizer | 9 | 7 | 10 | 2 | Patterns only |
| Context compression | caveman | 9 | 9 | 7 | 8 | Yes |
| Summarization | context-mode | 10 | 9 | 6 | 8 | No (store exact) |
| Pruning | rtk | 8 | 8 | 10 | 5 | Yes |
| Deduplication | token-optimizer | 8 | 8 | 9 | 5 | Yes |
| Tool output compression | rtk + caveman | 9 | 9 | 9 | 6 | Yes |
| Semantic filtering | claude-context | 8 | 7 | 5 | 7 | Phase 2 |
| Caching | token-optimizer-mcp | 8 | 7 | 9 | 6 | Yes |
| Token estimation | caveman (tiktoken) | 10 | — | 9 | 3 | Yes |
| Context selection | caveman BM25 | 8 | 8 | 9 | 6 | Yes |
| Structural code nav | token-savior | 9 | 9 | 7 | 7 | Partial |
| Knowledge graph | token-optimizer-mcp | 8 | 8 | 6 | 10 | Phase 2 |

## Quality Preservation Rules

Hard-coded in compressors:

1. Never remove `Traceback`, stack frames, or panic messages
2. Never remove `AssertionError`, test failure details
3. Never remove CRITICAL-tier items from context selection
4. Fail-closed if compression doesn't reduce tokens
5. Preserve file paths in error messages
6. Preserve function/class signatures in code compression

## Phase 2 Roadmap

- Recovery handles (CCR-style) for lossy compression
- Optional semantic index for monorepos (claude-context inspired)
- Rule-based knowledge graph for session findings
- Sandbox execute-outside-context (context-mode pattern)
