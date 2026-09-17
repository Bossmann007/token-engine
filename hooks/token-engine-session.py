#!/usr/bin/env python3
"""sessionStart stub for repo-local Cursor hook experiments.

Does not write global state. Emits empty JSON so Cursor stays unblocked.
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    try:
        json.load(sys.stdin)
    except Exception:
        pass
    print("{}")


if __name__ == "__main__":
    main()
