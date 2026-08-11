#!/usr/bin/env python3
"""Legacy `rush` alias that launches the SWARM Console bundled with this plugin."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    plugin_root = Path(__file__).resolve().parents[3]
    server = plugin_root / "console" / "server.py"
    if not server.exists():
        print(f"SWARM Console server not found (legacy rush alias): {server}", file=sys.stderr)
        return 2
    os.execv(sys.executable, [sys.executable, str(server), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
