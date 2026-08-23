"""Optional provider-neutral execution adapters behind SWARM routing authority.

Adapters translate an already-authorized execution request. They do not select
owners, store prompts or responses, review work, accept artifacts, or mutate
host task state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import PurePosixPath, PureWindowsPath
from typing import Mapping

from .core import ArtifactIdentity, ExecutionRoute, ExecutionRoutingDecision, InvariantError


_DIGEST_CHARS = frozenset("0123456789abcdef")


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(character in value for character in "\r\n\t"):
        raise InvariantError(f"{label} must be exact non-empty text")
    return value.strip()


def _digest(value: str, label: str) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ""
    if len(normalized) != 64 or any(character not in _DIGEST_CHARS for character in normalized):
        raise InvariantError(f"{label} must be a SHA-256 digest")
    return normalized


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


class AdapterCapabilityState(StrEnum):
    NATIVE = "native"
    ENFORCED = "enforced"
    INSTRUCTION_ONLY = "instruction_only"
    UNSUPPORTED = "unsupported"


class AdapterPlanStatus(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AdapterCapability:
    name: str
    state: AdapterCapabilityState
    evidence: str
    claim_limit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "adapter capability name"))
        if not isinstance(self.state, AdapterCapabilityState):
            raise InvariantError("adapter capability state must be typed")
        _text(self.evidence, "adapter capability evidence")
        _text(self.claim_limit, "adapter capability claim limit")


@dataclass(frozen=True)
class AdapterCapabilityMatrix:
    adapter_id: str
    provider_id: str
    optional: bool
    capabilities: tuple[AdapterCapability, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter_id", _text(self.adapter_id, "adapter id"))
        object.__setattr__(self, "provider_id", _text(self.provider_id, "adapter provider id"))
        if not isinstance(self.optional, bool) or not self.capabilities:
            raise InvariantError("adapter matrix requires optional state and capabilities")
        names = tuple(item.name for item in self.capabilities if isinstance(item, AdapterCapability))
        if len(names) != len(self.capabilities) or len(names) != len(set(names)):
            raise InvariantError("adapter matrix capabilities must be typed and distinct")

    def state_for(self, name: str) -> AdapterCapabilityState:
        target = _text(name, "adapter capability lookup")
        for capability in self.capabilities:
            if capability.name == target:
                return capability.state
        return AdapterCapabilityState.UNSUPPORTED

    def execution_ready(self, required: tuple[str, ...]) -> tuple[bool, str]:
        if len(required) != len(set(required)) or any(not isinstance(item, str) or not item.strip() for item in required):
            raise InvariantError("required adapter capabilities must be distinct non-empty names")
        for name in required:
            state = self.state_for(name)
            if state is AdapterCapabilityState.INSTRUCTION_ONLY:
                return False, f"required capability is instruction-only: {name}"
            if state is AdapterCapabilityState.UNSUPPORTED:
                return False, f"required capability is unsupported: {name}"
        return True, ""

    def digest(self) -> str:
        return _canonical_digest(
            {
                "adapter": self.adapter_id,
                "provider": self.provider_id,
                "optional": self.optional,
                "capabilities": tuple(
                    (item.name, item.state.value, item.evidence, item.claim_limit)
                    for item in sorted(self.capabilities, key=lambda value: value.name)
                ),
            }
        )


@dataclass(frozen=True)
class ExecutionAdapterRequest:
    request_id: str
    adapter_id: str
    task_id: str
    accountable_owner: str
    cwd: str
    artifact: ArtifactIdentity
    instruction_digest: str
    required_capabilities: tuple[str, ...]
    routing: ExecutionRoutingDecision
    model: str = ""
    approval_policy: str = ""
    sandbox: str = ""
    request_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for value, label in (
            (self.request_id, "adapter request id"),
            (self.adapter_id, "adapter request adapter id"),
            (self.task_id, "adapter request task id"),
            (self.accountable_owner, "adapter request accountable owner"),
            (self.cwd, "adapter request cwd"),
        ):
            _text(value, label)
        if not (PureWindowsPath(self.cwd).is_absolute() or PurePosixPath(self.cwd).is_absolute()):
            raise InvariantError("adapter request cwd must be absolute")
        if not isinstance(self.artifact, ArtifactIdentity):
            raise InvariantError("adapter request requires an exact artifact identity")
        object.__setattr__(self, "instruction_digest", _digest(self.instruction_digest, "adapter instruction"))
        if not isinstance(self.routing, ExecutionRoutingDecision):
            raise InvariantError("adapter request requires a SWARM execution routing decision")
        if self.routing.route is ExecutionRoute.HARD_BLOCKED:
            raise InvariantError("hard-blocked SWARM routing cannot invoke an execution adapter")
        if self.routing.accountable_owner != self.accountable_owner:
            raise InvariantError("adapter request owner must match the SWARM routing owner")
        required = tuple(_text(item, "required adapter capability") for item in self.required_capabilities)
        if len(required) != len(set(required)):
            raise InvariantError("required adapter capabilities must be distinct")
        object.__setattr__(self, "required_capabilities", required)
        for value, label in ((self.model, "adapter model"), (self.approval_policy, "adapter approval policy"), (self.sandbox, "adapter sandbox")):
            if value:
                _text(value, label)
        payload = {
            "request": self.request_id,
            "adapter": self.adapter_id,
            "task": self.task_id,
            "owner": self.accountable_owner,
            "cwd": self.cwd,
            "artifact": self.artifact.content_address(),
            "instruction": self.instruction_digest,
            "required": self.required_capabilities,
            "route": self.routing.route.value,
            "route_receipt": self.routing.host_receipt,
            "model": self.model,
            "approval_policy": self.approval_policy,
            "sandbox": self.sandbox,
        }
        object.__setattr__(self, "request_digest", _canonical_digest(payload))


@dataclass(frozen=True)
class AdapterExecutionPlan:
    status: AdapterPlanStatus
    adapter_id: str
    request_digest: str
    capability_matrix_digest: str
    entrypoint: tuple[str, ...] = ()
    protocol: str = ""
    blocker: str = ""
    claim_limit: str = "Execution transport is not ownership, proof, review, or acceptance authority."

    @property
    def ready(self) -> bool:
        return self.status is AdapterPlanStatus.READY


@dataclass(frozen=True)
class AdapterEvent:
    method: str
    thread_id: str = ""
    turn_id: str = ""
    item_id: str = ""
    status: str = ""
    evidence_digest: str = ""

    def __post_init__(self) -> None:
        _text(self.method, "adapter event method")
        if self.evidence_digest:
            object.__setattr__(self, "evidence_digest", _digest(self.evidence_digest, "adapter event evidence"))


class ExecutionAdapter:
    """Provider-neutral adapter contract with no implicit fallback."""

    def __init__(self, matrix: AdapterCapabilityMatrix, *, entrypoint: tuple[str, ...], protocol: str, enabled: bool = True) -> None:
        if not isinstance(matrix, AdapterCapabilityMatrix):
            raise InvariantError("execution adapter requires a capability matrix")
        if not isinstance(enabled, bool) or not isinstance(entrypoint, tuple) or any(not isinstance(part, str) or not part for part in entrypoint):
            raise InvariantError("execution adapter requires typed enablement and exact argv")
        self.matrix = matrix
        self.entrypoint = entrypoint
        self.protocol = _text(protocol, "adapter protocol")
        self.enabled = enabled

    def plan(self, request: ExecutionAdapterRequest) -> AdapterExecutionPlan:
        if not isinstance(request, ExecutionAdapterRequest) or request.adapter_id != self.matrix.adapter_id:
            raise InvariantError("execution request targets a different adapter")
        matrix_digest = self.matrix.digest()
        if not self.enabled:
            return AdapterExecutionPlan(
                AdapterPlanStatus.DISABLED,
                self.matrix.adapter_id,
                request.request_digest,
                matrix_digest,
                blocker="optional execution adapter is disabled",
            )
        ready, blocker = self.matrix.execution_ready(request.required_capabilities)
        if not ready:
            return AdapterExecutionPlan(
                AdapterPlanStatus.BLOCKED,
                self.matrix.adapter_id,
                request.request_digest,
                matrix_digest,
                blocker=blocker,
            )
        return AdapterExecutionPlan(
            AdapterPlanStatus.READY,
            self.matrix.adapter_id,
            request.request_digest,
            matrix_digest,
            self.entrypoint,
            self.protocol,
        )


class CodexAppServerAdapter(ExecutionAdapter):
    """Native Codex app-server JSONL protocol adapter; transport is host-owned."""

    ADAPTER_ID = "codex-app-server"

    def __init__(self, *, enabled: bool = True) -> None:
        docs = "official OpenAI Codex App Server protocol"
        matrix = AdapterCapabilityMatrix(
            adapter_id=self.ADAPTER_ID,
            provider_id="openai-codex",
            optional=True,
            capabilities=(
                AdapterCapability("thread.start", AdapterCapabilityState.NATIVE, docs, "Creates a Codex thread only."),
                AdapterCapability("thread.resume", AdapterCapabilityState.NATIVE, docs, "Resumes a recorded Codex thread only."),
                AdapterCapability("turn.start", AdapterCapabilityState.NATIVE, docs, "Starts one Codex turn; it does not accept the result."),
                AdapterCapability("turn.steer", AdapterCapabilityState.NATIVE, docs, "Steers an active turn without changing SWARM ownership."),
                AdapterCapability("event.stream", AdapterCapabilityState.NATIVE, docs, "Streams Codex lifecycle events; raw bodies are not retained by this adapter."),
                AdapterCapability("approval.request", AdapterCapabilityState.NATIVE, docs, "Codex may request approval; SWARM cannot forge a user decision."),
                AdapterCapability("swarm.routing", AdapterCapabilityState.ENFORCED, "ExecutionAdapterRequest", "The request must carry a non-blocked SWARM routing decision for the same owner."),
                AdapterCapability("model.instructions", AdapterCapabilityState.INSTRUCTION_ONLY, "model input", "Instructions guide behavior but do not enforce ownership, proof, or policy."),
                AdapterCapability("review.acceptance", AdapterCapabilityState.UNSUPPORTED, "SWARM review contract", "Adapter output cannot independently review or accept its own artifact."),
                AdapterCapability("host.task_mutation", AdapterCapabilityState.UNSUPPORTED, "SWARM user-custody contract", "No title, pin, folder, order, archive, or other host task mutation is exposed."),
            ),
        )
        super().__init__(matrix, entrypoint=("codex", "app-server", "--listen", "stdio://"), protocol="json-rpc-2.0-jsonl", enabled=enabled)

    @staticmethod
    def initialize_request(client_name: str, *, request_id: int = 0) -> dict[str, object]:
        name = _text(client_name, "Codex adapter client name")
        if not isinstance(request_id, int) or request_id < 0:
            raise InvariantError("Codex adapter request id must be non-negative")
        return {"method": "initialize", "id": request_id, "params": {"clientInfo": {"name": name, "title": name, "version": "1"}}}

    @staticmethod
    def initialized_notification() -> dict[str, object]:
        return {"method": "initialized", "params": {}}

    def thread_request(self, plan: AdapterExecutionPlan, request: ExecutionAdapterRequest, *, request_id: int = 1, thread_id: str = "") -> dict[str, object]:
        self._require_ready(plan, request)
        if not isinstance(request_id, int) or request_id < 0:
            raise InvariantError("Codex adapter request id must be non-negative")
        params: dict[str, object] = {}
        if thread_id:
            params["threadId"] = _text(thread_id, "Codex thread id")
            method = "thread/resume"
        else:
            method = "thread/start"
            params["cwd"] = request.cwd
        if request.model:
            params["model"] = request.model
        if request.approval_policy:
            params["approvalPolicy"] = request.approval_policy
        if request.sandbox:
            params["sandbox"] = request.sandbox
        return {"method": method, "id": request_id, "params": params}

    def turn_request(self, plan: AdapterExecutionPlan, request: ExecutionAdapterRequest, *, thread_id: str, instruction: str, request_id: int = 2) -> dict[str, object]:
        self._require_ready(plan, request)
        target = _text(thread_id, "Codex thread id")
        if not isinstance(instruction, str) or sha256(instruction.encode("utf-8")).hexdigest() != request.instruction_digest:
            raise InvariantError("Codex turn instruction does not match the authorized request digest")
        if not isinstance(request_id, int) or request_id < 0:
            raise InvariantError("Codex adapter request id must be non-negative")
        params: dict[str, object] = {"threadId": target, "input": [{"type": "text", "text": instruction}], "cwd": request.cwd}
        if request.model:
            params["model"] = request.model
        if request.approval_policy:
            params["approvalPolicy"] = request.approval_policy
        return {"method": "turn/start", "id": request_id, "params": params}

    def translate_event(self, message: Mapping[str, object]) -> AdapterEvent:
        if not isinstance(message, Mapping):
            raise InvariantError("Codex adapter event must be a JSON object")
        method = str(message.get("method") or "unknown")
        params = message.get("params")
        body = params if isinstance(params, Mapping) else {}
        thread = body.get("thread") if isinstance(body.get("thread"), Mapping) else {}
        turn = body.get("turn") if isinstance(body.get("turn"), Mapping) else {}
        item = body.get("item") if isinstance(body.get("item"), Mapping) else {}
        digest = _canonical_digest(message)
        return AdapterEvent(
            method=method,
            thread_id=str(body.get("threadId") or thread.get("id") or ""),
            turn_id=str(body.get("turnId") or turn.get("id") or ""),
            item_id=str(body.get("itemId") or item.get("id") or ""),
            status=str(body.get("status") or turn.get("status") or item.get("status") or ""),
            evidence_digest=digest,
        )

    def _require_ready(self, plan: AdapterExecutionPlan, request: ExecutionAdapterRequest) -> None:
        if not isinstance(plan, AdapterExecutionPlan) or not plan.ready or plan.adapter_id != self.matrix.adapter_id:
            raise InvariantError("Codex adapter wire messages require a ready execution plan")
        if plan.request_digest != request.request_digest or plan.capability_matrix_digest != self.matrix.digest():
            raise InvariantError("Codex adapter plan does not match the exact request or capability matrix")


class AdapterRegistry:
    """Explicit adapter selection; missing adapters never trigger a fallback."""

    def __init__(self, adapters: tuple[ExecutionAdapter, ...] = ()) -> None:
        if any(not isinstance(adapter, ExecutionAdapter) for adapter in adapters):
            raise InvariantError("adapter registry accepts execution adapters only")
        self._adapters = {adapter.matrix.adapter_id: adapter for adapter in adapters}
        if len(self._adapters) != len(adapters):
            raise InvariantError("adapter registry ids must be distinct")

    def capability_matrix(self, adapter_id: str) -> AdapterCapabilityMatrix | None:
        adapter = self._adapters.get(_text(adapter_id, "adapter id"))
        return None if adapter is None else adapter.matrix

    def plan(self, request: ExecutionAdapterRequest) -> AdapterExecutionPlan:
        if not isinstance(request, ExecutionAdapterRequest):
            raise InvariantError("adapter registry requires a typed execution request")
        adapter = self._adapters.get(request.adapter_id)
        if adapter is None:
            return AdapterExecutionPlan(
                AdapterPlanStatus.DISABLED,
                request.adapter_id,
                request.request_digest,
                "0" * 64,
                blocker="optional execution adapter is not configured",
            )
        return adapter.plan(request)
