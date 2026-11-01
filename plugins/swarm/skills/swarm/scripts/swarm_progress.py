#!/usr/bin/env python3
"""Write a local task pulse, assign retained task display IDs, retain bound block evidence, or read observed accepted counts per bucket."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


SWARM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWARM_ROOT))

from runtime.progress_events import HOUR_MS, Ledger, ProgressEventError, write_progress_pulse  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--assign-tickets", action="store_true", help="assign IDs to existing tasks from JSON project_id, project_code, task_ids")
    parser.add_argument("--ledger-root", type=Path, help="explicit existing Ledger root for ticket allocation")
    parser.add_argument("--bound-evidence", action="store_true", help="retain one file digest for a block of an existing host-created bound task from JSON")
    parser.add_argument("--accepted-rate", action="store_true", help="read-only observed accepted counts per bucket for --project-id; rates stay UNKNOWN without authoritative coverage; reads no stdin")
    parser.add_argument("--velocity", action="store_true", help="read-only daily Velocity comparison; unavailable buckets remain null")
    parser.add_argument("--start-velocity", action="store_true", help="start project Velocity recording at the expected Ledger revision")
    parser.add_argument("--expected-event-seq", type=int, help="expected Ledger revision for --start-velocity")
    parser.add_argument("--days", type=int, choices=(7, 30, 90), default=7)
    parser.add_argument("--project-id", help="project for --accepted-rate")
    parser.add_argument("--buckets", type=int, default=24, help="whole buckets ending at the last completed bucket boundary")
    parser.add_argument("--bucket-minutes", type=int, default=60)
    parser.add_argument("--as-of-ms", type=int, help="reader clock; defaults to now")
    args = parser.parse_args()
    if args.start_velocity:
        if args.velocity or args.accepted_rate or args.assign_tickets or args.bound_evidence or args.ledger_root is None or not args.project_id or args.expected_event_seq is None:
            parser.error("--start-velocity requires --ledger-root, --project-id and --expected-event-seq and excludes other modes")
        try:
            if not args.ledger_root.is_absolute() or not args.ledger_root.is_dir():
                raise ProgressEventError("velocity start requires an absolute existing Ledger root")
            result = Ledger(args.ledger_root).start_velocity_instrumentation(project_id=args.project_id, expected_event_seq=args.expected_event_seq)
        except (OSError, ProgressEventError) as error:
            print(json.dumps({"error": str(error)}, sort_keys=True, separators=(",", ":")))
            return 2
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.velocity:
        if args.accepted_rate or args.assign_tickets or args.bound_evidence or args.ledger_root is None or not args.project_id:
            parser.error("--velocity requires --ledger-root and --project-id and excludes other modes")
        try:
            if not args.ledger_root.is_absolute() or not args.ledger_root.is_dir():
                raise ProgressEventError("Velocity requires an absolute existing Ledger root")
            as_of = int(time.time() * 1000) if args.as_of_ms is None else args.as_of_ms
            result = Ledger(args.ledger_root).project_velocity(args.project_id, days=args.days, as_of_ms=as_of)
        except (OSError, ProgressEventError) as error:
            print(json.dumps({"error": str(error)}, sort_keys=True, separators=(",", ":")))
            return 2
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.accepted_rate:
        if args.assign_tickets or args.bound_evidence or args.ledger_root is None or not args.project_id:
            parser.error("--accepted-rate requires --ledger-root and --project-id and excludes write modes")
        try:
            if not args.ledger_root.is_absolute() or not args.ledger_root.is_dir():
                raise ProgressEventError("accepted rate requires an absolute existing Ledger root")
            if args.buckets < 1 or args.bucket_minutes < 1:
                raise ProgressEventError("--buckets and --bucket-minutes must be positive")
            as_of = int(time.time() * 1000) if args.as_of_ms is None else args.as_of_ms
            size = args.bucket_minutes * HOUR_MS // 60
            end = as_of - as_of % size  # Only completed buckets; the open bucket is never extrapolated.
            result = Ledger(args.ledger_root).project_accepted_progress_rate(
                args.project_id, observed_after_ms=end - args.buckets * size, observed_before_ms=end,
                as_of_ms=as_of, bucket_ms=size)
        except (OSError, ProgressEventError) as error:
            print(json.dumps({"error": str(error)}, sort_keys=True, separators=(",", ":")))
            return 2
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
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
            if not isinstance(payload, dict) or set(payload) not in (fields, fields | {"attempt"}) or not isinstance(payload["evidence_path"], str):
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
