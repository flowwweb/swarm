#!/usr/bin/env python3
"""Register generated proof media for automatic SWARM console discovery."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SWARM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWARM_ROOT))

from runtime.proof_events import ProofEventError, register_proof_event  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--caption", required=True)
    parser.add_argument("--claim-limit", default="Available for review; acceptance is recorded separately.")
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    args = parser.parse_args()
    try:
        result = register_proof_event(
            args.codex_home,
            args.path,
            evidence_id=args.evidence_id,
            task_id=args.task_id,
            kind=args.kind,
            caption=args.caption,
            claim_limit=args.claim_limit,
        )
    except (OSError, ProofEventError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
