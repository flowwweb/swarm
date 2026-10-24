from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.swarm.runtime import ArtifactIdentity, ProofClass  # noqa: E402


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
_UPDATE_LOCK = threading.Lock()
_MAX_BRIEF_BYTES = 512 * 1024


class ProjectModelError(ValueError):
    pass


def create_flow_draft() -> dict[str, Any]:
    steps = (("brief", "Define the outcome"), ("approach", "Choose the smallest useful approach"),
             ("produce", "Produce one bounded increment"), ("check", "Check the increment"), ("accept", "Obtain acceptance"))
    nodes = []
    for identity, objective in steps:
        previous = nodes[-1]["id"] if nodes else None
        nodes.append({"id": identity, "objective": objective, "owner_id": "unassigned", "capability": identity,
            "dependencies": [previous] if previous else [],
            "inputs": [{"node_id": previous, "output_id": "result"}] if previous else [], "outputs": ["result"],
            "completion": "Return the exact result and required evidence.", "proof_classes": ["HUMAN" if identity == "accept" else "SOURCE_STATIC"]})
    return {"id": "create", "version": 1, "objective": "Create a useful, verified result", "nodes": nodes}


def _flow_text(value: str) -> bool:
    return not any((ord(c) < 32 and c not in "\n\t") or 0xD800 <= ord(c) <= 0xDFFF for c in value)


