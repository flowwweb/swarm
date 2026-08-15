#!/usr/bin/env python3
"""Launch or reuse the SWARM Console bundled with this plugin."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    plugin_root = Path(__file__).resolve().parents[3]
    start = bool(sys.argv[1:] and sys.argv[1] == "--start")
    target = plugin_root / "console" / ("launcher.py" if start else "server.py")
    if not target.exists():
        print(f"SWARM Console entrypoint not found: {target}", file=sys.stderr)
        return 2
    args = sys.argv[2:] if start else sys.argv[1:]
    os.execv(sys.executable, [sys.executable, str(target), *args])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
