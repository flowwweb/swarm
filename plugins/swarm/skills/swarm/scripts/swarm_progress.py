#!/usr/bin/env python3
"""Write a local task pulse, assign retained task display IDs, or retain bound block evidence."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SWARM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWARM_ROOT))

from runtime.progress_events import Ledger, ProgressEventError, write_progress_pulse  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--assign-tickets", action="store_true", help="assign IDs to existing tasks from JSON project_id, project_code, task_ids")
    parser.add_argument("--ledger-root", type=Path, help="explicit existing Ledger root for ticket allocation")
    parser.add_argument("--bound-evidence", action="store_true", help="retain one file digest for a block of an existing host-created bound task from JSON")
    args = parser.parse_args()
    if args.bound_evidence:
        if args.assign_tickets or args.ledger_root is None:
            parser.error("--bound-evidence requires --ledger-root and excludes --assign-tickets")
    elif args.assign_tickets != (args.ledger_root is not None):
        parser.error("--assign-tickets and --ledger-root must be supplied together")
    try:
        payload = json.load(sys.stdin)
        if args.bound_evidence:
            if not args.ledger_root.is_absolute() or not args.ledger_root.is_dir():
                raise ProgressEventError("bound evidence requires an absolute existing Ledger root")
            fields = {"project_id", "task_id", "block_id", "manifest_digest", "expected_event_seq", "evidence_path", "expected_sha256"}
            if not isinstance(payload, dict) or set(payload) != fields or not isinstance(payload["evidence_path"], str):
                raise ProgressEventError("bound evidence envelope requires exactly " + ", ".join(sorted(fields)))
            result = Ledger(args.ledger_root).append_bound_block_evidence(
                **{**payload, "evidence_path": Path(payload["evidence_path"])})
        elif args.assign_tickets:
            if not args.ledger_root.is_absolute() or not args.ledger_root.is_dir():
                raise ProgressEventError("ticket allocation requires an absolute existing Ledger root")
            if not isinstance(payload, dict) or set(payload) != {"project_id", "project_code", "task_ids"} or not isinstance(payload["task_ids"], list):
                raise ProgressEventError("ticket envelope requires exactly project_id, project_code, task_ids")
            result = Ledger(args.ledger_root).assign_ticket_ids(payload["project_id"], payload["project_code"], tuple(payload["task_ids"]))
        else:
            result = write_progress_pulse(args.codex_home, payload)
    except (OSError, json.JSONDecodeError, ProgressEventError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
