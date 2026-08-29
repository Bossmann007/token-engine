#!/usr/bin/env bash
# Remind agent: token-engine MCP + optional REST harness on :8741
input=$(cat)
echo '{"additional_context":"Token Engine active: use caveman_compress on large tool output (>1.5k chars) and token_engine_compress_session for multi-item context. task_query improves path relevance."}' 
