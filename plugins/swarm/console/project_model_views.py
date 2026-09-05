from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.swarm.runtime import ArtifactIdentity  # noqa: E402


VIEW_SPECS = (
    ("view.project.overview-health", "Overview", "document", "blocks", ("/objective", "/risks_blockers", "/proof_acceptance"), ()),
    ("view.project.roadmap", "Roadmap", "timeline", "milestones", ("/milestones",), ()),
    ("view.project.work", "Work", "table", "records", ("/milestones", "/tasks"), ("/blocks",)),
    ("view.project.flow", "Flow", "canvas", "network", ("/objective", "/objective/ranked_outcomes", "/milestones", "/tasks", "/risks_blockers", "/artifacts"), ()),
    ("view.project.artifacts", "Artifacts", "gallery", "list", ("/artifacts", "/proof_acceptance"), ()),
    ("view.project.agents", "Agents", "table", "records", ("/authority", "/ownership"), ()),
)
LENS_VIEW_IDS = {
    "lens-overview-health": "view.project.overview-health",
    "lens-roadmap-milestones": "view.project.roadmap",
    "lens-tasks-kanban": "view.project.work",
    "lens-flow-architecture": "view.project.flow",
    "lens-artifacts-proof": "view.project.artifacts",
    "lens-agents": "view.project.agents",
}
_TYPE_ORDER = {"outcome": 0, "milestone": 1, "task": 2, "block": 3, "blocker": 4, "artifact": 5}
_BRIEF_MARKER = "<!-- swarm-project-brief:schema=1 -->"
_BRIEF_FENCE = re.compile(r"```json[ \t]*\r?\n(?P<payload>[\s\S]*?)(?=\r?\n```)", re.IGNORECASE)
_BRIEF_REQUIRED = {
    "schema_version", "updated_at", "project", "users_outcomes", "objective", "repo",
    "authority", "milestones", "decisions", "ownership", "proof_acceptance",
    "risks_blockers", "links",
}
_LIFECYCLE_COLLECTIONS = frozenset({"goals", "milestones", "tasks", "blocks", "risks_blockers"})
_REOPENABLE_STATES = frozenset({
    "complete", "completed", "accepted", "cancelled", "canceled", "closed",
    "archived", "archived_stale", "tombstoned",
})
_LIFECYCLE_FIELDS = frozenset({
    "label", "name", "task_name", "summary", "outcome", "description", "state", "rank", "role_scope",
    "goal_refs", "milestone_id", "milestone_ref", "task_id", "task_ids", "dependency_ids", "blocker_ids",
    "affected_ids", "acceptance_criteria", "artifact_ids", "artifact_refs", "release_condition",
    "suggested_recovery", "critical_path", "attempts", "note",
})
# ponytail: process-local serialization; add a host-owned cross-process lock only if multiple writers are introduced.
_UPDATE_LOCK = threading.Lock()
_MAX_BRIEF_BYTES = 512 * 1024


class ProjectModelError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _finite_json(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _finite_json(item) for key, item in value.items())
    return True


