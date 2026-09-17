"""Security gates for the Python subprocess runner (not a sandbox)."""

from __future__ import annotations

import pytest

from token_engine.core.config import EngineConfig
from token_engine.sandbox.executor import ExecutionDisabledError, execute_and_compress


def test_disabled_by_default():
    assert EngineConfig().enable_sandbox_execute is False
    assert EngineConfig.default().enable_sandbox_execute is False


def test_execute_raises_when_disabled():
    with pytest.raises(ExecutionDisabledError):
        execute_and_compress("print(1)", config=EngineConfig(enable_sandbox_execute=False))


def test_execute_runs_when_explicitly_enabled():
    result = execute_and_compress(
        "print('te-ok-42')",
        config=EngineConfig(enable_sandbox_execute=True),
        timeout=10,
    )
    assert result.returncode == 0
    assert "te-ok-42" in result.stdout
    assert result.isolation == "none"


def test_rejects_oversized_code():
    with pytest.raises(ValueError):
        execute_and_compress(
            "x" * 30_000,
            config=EngineConfig(enable_sandbox_execute=True),
            max_code_chars=100,
        )


def test_resource_not_imported_at_module_top_level():
    """Windows lacks `resource`; keep it lazy so MCP can import on win32."""
    import ast
    from pathlib import Path

    import token_engine.sandbox.executor as ex

    tree = ast.parse(Path(ex.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(alias.name != "resource" for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module == "resource":
            raise AssertionError("resource must not be imported at module top level")


def test_mcp_tool_rejects_when_disabled():
    from token_engine.mcp.server import token_engine_run_python

    out = token_engine_run_python("print(1)")
    assert out["enabled"] is False
    assert out["error"] == "execution_disabled"
    assert "compressed_output" not in out
