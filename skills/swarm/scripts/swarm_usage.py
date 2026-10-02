"""Read-only, task-local Codex usage accounting. Writes reports only when requested."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
          "output_tokens", "reasoning_output_tokens", "total_tokens")
RATES = {"gpt-6.1-sol": (Decimal("2"), Decimal("0.10"), Decimal("2.50"), Decimal("10"))}
RATE_SOURCE = "https://developers.openai.com/api/docs/models/gpt-6.1-sol"


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return result


def usage(value):
    if not isinstance(value, dict) or any(type(value.get(k)) is not int or value[k] < 0 for k in FIELDS):
        raise ValueError("missing or invalid token categories")
    if value["input_tokens"] + value["output_tokens"] != value["total_tokens"]:
        raise ValueError("input plus output differs from total")
    if value["cached_input_tokens"] > value["input_tokens"] or value["reasoning_output_tokens"] > value["output_tokens"]:
        raise ValueError("cached/reasoning count exceeds its parent category")
    return {k: value[k] for k in FIELDS}


def standard_cost(tokens, model):
    """Per-request Standard equivalent; reasoning already belongs to output."""
    if model not in RATES:
        raise ValueError("no verified rate for observed model")
    # Cache-write membership in input is not established by local records.
    if tokens["cache_write_input_tokens"]:
        raise ValueError("nonzero cache writes require provider accounting reconciliation")
    input_rate, cache_rate, _, output_rate = RATES[model]
    long_input = tokens["input_tokens"] > 272_000
    input_factor = Decimal(2 if long_input else 1)
    output_factor = Decimal("1.5") if long_input else Decimal(1)
    return ((tokens["input_tokens"] - tokens["cached_input_tokens"]) * input_rate * input_factor
            + tokens["cached_input_tokens"] * cache_rate * input_factor
            + tokens["output_tokens"] * output_rate * output_factor) / Decimal(1_000_000)


def read_session(path, after=None, before=None):
    """Attribute cumulative deltas, ignoring repeated cumulative events."""
    if after and before and utc(before) <= utc(after):
        raise ValueError("before must be later than after")
    path = Path(path).resolve()
    groups = defaultdict(lambda: {"tokens": {k: 0 for k in FIELDS}, "requests": 0,
                                  "standard_cost": Decimal(0), "pricing_complete": True})
    previous = {k: 0 for k in FIELDS}
    meta, context, issues = {}, {}, []
    started = finished = None
    closed = False
    selected = 0
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            digest.update(raw)
            try:
                record = json.loads(raw)
            except (ValueError, UnicodeError):
                issues.append(f"line {number}: malformed JSON; coverage unknown")
                continue
            if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
                issues.append(f"line {number}: invalid record shape")
                continue
            payload = record["payload"]
            if record.get("type") == "session_meta":
                if meta and meta.get("id") != payload.get("id"):
                    issues.append("conflicting session identities")
                meta = {k: payload.get(k) for k in ("id", "cwd", "source", "model_provider")}
            if record.get("type") == "turn_context":
                context = {"model": payload.get("model"),
                           "effort": payload.get("effort", payload.get("reasoning_effort")),
                           "service_tier": payload.get("service_tier")}
            if record.get("type") != "event_msg":
                continue
            timestamp = record.get("timestamp")
            try:
                time = utc(timestamp)
            except (TypeError, ValueError, AttributeError):
                if payload.get("type") == "token_count":
                    issues.append(f"line {number}: token event missing valid timestamp")
                continue
            in_scope = (not after or time >= utc(after)) and (not before or time <= utc(before))
            if payload.get("type") == "task_complete" and in_scope:
                closed = True
            if payload.get("type") != "token_count":
                continue
            info = payload.get("info")
            if not isinstance(info, dict) or not isinstance(info.get("total_token_usage"), dict):
                continue  # Host emits rate-limit-only events with info=null.
            try:
                total = usage(info["total_token_usage"])
                delta = {k: total[k] - previous[k] for k in FIELDS}
                if any(v < 0 for v in delta.values()):
                    raise ValueError("cumulative counters decreased; reset requires reconciliation")
                usage(delta)
            except ValueError as exc:
                issues.append(f"line {number}: {exc}")
                continue
            previous = total
            if not in_scope or not delta["total_tokens"]:
                continue
            selected += 1
            started = started or timestamp
            finished = timestamp
            closed = False
            key = (context.get("model"), context.get("effort"), context.get("service_tier"))
            group = groups[key]
            group["requests"] += 1
            for field in FIELDS:
                group["tokens"][field] += delta[field]
            try:
                last = usage(info.get("last_token_usage"))
                if last != delta:
                    raise ValueError("last request does not reconcile to cumulative delta")
                group["standard_cost"] += standard_cost(delta, key[0])
            except ValueError as exc:
                group["pricing_complete"] = False
                issues.append(f"line {number}: {exc}")
    rows = []
    for (model, effort, tier), group in groups.items():
        rows.append({"model": model, "effort": effort, "service_tier_observed": tier,
                     "tokens": group["tokens"], "requests": group["requests"],
                     "standard_api_equivalent_usd": str(group["standard_cost"]) if group["pricing_complete"] else None,
                     "price_basis": "Conditional Standard tier, no regional premium or external tool fees",
                     "model_evidence": "local turn_context, not provider response verification"})
    totals = {k: sum(row["tokens"][k] for row in rows) for k in FIELDS}
    return {"thread_id": meta.get("id"), "path": str(path), "sha256": digest.hexdigest(),
            "provider_observed": meta.get("model_provider"), "cwd": meta.get("cwd"),
            "source": meta.get("source"), "after": after, "before": before,
            "first_usage_at": started, "last_usage_at": finished,
            "closed_turn_observed": closed, "usage_events": selected,
            "tokens": totals, "by_model": rows, "issues": issues,
            "accounting_status": "SNAPSHOT" if rows and not issues else "UNVERIFIED"}


def verify_candidate(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    root = Path(manifest["candidate_root"]).resolve()
    expected = set()
    problems = []
    for item in manifest["files"]:
        target = (root / item["path"]).resolve()
        if not target.is_relative_to(root):
            raise ValueError("candidate manifest path escapes root")
        expected.add(target)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest().upper() != item["sha256"].upper():
            problems.append(item["path"])
    unexpected = {p.resolve() for p in root.rglob("*") if p.is_file()} - expected
    return {"status": "PASS" if not problems and not unexpected else "FAIL",
            "checked": len(expected), "changed_or_missing": problems,
            "unexpected": sorted(str(p.relative_to(root)) for p in unexpected)}


def build_report(sessions, expected_model="gpt-6.1-sol", expected_effort="xhigh"):
    identities = [s["thread_id"] for s in sessions]
    if not all(identities) or len(set(identities)) != len(identities):
        raise ValueError("sessions require unique observed thread identities")
    totals = {k: sum(s["tokens"][k] for s in sessions) for k in FIELDS}
    rows = [row for s in sessions for row in s["by_model"]]
    lock_ok = bool(sessions) and all(s["by_model"] for s in sessions) and all(
        row["model"] == expected_model and row["effort"] == expected_effort for row in rows)
    costs = [row["standard_api_equivalent_usd"] for row in rows]
    complete = bool(sessions) and all(s["accounting_status"] == "SNAPSHOT" for s in sessions)
    return {"schema_version": 1, "rate_source": RATE_SOURCE, "rates_verified_on": "2026-10-01",
            "expected_model": expected_model, "expected_effort": expected_effort,
            "model_lock_status": "PASS" if lock_ok else "FAIL",
            "token_coverage": "SUPPLIED_SESSIONS_ONLY" if complete else "UNVERIFIED",
            "participant_roster_status": "REQUIRES_HOST_RECONCILIATION",
            "tokens": totals if complete else None,
            "observed_partial_tokens": totals,
            "standard_api_equivalent_usd": str(sum(map(Decimal, costs))) if complete and costs and all(c is not None for c in costs) else None,
            "actual_billed_usd": None, "sessions": sessions,
            "claim_limit": "Snapshot of supplied sessions. Host roster, actual tier, provider model and final closure require separate evidence. Reasoning is included in output."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    candidate = sub.add_parser("verify-candidate")
    candidate.add_argument("manifest", type=Path)
    report = sub.add_parser("report")
    report.add_argument("sessions", type=Path, nargs="+")
    report.add_argument("--after")
    report.add_argument("--before")
    report.add_argument("--model", default="gpt-6.1-sol")
    report.add_argument("--effort", default="xhigh")
    report.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "verify-candidate":
            result = verify_candidate(args.manifest)
        else:
            result = build_report([read_session(p, args.after, args.before) for p in args.sessions], args.model, args.effort)
            if args.output:
                args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1 if result.get("status") == "FAIL" or result.get("model_lock_status") == "FAIL" or result.get("token_coverage") == "UNVERIFIED" else 0
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
