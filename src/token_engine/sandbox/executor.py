"""Sandbox execute — run analysis outside context (context-mode-inspired)."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from token_engine import EngineConfig, TokenEngine


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    returncode: int
    compressed_stdout: str
    tokens_saved: int


def execute_and_compress(
    code: str,
    *,
    timeout: int = 30,
    max_output_chars: int = 50_000,
    config: EngineConfig | None = None,
) -> SandboxResult:
    """Run Python code in subprocess; return compressed stdout only."""
    engine = TokenEngine(config or EngineConfig())

    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            stdout="",
            stderr="[timeout]",
            returncode=-1,
            compressed_stdout="[sandbox timeout]",
            tokens_saved=0,
        )

    stdout = proc.stdout[:max_output_chars]
    stderr = proc.stderr[:max_output_chars]

    combined = stdout
    if stderr.strip():
        combined += f"\n=== STDERR ===\n{stderr}"

    original_tokens = engine.count_tokens(combined)
    result = engine.optimize(combined, content_type="log")
    compressed = result.content
    new_tokens = engine.count_tokens(compressed)

    return SandboxResult(
        stdout=stdout,
        stderr=stderr,
        returncode=proc.returncode,
        compressed_stdout=compressed,
        tokens_saved=max(0, original_tokens - new_tokens),
    )
