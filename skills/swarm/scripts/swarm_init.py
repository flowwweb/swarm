#!/usr/bin/env python3
"""Initialize one explicit project root without overwriting existing documents."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
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
from project_model_views import _BRIEF_REQUIRED, _brief_update_lock, _create_brief_bytes, _publish_brief_archive, compact_project_brief, parse_project_brief_markdown
sys.path.insert(0, str(Path(__file__).resolve().parent))
from swarm_config import ConfigError, load as load_config, resolve_config_path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import ArtifactIdentity, Role, Swarm

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


def _targets(root: Path, names: tuple[str, ...] = ("SWARM.md", "project.md")) -> dict[str, Path]:
    for ancestor in (*reversed(root.parents), root):
        _regular(ancestor, directory=True)
    result = {}
    for name in names:
        matches = [p for p in root.iterdir() if p.name.casefold() == name.casefold()]
        if len(matches) > 1:
            raise ValueError(f"case-insensitive collision: {name}")
        if matches:
            _regular(matches[0])
            result[name] = matches[0]
    return result


def _read(path: Path, *, limit: int = MAX_BYTES) -> str:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"document exceeds {limit} bytes: {path}")
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
    _create_brief_bytes(path, text.encode("utf-8"))


def _retained_brief(text: str) -> tuple[dict, str, re.Match]:
    """Validate retained content through the unchanged active schema/size bound."""
    blocks = list(re.finditer(r"```json\s*\n(?P<payload>[\s\S]*?)\n```", text))
    if text.count("<!-- swarm-project-brief:schema=1 -->") != 1 or len(blocks) != 1:
        raise ValueError("retained brief requires one schema-1 document")
    document = json.loads(blocks[0].group("payload"))
    compact = "<!-- swarm-project-brief:schema=1 -->\n```json\n" + json.dumps(
        document, ensure_ascii=False, separators=(",", ":")) + "\n```"
    checked, digest = parse_project_brief_markdown(compact)
    return checked, digest, blocks[0]


def read_brief_history(root: Path, reference: dict):
    """Resolve one immutable root-confined historical section, never live state."""
    if (not isinstance(reference, dict)
            or set(reference) != {"rel", "path", "sha256", "bytes", "canonical_digest", "field"}
            or reference["rel"] != "brief_history"
            or not isinstance(reference["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", reference["sha256"]) is None
            or type(reference["bytes"]) is not int or not 0 < reference["bytes"] <= 2 * MAX_BYTES
            or not isinstance(reference["field"], str)
            or re.fullmatch(r"[a-z][a-z0-9_]*", reference["field"]) is None
            or reference["path"] != f"history/swarm-brief-{reference['sha256']}.md"):
        raise ValueError("invalid brief history reference")
    root = Path(os.path.abspath(root))
    _targets(root, ())
    path = root / reference["path"]
    _regular(path.parent, directory=True)
    _regular(path)
    text = _read(path, limit=2 * MAX_BYTES)
    raw = text.encode("utf-8")
    if len(raw) != reference["bytes"] or hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("brief history bytes/digest mismatch")
    document, digest, _ = _retained_brief(text)
    if digest != reference["canonical_digest"] or reference["field"] not in document:
        raise ValueError("brief history canonical binding mismatch")
    return document[reference["field"]]


def _validate_history(root: Path, brief: dict) -> None:
    for link in brief["links"]:
        if isinstance(link, dict) and link.get("rel") == "brief_history":
            if brief.get(link.get("field")) != link:
                raise ValueError("brief history link conflicts with current section")
            read_brief_history(root, link)


def archive_brief_section(root: Path, field: str, *, expected_sha256: str) -> dict:
    """Losslessly externalize one explicitly selected optional legacy section."""
    with _brief_update_lock(Path(os.path.abspath(root)) / "SWARM.md"):
        return _archive_brief_section(root, field, expected_sha256=expected_sha256)


def _archive_brief_section(root: Path, field: str, *, expected_sha256: str) -> dict:
    if not isinstance(field, str) or re.fullmatch(r"[a-z][a-z0-9_]*", field) is None:
        raise ValueError("one exact top-level field is required")
    if field in _BRIEF_REQUIRED or field in {"tasks", "blocks", "artifacts", "flow_definitions", "proposed_lens_ids"}:
        raise ValueError("current canonical state cannot be externalized as legacy history")
    root = Path(os.path.abspath(root))
    targets = _targets(root)
    path = targets.get("SWARM.md")
    if path is None:
        raise ValueError("canonical SWARM.md is required; no human document is replaced")
    original = _read(path, limit=2 * MAX_BYTES)
    raw = original.encode("utf-8")
    original_sha = hashlib.sha256(raw).hexdigest()
    document, original_digest, fence = _retained_brief(original)
    section = document.get(field)
    if isinstance(section, dict) and section.get("rel") == "brief_history":
        if section.get("sha256") != expected_sha256:
            raise ValueError("history operation identity conflicts")
        _validate_history(root, document)
        return {"status": "REPLAY", "archive": section, "current_sha256": original_sha}
    if original_sha != expected_sha256 or not isinstance(section, (dict, list)):
        raise ValueError("brief changed or selected section is not structured data")
    if not isinstance(document["links"], list):
        raise ValueError("named links must be explicitly migrated before appending a brief history link; preserved")
    reference = {"rel": "brief_history", "path": f"history/swarm-brief-{original_sha}.md",
                 "sha256": original_sha, "bytes": len(raw), "canonical_digest": original_digest, "field": field}
    document[field] = reference
    document["links"] = [*document["links"], reference]
    document["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(document, ensure_ascii=False, indent=2)
    if "\r\n" in original:
        payload = payload.replace("\n", "\r\n")
    candidate = original[:fence.start("payload")] + payload + original[fence.end("payload"):]
    # Active brief cap is unchanged; required/core fields cannot be externalized.
    checked, digest = parse_project_brief_markdown(candidate)
    archive = root / reference["path"]
    archive.parent.mkdir(exist_ok=True)
    _regular(archive.parent, directory=True)
    if archive.exists():
        _regular(archive)
        if _read(archive, limit=2 * MAX_BYTES) != original:
            raise ValueError("immutable history archive conflicts")
    else:
        _publish_brief_archive(archive, raw, create=lambda path, data: _create(path, data.decode("utf-8")))
    if read_brief_history(root, reference) != section:
        raise ValueError("history roundtrip mismatch")
    _validate_history(root, checked)
    temporary = root / (".swarm-brief-" + uuid.uuid4().hex + ".tmp")
    created = False
    try:
        _create(temporary, candidate)
        created = True
        if _targets(root) != targets or _read(path, limit=2 * MAX_BYTES) != original:
            raise ValueError("canonical brief changed before history replacement")
        os.replace(temporary, path)
    finally:
        if created and temporary.exists():
            temporary.unlink()
    return {"status": "ARCHIVED", "archive": reference, "canonical_digest": digest,
            "current_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
            "current_bytes": len(candidate.encode("utf-8")), "archived_count": len(section)}


def plan_alignment(root: Path, *, questions_enabled: bool | None = None, config_path: Path | None = None,
                   cohort_dir: Path | None = None, staged_answers: dict | None = None) -> dict:
    """Inspect a four-document cohort; never write or infer its approval."""
    if questions_enabled is not None and type(questions_enabled) is not bool:
        raise ValueError("questions_enabled must be a boolean")
    try:
        effective, config_exists = load_config(resolve_config_path(config_path))
    except ConfigError as exc:
        raise ValueError(str(exc)) from exc
    question_source = "USER_OVERRIDE" if questions_enabled is not None else "CONFIG"
    if questions_enabled is None:
        questions_enabled = effective["init"]["guided_interview"]
    root = Path(os.path.abspath(root))
    documents_root = root
    root_text = root_path = None
    root_digest = None
    bound_brief = None
    if cohort_dir is not None:
        relative = Path(cohort_dir)
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise ValueError("cohort_dir must be a relative directory inside the project root")
        documents_root = root / relative
        roots = _targets(root, ("SWARM.md",))
        root_path = roots.get("SWARM.md")
        if root_path is None:
            raise ValueError("an explicit cohort directory requires a canonical root SWARM.md")
        root_text = _read(root_path)
        bound_brief, root_digest = parse_project_brief_markdown(root_text, root=root)
        _validate_history(root, bound_brief)
    names = ("project.md", "roadmap.md", "swarm.md", "design.md")
    targets = _targets(documents_root, names)
    before = {name: _read(path) for name, path in targets.items()}
    documents = []
    legacy = []
    brief = snapshot = None
    for name in names:
        text = before.get(name)
        kind = "MISSING" if text is None else "HUMAN_MARKDOWN"
        if name == "project.md" and text is not None and "<!-- swarm-project-index:" in text:
            snapshot = _parse_manifest(text)
            kind = "LEGACY_INDEX"
        if name == "swarm.md" and text is not None and "<!-- swarm-project-brief:" in text:
            brief, _ = parse_project_brief_markdown(text, root=documents_root)
            _validate_history(documents_root, brief)
            kind = "LEGACY_BRIEF"
        if kind.startswith("LEGACY_"):
            legacy.append(name)
        documents.append({"name": name, "path": targets[name].name if name in targets else None,
                          "kind": kind, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()
                          if text is not None else None})
    if snapshot is not None and brief is not None and snapshot["project"]["id"] != brief["project"]["id"]:
        raise ValueError("SWARM.md and project.md identities conflict; preserved")
    if bound_brief is not None and brief is not None and bound_brief["project"]["id"] != brief["project"]["id"]:
        raise ValueError("cohort brief belongs to another project; preserved")
    if bound_brief is not None and snapshot is not None and bound_brief["project"]["id"] != snapshot["project"]["id"]:
        raise ValueError("cohort index belongs to another project; preserved")
    if _targets(documents_root, names) != targets or any(_read(path) != before[name] for name, path in targets.items()):
        raise ValueError("project documents changed during alignment; rerun after custody reconciliation")
    if root_path is not None and (_targets(root, ("SWARM.md",)) != roots or _read(root_path) != root_text):
        raise ValueError("canonical root brief changed during alignment")
    missing = [row["name"] for row in documents if row["kind"] == "MISSING"]
    status = ("LEGACY_LAYOUT" if legacy else "MISSING" if len(missing) == len(names)
              else "PARTIAL" if missing else "PROVISIONAL")
    cohort = json.dumps(documents, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cohort_digest = "sha256:" + hashlib.sha256(cohort.encode("utf-8")).hexdigest()
    binding = {"root": str(root), "documents_root": str(documents_root),
               "canonical_brief_digest": root_digest,
               "root_sha256": hashlib.sha256(root_text.encode("utf-8")).hexdigest() if root_text is not None else None,
               "cohort_digest": cohort_digest}
    binding_digest = "sha256:" + hashlib.sha256(json.dumps(
        binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    questions = [
        {"id": "outcome", "text": "What should this project achieve, and what would prove it is complete?"},
        {"id": "boundaries", "text": "What must remain out of scope or unchanged?"},
    ]
    answers = {}
    if staged_answers is not None:
        if (not isinstance(staged_answers, dict) or set(staged_answers) != {"binding_digest", "answers"}
                or staged_answers["binding_digest"] != binding_digest):
            raise ValueError("staged answers require the exact current project/cohort binding")
        answers = staged_answers["answers"]
        adaptive_ids = {"baseline", "correction", "correction_proof", "decision_prompt", "decision", "decision_correction", "decision_proof", "wording", "wording_correction", "draft_digest", "draft_confirmation", "revision"}
        if (not isinstance(answers, dict) or set(answers) - ({q["id"] for q in questions} | adaptive_ids)
                or any(not isinstance(v, str) or not v.strip() or len(v.encode("utf-8")) > 2000 for v in answers.values())):
            raise ValueError("staged answers must contain only bounded nonempty answers to known questions")
    answers_digest = "sha256:" + hashlib.sha256(json.dumps(
        answers, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    pending = [q for q in questions if q["id"] not in answers]
    ready = status == "PROVISIONAL" and (not questions_enabled or not pending)
    review_digest = "sha256:" + hashlib.sha256((binding_digest + answers_digest).encode("ascii")).hexdigest()
    return {"status": status, "root": str(root), "documents": documents,
            "documents_root": str(documents_root), "cohort_digest": cohort_digest,
            "source_binding": binding, "binding_digest": binding_digest,
            "review_digest": review_digest, "answers_digest": answers_digest,
            "answered_question_ids": [q["id"] for q in questions if q["id"] in answers],
            "ready_for_explicit_review": ready,
            "missing": missing, "legacy": legacy, "questions_enabled": questions_enabled,
            "question_source": question_source, "config_exists": config_exists,
            "questions": pending if questions_enabled else [],
            "approval_verified": False, "requires_explicit_approval": True, "created": [],
            "next_action": "REVIEW_LEGACY_MIGRATION" if legacy else
                           "GUIDED_ALIGNMENT" if questions_enabled and pending else "EXPLICIT_BASELINE_REVIEW",
            "claim_limit": "Read-only alignment plan. No baseline approval, migration, host binding or task-state refresh."}


def alignment_review_artifact(root: Path, **alignment_options) -> ArtifactIdentity:
    """Bind the current cohort/answers to the existing runtime artifact contract."""
    plan = plan_alignment(root, **alignment_options)
    staged = alignment_options.get("staged_answers")
    if staged is not None and "baseline" in staged["answers"]:
        def incomplete(_):
            raise ValueError("adaptive alignment requires a completed exact-draft response before review")
        aligned = _adaptive_alignment(root, cohort_dir=alignment_options.get("cohort_dir"),
                                      config_path=alignment_options.get("config_path"),
                                      staged_answers=staged, ask=incomplete)
        if aligned["status"] != "DRAFT_READY_FOR_EXACT_REVIEW":
            raise ValueError("adaptive alignment requires a completed exact-draft response before review")
        plan = aligned["plan"]
    if not plan["ready_for_explicit_review"]:
        raise ValueError("alignment must have a complete human cohort and resolved questions before review")
    root = Path(plan["root"])
    documents_root = Path(plan["documents_root"])
    files = {str((documents_root / row["path"]).relative_to(root).as_posix()): "file:" + row["sha256"]
             for row in plan["documents"]}
    if plan["source_binding"]["root_sha256"] is not None:
        path = _targets(root, ("SWARM.md",))["SWARM.md"]
        files[path.name] = "file:" + plan["source_binding"]["root_sha256"]
    artifact = ArtifactIdentity(str(root), plan["review_digest"], "init-baseline-review",
                                tuple(files.items()), tuple(files))
    if artifact.reobserve(str(root)) != artifact:
        raise ValueError("alignment source changed before review binding")
    return artifact


def register_alignment_review(root: Path, swarm: Swarm, stage_id: str, decision_event_receipt: str,
                              *, accepted_at: int, due, **alignment_options):
    """Register only an exact live staged review; never mint approval from answers."""
    root = Path(os.path.abspath(root))
    if (not isinstance(swarm, Swarm) or swarm.request_store is None
            or swarm.request_store.repo_root != root.resolve()):
        raise ValueError("alignment review requires the live Swarm request authority for this exact root")
    artifact = alignment_review_artifact(root, **alignment_options)
    state, _, _ = swarm.request_store.peek()
    stage = state["stages"].get(stage_id)
    task = swarm.tasks.get(stage["task_id"]) if stage is not None else None
    if task is None or task.acceptance_contract is None or task.acceptance_contract.artifact != artifact:
        raise ValueError("staged review does not bind the current exact cohort and answers")
    if artifact.reobserve(str(root)) != artifact:
        raise ValueError("alignment source changed before review registration")
    return swarm.accept_request(Role.CTRL, stage_id, decision_event_receipt, accepted_at=accepted_at, due=due)


def space_snapshot(root: Path, *, cohort_dir: Path) -> dict:
    """Explicit-refresh Markdown payload only; no publication or live-state inference."""
    plan = plan_alignment(root, cohort_dir=cohort_dir, questions_enabled=False)
    if plan["status"] != "PROVISIONAL" or plan["source_binding"]["root_sha256"] is None:
        raise ValueError("Space snapshot requires a complete separate human cohort and canonical root brief")
    root = Path(plan["root"])
    brief_path = _targets(root, ("SWARM.md",))["SWARM.md"]
    brief_text = _read(brief_path)
    if hashlib.sha256(brief_text.encode("utf-8")).hexdigest() != plan["source_binding"]["root_sha256"]:
        raise ValueError("canonical brief changed before Space refresh")
    brief, canonical_digest = parse_project_brief_markdown(brief_text, root=root)
    documents = []
    for row in plan["documents"]:
        path = Path(plan["documents_root"]) / row["path"]
        text = _read(path)
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != row["sha256"]:
            raise ValueError("cohort changed before Space refresh")
        documents.append({"name": row["name"], "source_path": path.relative_to(root).as_posix(),
                          "sha256": row["sha256"], "markdown": text})
    records = {}
    display_fields = ("id", "title", "state", "owner_id", "milestone_id", "task_ids", "dependency_ids",
                      "roadmap_order", "planning_status", "execution_status")
    for kind in ("milestones", "tasks"):
        values = brief.get(kind)
        if values is not None and not isinstance(values, list):
            raise ValueError(f"Space snapshot requires a declared {kind} list, not a guessed conversion")
        if values is not None and (any(not isinstance(value, dict) or not isinstance(value.get("id"), str)
                                       or not value["id"].strip() for value in values)
                                   or len({value["id"] for value in values}) != len(values)):
            raise ValueError(f"Space snapshot requires unique declared {kind} identities")
        for value in values or ():
            for key in display_fields:
                if key not in value:
                    continue
                item = value[key]
                valid = (type(item) is int if key == "roadmap_order" else
                         isinstance(item, list) and all(isinstance(i, str) for i in item)
                         if key in {"task_ids", "dependency_ids"} else isinstance(item, str))
                if not valid:
                    raise ValueError(f"invalid Space display field: {kind}.{key}")
        records[kind] = None if values is None else [
            {"source_pointer": f"/{kind}/{i}", "value": {key: value[key] for key in display_fields if key in value},
             "source_record_digest": "sha256:" + hashlib.sha256(json.dumps(
                 value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()}
            for i, value in enumerate(values)]
    if plan_alignment(root, cohort_dir=cohort_dir, questions_enabled=False)["binding_digest"] != plan["binding_digest"]:
        raise ValueError("source changed during Space refresh; previous accepted snapshot must be preserved")
    for kind in ("milestones", "tasks"):
        for row, original in zip(records[kind] or (), brief.get(kind) or ()):
            if "title" not in row["value"] and isinstance(original.get("name"), str):
                row["value"]["title"] = original["name"]
    snapshot = {"project_id": brief["project"]["id"], "source_version": brief.get("updated_at"),
                "project_name": brief["project"].get("name"),
                "objective": brief.get("objective", {}).get("current"),
                "source_file_sha256": plan["source_binding"]["root_sha256"], "canonical_digest": canonical_digest,
                "binding_digest": plan["binding_digest"], "cursor": None, "records": records, "documents": documents}
    snapshot_digest = "sha256:" + hashlib.sha256(json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"status": "REFRESHED_LOCAL_SOURCE_SNAPSHOT_NOT_PUBLISHED", "snapshot": snapshot,
            "snapshot_digest": snapshot_digest, "refreshed_at_utc": datetime.now(timezone.utc).isoformat(),
            "destination": None, "approval_verified": False, "source_admission": "UNVERIFIED_BY_THIS_SNAPSHOT",
            "claim_limit": "Explicit-refresh source projection only; no live cursor, human approval or Space publication."}


def space_view_html(payload: dict, *, reference_html: Path, reference_sha256: str) -> dict:
    """Export an exact source snapshot, not a publisher, host bridge or approval."""
    if not isinstance(payload, dict):
        raise ValueError("Space HTML requires an existing source snapshot")
    snapshot = payload.get("snapshot")
    digest = "sha256:" + hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if payload.get("status") != "REFRESHED_LOCAL_SOURCE_SNAPSHOT_NOT_PUBLISHED" or not isinstance(snapshot, dict) or payload.get("snapshot_digest") != digest:
        raise ValueError("Space HTML requires an exact existing source snapshot digest")
    _regular(reference_html)
    if reference_html.stat().st_size > 256 * 1024:
        raise ValueError("Space HTML reference exceeds the existing visualization limit")
    original = reference_html.read_bytes()
    if not re.fullmatch(r"[a-f0-9]{64}", reference_sha256) or hashlib.sha256(original).hexdigest() != reference_sha256:
        raise ValueError("Space HTML reference differs from the selected immutable Space original")
    styles = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", original.decode("utf-8"), re.S | re.I))
    if not styles:
        raise ValueError("selected Space original has no styles")
    # Bind the selected .ms-* composition directly. Neither its illustrative
    # scripts nor the separate portable .stv renderer runs in this export.
    view = {key: snapshot[key] for key in ("project_id", "source_version", "source_file_sha256", "canonical_digest", "binding_digest", "cursor", "records")}
    # Display a declared name or exact ID, never invent a milestone title.
    view["records"] = {kind: None if rows is None else [
        {**row, "value": {**row["value"], "title": row["value"].get("title") or row["value"]["id"]}}
        for row in rows] for kind, rows in snapshot["records"].items()}
    data = json.dumps(view, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    esc = lambda value: html.escape(str(value), quote=True)
    objective = snapshot.get("objective")
    goal = objective.strip() if isinstance(objective, str) and objective.strip() else "Goal unavailable in this source snapshot"
    observed = payload.get("refreshed_at_utc")
    if not isinstance(observed, str) or not observed.strip():
        raise ValueError("Space HTML requires the snapshot observation time")
    owners = [(row["value"]["id"], row["value"].get("owner_id")) for row in snapshot["records"].get("tasks") or []]
    owner_rows = "".join("<li>" + esc(task) + ": " + esc(owner or "UNKNOWN") + " · owner link UNKNOWN</li>" for task, owner in owners)
    draft_planning = any(str(row["value"].get("planning_status", "")).startswith("DRAFT_")
                         for rows in snapshot["records"].values() for row in rows or [])
    baseline_label = ("Draft planning · " if draft_planning else "") + "Baseline alignment unverified"
    name = snapshot.get("project_name")
    project_label = name.strip() if isinstance(name, str) and name.strip() else snapshot["project_id"]
    brand = (Path(__file__).resolve().parents[3] / "console/static/swarm-icon-64.png").read_bytes()
    brand_uri = "data:image/png;base64," + base64.b64encode(brand).decode("ascii")
    composition = '''
body{margin:0;background:#091321}
.space-snapshot{font:14px/1.5 system-ui,sans-serif}
.space-snapshot .space-header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.space-snapshot .space-brand{display:flex;align-items:center;gap:8px;margin:0;font:inherit;font-weight:600}
.space-snapshot .space-brand img{width:28px;height:28px;object-fit:contain}
.space-snapshot .space-baseline{margin:0;color:#a9bace;font-size:.8125rem}
.space-snapshot .ms-goal{height:auto;min-height:0;overflow:visible}
.space-snapshot .ms-goal-heading{display:block;height:auto;min-height:0;white-space:normal;overflow-wrap:anywhere}
.space-snapshot [hidden]{display:none!important}
.space-snapshot .ms-tasktop a{white-space:normal;overflow-wrap:anywhere;text-overflow:clip}
.space-snapshot .ms-track[data-measurement=UNKNOWN]>span,.space-snapshot .ms-goal-track[data-measurement=UNKNOWN]>span{display:none}
.space-snapshot .ms-record dl{overflow-wrap:anywhere}
.space-snapshot .ms-record dd{margin:0 0 12px}
.space-snapshot dialog[data-inspector]{position:fixed;inset:96px 16px 16px auto;width:min(360px,calc(100vw - 32px));max-width:none;max-height:none;margin:0;padding:16px;border:1px solid #455d75;border-radius:10px;background:#0d1a29;color:#e9eff7;display:flex;flex-direction:column;gap:16px;overflow:hidden}
.space-snapshot dialog[data-inspector]:not([open]){display:none!important}
.space-snapshot dialog[data-inspector] .inspector-top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex:none}
.space-snapshot dialog[data-inspector] .inspector-top h2{margin:0;font-size:16px}
.space-snapshot dialog[data-inspector] [data-close-inspector]{min-width:44px;min-height:44px;font:inherit}
.space-snapshot dialog[data-inspector] .inspector-body{min-height:0;overflow-y:auto;overscroll-behavior:contain;flex:1}
.space-snapshot dialog[data-inspector]::backdrop{background:#0409107a}
.space-snapshot:has(dialog[data-inspector][open][data-mobile=false]) .swarm-milestones{padding-right:376px}
.space-snapshot .ms-task:has([aria-current=true]){outline:1px solid #79d8de;outline-offset:-1px}
html:has(dialog[data-inspector][open][data-mobile=true]){overflow:hidden}
@media(max-width:720px){.space-snapshot dialog[data-inspector]{inset:auto 0 0;width:100%;max-height:85vh;max-height:85dvh;padding:16px max(16px,env(safe-area-inset-right)) max(16px,env(safe-area-inset-bottom)) max(16px,env(safe-area-inset-left));border-bottom:0;border-radius:18px 18px 0 0}}
.space-snapshot .ms-chevron svg{width:16px;height:16px}
.space-snapshot .ms-group>summary{display:grid;grid-template-columns:24px minmax(0,1fr) auto 18px;gap:8px 12px;align-items:center}
.space-snapshot .ms-group>summary>span{float:none;margin:0;min-width:0}
.space-snapshot .ms-group>summary>[data-milestone-mark]{grid-column:1;grid-row:1}
.space-snapshot .ms-group>summary>span:nth-child(2){grid-column:2;grid-row:1;overflow-wrap:anywhere}
.space-snapshot .ms-group>summary>.ms-summary-meta{grid-column:3;grid-row:1}
.space-snapshot .ms-group>summary>.ms-track{grid-column:2 / 4;grid-row:2;width:100%;margin:0}
.space-snapshot .ms-group>summary>.ms-chevron{grid-column:4;grid-row:1 / 3}
.space-snapshot .ms-group[open]>summary>.ms-chevron{transform:rotate(90deg)}
@media(max-width:520px){.space-snapshot .ms-group>summary{grid-template-columns:24px minmax(0,1fr) 18px}.space-snapshot .ms-group>summary>.ms-summary-meta{grid-column:2;grid-row:2;justify-content:flex-start}.space-snapshot .ms-group>summary>.ms-track{grid-column:2;grid-row:3}.space-snapshot .ms-group>summary>.ms-chevron{grid-column:3;grid-row:1 / 4}}
'''
    icons = {
        "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
        "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
        "help": '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3m.1 4h.01"/>',
        "check": '<path d="m9 12 2 2 4-4"/><circle cx="12" cy="12" r="10"/>',
        "alert": '<circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/>',
        "chevron": '<path d="m9 6 6 6-6 6"/>',
    }
    def icon(name):
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + icons[name] + '</svg>'

    states = {"OPEN": ("Open", "clock", "muted"), "ACTIVE": ("Active", "activity", "orange"),
              "ACCEPTANCE_OPEN": ("Acceptance open", "help", "blue"),
              "IMPLEMENTATION_OPEN": ("Implementation open", "activity", "orange"),
              "COMPLETE_LOCAL_SOURCE": ("Local source complete", "check", "green"),
              "ACCEPTED_LOCAL_WEB": ("Local web accepted", "check", "green"),
              "BLOCKED": ("Blocked", "alert", "red"), "COMPLETED": ("Completed (declared)", "check", "green")}
    def state(value, *, with_icon=True):
        label, symbol, tone = states.get(str(value or "").upper(), (str(value or "Unknown").replace("_", " "), "help", "muted"))
        return '<span class="ms-status ms-' + tone + '" data-source-state="' + esc(value or "UNKNOWN") + '">' + (icon(symbol) if with_icon else '') + '<span>' + esc(label) + '</span></span>'

    task_rows = view["records"].get("tasks")
    milestone_rows = view["records"].get("milestones")
    task_by_id = {row["value"]["id"]: row for row in task_rows or []}
    membership = {identity: set() for identity in task_by_id}
    for row in milestone_rows or []:
        for identity in row["value"].get("task_ids", []):
            if identity in membership:
                membership[identity].add(row["value"]["id"])
    for row in task_rows or []:
        if row["value"].get("milestone_id"):
            membership[row["value"]["id"]].add(row["value"]["milestone_id"])

    def task_markup(row):
        value = row["value"]
        identity = esc(value["id"])
        return ('<div class="ms-task" data-task-id="' + identity + '"><div class="ms-tasktop"><a href="#space-record" data-record-id="' + identity + '">' + esc(value["title"]) + '</a><span data-status>' + state(value.get("state")) + '</span></div></div>')

    groups = []
    shown = set()
    for index, row in enumerate(milestone_rows or []):
        value = row["value"]
        identity = value["id"]
        linked = list(dict.fromkeys([*value.get("task_ids", []), *(task_id for task_id, parents in membership.items() if parents == {identity})]))
        children = []
        for task_id in linked:
            task = task_by_id.get(task_id)
            if task is not None and membership[task_id] == {identity}:
                children.append(task_markup(task)); shown.add(task_id)
            elif task is None:
                children.append('<p class="ms-muted" data-missing-task-id="' + esc(task_id) + '">' + esc(task_id) + ' · task record unavailable</p>')
        mark = states.get(str(value.get("state", "")).upper(), (None, 'help', None))[1]
        empty = 'Task records not declared.' if task_rows is None else 'No tasks declared for this milestone.'
        groups.append('<details class="ms-group" data-group="' + esc(identity) + '" data-milestone-id="' + esc(identity) + '"' + (' open' if index == 0 else '') + '><summary><span data-milestone-mark>' + icon(mark) + '</span><span>' + esc(value["title"]) + '</span><span class="ms-summary-meta">' + state(value.get("state"), with_icon=False) + '</span><span class="ms-track" data-measurement="UNKNOWN" role="img" aria-label="Milestone progress unknown"><span hidden></span></span><span class="ms-chevron" aria-hidden="true">' + icon('chevron') + '</span></summary><div class="ms-rows">' + (''.join(children) or '<p class="ms-muted">' + empty + '</p>') + '</div></details>')
    unbound = [row for row in task_rows or [] if row["value"]["id"] not in shown]
    if unbound:
        groups.append('<details class="ms-group" data-unbound><summary>Unbound or conflicting task membership</summary><div class="ms-rows">' + ''.join(task_markup(row) for row in unbound) + '</div></details>')
    progress_markup = ''.join(groups) if milestone_rows is not None else '<p>Milestones not declared.</p>'
    tasks_markup = ''.join(task_markup(row) for row in task_rows or []) if task_rows is not None else '<p>Tasks not declared.</p>'
    interactions = '''
const sourceSnapshot=SNAPSHOT;
const host=document.getElementById('swarm-constellation-test'),detail=document.getElementById('space-record'),narrow=matchMedia('(max-width:720px)');let returnLink=null;
host.querySelectorAll('[data-layout]').forEach(button=>button.addEventListener('click',()=>{
  returnLink=null;if(detail.open)detail.close();
  host.querySelectorAll('[data-layout]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
  document.getElementById('space-progress').hidden=button.dataset.layout!=='milestones';
  document.getElementById('space-tasks').hidden=button.dataset.layout!=='inspector';
}));
host.querySelectorAll('[data-record-id]').forEach(link=>link.addEventListener('click',event=>{
  event.preventDefault();const row=(sourceSnapshot.records.tasks||[]).find(record=>record.value.id===link.dataset.recordId);if(!row)return;
  const body=detail.querySelector('[data-record-body]');body.replaceChildren();
  const heading=document.createElement('h3');heading.textContent=row.value.title;body.append(heading);
  const fields=[['Task ID',row.value.id],['Declared state',row.value.state||'UNKNOWN'],['Owner',row.value.owner_id||'UNKNOWN'],['Owner link','UNKNOWN'],['Source pointer',row.source_pointer],['Record digest',row.source_record_digest]];
  const list=document.createElement('dl');fields.forEach(([label,value])=>{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;list.append(dt,dd)});body.append(list);
  returnLink=link;host.querySelectorAll('[data-record-id]').forEach(other=>other.setAttribute('aria-current',String(other.dataset.recordId===row.value.id)));
  detail.dataset.mobile=String(narrow.matches);detail.setAttribute('aria-modal',String(narrow.matches));
  if(!detail.open){if(narrow.matches)detail.showModal();else detail.show();}detail.querySelector('[data-close-inspector]').focus();
}));
detail.querySelector('[data-close-inspector]').addEventListener('click',()=>detail.close());
detail.addEventListener('close',()=>{if(returnLink?.isConnected)returnLink.focus()});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&detail.open){detail.close();event.preventDefault()}});
narrow.addEventListener('change',()=>{if(detail.open)detail.close()});
'''.replace('SNAPSHOT', data)
    project_suffix = '' if str(project_label).casefold() == 'swarm' else ' <span>· ' + esc(project_label) + '</span>'
    document = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; connect-src \'none\'; img-src data:; base-uri \'none\'; form-action \'none\'">'
        '<title>' + esc(project_label) + ' · SWARM</title><style>@layer swarm-reference{' + styles + '}\n' + composition + '</style>'
        '<main id="swarm-constellation-test" class="space-snapshot"><header class="space-header"><h2 class="space-brand"><img src="' + brand_uri + '" alt="" width="28" height="28">SWARM' + project_suffix + '</h2><p class="space-baseline">' + esc(baseline_label) + '</p></header>'
        '<nav class="toolbar" aria-label="Project views"><button type="button" data-layout="milestones" aria-pressed="true">Progress</button><button type="button" data-layout="inspector" aria-pressed="false">Tasks</button></nav>'
        '<section class="swarm-milestones"><section class="ms-goal"><div class="ms-goal-top"><div class="ms-goal-kicker">Goal</div></div><div class="ms-goal-heading">' + esc(goal) + '</div><div class="ms-goal-meter"><span data-goal-value>Unknown</span><div class="ms-goal-track" data-measurement="UNKNOWN" role="img" aria-label="Goal progress unknown"><span hidden></span></div></div></section>'
        '<section id="space-progress" aria-label="Milestones"><div class="ms-head">Milestones</div>' + progress_markup + '</section><section id="space-tasks" aria-label="Tasks" hidden><div class="ms-head">Tasks</div><div class="ms-rows">' + tasks_markup + '</div></section><dialog id="space-record" class="ms-record" data-inspector aria-labelledby="space-record-title"><div class="inspector-top"><h2 id="space-record-title">Task details</h2><button type="button" data-close-inspector aria-label="Close task details">Close</button></div><div class="inspector-body" data-record-body></div></dialog></section>'
        '<details><summary>Source details</summary><dl><dt>Revision</dt><dd>' + esc(snapshot["source_version"]) + '</dd><dt>Canonical digest</dt><dd>' + esc(snapshot["canonical_digest"]) + '</dd><dt>Captured</dt><dd><time>' + esc(observed) + '</time></dd></dl><ul>' + owner_rows + '</ul><p>No host cursor, verified owner links, live connection, writeback or approval is inferred.</p></details></main>'
        '<script>' + interactions + '</script></html>')
    raw = document.encode("utf-8")
    if len(raw) > 256 * 1024:
        raise ValueError("Space HTML exceeds the existing 256 KiB visualization limit")
    return {"status": "READY_SOURCE_BOUND_SPACE_HTML_NOT_PUBLISHED", "html": document,
            "html_sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
            "snapshot_digest": digest, "reference_sha256": hashlib.sha256(original).hexdigest(),
            "brand_sha256": hashlib.sha256(brand).hexdigest(), "baseline_label": baseline_label,
            "destination": None, "approval_verified": False,
            "claim_limit": "Explicit-refresh source projection only; no publication, host binding, owner-link verification or Space sidebar placement."}


def _adaptive_alignment(root: Path, *, cohort_dir=None, config_path=None, ask=None,
                        staged_answers=None, decision=None) -> dict:
    options = {"cohort_dir": cohort_dir, "config_path": config_path}
    plan = plan_alignment(root, staged_answers=staged_answers, **options)
    answers = dict(staged_answers["answers"]) if staged_answers is not None else {}
    if not plan["questions_enabled"]:
        return {"plan": plan, "draft_documents": None, "approval_verified": False}
    target = _targets(Path(plan["root"]), ("SWARM.md",)).get("SWARM.md")
    root_text = _read(target) if target is not None else ""
    brief = parse_project_brief_markdown(root_text, root=root)[0] if plan["source_binding"]["canonical_brief_digest"] is not None else {}
    objective = brief.get("objective", {})
    summary = {"project_id": brief.get("project", {}).get("id"),
               "objective": objective.get("current"), "documents": [row["name"] for row in plan["documents"]],
               "binding_digest": plan["binding_digest"], "source_state": plan["status"],
               "legacy_root_excerpt": root_text[:1200] if root_text and not brief else None,
               "approval_verified": False}
    baseline_outcome = str(objective.get("current") or "Preserve the existing source baseline")
    encoded = json.dumps(decision, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if decision is not None else answers.get("decision_prompt")
    wording_question = None
    if encoded is not None:
        if len(encoded.encode("utf-8")) > 2000:
            raise ValueError("adaptive decision requires bounded explicit choices within the retained answer limit")
        question = json.loads(encoded)
        fields = {"question", "choices"}
        def checked(value):
            if (not isinstance(value, dict) or set(value) != fields
                    or not isinstance(value["question"], str) or not value["question"].strip() or len(value["question"]) > 2000
                    or not isinstance(value["choices"], list) or not 1 <= len(value["choices"]) <= 32
                    or any(not isinstance(item, str) or not item.strip() or len(item) > 2000 for item in value["choices"])
                    or len({item.strip().casefold() for item in value["choices"]}) != len(value["choices"])):
                raise ValueError("adaptive decision requires one bounded question and 1-32 unique explicit choices")
        if not isinstance(question, dict) or set(question) not in (fields, fields | {"clarification"}):
            raise ValueError("adaptive decision requires one bounded question and 1-32 unique explicit choices")
        checked({key: question[key] for key in fields})
        if "clarification" in question:
            clarification = question["clarification"]
            correction = answers.get("correction")
            baseline = answers.get("baseline")
            if (not isinstance(clarification, dict) or set(clarification) != fields | {"scope", "answer_digest"}
                    or clarification["scope"] != "WORDING" or not correction or not baseline
                    or (baseline not in {"1", "2", "3"} and baseline != correction)
                    or clarification["answer_digest"] != "sha256:" + hashlib.sha256(correction.encode("utf-8")).hexdigest()
                    or answers.get("outcome", baseline_outcome) != baseline_outcome):
                raise ValueError("wording clarification requires the exact retained answer and unchanged source baseline")
            wording_question = {key: clarification[key] for key in fields}
            checked(wording_question)
        if answers.get("decision_prompt", encoded) != encoded:
            prior = json.loads(answers["decision_prompt"])
            # Attach a bound clarification only to the exact unanswered pending decision.
            if not (wording_question is not None and isinstance(prior, dict) and set(prior) == fields
                    and all(prior[key] == question[key] for key in fields)
                    and not set(answers) & {"decision", "decision_correction", "decision_proof", "wording", "wording_correction", "draft_digest", "draft_confirmation"}):
                raise ValueError("decision changed; prior answers cannot bind a different question")
        answers["decision_prompt"] = encoded
    else:
        question = None

    def current():
        return plan_alignment(root, staged_answers={"binding_digest": plan["binding_digest"], "answers": answers}, **options)

    def answer(key, text):
        if key in answers:
            return answers[key]
        if ask is None:
            print(text, file=sys.stderr)
            value = sys.stdin.readline(2002)
        else:
            try:
                value = ask(text)
            except (EOFError, StopIteration):
                value = None
        if value is None or value == "":
            raise EOFError
        answers[key] = value.rstrip("\r\n") if isinstance(value, str) else value
        current()  # Same existing source/answer binding; source races fail here.
        return answers[key]

    def result(status, drafts=None, draft_digest=None):
        return {"status": status, "plan": current(), "source_summary": summary,
                "resume": {"binding_digest": plan["binding_digest"], "answers": dict(answers)},
                "draft_documents": drafts, "draft_digest": draft_digest, "approval_verified": False,
                "claim_limit": "Source-bound answers and unwritten drafts only; no human approval receipt, document adoption, host task or Space publication."}

    def choose(key, supplied):
        choices = {str(i): text for i, text in enumerate(supplied["choices"], 1)}
        custom = str(len(choices) + 1)
        prompt = supplied["question"] + "\n" + "\n".join(f"{i} {text}" for i, text in choices.items())
        selected = answer(key, prompt + f"\n{custom} None fit; describe your own answer.")
        if selected not in choices:
            if selected != custom:
                answers[key + "_correction"] = selected
            return answer(key + "_correction", "For ‘" + supplied["question"] + "’, what would you choose instead?")
        return None

    current()
    try:
        baseline = answer("baseline", "Current source baseline (not approval): " + json.dumps(summary, ensure_ascii=False) + "\n1 Keep this baseline; 2 Correct it; 3 Neither, describe your own direction.")
        if baseline not in {"1", "2", "3"}:
            answers["correction"] = baseline
        if baseline != "1":
            correction = answer("correction", "What should replace or change this source baseline?")
            if wording_question is None:
                answer("correction_proof", "For your direction ‘" + correction + "’, what observable result would settle it?")
        if wording_question is not None:
            choose("wording", wording_question)
        if question:
            alternative = choose("decision", question)
            if alternative is not None:
                answer("decision_proof", "For ‘" + alternative + "’, which boundary or check makes that acceptable?")
        answers.setdefault("outcome", baseline_outcome if wording_question is not None else answers.get("correction") or str(objective.get("current") or "Current outcome remains unspecified"))
        answers.setdefault("boundaries", "Preserve source-bound policies and non-goals at " + plan["binding_digest"])
        current()
        def draft():
            documents = {row["name"]: _read(Path(plan["documents_root"]) / row["path"]) for row in plan["documents"] if row["kind"] == "HUMAN_MARKDOWN"}
            notes = {key: value for key, value in answers.items() if key not in {"draft_digest", "draft_confirmation"}}
            name = "project.md" if "project.md" in documents else "alignment.md"
            documents[name] = documents.get(name, "# Proposed project baseline\n") + "\n\n## Alignment proposal (not adopted)\n\n```json\n" + json.dumps(notes, ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"
            revision = "sha256:" + hashlib.sha256(json.dumps(documents, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            return documents, revision
        drafts, digest = draft()
        if answers.get("draft_digest", digest) != digest:
            raise ValueError("draft changed; retained confirmation cannot approve another draft")
        answers["draft_digest"] = digest
        confirmation = answer("draft_confirmation", "Draft " + digest + " reflects these answers. 1 Keep for exact-version review; 2 Revise. This does not approve or write documents.")
        if confirmation != "1":
            answer("revision", "Which part of draft " + digest + " should change, and what should replace it?")
            answers.pop("draft_digest", None); answers.pop("draft_confirmation", None)
            drafts, digest = draft()
            return result("REVISION_REQUESTED", drafts, digest)
        return result("DRAFT_READY_FOR_EXACT_REVIEW", drafts, digest)
    except EOFError:
        return result("INTERRUPTED_RESUMABLE")


def interview_alignment(root: Path, *, cohort_dir: Path | None = None,
                        config_path: Path | None = None, ask=None, adaptive=False,
                        staged_answers=None, decision=None) -> dict:
    """Run the initial human interview and return drafts, never write or approve them."""
    if adaptive:
        return _adaptive_alignment(root, cohort_dir=cohort_dir, config_path=config_path, ask=ask,
                                   staged_answers=staged_answers, decision=decision)
    options = {"cohort_dir": cohort_dir, "config_path": config_path}
    plan = plan_alignment(root, **options)
    answers = {}
    for question in plan["questions"]:
        if ask is None:
            print(question["text"], file=sys.stderr)
            answer = sys.stdin.readline(2002)
            if not answer:
                raise ValueError("interview ended before the answer; no documents or approval were written")
            answer = answer.rstrip("\r\n")
        else:
            answer = ask(question["text"])
        answers[question["id"]] = answer
        current = plan_alignment(root, staged_answers={"binding_digest": plan["binding_digest"], "answers": answers}, **options)
    if not answers:
        return {"plan": plan, "draft_documents": None, "claim_limit": "Questions disabled; no answers, drafts or approval invented."}
    drafts = {
        "project.md": f"# Project\n\nDraft pending exact-version review.\n\n## Objective\n\n{answers['outcome']}\n\n## Boundaries\n\n{answers['boundaries']}\n",
        "roadmap.md": "# Roadmap\n\nDraft pending review. Milestones, dependencies and task states remain in canonical root SWARM.md; no dates or completion inferred.\n",
        "design.md": "# Design\n\nDraft pending review. Preserve the project's accepted visual references. Unspecified brand and interaction choices remain open.\n",
        "swarm.md": "# Working agreement\n\nDraft pending review. Use the installed SWARM skill's task-contract, hierarchy and review-contract references. Project bindings and acceptance remain with their existing owners.\n",
    }
    draft_digest = "sha256:" + hashlib.sha256(json.dumps(
        drafts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"plan": current, "draft_documents": drafts, "draft_digest": draft_digest,
            "source_review_digest": current["review_digest"], "approval_verified": False,
            "claim_limit": "Initial two-question alignment and unwritten proposals only; not full adaptive grill-me, approval, installation or publication."}


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
    brief, digest = parse_project_brief_markdown(brief_text, root=root)
    _validate_history(root, brief)
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
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--plan", action="store_true", help="inspect four-document alignment without writing")
    action.add_argument("--space-snapshot", action="store_true", help="print a source-bound four-document Space payload without publishing")
    action.add_argument("--space-html", action="store_true", help="print compact source-bound Space HTML without publishing")
    action.add_argument("--interview", action="store_true", help="ask initial alignment questions and print unwritten four-document proposals")
    action.add_argument("--archive-section", help="archive one selected optional legacy section losslessly")
    action.add_argument("--compact-brief", action="store_true", help="retain full canonical detail in digest-bound history and write a short human index")
    parser.add_argument("--expected-sha256", help="exact current brief bytes required for history migration")
    parser.add_argument("--config", type=Path, help="one existing config authority for read-only alignment")
    parser.add_argument("--cohort-dir", type=Path, help="existing root-relative human-document directory; preserves root/index")
    parser.add_argument("--answers", type=Path, help="bounded staged-answer JSON bound to the exact project/cohort")
    parser.add_argument("--reference-html", type=Path, help="exact selected immutable Space HTML reference; used only with --space-html")
    parser.add_argument("--reference-sha256", help="expected immutable reference file SHA-256; identity, not design approval")
    parser.add_argument("--adaptive", action="store_true", help="document-led --interview with source-bound resume and exact-draft review")
    parser.add_argument("--decision", help="one bounded JSON question with 1-32 unique explicit choices for --interview --adaptive")
    parser.add_argument("--no-questions", action="store_true", help="plan without questions; explicit approval still required")
    args = parser.parse_args()
    if args.no_questions and not args.plan:
        parser.error("--no-questions requires --plan")
    if args.config is not None and not (args.plan or args.interview):
        parser.error("--config requires --plan or --interview")
    if (args.adaptive or args.decision is not None) and not args.interview:
        parser.error("--adaptive and --decision require --interview")
    if args.decision is not None and (not args.adaptive or len(args.decision.encode("utf-8")) > 2000):
        parser.error("--decision requires --adaptive and at most 2000 UTF-8 bytes")
    if args.answers is not None and not (args.plan or (args.interview and args.adaptive)):
        parser.error("--cohort-dir and --answers require --plan")
    if (args.reference_html is not None or args.reference_sha256 is not None) and not args.space_html:
        parser.error("--reference-html requires --space-html")
    if args.cohort_dir is not None and not (args.plan or args.space_snapshot or args.space_html or args.interview):
        parser.error("--cohort-dir and --answers require --plan or --space-snapshot or --interview")
    if bool(args.archive_section or args.compact_brief) != bool(args.expected_sha256):
        parser.error("--archive-section or --compact-brief requires --expected-sha256")
    try:
        if args.compact_brief:
            root = Path(os.path.abspath(args.root))
            targets = _targets(root)
            if "SWARM.md" not in targets:
                raise ValueError("canonical SWARM.md is required")
            result = compact_project_brief(targets["SWARM.md"], expected_sha256=args.expected_sha256)
        elif args.archive_section:
            result = archive_brief_section(args.root, args.archive_section, expected_sha256=args.expected_sha256)
        elif args.space_snapshot or args.space_html:
            if args.cohort_dir is None:
                raise ValueError("--space-snapshot requires an explicit --cohort-dir")
            result = space_snapshot(args.root, cohort_dir=args.cohort_dir)
            if args.space_html:
                if args.reference_html is None or args.reference_sha256 is None:
                    raise ValueError("--space-html requires exact --reference-html and --reference-sha256")
                result = space_view_html(result, reference_html=args.reference_html, reference_sha256=args.reference_sha256)
        elif args.interview:
            answers = None
            if args.answers is not None:
                _regular(args.answers)
                answers = json.loads(_read(args.answers, limit=8192))
            result = interview_alignment(args.root, cohort_dir=args.cohort_dir, config_path=args.config,
                                         adaptive=args.adaptive, staged_answers=answers,
                                         decision=json.loads(args.decision) if args.decision is not None else None)
        else:
            answers = None
            if args.answers is not None:
                _regular(args.answers)
                answers = json.loads(_read(args.answers, limit=8192))
            result = plan_alignment(args.root, questions_enabled=False if args.no_questions else None,
                                    config_path=args.config, cohort_dir=args.cohort_dir,
                                    staged_answers=answers) if args.plan else initialize(args.root)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
