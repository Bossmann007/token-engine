"""Unit tests for Cursor hook scripts (stdin JSON → stdout JSON)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MCP_HOOK = REPO / "hooks" / "compress-mcp-output.py"
SHELL_HOOK = REPO / "hooks" / "compress-tool-output.py"


def _run(script: Path, payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(REPO),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    raw = proc.stdout.strip() or "{}"
    return json.loads(raw)


def test_mcp_hook_compresses_npm_envelope():
    npm = ("npm warn deprecated foo@1.0.0: x\n" * 40) + "added 200 packages\naudited 200 packages\n"
    envelope = {"content": [{"type": "text", "text": npm}], "isError": False}
    out = _run(MCP_HOOK, {"tool_output": json.dumps(envelope)})
    assert "updated_mcp_tool_output" in out
    rewritten = out["updated_mcp_tool_output"]
    assert isinstance(rewritten, dict)
    text = rewritten["content"][0]["text"]
    assert len(text) < len(npm)
    assert "added 200 packages" in text


def test_mcp_hook_fail_open_on_small():
    out = _run(MCP_HOOK, {"tool_output": "tiny"})
    assert out == {}


def test_mcp_hook_skips_invalid_json():
    proc = subprocess.run(
        [sys.executable, str(MCP_HOOK)],
        input="not-json",
        text=True,
        capture_output=True,
        cwd=str(REPO),
        check=False,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout.strip() or "{}") == {}


def test_mcp_hook_skips_error_payloads():
    npm = ("npm warn deprecated foo@1.0.0: x\n" * 40) + "added 200 packages\naudited 200 packages\n"
    envelope = {"content": [{"type": "text", "text": npm}], "isError": True}
    out = _run(MCP_HOOK, {"tool_output": json.dumps(envelope)})
    assert out == {}


def test_mcp_hook_preserves_is_error():
    # When not skipped (isError false), flag stays false after rewrite
    npm = ("npm warn deprecated foo@1.0.0: x\n" * 40) + "added 200 packages\naudited 200 packages\n"
    envelope = {"content": [{"type": "text", "text": npm}], "isError": False}
    out = _run(MCP_HOOK, {"tool_output": json.dumps(envelope)})
    assert "updated_mcp_tool_output" in out
    assert out["updated_mcp_tool_output"]["isError"] is False

    big = "x" * 2500
    out = _run(SHELL_HOOK, {"tool_name": "Shell", "tool_output": big})
    assert "additional_context" in out
    assert "caveman_compress" in out["additional_context"]
    assert "updated_mcp_tool_output" not in out


def test_shell_hook_silent_when_small():
    out = _run(SHELL_HOOK, {"tool_name": "Shell", "tool_output": "ok"})
    assert out == {}
