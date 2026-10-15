#!/usr/bin/env python3
"""Initialize one explicit project root without overwriting existing documents."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "console"))
from project_model_views import parse_project_brief_markdown

MAX_BYTES = 512 * 1024
MANIFEST_MARKER = "<!-- swarm-project-index:schema=1 -->"


def _unknown(reason: str) -> dict:
    return {"status": "UNKNOWN", "reason": reason}


def _regular(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f"link/reparse path is not admissible: {path}")
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError(f"non-regular target: {path}")


def _targets(root: Path) -> dict[str, Path]:
    for ancestor in (*reversed(root.parents), root):
        _regular(ancestor, directory=True)
    result = {}
    for name in ("SWARM.md", "project.md"):
        matches = [p for p in root.iterdir() if p.name.casefold() == name.casefold()]
        if len(matches) > 1:
            raise ValueError(f"case-insensitive collision: {name}")
        if matches:
            _regular(matches[0])
            result[name] = matches[0]
    return result


def _read(path: Path) -> str:
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"document exceeds {MAX_BYTES} bytes: {path}")
    return data.decode("utf-8")


def _markdown(title: str, marker: str, value: dict) -> str:
    return f"# {title}\n\n{marker}\n```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```\n"


def _repo_facts(root: Path) -> dict:
    """Observe local Git only; never query remotes or treat a parent repo as this root."""
    try:
        def git(*args: str) -> str:
            return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                                  text=True, timeout=5).stdout.strip()
        top = Path(git("rev-parse", "--show-toplevel"))
        if top.resolve() != root.resolve():
            return _unknown("selected root is not the Git repository root")
        head = git("rev-parse", "--verify", "HEAD")
        return {"status": "OBSERVED_LOCAL", "root": str(root), "head": head}
    except (OSError, subprocess.SubprocessError):
        return _unknown("no local Git root and HEAD could be verified")


def _new_brief(root: Path) -> dict:
    return {
        "schema_version": 1, "updated_at": datetime.now(timezone.utc).isoformat(),
        "project": {"id": "project-" + uuid.uuid4().hex, "name": root.name,
                    "purpose": "UNKNOWN: purpose has not been supplied",
                    "name_source": "local directory name; not a verified app identity"},
        "users_outcomes": [],
        "objective": {"current": "UNKNOWN: objective has not been supplied",
                      "scope": "UNKNOWN: scope has not been supplied", "non_goals": []},
        "repo": {"local_git": _repo_facts(root), "remote": _unknown("not verified"),
                 "app": _unknown("no host app binding supplied")},
        "authority": {"intent": "SWARM.md", "observed_state": "existing Ledger, if bound",
                      "constraints": ["Initialization grants no execution or acceptance authority."]},
        "milestones": [], "decisions": [],
        "ownership": {"ctrl": _unknown("no owner assigned"), "lanes": []},
        "proof_acceptance": {"required": _unknown("proof plan not supplied"),
                             "accepting_route": _unknown("review owner not assigned"),
                             "claim_limit": "Documents initialized only; no runtime or host readiness proof."},
        "risks_blockers": ["Purpose, scope, users/outcomes, roadmap, owners and acceptance remain UNKNOWN."],
        "links": ["project.md", "SWARM skill: roles/", "SWARM skill: references/task-contract.md",
                  "SWARM skill: references/hierarchy.md", "SWARM skill: references/review-contract.md",
                  "SWARM skill: scripts/swarm_proof.py"],
    }


def _manifest(brief: dict, digest: str, brief_name: str) -> dict:
    project = brief["project"]
    milestone_ids = [m["id"] for m in brief["milestones"]
                     if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"].strip()]
    return {
        "schema_version": 1,
        "authority": "Snapshot/index only. SWARM.md owns intent; the existing Ledger owns observed state.",
        "project": {"id": project["id"], "name": project.get("name", _unknown("brief has no name")),
                    "purpose": project.get("purpose", _unknown("brief has no purpose"))},
        "scope": brief["objective"].get("scope", _unknown("brief has no scope")),
        "bindings": {"local_git": _unknown("no verified local binding in brief"),
                     "remote": _unknown("no verified remote in brief"),
                     "app": _unknown("no host app binding in brief"), **brief["repo"]},
        "owners": {"ctrl": _unknown("no owner in brief"), **brief["ownership"]},
        "roadmap": {"ids": milestone_ids,
                    "source": f"{brief_name}#/milestones",
                    "status": "REFERENCED" if milestone_ids else "UNKNOWN",
                    "reason": "References only; no milestone state copied." if milestone_ids else "No usable milestone IDs supplied."},
        "acceptance_evidence": {"required": _unknown("proof plan not supplied"),
                                "accepting_route": _unknown("review owner not assigned"),
                                **brief["proof_acceptance"]},
        "provenance": {"path": brief_name, "canonical_digest": digest,
                       "pointers": ["/project", "/objective", "/repo", "/ownership", "/milestones", "/proof_acceptance"]},
    }


def _parse_manifest(text: str) -> dict:
    blocks = re.findall(r"```json\s*\n([\s\S]*?)\n```", text)
    if text.count(MANIFEST_MARKER) != 1 or len(blocks) != 1:
        raise ValueError("project.md is not one recognized manifest snapshot; preserved")
    value = json.loads(blocks[0])
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("project.md snapshot schema is unsupported")
    if not isinstance(value.get("project"), dict) or not isinstance(value["project"].get("id"), str):
        raise ValueError("project.md snapshot identity is missing")
    provenance = value.get("provenance")
    if (not isinstance(provenance, dict)
            or not isinstance(provenance.get("canonical_digest"), str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", provenance["canonical_digest"]) is None
            or not isinstance(provenance.get("path"), str)
            or provenance["path"].casefold() != "swarm.md"):
        raise ValueError("project.md snapshot provenance is missing")
    return value


def _create(path: Path, text: str) -> None:
    # No replacement: interruption leaves a visible partial file for explicit recovery.
    with path.open("xb") as stream:
        stream.write(text.encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())


def initialize(root: Path) -> dict:
    root = Path(os.path.abspath(root))
    targets = _targets(root)
    before = {name: _read(path) for name, path in targets.items()}
    snapshot = _parse_manifest(before["project.md"]) if "project.md" in before else None
    if "SWARM.md" not in before and snapshot is not None:
        raise ValueError("project.md is a snapshot, not authority to reconstruct missing SWARM.md; preserved")
    brief_text = before.get("SWARM.md")
    if brief_text is None:
        brief_text = _markdown("SWARM project brief", "<!-- swarm-project-brief:schema=1 -->", _new_brief(root))
    brief, digest = parse_project_brief_markdown(brief_text)
    warnings = []
    if snapshot is not None:
        if snapshot["project"]["id"] != brief["project"]["id"]:
            raise ValueError("SWARM.md and project.md identities conflict; preserved")
        if snapshot["provenance"]["canonical_digest"] != digest:
            warnings.append("project.md snapshot provenance is stale; preserved, SWARM.md remains authoritative")
    if "project.md" not in brief["links"]:
        warnings.append("existing brief has no project.md link; preserved")
    created = []
    documents = (
        ("SWARM.md", brief_text),
        ("project.md", _markdown("Project manifest snapshot", MANIFEST_MARKER,
                                 _manifest(brief, digest, targets.get("SWARM.md", root / "SWARM.md").name))),
    )
    if any(len(text.encode("utf-8")) > MAX_BYTES for _, text in documents):
        raise ValueError("generated document exceeds bounded document size")
    for name, text in documents:
        if name in targets:
            continue
        current = _targets(root)
        if current != targets or any(_read(path) != before[key] for key, path in targets.items()):
            raise ValueError("project documents changed during initialization; rerun after custody reconciliation")
        path = root / name
        _create(path, text)
        targets[name], before[name] = path, text
        created.append(name)
    return {"status": "INITIALIZED" if created else "ADOPTED", "root": str(root),
            "project_id": brief["project"]["id"], "canonical_brief_digest": digest,
            "created": created, "warnings": warnings,
            "claim_limit": "Document initialization only; host bindings, routing and acceptance are not established."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="one existing project root")
    args = parser.parse_args()
    try:
        print(json.dumps(initialize(args.root), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