def validate_flow_assignment(value: Any, definitions: list[dict[str, Any]]) -> dict[str, Any]:
    """Project-scoped preferences only; repetition never grants dispatch authority."""
    fields = {"id", "version", "subject_kind", "subject_id", "subject_version", "ctrl_id",
              "flow_id", "flow_version", "flow_digest", "label", "notes", "repeat_count", "digest"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ProjectModelError("Flow assignment fields are invalid")
    if not isinstance(value["subject_kind"], str) or value["subject_kind"] not in {"ROLE", "LAB", "FACTORY"}:
        raise ProjectModelError("Flow assignment subject kind is invalid")
    for key in ("subject_id", "subject_version", "flow_id"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value[key]):
            raise ProjectModelError("Flow assignment identity is invalid")
    if value["ctrl_id"] is not None and (not isinstance(value["ctrl_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value["ctrl_id"])):
        raise ProjectModelError("Flow assignment CTRL is invalid")
    if value["subject_kind"] != "ROLE" and value["ctrl_id"] is None:
        raise ProjectModelError("Unit Flow assignment requires its owning CTRL")
    if any(type(value[k]) is not int or value[k] < 1 for k in ("version", "flow_version")):
        raise ProjectModelError("Flow assignment versions are invalid")
    # JSON numbers cross the browser boundary: preserve exact integer identity,
    # not a product quota. This is metadata and never starts repeated execution.
    if type(value["repeat_count"]) is not int or not 1 <= value["repeat_count"] <= 2**53 - 1:
        raise ProjectModelError("Flow repetition must be a positive JSON-safe integer")
    for key, limit in (("label", 160), ("notes", 2048)):
        if not isinstance(value[key], str) or len(value[key]) > limit or not _flow_text(value[key]):
            raise ProjectModelError("Flow assignment customization is invalid")
    identity = {k: value[k] for k in ("subject_kind", "subject_id", "ctrl_id")}
    if value["id"] != "assignment-" + _digest(identity):
        raise ProjectModelError("Flow assignment identity conflicts with its scope")
    if not any((d["id"], d["version"], d["digest"]) == (value["flow_id"], value["flow_version"], value["flow_digest"]) for d in definitions):
        raise ProjectModelError("Flow assignment requires an exact retained Flow version")
    if value["digest"] != "sha256:" + _digest({k: v for k, v in value.items() if k != "digest"}):
        raise ProjectModelError("Flow assignment digest mismatch")
    return value


def validate_flow_definition(value: Any) -> dict[str, Any]:
    """Validate project-owned planning data, never execution or acceptance authority."""
    fields = {"id", "version", "objective", "nodes", "digest"}
    node_fields = {"id", "objective", "owner_id", "capability", "dependencies", "inputs", "outputs", "completion", "proof_classes"}

    def token(item: Any) -> bool:
        return isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", item) is not None

    def text(item: Any) -> bool:
        return isinstance(item, str) and 0 < len(item.strip()) <= 2048 and _flow_text(item)

    def tokens(items: Any) -> bool:
        return isinstance(items, list) and len(items) <= 64 and all(token(item) for item in items) and len(set(items)) == len(items)

    if not isinstance(value, dict) or set(value) != fields:
        raise ProjectModelError("Flow requires exact id, version, objective, nodes and digest fields")
    if not token(value["id"]) or type(value["version"]) is not int or value["version"] < 1 or not text(value["objective"]):
        raise ProjectModelError("Flow identity, version or objective is invalid")
    nodes = value["nodes"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 64:
        raise ProjectModelError("Flow requires 1 to 64 nodes")
    indexed: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict) or set(node) != node_fields:
            raise ProjectModelError("Flow node fields are invalid")
        if not all(token(node[key]) for key in ("id", "owner_id", "capability")) or not all(text(node[key]) for key in ("objective", "completion")):
            raise ProjectModelError("Flow node identity, owner, capability or instructions are invalid")
        if node["id"] in indexed:
            raise ProjectModelError("Flow node IDs must be unique")
        if not tokens(node["dependencies"]) or not tokens(node["outputs"]) or not node["outputs"]:
            raise ProjectModelError("Flow dependencies and output references are invalid")
        classes = node["proof_classes"]
        if not tokens(classes) or not classes or not set(classes) <= {item.value for item in ProofClass}:
            raise ProjectModelError("Flow proof classes must use the existing proof taxonomy")
        if not isinstance(node["inputs"], list) or len(node["inputs"]) > 64:
            raise ProjectModelError("Flow input references are invalid")
        input_keys = set()
        for ref in node["inputs"]:
            if not isinstance(ref, dict) or set(ref) != {"node_id", "output_id"} or not all(token(item) for item in ref.values()):
                raise ProjectModelError("Flow input requires a node and output reference")
            key = (ref["node_id"], ref["output_id"])
            if key in input_keys:
                raise ProjectModelError("Flow input references must be unique")
            input_keys.add(key)
        indexed[node["id"]] = node

    ancestors: dict[str, set[str]] = {}
    visiting: set[str] = set()

    def visit(node_id: str) -> set[str]:
        if node_id in visiting:
            raise ProjectModelError("Flow dependencies contain a cycle")
        if node_id not in indexed:
            raise ProjectModelError("Flow dependency references a missing node")
        if node_id not in ancestors:
            visiting.add(node_id)
            result: set[str] = set()
            for parent in indexed[node_id]["dependencies"]:
                result.add(parent)
                result.update(visit(parent))
            visiting.remove(node_id)
            ancestors[node_id] = result
        return ancestors[node_id]

    for node_id, node in indexed.items():
        upstream = visit(node_id)
        for ref in node["inputs"]:
            if ref["node_id"] not in upstream or ref["output_id"] not in indexed[ref["node_id"]]["outputs"]:
                raise ProjectModelError("Flow inputs must reference declared upstream outputs")
    # Layout is intentionally not a definition field: graph geometry is a projection.
    semantic = {key: value[key] for key in ("id", "version", "objective", "nodes")}
    digest = f"sha256:{_digest(semantic)}"
    if value["digest"] != digest:
        raise ProjectModelError("Flow definition digest mismatch")
    return json.loads(json.dumps(value, ensure_ascii=False))


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


def _brief_regular_path(path: Path):
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ProjectModelError("brief content links/reparse points are not admissible")
        if not (stat.S_ISREG(info.st_mode) if item == path else stat.S_ISDIR(info.st_mode)):
            raise ProjectModelError("brief content path is not regular")
    return path.stat()


@contextmanager
def _brief_update_lock(path: Path):
    """Serialize the existing root writers, including independent CLI processes."""
    with _UPDATE_LOCK:
        _brief_regular_path(path)
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
            kernel.CreateMutexW.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            kernel.WaitForSingleObject.restype = wintypes.DWORD
            kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            identity = hashlib.sha256(os.path.normcase(str(path.parent.resolve())).encode("utf-8")).hexdigest()
            handle = kernel.CreateMutexW(None, False, "Local\\SWARMBrief-" + identity)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            acquired = False
            try:
                result = kernel.WaitForSingleObject(handle, 10000)
                if result not in (0, 0x80):  # acquired, or recovered after a dead writer
                    raise ProjectModelError("project brief writer unavailable; retry with the same expected digest")
                acquired = True
                yield
            finally:
                if acquired:
                    kernel.ReleaseMutex(handle)
                kernel.CloseHandle(handle)
        else:
            import fcntl
            descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def read_brief_content(root: Path, reference: Mapping[str, Any]) -> bytes:
    """Read one immutable full brief from the existing root-local history directory."""
    if (not isinstance(reference, dict)
            or set(reference) != {"rel", "path", "sha256", "bytes", "canonical_digest", "project_id"}
            or reference.get("rel") != "brief_content"
            or not isinstance(reference.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", reference["sha256"]) is None
            or reference.get("path") != f"history/swarm-brief-{reference['sha256']}.md"
            or type(reference.get("bytes")) is not int or not 0 < reference["bytes"] <= 2 * _MAX_BRIEF_BYTES
            or not isinstance(reference.get("canonical_digest"), str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", reference["canonical_digest"]) is None
            or not isinstance(reference.get("project_id"), str) or not reference["project_id"].strip()):
        raise ProjectModelError("invalid full brief reference")
    root = Path(os.path.abspath(root))
    path = root / reference["path"]

    def check_path():
        info = _brief_regular_path(path)
        if path.resolve() != root.resolve() / reference["path"]:
            raise ProjectModelError("brief content escapes the project root")
        return info

    try:
        before = check_path()
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            raw = stream.read(2 * _MAX_BRIEF_BYTES + 1)
        after = check_path()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ProjectModelError("brief content changed during read")
    except (OSError, UnicodeError) as exc:
        raise ProjectModelError("brief content is unavailable") from exc
    if len(raw) != reference["bytes"] or hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ProjectModelError("brief content bytes/digest mismatch")
    return raw


def parse_project_brief_markdown(text: str, *, project_id: str | None = None,
                                 root: Path | None = None) -> tuple[dict[str, Any], str]:
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
    if isinstance(document, dict) and "brief_content" in document:
        if (root is None or set(document) != {"schema_version", "updated_at", "project", "links", "brief_content"}
                or type(document["schema_version"]) is not int or document["schema_version"] != 1):
            raise ProjectModelError("full brief reference requires an exact root-bound envelope")
        raw = read_brief_content(root, document["brief_content"])
        try:
            # One hop only: an archive must contain the full model, never another pointer.
            full_text = raw.decode("utf-8")
            archived = list(_BRIEF_FENCE.finditer(full_text))
            if len(archived) != 1:
                raise ProjectModelError("full brief content requires one object")
            archived_document = json.loads(archived[0].group("payload"))
            if not isinstance(archived_document, dict) or "brief_content" in archived_document:
                raise ProjectModelError("full brief reference cannot chain")
            full, digest = parse_project_brief_markdown(full_text, project_id=project_id)
        except (ValueError, UnicodeError) as exc:
            raise ProjectModelError("full brief content is invalid") from exc
        reference = document["brief_content"]
        if (digest != reference["canonical_digest"] or full["project"]["id"] != reference["project_id"]
                or any(document[key] != full[key] for key in ("schema_version", "updated_at", "project", "links"))):
            raise ProjectModelError("full brief identity/metadata binding mismatch")
        return full, digest
    if not isinstance(document, dict) or not _BRIEF_REQUIRED.issubset(document):
        raise ProjectModelError("project brief is missing required fields")
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1 or not _finite_json(document):
        raise ProjectModelError("project brief schema is unsupported")
    if not isinstance(document.get("updated_at"), str) or not document["updated_at"].strip():
        raise ProjectModelError("project brief timestamp is invalid")
    for field in ("project", "objective", "repo", "authority", "ownership", "proof_acceptance"):
        if not isinstance(document.get(field), dict):
            raise ProjectModelError(f"project brief field {field} is invalid")
    for field in ("users_outcomes", "milestones", "decisions", "risks_blockers"):
        if not isinstance(document.get(field), list):
            raise ProjectModelError(f"project brief field {field} is invalid")
    # Retained schema-1 briefs also use named pointers. Preserve their exact
    # representation in the canonical digest; these are not executable links.
    links = document["links"]
    if not isinstance(links, list) and not (
        isinstance(links, dict) and all(
            isinstance(value, str) and value.strip() and not any(ord(char) < 32 for char in value)
            for pair in links.items() for value in pair
        )
    ):
        raise ProjectModelError("project brief field links is invalid")
    for field in ("tasks", "blocks", "artifacts"):
        if field in document and (
            not isinstance(document[field], list) or any(not isinstance(item, dict) for item in document[field])
        ):
            raise ProjectModelError(f"project brief field {field} is invalid")
    definitions = document.get("flow_definitions", [])
    if not isinstance(definitions, list) or len(definitions) > 128:
        raise ProjectModelError("project brief Flow definitions are invalid")
    identities = set()
    for definition in definitions:
        checked = validate_flow_definition(definition)
        identity = (checked["id"], checked["version"])
        if identity in identities:
            raise ProjectModelError("project brief contains a duplicate Flow version")
        identities.add(identity)
    assignments = document.get("flow_assignments", [])
    # Preserve every version within the existing bounded brief and readback budget.
    if not isinstance(assignments, list):
        raise ProjectModelError("project brief Flow assignments are invalid")
    assignment_versions = {}
    for assignment in assignments:
        checked = validate_flow_assignment(assignment, definitions)
        if checked["version"] != assignment_versions.get(checked["id"], 0) + 1:
            raise ProjectModelError("Flow assignment version must follow its retained history")
        assignment_versions[checked["id"]] = checked["version"]
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


def render_project_brief_markdown(text: str, document: Mapping[str, Any], *, root: Path | None = None) -> str:
    current, _ = parse_project_brief_markdown(text, root=root)
    replacement = dict(document)
    if replacement == current:
        return text
    if "brief_content" in json.loads(next(_BRIEF_FENCE.finditer(text)).group("payload")):
        raise ProjectModelError("referenced brief changes require the atomic brief writer")
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
    with _brief_update_lock(path):
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
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProjectModelError("project brief is unreadable") from exc
    document, digest = parse_project_brief_markdown(text, root=path.parent)
    if digest != expected_digest:
        raise ProjectModelError("project brief digest conflict")
    if collection in {"flow_definitions", "flow_assignments"}:
        if operation != "create" or not isinstance(changes, Mapping) or "id" in changes:
            raise ProjectModelError("Flow versions are append-only; edit a new draft version")
        candidate = {"id": record_id, **changes}
        definition = (validate_flow_definition(candidate) if collection == "flow_definitions"
                      else validate_flow_assignment(candidate, document.get("flow_definitions", [])))
        retained = document.setdefault(collection, [])
        versions = [item["version"] for item in retained if item["id"] == record_id]
        if definition["version"] != max(versions, default=0) + 1:
            raise ProjectModelError("Flow version must follow the last retained version")
        retained.append(definition)
        return _write_project_brief(path, text, document, updated_at)
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
        for key in _LIFECYCLE_COLLECTIONS | {"artifacts"}
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
    return _write_project_brief(path, text, document, updated_at)


def _write_project_brief(path: Path, text: str, document: dict[str, Any], updated_at: str) -> str:
    if not isinstance(updated_at, str) or not updated_at.strip():
        raise ProjectModelError("project brief timestamp is invalid")
    document["updated_at"] = updated_at.strip()
    envelope = json.loads(next(_BRIEF_FENCE.finditer(text)).group("payload"))
    if "brief_content" in envelope:
        full_text = read_brief_content(path.parent, envelope["brief_content"]).decode("utf-8")
        full_text = render_project_brief_markdown(full_text, document)
        return _replace_compact_brief(path, text.encode("utf-8"), full_text.encode("utf-8"))["canonical_digest"]
    updated = render_project_brief_markdown(text, document)
    _, new_digest = parse_project_brief_markdown(updated)

    try:
        _replace_brief_bytes(path, text.encode("utf-8"), updated.encode("utf-8"))
    except OSError as exc:
        raise ProjectModelError("project brief update failed") from exc
    return new_digest


def _replace_brief_bytes(path: Path, expected: bytes, updated: bytes) -> None:
    """The caller holds the shared root lock through comparison and replacement."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        if path.read_bytes() != expected:
            raise ProjectModelError("project brief changed before replacement")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _create_brief_bytes(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _publish_brief_archive(archive: Path, full: bytes, *, create=None) -> None:
    """Atomic create-if-absent; callers validate the retained immutable identity."""
    archive.parent.mkdir(exist_ok=True)
    info = archive.parent.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ProjectModelError("brief history directory must not be a link/reparse point")
    if not archive.exists():
        temporary = archive.with_name(".swarm-brief-" + uuid.uuid4().hex + ".tmp")
        try:
            (create or _create_brief_bytes)(temporary, full)
            # Atomic create-if-absent; never overwrite a pre-existing immutable identity.
            try:
                if os.name == "nt":
                    os.rename(temporary, archive)  # Windows rename refuses an existing destination.
                else:
                    os.link(temporary, archive)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)


def _replace_compact_brief(path: Path, original: bytes, full: bytes) -> dict[str, Any]:
    """Publish durable full content first, then atomically advance the sole root pointer."""
    _brief_regular_path(path)
    document, digest = parse_project_brief_markdown(full.decode("utf-8"))
    sha = hashlib.sha256(full).hexdigest()
    reference = {"rel": "brief_content", "path": f"history/swarm-brief-{sha}.md", "sha256": sha,
                 "bytes": len(full), "canonical_digest": digest, "project_id": document["project"]["id"]}
    archive = path.parent / reference["path"]
    _publish_brief_archive(archive, full)
    if read_brief_content(path.parent, reference) != full:
        raise ProjectModelError("immutable full brief conflicts")

    def label(item):
        return next((item[key] for key in ("title", "name", "label", "summary", "id")
                     if isinstance(item.get(key), str) and item[key].strip()), "Untitled record")

    # Human index only; no shortened field is parsed as current authority.
    lines = [f"# {document['project']['id']}", "", "## Current outcome", "",
             str(document["objective"].get("current", document["project"].get("purpose", ""))), ""]
    for heading, field in (("Milestones", "milestones"), ("Work", "tasks"), ("Risks and blockers", "risks_blockers")):
        lines += [f"## {heading}", ""]
        for item in document.get(field, []):
            if isinstance(item, dict):
                lines.append(f"- {label(item)} [{item.get('id', 'no stable ID')}; {item.get('state', 'UNKNOWN')}]")
        lines.append("")
    lines += ["## Full current detail and preserved history", "",
              f"[Read the complete brief]({reference['path']}). Ownership, requirements, decisions, risks and acceptance remain there unchanged.",
              "This index grants no approval or runtime authority.", "", _BRIEF_MARKER, "```json"]
    envelope = {key: document[key] for key in ("schema_version", "updated_at", "project", "links")}
    envelope["brief_content"] = reference
    candidate = "\n".join(lines) + "\n" + json.dumps(envelope, ensure_ascii=False, indent=2) + "\n```\n"
    observed, observed_digest = parse_project_brief_markdown(candidate, root=path.parent)
    if observed != document or observed_digest != digest:
        raise ProjectModelError("compact brief semantic roundtrip mismatch")
    _replace_brief_bytes(path, original, candidate.encode("utf-8"))
    return {"status": "COMPACTED", "archive": reference, "canonical_digest": digest,
            "current_bytes": len(candidate.encode("utf-8")),
            "current_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest()}


def compact_project_brief(path: Path, *, expected_sha256: str) -> dict[str, Any]:
    """Losslessly compact one explicit canonical brief; retry reuses immutable history."""
    with _brief_update_lock(path):
        if path.name != "SWARM.md" or path.is_symlink() or not path.is_file():
            raise ProjectModelError("one existing regular canonical SWARM.md is required")
        _brief_regular_path(path)
        original = path.read_bytes()
        document, digest = parse_project_brief_markdown(original.decode("utf-8"), root=path.parent)
        envelope = json.loads(next(_BRIEF_FENCE.finditer(original.decode("utf-8"))).group("payload"))
        sha = hashlib.sha256(original).hexdigest()
        if "brief_content" in envelope and expected_sha256 in {sha, envelope["brief_content"]["sha256"]}:
            return {"status": "REPLAY", "archive": envelope["brief_content"], "canonical_digest": digest,
                    "current_sha256": sha, "current_bytes": len(original)}
        if sha != expected_sha256:
            raise ProjectModelError("project brief digest conflict")
        return _replace_compact_brief(path, original, original)


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
    selected_lens_ids: list[str] | None = None,
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

    lens_ids = model.get("proposed_lens_ids", []) if selected_lens_ids is None else selected_lens_ids
    if (
        not isinstance(lens_ids, list)
        or len(lens_ids) > 32
        or any(not isinstance(item, str) or not item.strip() for item in lens_ids)
        or len({item.casefold() for item in lens_ids}) != len(lens_ids)
    ):
        raise ProjectModelError("project brief proposed_lens_ids is invalid")
    if selected_lens_ids is not None and any(item not in LENS_VIEW_IDS for item in lens_ids):
        raise ProjectModelError("selected_lens_ids contains an unknown lens")
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
        declared_state = record.get("state")
        if declared_state is not None and (not isinstance(declared_state, str) or not declared_state.strip() or len(declared_state) > 128):
            raise ProjectModelError("declared work state must be bounded non-empty text")
        rows.append({
            "id": identity,
            "kind": kind,
            "label": _label(record, identity),
            "depth": depth,
            "parent_id": parent_id,
            "declared_state": declared_state.strip() if declared_state is not None else None,
            "owner_id": _text(record.get("owner_id") or record.get("owner")),
            "progress_percent": _progress(record),
            "action": {"kind": "open_entity", "project_id": project_id, "entity_id": identity},
        })

    task_lookup = {str(item["id"]).strip(): item for item in groups["task"]}
    tasks_by_milestone = {str(item["id"]).strip(): list(_ids(item.get("task_ids"))) for item in milestone_order}
    parents: dict[str, str] = {}
    for milestone_id, task_ids in tasks_by_milestone.items():
        for task_id in task_ids:
            if task_id in parents and parents[task_id] != milestone_id:
                raise ProjectModelError("work task has conflicting milestone parents")
            parents[task_id] = milestone_id
    for task_id, task in task_lookup.items():
        declared_parent = task.get("milestone_id")
        if declared_parent is None:
            continue
        if not isinstance(declared_parent, str) or declared_parent.strip() not in tasks_by_milestone:
            raise ProjectModelError("work task milestone_id must name an existing milestone")
        milestone_id = declared_parent.strip()
        if task_id in parents and parents[task_id] != milestone_id:
            raise ProjectModelError("work task has conflicting milestone parents")
        if task_id not in tasks_by_milestone[milestone_id]:
            tasks_by_milestone[milestone_id].append(task_id)
        parents[task_id] = milestone_id
    for milestone in milestone_order:
        milestone_id = str(milestone["id"]).strip()
        add_work(milestone, "milestone", 0, None)
        for task_id in tasks_by_milestone[milestone_id]:
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
        content = content_by_id[view_id]
        if view_id == "view.project.work" and isinstance(objective.get("current"), str) and objective["current"].strip():
            content = {**content, "declared_goal": {"text": objective["current"].strip(), "source_pointer": "/objective"}}
            pointers += ("/objective",)
        if view_id == "view.project.work" and selected_lens_ids is not None and "ranked_outcomes" in objective:
            pointer = "/objective/ranked_outcomes"
            if not _valid_pointer(model, pointer):
                diagnostics.append({"code": "WITHHELD_VIEW", "view_id": view_id, "reason": "INVALID_GOAL_ASSOCIATIONS"})
                continue
            associations = []
            for goal in ranked_outcomes:
                target = goal.get("milestone_id")
                if target is None:
                    continue
                if not isinstance(target, str) or target not in indexed or indexed[target][0] != "milestone":
                    diagnostics.append({"code": "UNRESOLVED_GOAL_ASSOCIATION", "source_id": str(goal["id"])})
                    continue
                associations.append({"goal_id": str(goal["id"]).strip(), "milestone_id": target})
            content = {**content, "goal_associations": associations}
            pointers += (pointer,)
        sources = _source_bindings(model, pointers)
        for source in sources:
            source["source_digest"] = f"sha256:{_digest({'project_id': project_id, 'model_project_id': model_project_id, 'source_digest': source_digest, 'accepted_cursor': accepted_cursor, **source})}"
        allowed = ["open_artifact", "open_entity"] if view_id == "view.project.artifacts" else ["open_entity"]
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
