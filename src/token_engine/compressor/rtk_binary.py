"""Optional detection of the official RTK CLI binary (never required)."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any


def find_rtk_binary() -> str | None:
    return shutil.which("rtk")


def rtk_version(binary: str | None = None) -> str | None:
    path = binary or find_rtk_binary()
    if not path:
        return None
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (proc.stdout or proc.stderr or "").strip()
    return out or None


def rtk_status() -> dict[str, Any]:
    """Report whether the official RTK binary is available (user installs separately)."""
    path = find_rtk_binary()
    version = rtk_version(path) if path else None
    return {
        "installed": path is not None,
        "path": path,
        "version": version,
        "python_filters": "always available (token_engine.compressor.rtk_filters)",
        "cursor_hook": {
            "docs": "https://github.com/rtk-ai/rtk/tree/master/hooks/cursor",
            "requires": "rtk >= 0.23.0, jq; user runs RTK's install — Token Engine never auto-writes ~/.cursor",
            "note": "Shell output savings ≠ total bill savings; RTK estimates tokens as bytes/4",
        },
        "install_hint": "brew install rtk  # or: curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh",
    }
