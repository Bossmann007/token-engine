#!/usr/bin/env python3
"""Local marker harness for hooks/compress-mcp-output.py.

Proves the hook rewrites payloads. Does NOT prove Cursor applies
updated_mcp_tool_output in a live agent turn — that needs a manual Cursor check.

Usage:
  python scripts/marker_test_mcp_hook.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "hooks" / "compress-mcp-output.py"
MARKER = "TE_MCP_HOOK_MARKER_UNCOMPRESSED_9f3a"


def main() -> int:
    # Large npm-like blob with an embedded marker that compression should drop or shrink past
    body = ("npm warn deprecated pkg@1.0.0: noise\n" * 50) + f"{MARKER}\nadded 99 packages\naudited 99 packages\n"
    envelope = {"content": [{"type": "text", "text": body}], "isError": False}
    payload = {"tool_name": "MCP:user-token-engine-caveman_compress", "tool_output": json.dumps(envelope)}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(REPO),
        check=False,
    )
    if proc.returncode != 0:
        print("FAIL: hook non-zero exit", proc.stderr, file=sys.stderr)
        return 1
    out = json.loads(proc.stdout.strip() or "{}")
    if "updated_mcp_tool_output" not in out:
        print("FAIL: no rewrite", out)
        return 1
    text = out["updated_mcp_tool_output"]["content"][0]["text"]
    if len(text) >= len(body):
        print("FAIL: not smaller", len(text), len(body))
        return 1
    print("PASS: hook rewrote MCP envelope")
    print(f"  {len(body)} → {len(text)} chars")
    print(f"  strategy note: {out.get('additional_context', '')}")
    print()
    print("Manual Cursor check (you run):")
    print("  1. Point a project hooks.json postToolUse at hooks/compress-mcp-output.py (MCP matcher).")
    print("  2. Call an MCP tool that returns >800 chars of npm-like output.")
    print("  3. Confirm the model sees the compressed text, not the raw dump.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
