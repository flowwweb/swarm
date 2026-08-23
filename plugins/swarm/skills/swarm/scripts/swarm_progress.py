#!/usr/bin/env python3
"""Write one validated local SWARM task pulse from a JSON stdin envelope."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SWARM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWARM_ROOT))

from runtime.progress_events import ProgressEventError, write_progress_pulse  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        result = write_progress_pulse(args.codex_home, payload)
    except (OSError, json.JSONDecodeError, ProgressEventError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
