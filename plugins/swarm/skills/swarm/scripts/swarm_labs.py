#!/usr/bin/env python3
"""Validate SWARM Labs and summarize measured comparison runs."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "labs" / "labs.json"
SHARED_NUMBERS = ("elapsed_ms", "user_interventions", "nonproductive_retries")
OPTIONAL_TOKENS = ("codex_tokens", "chatgpt_tokens")


class LabError(ValueError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(f"cannot read {path}: {exc}") from exc


def validate_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise LabError("manifest schema_version must be 1")
    scenarios = data.get("scenarios")
    labs = data.get("labs")
    if not isinstance(scenarios, list) or not scenarios:
        raise LabError("manifest scenarios must be a non-empty list")
    if not isinstance(labs, list) or not labs:
        raise LabError("manifest labs must be a non-empty list")
    scenario_ids = {item.get("id") for item in scenarios if isinstance(item, dict)}
    if None in scenario_ids or len(scenario_ids) != len(scenarios):
        raise LabError("scenario ids must be present and unique")
    lab_ids: set[str] = set()
    for lab in labs:
        if not isinstance(lab, dict) or not isinstance(lab.get("id"), str):
            raise LabError("every lab requires an id")
        if lab["id"] in lab_ids:
            raise LabError(f"duplicate lab id: {lab['id']}")
        lab_ids.add(lab["id"])
        candidates = lab.get("candidates")
        if not isinstance(candidates, list) or not candidates or len(set(candidates)) != len(candidates):
            raise LabError(f"{lab['id']} candidates must be unique and non-empty")
        if lab.get("baseline_candidate") not in candidates:
            raise LabError(f"{lab['id']} baseline_candidate must be a candidate")
        unknown = set(lab.get("scenario_ids", [])) - scenario_ids
        if unknown:
            raise LabError(f"{lab['id']} references unknown scenarios: {sorted(unknown)}")
    return data


def validate_runs(data: Any, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    runs = data.get("runs") if isinstance(data, dict) else None
    if not isinstance(runs, list):
        raise LabError("results must contain a runs list")
    labs = {lab["id"]: lab for lab in manifest["labs"]}
    seen: set[tuple[str, str, str]] = set()
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise LabError(f"run {index} must be an object")
        lab = labs.get(run.get("lab_id"))
        if lab is None:
            raise LabError(f"run {index} has unknown lab_id")
        key = (run.get("lab_id"), run.get("scenario_id"), run.get("candidate_id"))
        if key[1] not in lab["scenario_ids"] or key[2] not in lab["candidates"]:
            raise LabError(f"run {index} is outside the declared lab matrix")
        if key in seen:
            raise LabError(f"duplicate run: {key}")
        seen.add(key)
        if type(run.get("accepted")) is not bool:
            raise LabError(f"run {index} accepted must be boolean")
        for field in SHARED_NUMBERS:
            if type(run.get(field)) is not int or run[field] < 0:
                raise LabError(f"run {index} {field} must be a non-negative integer")
        for field in OPTIONAL_TOKENS:
            value = run.get(field)
            if value is not None and (type(value) is not int or value < 0):
                raise LabError(f"run {index} {field} must be null or a non-negative integer")
        evidence = run.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item for item in evidence):
            raise LabError(f"run {index} requires evidence")
    return runs


def build_report(manifest: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_matrix = {(run["lab_id"], run["scenario_id"], run["candidate_id"]): run for run in runs}
    for run in runs:
        grouped[(run["lab_id"], run["candidate_id"])].append(run)
    lab_reports = []
    savings_pairs = []
    for lab in manifest["labs"]:
        candidates = []
        for candidate_id in lab["candidates"]:
            candidate_runs = grouped[(lab["id"], candidate_id)]
            expected = len(lab["scenario_ids"])
            tokens_known = bool(candidate_runs) and all(run["codex_tokens"] is not None for run in candidate_runs)
            candidates.append({
                "candidate_id": candidate_id,
                "coverage": f"{len(candidate_runs)}/{expected}",
                "accepted": len(candidate_runs) == expected and all(run["accepted"] for run in candidate_runs),
                "codex_tokens": sum(run["codex_tokens"] for run in candidate_runs) if tokens_known else None,
                "chatgpt_tokens": sum(run["chatgpt_tokens"] for run in candidate_runs if run["chatgpt_tokens"] is not None) if candidate_runs and all(run["chatgpt_tokens"] is not None for run in candidate_runs) else None,
                "elapsed_ms": sum(run["elapsed_ms"] for run in candidate_runs),
                "user_interventions": sum(run["user_interventions"] for run in candidate_runs),
                "nonproductive_retries": sum(run["nonproductive_retries"] for run in candidate_runs),
            })
        baseline = lab["baseline_candidate"]
        for candidate_id in lab["candidates"]:
            if candidate_id == baseline:
                continue
            paired = []
            for scenario_id in lab["scenario_ids"]:
                before = by_matrix.get((lab["id"], scenario_id, baseline))
                after = by_matrix.get((lab["id"], scenario_id, candidate_id))
                if before and after and before["codex_tokens"] is not None and after["codex_tokens"] is not None:
                    paired.append(before["codex_tokens"] - after["codex_tokens"])
            if paired:
                savings_pairs.append({
                    "lab_id": lab["id"],
                    "candidate_id": candidate_id,
                    "paired_scenarios": len(paired),
                    "estimated_codex_tokens_saved": sum(paired),
                })
        lab_reports.append({"lab_id": lab["id"], "candidates": candidates})
    return {
        "schema_version": 1,
        "labs": lab_reports,
        "usage_saver_estimate": {
            "status": "MEASURED" if savings_pairs else "UNKNOWN",
            "pairs": savings_pairs,
            "claim_limit": "Savings use paired measured Codex token receipts only; ChatGPT tokens are reported separately.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "report"))
    parser.add_argument("results", nargs="?", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        manifest = validate_manifest(_read_json(args.manifest))
        if args.command == "validate":
            payload = {"ok": True, "labs": len(manifest["labs"]), "scenarios": len(manifest["scenarios"])}
        else:
            if args.results is None:
                raise LabError("report requires a results file")
            payload = build_report(manifest, validate_runs(_read_json(args.results), manifest))
    except LabError as exc:
        parser.error(str(exc))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