def parse_project_brief_markdown(text: str, *, project_id: str | None = None) -> tuple[dict[str, Any], str]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > _MAX_BRIEF_BYTES:
        raise ProjectModelError("project brief must be bounded UTF-8 text")
    if text.count(_BRIEF_MARKER) != 1:
        raise ProjectModelError("project brief requires exactly one schema-1 marker")
    matches = list(_BRIEF_FENCE.finditer(text))
    if len(matches) != 1:
        raise ProjectModelError("project brief requires exactly one JSON document")

    try:
        document = json.loads(matches[0].group("payload"), parse_constant=_reject_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProjectModelError("project brief JSON is invalid") from exc
    if not isinstance(document, dict) or not _BRIEF_REQUIRED.issubset(document):
        raise ProjectModelError("project brief is missing required fields")
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1 or not _finite_json(document):
        raise ProjectModelError("project brief schema is unsupported")
    if not isinstance(document.get("updated_at"), str) or not document["updated_at"].strip():
        raise ProjectModelError("project brief timestamp is invalid")
    for field in ("project", "objective", "repo", "authority", "ownership", "proof_acceptance"):
        if not isinstance(document.get(field), dict):
            raise ProjectModelError(f"project brief field {field} is invalid")
    for field in ("users_outcomes", "milestones", "decisions", "risks_blockers", "links"):
        if not isinstance(document.get(field), list):
            raise ProjectModelError(f"project brief field {field} is invalid")
    for field in ("tasks", "blocks", "artifacts"):
        if field in document and (
            not isinstance(document[field], list) or any(not isinstance(item, dict) for item in document[field])
        ):
            raise ProjectModelError(f"project brief field {field} is invalid")
    lens_ids = document.get("proposed_lens_ids", [])
    if (
        not isinstance(lens_ids, list)
        or len(lens_ids) > 32
        or any(not isinstance(item, str) or not item.strip() for item in lens_ids)
        or len({item.casefold() for item in lens_ids}) != len(lens_ids)
    ):
        raise ProjectModelError("project brief proposed_lens_ids is invalid")
    actual_project_id = document["project"].get("id")
    if not isinstance(actual_project_id, str) or not actual_project_id.strip():
        raise ProjectModelError("project brief project.id is invalid")
    if project_id is not None and actual_project_id.casefold() != project_id.casefold():
        raise ProjectModelError("project brief belongs to another project")
    return document, f"sha256:{_digest(document)}"


def render_project_brief_markdown(text: str, document: Mapping[str, Any]) -> str:
    current, _ = parse_project_brief_markdown(text)
    replacement = dict(document)
    if replacement == current:
        return text
    rendered = json.dumps(replacement, ensure_ascii=False, indent=2)
    if "\r\n" in text:
        rendered = rendered.replace("\n", "\r\n")
    match = next(iter(_BRIEF_FENCE.finditer(text)))
    candidate = text[:match.start("payload")] + rendered + text[match.end("payload"):]
    parse_project_brief_markdown(candidate, project_id=str(current["project"]["id"]))
    return candidate


def update_project_brief(
    path: Path,
    *,
    expected_digest: str,
    collection: str,
    record_id: str,
    state: str,
    updated_at: str,
) -> str:
    return mutate_project_brief(
        path,
        expected_digest=expected_digest,
        operation="update",
        collection=collection,
        record_id=record_id,
        changes={"state": state},
        updated_at=updated_at,
    )


def mutate_project_brief(
    path: Path,
    *,
    expected_digest: str,
    operation: str,
    collection: str,
    record_id: str,
    changes: Mapping[str, Any],
    updated_at: str,
) -> str:
    """Persist create/update/reopen; a process restart only reparses these bytes."""
    with _UPDATE_LOCK:
        return _mutate_project_brief(
            path,
            expected_digest=expected_digest,
            operation=operation,
            collection=collection,
            record_id=record_id,
            changes=changes,
            updated_at=updated_at,
        )


def _mutate_project_brief(
    path: Path,
    *,
    expected_digest: str,
    operation: str,
    collection: str,
    record_id: str,
    changes: Mapping[str, Any],
    updated_at: str,
) -> str:
    if path.name != "SWARM.md" or path.is_symlink() or not path.is_file():
        raise ProjectModelError("project brief path must be an existing regular SWARM.md")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProjectModelError("project brief is unreadable") from exc
    document, digest = parse_project_brief_markdown(text)
    if digest != expected_digest:
        raise ProjectModelError("project brief digest conflict")
    if collection not in _LIFECYCLE_COLLECTIONS:
        raise ProjectModelError("project brief collection is not editable")
    if (
        not isinstance(record_id, str) or not record_id.strip()
        or len(record_id.strip().encode("utf-8")) > 128
        or any(ord(char) < 32 for char in record_id)
    ):
        raise ProjectModelError("project brief record id is invalid")
    record_id = record_id.strip()
    if not isinstance(updated_at, str) or not updated_at.strip():
        raise ProjectModelError("project brief timestamp is invalid")
    if operation not in {"create", "update", "reopen"} or collection not in _LIFECYCLE_COLLECTIONS:
        raise ProjectModelError("project brief lifecycle operation is invalid")
    if not isinstance(changes, Mapping) or "id" in changes or not changes:
        raise ProjectModelError("project brief changes are invalid")
    try:
        patch = json.loads(json.dumps(dict(changes), ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ProjectModelError("project brief changes must be finite JSON") from exc
    if not isinstance(patch, dict):
        raise ProjectModelError("project brief changes are invalid")
    if not set(patch) <= _LIFECYCLE_FIELDS:
        raise ProjectModelError("project brief changes contain authority-owned fields")
    state = patch.get("state")
    if "state" in patch and (
        not isinstance(state, str) or not 0 < len(state.strip()) <= 64 or any(ord(char) < 32 for char in state)
    ):
        raise ProjectModelError("project brief state is invalid")
    if "state" in patch:
        patch["state"] = state.strip()

    records = document["objective"].setdefault("ranked_outcomes", []) if collection == "goals" else document.setdefault(collection, [])
    if not isinstance(records, list):
        raise ProjectModelError(f"project brief field {collection} is invalid")
    all_records = [
        item
        for key in _LIFECYCLE_COLLECTIONS
        for item in (document["objective"].get("ranked_outcomes", []) if key == "goals" else document.get(key, []))
        if isinstance(item, dict)
    ]
    identity_matches = [
        item for item in all_records
        if isinstance(item.get("id"), str) and item["id"].casefold() == record_id.casefold()
    ]
    if operation == "create":
        if identity_matches:
            raise ProjectModelError("project brief record id already exists")
        records.append({"id": record_id, **patch})
    else:
        matches = [item for item in records if isinstance(item, dict) and item.get("id") == record_id]
        if len(matches) != 1 or len(identity_matches) != 1:
            raise ProjectModelError("project brief edit requires one exact record")
        current = matches[0].get("state")
        target = patch.get("state")
        if (
            operation == "update" and "state" in patch
            and isinstance(current, str) and current.casefold() in _REOPENABLE_STATES
            and target.casefold() not in _REOPENABLE_STATES
        ):
            raise ProjectModelError("project brief terminal record requires explicit reopen")
        if operation == "reopen":
            if (
                set(patch) != {"state"}
                or not isinstance(current, str) or current.casefold() not in _REOPENABLE_STATES
                or not isinstance(target, str) or not target.strip()
                or target.casefold() in _REOPENABLE_STATES
            ):
                raise ProjectModelError("project brief reopen requires a terminal record and nonterminal target state")
        matches[0].update(patch)
    document["updated_at"] = updated_at.strip()
    updated = render_project_brief_markdown(text, document)
    _, new_digest = parse_project_brief_markdown(updated)

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ProjectModelError("project brief update failed") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return new_digest


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(value: Any, fallback: str = "Unknown") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _ids(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ProjectModelError("relationship IDs must be an array of non-empty strings")
    return tuple(item.strip() for item in value)


def _records(model: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = model.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ProjectModelError(f"{key} must be an array of objects")
    return value


def _label(record: Mapping[str, Any], identity: str) -> str:
    for key in ("name", "task_name", "label", "title", "summary", "outcome"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return identity


def _progress(record: Mapping[str, Any]) -> float | None:
    value = record.get("progress_percent")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
        return None
    return float(value)


def _artifact_identity(artifact: ArtifactIdentity) -> dict[str, Any]:
    return {
        "base": artifact.base,
        "revision": artifact.revision,
        "purpose": artifact.purpose,
        "observables": [list(item) for item in artifact.observables],
        "observed_paths": list(artifact.observed_paths),
        "content_address": artifact.content_address(),
    }


def _pointer_value(model: Mapping[str, Any], pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise ProjectModelError("project model source pointer must be RFC6901")
    value: Any = model
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, Mapping) or token not in value:
            raise ProjectModelError(f"project model source pointer is missing: {pointer}")
        value = value[token]
    return value


def _source_bindings(model: Mapping[str, Any], pointers: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {"pointer": pointer, "digest": f"sha256:{_digest(_pointer_value(model, pointer))}"}
        for pointer in pointers
    ]


def _valid_pointer(model: Mapping[str, Any], pointer: str) -> bool:
    try:
        value = _pointer_value(model, pointer)
    except ProjectModelError:
        return False
    if pointer in {"/objective", "/proof_acceptance", "/authority", "/ownership"}:
        return isinstance(value, Mapping)
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _safe_artifact_ref(value: Any, project_ids: frozenset[str]) -> str | None:
    if not isinstance(value, str) or "\\" in value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"project", "artifact"} or parsed.netloc not in project_ids or parsed.query or parsed.fragment:
        return None
    parts = tuple(part for part in parsed.path.split("/") if part)
    if not parts or any(part in {".", ".."} for part in parts):
        return None
    return value


def project_schema1_views(
    model: Mapping[str, Any],
    source_artifact: ArtifactIdentity,
    renderer_registry: Mapping[str, Any],
    allowed_actions: set[str] | frozenset[str],
    *,
    runtime_project_id: str | None = None,
    projection_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not {"open_entity", "open_artifact"}.issubset(allowed_actions):
        raise ProjectModelError("existing action registry is missing required project-view actions")

    project = model.get("project")
    if not isinstance(project, Mapping):
        raise ProjectModelError("project must be an object")
    model_project_id = _text(project.get("id"), "")
    if not model_project_id:
        raise ProjectModelError("project.id is required")
    project_id = _text(runtime_project_id, model_project_id)
    if source_artifact.base != f"project-brief:{project_id}":
        raise ProjectModelError("project model source artifact belongs to another project")
    if not re.fullmatch(r"(?:sha256:)?[0-9a-fA-F]{64}", source_artifact.revision):
        raise ProjectModelError("project model source artifact requires an immutable SHA-256 revision")
    source_digest = source_artifact.revision if source_artifact.revision.startswith("sha256:") else f"sha256:{source_artifact.revision}"
    if source_digest.casefold() != f"sha256:{_digest(model)}":
        raise ProjectModelError("project model source artifact digest does not match the model")

    lens_ids = model.get("proposed_lens_ids", [])
    if (
        not isinstance(lens_ids, list)
        or len(lens_ids) > 32
        or any(not isinstance(item, str) or not item.strip() for item in lens_ids)
        or len({item.casefold() for item in lens_ids}) != len(lens_ids)
    ):
        raise ProjectModelError("project brief proposed_lens_ids is invalid")
    specs_by_id = {spec[0]: spec for spec in VIEW_SPECS}
    selected_specs = tuple(specs_by_id[LENS_VIEW_IDS[item]] for item in lens_ids if item in LENS_VIEW_IDS)
    for _, _, renderer, mode, _, _ in selected_specs:
        if renderer not in renderer_registry or mode not in renderer_registry[renderer]:
            raise ProjectModelError(f"existing RendererRegistry does not admit {renderer}/{mode}")

    binding = dict(projection_binding or {})
    if projection_binding is not None:
        required_binding = {
            "project_id", "model_project_id", "canonical_root", "brief_bytes_digest",
            "source_digest", "project_briefs_cursor", "locator",
        }
        if set(binding) != required_binding or binding.get("project_id") != project_id or binding.get("model_project_id") != model_project_id:
            raise ProjectModelError("project view projection binding is invalid")
        if binding.get("source_digest") != source_digest:
            raise ProjectModelError("project view projection binding source digest is stale")
        for key in ("brief_bytes_digest", "source_digest"):
            if not isinstance(binding.get(key), str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", binding[key]):
                raise ProjectModelError("project view projection binding digest is invalid")
        if not isinstance(binding.get("canonical_root"), str) or not binding["canonical_root"]:
            raise ProjectModelError("project view projection root binding is invalid")
        cursor = binding.get("project_briefs_cursor")
        if (
            not isinstance(cursor, Mapping)
            or set(cursor) != {"type", "digest"}
            or cursor.get("type") != "project_briefs_v1"
            or not isinstance(cursor.get("digest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", cursor["digest"])
        ):
            raise ProjectModelError("project view projection cursor is invalid")
        if binding.get("locator") is not None:
            raise ProjectModelError("direct root projection does not accept locator metadata")
    accepted_cursor = {
        "type": "schema1_project_views_v1",
        "digest": f"sha256:{_digest(binding)}",
    } if binding else None

    objective = model.get("objective") if isinstance(model.get("objective"), Mapping) else {}
    proof_acceptance = model.get("proof_acceptance") if isinstance(model.get("proof_acceptance"), Mapping) else {}
    authority = model.get("authority") if isinstance(model.get("authority"), Mapping) else {}
    ownership = model.get("ownership") if isinstance(model.get("ownership"), Mapping) else {}
    ranked_outcomes = objective.get("ranked_outcomes")
    if not isinstance(ranked_outcomes, list) or any(not isinstance(item, dict) for item in ranked_outcomes):
        ranked_outcomes = []

    def records(key: str) -> list[dict[str, Any]]:
        return _records(model, key) if _valid_pointer(model, f"/{key}") else []

    groups = {
        "outcome": ranked_outcomes,
        "milestone": records("milestones"),
        "task": records("tasks"),
        "block": records("blocks"),
        "blocker": records("risks_blockers"),
        "artifact": records("artifacts"),
    }
    indexed: dict[str, tuple[str, dict[str, Any], int]] = {}
    for kind, records in groups.items():
        for index, record in enumerate(records):
            identity = record.get("id")
            if not isinstance(identity, str) or not identity.strip():
                raise ProjectModelError(f"{kind} record requires a stable id")
            identity = identity.strip()
            if identity in indexed:
                raise ProjectModelError(f"duplicate stable id: {identity}")
            indexed[identity] = (kind, record, index)

    diagnostics: list[dict[str, str]] = []
    nodes: list[dict[str, Any]] = []
    for identity, (kind, record, index) in indexed.items():
        nodes.append({
            "id": identity,
            "kind": kind,
            "label": _label(record, identity),
            "order": index,
            "rank": record.get("rank") if isinstance(record.get("rank"), (int, float)) else None,
            "owner_id": _text(record.get("owner_id") or record.get("owner")),
            "progress_percent": _progress(record),
            "action": {"kind": "open_entity", "project_id": project_id, "entity_id": identity},
        })
    nodes.sort(key=lambda item: (_TYPE_ORDER[item["kind"]], item["rank"] is None, item["rank"] or 0, item["order"], item["id"]))

    edges: list[dict[str, str]] = []
    edge_keys: set[tuple[str, str, str]] = set()

    def add_edge(source: str, target: str, relation: str) -> None:
        if target not in indexed:
            diagnostics.append({"code": "UNRESOLVED_RELATIONSHIP", "source_id": source, "target_id": target, "relation": relation})
            return
        key = (source, target, relation)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({"id": f"edge:{relation}:{source}:{target}", "source": source, "target": target, "type": relation})

    for identity, (kind, record, _) in indexed.items():
        for target in _ids(record.get("dependency_ids")):
            add_edge(identity, target, "depends_on")
        if kind == "milestone":
            for target in _ids(record.get("task_ids")):
                add_edge(identity, target, "contains")
            for target in _ids(record.get("blocker_ids")):
                add_edge(identity, target, "blocked_by")
        elif kind == "task":
            for target in _ids(record.get("blocker_ids")):
                add_edge(identity, target, "blocked_by")
        elif kind == "blocker":
            for target in _ids(record.get("affected_ids")):
                add_edge(identity, target, "blocks")
        elif kind == "outcome":
            milestone_id = record.get("milestone_id")
            if isinstance(milestone_id, str) and milestone_id.strip():
                add_edge(identity, milestone_id.strip(), "targets")
    edges.sort(key=lambda item: (item["type"], item["source"], item["target"]))
    rows: list[dict[str, Any]] = []
    milestone_order = sorted(
        groups["milestone"],
        key=lambda item: (item.get("rank") is None, item.get("rank") or 0, groups["milestone"].index(item), str(item["id"])),
    )
    emitted_tasks: set[str] = set()
    blocks_by_task: dict[str, list[dict[str, Any]]] = {}
    for block in groups["block"]:
        task_id = block.get("task_id")
        if isinstance(task_id, str) and task_id.strip():
            blocks_by_task.setdefault(task_id.strip(), []).append(block)

    def add_work(record: Mapping[str, Any], kind: str, depth: int, parent_id: str | None) -> None:
        identity = str(record["id"]).strip()
        rows.append({
            "id": identity,
            "kind": kind,
            "label": _label(record, identity),
            "depth": depth,
            "parent_id": parent_id,
            "owner_id": _text(record.get("owner_id") or record.get("owner")),
            "progress_percent": _progress(record),
            "action": {"kind": "open_entity", "project_id": project_id, "entity_id": identity},
        })

    task_lookup = {str(item["id"]).strip(): item for item in groups["task"]}
    for milestone in milestone_order:
        milestone_id = str(milestone["id"]).strip()
        add_work(milestone, "milestone", 0, None)
        for task_id in _ids(milestone.get("task_ids")):
            task = task_lookup.get(task_id)
            if task is None or task_id in emitted_tasks:
                continue
            emitted_tasks.add(task_id)
            add_work(task, "task", 1, milestone_id)
            for block in blocks_by_task.get(task_id, []):
                add_work(block, "block", 2, task_id)
    for task in groups["task"]:
        task_id = str(task["id"]).strip()
        if task_id in emitted_tasks:
            continue
        add_work(task, "task", 0, None)
        for block in blocks_by_task.get(task_id, []):
            add_work(block, "block", 1, task_id)

    artifact_cards: list[dict[str, Any]] = []
    for artifact in groups["artifact"]:
        artifact_id = str(artifact["id"]).strip()
        associations = sorted({
            source_id
            for source_id, (_, source, _) in indexed.items()
            if source_id != artifact_id and artifact_id in _ids(source.get("dependency_ids"))
            and indexed[source_id][0] in {"milestone", "task", "block"}
        })
        ref = _safe_artifact_ref(artifact.get("ref"), frozenset({project_id, model_project_id}))
        digest = artifact.get("digest") or artifact.get("sha256")
        valid_digest = isinstance(digest, str) and bool(re.fullmatch(r"(?:sha256:)?[0-9a-fA-F]{64}", digest))
        action = None
        if ref and valid_digest:
            action = {
                "kind": "open_artifact",
                "project_id": project_id,
                "artifact_id": artifact_id,
                "ref": ref,
                "digest": digest.lower() if digest.startswith("sha256:") else f"sha256:{digest.lower()}",
            }
        artifact_cards.append({
            "id": artifact_id,
            "label": _label(artifact, artifact_id),
            "revision": _text(artifact.get("revision")),
            "proof_class": _text(artifact.get("proof_class")),
            "associated_ids": associations,
            "action": action,
        })
    artifact_cards.sort(key=lambda item: item["id"])

    overview_blocks = [{
        "id": "overview.objective",
        "kind": "objective",
        "label": "Objective",
        "text": _text(objective.get("current")),
    }]
    overview_blocks.extend({
        "id": str(item["id"]).strip(),
        "kind": "risk",
        "label": _label(item, str(item["id"]).strip()),
        "text": _text(item.get("release_condition")),
        "action": {"kind": "open_entity", "project_id": project_id, "entity_id": str(item["id"]).strip()},
    } for item in groups["blocker"])
    overview_blocks.append({
        "id": "overview.proof-acceptance",
        "kind": "proof_acceptance",
        "label": "Proof and acceptance",
        "text": _text(proof_acceptance.get("claim_limit")),
    })

    roadmap = [{
        "id": str(item["id"]).strip(),
        "label": _label(item, str(item["id"]).strip()),
        "order": index,
        "rank": item.get("rank") if isinstance(item.get("rank"), (int, float)) else None,
        "dependency_ids": list(_ids(item.get("dependency_ids"))),
        "action": {"kind": "open_entity", "project_id": project_id, "entity_id": str(item["id"]).strip()},
    } for index, item in enumerate(milestone_order)]

    agent_roles: dict[str, set[str]] = {}

    def add_agent(value: Any, role: str) -> None:
        if isinstance(value, str) and value.strip():
            agent_roles.setdefault(value.strip(), set()).add(role)

    for key, value in authority.items():
        if isinstance(value, Mapping):
            add_agent(value.get("id"), key)
        elif key.endswith("_id"):
            add_agent(value, key)
    add_agent(ownership.get("active_ctrl_id"), "active_ctrl")
    for value in _ids(ownership.get("active_lead_ids")):
        add_agent(value, "active_lead")
    agent_records = [{
        "id": agent_id,
        "label": agent_id,
        "roles": sorted(roles),
        "action": {"kind": "open_entity", "project_id": project_id, "entity_id": agent_id},
    } for agent_id, roles in sorted(agent_roles.items())]

    content_by_id = {
        "view.project.overview-health": {"blocks": overview_blocks},
        "view.project.roadmap": {"milestones": roadmap},
        "view.project.work": {"rows": rows, "blocks_state": "KNOWN" if "blocks" in model else "UNKNOWN", "progress_state": "KNOWN" if any(row["progress_percent"] is not None for row in rows) else "UNKNOWN"},
        "view.project.flow": {"nodes": nodes, "edges": edges},
        "view.project.artifacts": {"artifacts": artifact_cards, "proof_acceptance_digest": f"sha256:{_digest(proof_acceptance)}"},
        "view.project.agents": {"records": agent_records},
    }
    tabs = []
    for view_id, label, renderer, mode, required_pointers, optional_pointers in selected_specs:
        unavailable = [pointer for pointer in required_pointers if not _valid_pointer(model, pointer)]
        if view_id == "view.project.agents":
            unavailable.extend(pointer for pointer, value in (("/authority", authority), ("/ownership", ownership)) if not value and pointer not in unavailable)
        unavailable.extend(pointer for pointer in optional_pointers if pointer[1:] in model and not _valid_pointer(model, pointer))
        if unavailable:
            diagnostics.append({
                "code": "WITHHELD_VIEW",
                "view_id": view_id,
                "reason": "MISSING_OR_INVALID_SOURCE",
                "pointers": ",".join(unavailable),
            })
            continue
        pointers = required_pointers + tuple(pointer for pointer in optional_pointers if pointer[1:] in model)
        sources = _source_bindings(model, pointers)
        for source in sources:
            source["source_digest"] = f"sha256:{_digest({'project_id': project_id, 'model_project_id': model_project_id, 'source_digest': source_digest, 'accepted_cursor': accepted_cursor, **source})}"
        allowed = ["open_artifact", "open_entity"] if view_id == "view.project.artifacts" else ["open_entity"]
        content = content_by_id[view_id]
        tabs.append({
            "id": view_id,
            "label": label,
            "renderer": renderer,
            "mode": mode,
            "sources": sources,
            "allowed_actions": allowed,
            "content": content,
            "view_digest": f"sha256:{_digest({'id': view_id, 'renderer': renderer, 'mode': mode, 'source_digest': source_digest, 'accepted_cursor': accepted_cursor, 'sources': sources, 'content': content})}",
        })
    for lens_id in lens_ids:
        if lens_id not in LENS_VIEW_IDS:
            diagnostics.append({"code": "UNKNOWN_LENS_WITHHELD", "lens_id": lens_id})
    return {
        "schema_version": 1,
        "project_id": project_id,
        "model_project_id": model_project_id,
        "project_label": _text(project.get("name") or project.get("purpose"), model_project_id),
        "tab": {"id": "ui", "label": "Workspace"},
        "views": tabs,
        "source_artifact": _artifact_identity(source_artifact),
        "source_digest": source_digest,
        "projection_binding": binding or None,
        "accepted_cursor": accepted_cursor,
        "projection_digest": f"sha256:{_digest({'project_id': project_id, 'model_project_id': model_project_id, 'source_digest': source_digest, 'accepted_cursor': accepted_cursor, 'tabs': tabs})}",
        "snapshot_only": True,
        "tabs": tabs,
        "diagnostics": sorted(diagnostics, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))),
    }
