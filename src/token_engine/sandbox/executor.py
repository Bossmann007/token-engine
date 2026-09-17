"""Gated Python subprocess runner — NOT a security sandbox.

This module runs ``python -c`` in a child process with a scrubbed environment,
timeouts, and output caps. It does **not** provide filesystem or network
isolation. Prefer keeping ``enable_sandbox_execute=False`` (the default).
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

from token_engine import EngineConfig, TokenEngine

# Soft defaults — platform may ignore some limits
_DEFAULT_MAX_CODE_CHARS = 20_000
_DEFAULT_MAX_OUTPUT_CHARS = 50_000
_DEFAULT_TIMEOUT = 15
_MEMORY_BYTES = 256 * 1024 * 1024  # 256 MiB soft/hard where supported
_CPU_SECONDS = 15


class ExecutionDisabledError(RuntimeError):
    """Raised when enable_sandbox_execute is false."""


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    returncode: int
    compressed_stdout: str
    tokens_saved: int
    isolation: str = "none"  # honest: no FS/network jail


def _scrubbed_env() -> dict[str, str]:
    """Minimal env — drop secrets-bearing inherited variables."""
    keep = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "TMP": os.environ.get("TMP", "/tmp"),
        "TEMP": os.environ.get("TEMP", "/tmp"),
    }
    return {k: v for k, v in keep.items() if v}


def _limit_resources() -> None:
    # Lazy import: `resource` is POSIX-only (breaks Windows MCP import if top-level).
    import resource

    try:
        resource.setrlimit(resource.RLIMIT_CPU, (_CPU_SECONDS, _CPU_SECONDS))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_AS, (_MEMORY_BYTES, _MEMORY_BYTES))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    except (ValueError, OSError, AttributeError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    except (ValueError, OSError):
        pass


def execute_and_compress(
    code: str,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
    max_output_chars: int = _DEFAULT_MAX_OUTPUT_CHARS,
    max_code_chars: int = _DEFAULT_MAX_CODE_CHARS,
    config: EngineConfig | None = None,
) -> SandboxResult:
    """Run Python in a scrubbed subprocess; compress stdout. Not a sandbox."""
    cfg = config or EngineConfig()
    if not cfg.enable_sandbox_execute:
        raise ExecutionDisabledError(
            "Python subprocess execution is disabled "
            "(enable_sandbox_execute=false). This is not an isolated sandbox; "
            "enable only if you accept host process risk."
        )

    if len(code) > max_code_chars:
        raise ValueError(f"code exceeds max_code_chars={max_code_chars}")

    engine = TokenEngine(cfg)
    timeout = max(1, min(int(timeout), 60))
    preexec = _limit_resources if os.name == "posix" else None

    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_scrubbed_env(),
            cwd="/tmp" if os.name == "posix" else None,
            preexec_fn=preexec,
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            stdout="",
            stderr="[timeout]",
            returncode=-1,
            compressed_stdout="[subprocess timeout]",
            tokens_saved=0,
            isolation="none",
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
        isolation="none",
    )
