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
from typing import Mapping, Protocol

from .core import (
    ArtifactIdentity,
    DelegatedReceiptVerdict,
    DelegatedReturnReceipt,
    ExecutionRoute,
    ExecutionRoutingDecision,
    InvariantError,
    ProofState,
    Swarm,
    TaskState,
)
from .topology import TopologyDispatchPacket


_DIGEST_CHARS = frozenset("0123456789abcdef")
_HOST_EVENT_AUTHORITY = object()
_HOST_RESPONSE_AUTHORITY = object()


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


class ChatGPTRouteStatus(StrEnum):
    READY = "ready"
    FALLBACK = "fallback"
    UNAVAILABLE = "unavailable"


class HQCommandAction(StrEnum):
    AUTO = "AUTO"
    MANUAL_AGENT = "MANUAL_AGENT"
    TASK = "TASK"
    TOPOLOGY_MATERIALIZE = "TOPOLOGY_MATERIALIZE"
    REPAIR = "REPAIR"
    LOCAL_HQ = "LOCAL_HQ"


class HQTargetIntent(StrEnum):
    NEW_THREAD = "NEW_THREAD"
    EXISTING_THREAD = "EXISTING_THREAD"
    LOCAL = "LOCAL"


HQ_ACTION_CAPABILITIES = {
    HQCommandAction.AUTO: (("thread.resume", "turn.start"), HQTargetIntent.EXISTING_THREAD),
    HQCommandAction.MANUAL_AGENT: (("thread.start", "turn.start"), HQTargetIntent.NEW_THREAD),
    HQCommandAction.TASK: (("thread.resume", "turn.start"), HQTargetIntent.EXISTING_THREAD),
    HQCommandAction.TOPOLOGY_MATERIALIZE: (("thread.start", "turn.start"), HQTargetIntent.NEW_THREAD),
    HQCommandAction.REPAIR: (("thread.resume", "turn.steer"), HQTargetIntent.EXISTING_THREAD),
    HQCommandAction.LOCAL_HQ: (("local",), HQTargetIntent.LOCAL),
}


@dataclass(frozen=True)
class HQCommandEnvelope:
    command_id: str
    idempotency_key: str
    action: HQCommandAction
    project_id: str
    root_digest: str
    ctrl_id: str
    target_intent: HQTargetIntent
    target_thread_id: str
    payload_digest: str
    expected_ledger_revision: int
    submitted_at_ms: int
    expires_at_ms: int
    target_turn_id: str = ""
    acknowledgement_required: bool = True
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        for value, label in ((self.command_id, "HQ command"), (self.idempotency_key, "HQ idempotency key"), (self.project_id, "HQ project")):
            _text(value, label)
        if not isinstance(self.action, HQCommandAction) or not isinstance(self.target_intent, HQTargetIntent):
            raise InvariantError("HQ action and target intent must be typed")
        _, expected_target = HQ_ACTION_CAPABILITIES[self.action]
        if self.target_intent is not expected_target:
            raise InvariantError("HQ target intent conflicts with action")
        if self.ctrl_id:
            _text(self.ctrl_id, "HQ CTRL")
        if self.target_intent is HQTargetIntent.EXISTING_THREAD:
            _text(self.target_thread_id, "HQ target thread")
        elif self.target_thread_id:
            raise InvariantError("new-thread and local commands cannot name an existing thread")
        if self.action is HQCommandAction.REPAIR:
            _text(self.target_turn_id, "HQ target turn")
        elif self.target_turn_id:
            raise InvariantError("only repair commands may name an active turn")
        object.__setattr__(self, "root_digest", _digest(self.root_digest, "HQ root"))
        object.__setattr__(self, "payload_digest", _digest(self.payload_digest, "HQ payload"))
        if not isinstance(self.expected_ledger_revision, int) or isinstance(self.expected_ledger_revision, bool) or self.expected_ledger_revision < 0:
            raise InvariantError("HQ expected Ledger revision must be nonnegative")
        if not isinstance(self.submitted_at_ms, int) or isinstance(self.submitted_at_ms, bool) or self.submitted_at_ms < 0 or not isinstance(self.expires_at_ms, int) or isinstance(self.expires_at_ms, bool) or self.expires_at_ms < self.submitted_at_ms or self.acknowledgement_required is not True:
            raise InvariantError("HQ command requires bounded submission, expiry, and acknowledgement")
        object.__setattr__(self, "digest", _canonical_digest({
            "command_id": self.command_id, "idempotency_key": self.idempotency_key, "action": self.action.value,
            "project_id": self.project_id, "root_digest": self.root_digest, "ctrl_id": self.ctrl_id,
            "target_intent": self.target_intent.value, "target_thread_id": self.target_thread_id,
            "target_turn_id": self.target_turn_id,
            "payload_digest": self.payload_digest, "expected_ledger_revision": self.expected_ledger_revision,
            "submitted_at_ms": self.submitted_at_ms, "expires_at_ms": self.expires_at_ms, "acknowledgement_required": True,
        }))


@dataclass(frozen=True, repr=False)
class HQDispatchMaterial:
    """Ephemeral host-resolved cwd and instruction bytes; never persisted."""

    cwd: str = field(repr=False)
    instruction_bytes: bytes = field(repr=False)
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "cwd", _text(self.cwd, "HQ dispatch cwd"))
        if not isinstance(self.instruction_bytes, bytes) or not self.instruction_bytes or len(self.instruction_bytes) > 32_768:
            raise InvariantError("HQ dispatch material requires bounded instruction bytes")
        try:
            instruction = self.instruction_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvariantError("HQ dispatch instruction must be UTF-8") from exc
        if not instruction.strip() or "\x00" in instruction:
            raise InvariantError("HQ dispatch instruction must be non-empty text")
        object.__setattr__(self, "digest", sha256(self.instruction_bytes).hexdigest())

    @property
    def instruction(self) -> str:
        return self.instruction_bytes.decode("utf-8")

    def input_items(self) -> list[dict[str, object]]:
        return [{"type": "text", "text": self.instruction, "text_elements": []}]

    def __repr__(self) -> str:
        return "HQDispatchMaterial(<redacted>)"


@dataclass(frozen=True)
class HQAuthorizationReceipt:
    receipt_id: str
    envelope_digest: str
    project_id: str
    root_digest: str
    ctrl_id: str
    actions: tuple[HQCommandAction, ...]
    expires_at_ms: int

    def __post_init__(self) -> None:
        _text(self.receipt_id, "HQ authorization receipt")
        object.__setattr__(self, "envelope_digest", _digest(self.envelope_digest, "HQ authorization envelope"))
        object.__setattr__(self, "root_digest", _digest(self.root_digest, "HQ authorization root"))
        _text(self.project_id, "HQ authorization project")
        if self.ctrl_id:
            _text(self.ctrl_id, "HQ authorization CTRL")
        if not self.actions or any(not isinstance(action, HQCommandAction) for action in self.actions):
            raise InvariantError("HQ authorization actions must be typed")
        if not isinstance(self.expires_at_ms, int) or isinstance(self.expires_at_ms, bool) or self.expires_at_ms < 1:
            raise InvariantError("HQ authorization expiry must be positive")


@dataclass(frozen=True)
class HQAutoGrant:
    grant_id: str
    project_id: str
    root_digest: str
    ctrl_id: str
    actions: tuple[HQCommandAction, ...]
    expires_at_ms: int

    def __post_init__(self) -> None:
        _text(self.grant_id, "HQ Auto grant")
        _text(self.project_id, "HQ Auto project")
        _text(self.ctrl_id, "HQ Auto CTRL")
        object.__setattr__(self, "root_digest", _digest(self.root_digest, "HQ Auto root"))
        if self.actions != (HQCommandAction.AUTO,):
            raise InvariantError("HQ Auto grant may authorize only AUTO")
        if not isinstance(self.expires_at_ms, int) or isinstance(self.expires_at_ms, bool) or self.expires_at_ms < 1:
            raise InvariantError("HQ Auto grant expiry must be positive")


class HQAuthorizationVerifier(Protocol):
    def verify(self, authorization: HQAuthorizationReceipt | HQAutoGrant, envelope: HQCommandEnvelope, now_ms: int) -> bool: ...


class HQDispatchMaterialResolver(Protocol):
    def resolve(self, envelope: HQCommandEnvelope) -> HQDispatchMaterial: ...


@dataclass(frozen=True)
class HQRootObservation:
    receipt_id: str
    canonical_cwd: str
    root_digest: str

    def __post_init__(self) -> None:
        _text(self.receipt_id, "HQ root observation receipt")
        _text(self.canonical_cwd, "HQ canonical cwd")
        object.__setattr__(self, "root_digest", _digest(self.root_digest, "HQ observed root"))


class HQRootVerifier(Protocol):
    def observe(self, cwd: str) -> HQRootObservation: ...

    def verify(self, observation: HQRootObservation, envelope: HQCommandEnvelope) -> bool: ...


class CodexAppServerTransport(Protocol):
    def request(self, method: str, params: Mapping[str, object]) -> Mapping[str, object]: ...

    def reconcile(self, command_id: str, action: str, target_thread_id: str) -> Mapping[str, object] | None: ...


@dataclass(frozen=True)
class HQConnectorResult:
    status: str
    command_digest: str
    thread_id: str = ""
    turn_id: str = ""
    local_plan: Mapping[str, str] | None = None
    attention: str = ""


class UniversalHQConnector:
    def __init__(self, adapter: "CodexAppServerAdapter", *, authorization_verifier: HQAuthorizationVerifier, material_resolver: HQDispatchMaterialResolver, root_verifier: HQRootVerifier) -> None:
        if not isinstance(adapter, CodexAppServerAdapter):
            raise InvariantError("universal connector requires the Codex adapter")
        self.adapter = adapter
        self.authorization_verifier = authorization_verifier
        self.material_resolver = material_resolver
        self.root_verifier = root_verifier

    @staticmethod
    def _receipt(envelope: HQCommandEnvelope, *, receipt_id: str, index: int, status: str, observed_at_ms: int, thread_id: str | None = None, turn_id: str | None = None, observed_root_digest: str | None = None) -> dict[str, object]:
        return {"schema_version": 1, "record_type": "CONNECTOR", "receipt_id": receipt_id, "command_id": envelope.command_id, "receipt_index": index, "idempotency_key": envelope.idempotency_key, "command_digest": envelope.digest, "project_id": envelope.project_id, "root_digest": envelope.root_digest, "action": envelope.action.value, "status": status, "thread_id": thread_id, "turn_id": turn_id, "observed_root_digest": observed_root_digest, "observed_at_ms": observed_at_ms}

    @staticmethod
    def _host_binding(response: Mapping[str, object]) -> tuple[str, str, str]:
        if not isinstance(response, Mapping):
            raise InvariantError("Codex host response must be an object")
        bodies = [response]
        if "result" in response:
            result = response["result"]
            if not isinstance(result, Mapping):
                raise InvariantError("Codex host result must be an object")
            bodies.append(result)

        def string_alias(label: str, candidates: list[object]) -> str:
            values: list[str] = []
            for candidate in candidates:
                if candidate is None:
                    continue
                if not isinstance(candidate, str) or not candidate.strip():
                    raise InvariantError(f"Codex host {label} must be a non-empty string")
                values.append(candidate)
            if len(set(values)) > 1:
                raise InvariantError(f"Codex host {label} aliases conflict")
            return values[0] if values else ""

        def identity(kind: str) -> str:
            candidates: list[object] = []
            for body in bodies:
                direct = body.get(f"{kind}Id")
                nested = body.get(kind)
                candidates.append(direct)
                if nested is not None:
                    if not isinstance(nested, Mapping):
                        raise InvariantError(f"Codex host {kind} identity must be an object")
                    candidates.append(nested.get("id"))
                if kind == "thread":
                    turn = body.get("turn")
                    if turn is not None:
                        if not isinstance(turn, Mapping):
                            raise InvariantError("Codex host turn identity must be an object")
                        candidates.append(turn.get("threadId"))
            return string_alias(f"{kind} identity", candidates)

        cwd_candidates: list[object] = []
        for body in bodies:
            cwd_candidates.append(body.get("cwd"))
            thread = body.get("thread")
            if thread is not None:
                if not isinstance(thread, Mapping):
                    raise InvariantError("Codex host thread identity must be an object")
                cwd_candidates.append(thread.get("cwd"))
        return identity("thread"), identity("turn"), string_alias("cwd", cwd_candidates)

    @staticmethod
    def _require_host_binding(response: Mapping[str, object], envelope: HQCommandEnvelope, *, thread_id: str = "", require_turn: bool) -> tuple[str, str, str]:
        observed_thread, observed_turn, observed_cwd = UniversalHQConnector._host_binding(response)
        if not observed_thread and observed_turn and thread_id:
            observed_thread = thread_id
        if not observed_thread or (thread_id and observed_thread != thread_id):
            raise InvariantError("Codex host response has ambiguous or conflicting thread identity")
        if require_turn and not observed_turn:
            raise InvariantError("Codex host turn response omitted turn identity")
        if envelope.action is HQCommandAction.REPAIR and observed_turn and (
            observed_thread != envelope.target_thread_id or observed_turn != envelope.target_turn_id
        ):
            raise InvariantError("Codex repair response conflicts with the targeted thread or turn")
        return observed_thread, observed_turn, observed_cwd

    def _verify_cwd_root(self, envelope: HQCommandEnvelope, cwd: str) -> str:
        observation = self.root_verifier.observe(cwd)
        if (
            not isinstance(observation, HQRootObservation)
            or observation.canonical_cwd != cwd
            or observation.root_digest != envelope.root_digest
            or not self.root_verifier.verify(observation, envelope)
        ):
            raise InvariantError("HQ host cwd does not bind the authorized canonical root")
        return observation.root_digest

    def _require_root_bound_thread(self, response: Mapping[str, object], envelope: HQCommandEnvelope, *, thread_id: str = "") -> tuple[str, str, str]:
        observed_thread, observed_turn, observed_cwd = self._require_host_binding(response, envelope, thread_id=thread_id, require_turn=False)
        if not observed_cwd:
            raise InvariantError("Codex host thread response omitted cwd")
        return observed_thread, observed_turn, self._verify_cwd_root(envelope, observed_cwd)

    def _validate_authorization(self, envelope: HQCommandEnvelope, authorization: HQAuthorizationReceipt | HQAutoGrant, now_ms: int) -> None:
        if isinstance(authorization, HQAuthorizationReceipt):
            if authorization.envelope_digest != envelope.digest:
                raise InvariantError("explicit HQ authorization does not bind the command")
        elif isinstance(authorization, HQAutoGrant):
            if envelope.action is not HQCommandAction.AUTO:
                raise InvariantError("HQ Auto grant cannot authorize this action")
        else:
            raise InvariantError("connector requires typed host authorization")
        if now_ms > min(envelope.expires_at_ms, authorization.expires_at_ms):
            raise InvariantError("HQ command authorization expired")
        if isinstance(authorization, HQAuthorizationReceipt) and authorization.actions != (envelope.action,):
            raise InvariantError("explicit HQ authorization must bind exactly one action")
        if envelope.action not in authorization.actions:
            raise InvariantError("HQ authorization does not bind the command")
        if (authorization.project_id, authorization.root_digest, authorization.ctrl_id) != (envelope.project_id, envelope.root_digest, envelope.ctrl_id):
            raise InvariantError("HQ authorization scope conflicts")
        if not self.authorization_verifier.verify(authorization, envelope, now_ms):
            raise InvariantError("host verifier rejected HQ authorization")

    @staticmethod
    def _receipts(command: Mapping[str, object]) -> list[Mapping[str, object]]:
        receipts = command.get("receipts")
        return list(receipts) if isinstance(receipts, list) else []

    def _append_complete(self, envelope: HQCommandEnvelope, ledger: object, *, now_ms: int, thread_id: str, turn_id: str, observed_root_digest: str, ack_exists: bool) -> HQConnectorResult:
        if not ack_exists:
            ledger.append_connector_receipt(self._receipt(envelope, receipt_id=f"{envelope.command_id}-ack", index=1, status="ACKNOWLEDGED", observed_at_ms=now_ms, thread_id=thread_id, observed_root_digest=observed_root_digest))
        ledger.append_connector_receipt(self._receipt(envelope, receipt_id=f"{envelope.command_id}-result", index=2, status="RESULT", observed_at_ms=now_ms, thread_id=thread_id, turn_id=turn_id, observed_root_digest=observed_root_digest))
        return HQConnectorResult("RESULT", envelope.digest, thread_id, turn_id)

    def _reconcile(self, envelope: HQCommandEnvelope, ledger: object, command: Mapping[str, object], *, now_ms: int) -> HQConnectorResult:
        receipts = self._receipts(command)
        if receipts and str(receipts[-1].get("status") or "") in {"RESULT", "UNSUPPORTED"}:
            return HQConnectorResult("REPLAY", envelope.digest)
        ack = receipts[-1] if receipts and str(receipts[-1].get("status") or "") == "ACKNOWLEDGED" else None
        known_thread = str(ack.get("thread_id") or "") if ack else envelope.target_thread_id
        try:
            response = self.adapter.reconcile(envelope, thread_id=known_thread)
        except Exception:
            return HQConnectorResult("PENDING", envelope.digest, known_thread, attention="HOST_RECONCILIATION_UNAVAILABLE")
        if response is None:
            return HQConnectorResult("PENDING", envelope.digest, known_thread, attention="HOST_OUTCOME_PENDING")
        try:
            thread_id, turn_id, verified_root_digest = self._require_root_bound_thread(response, envelope, thread_id=known_thread)
        except InvariantError:
            return HQConnectorResult("ATTENTION", envelope.digest, known_thread, attention="HOST_IDENTITY_CONFLICT")
        if not turn_id:
            if ack is None:
                ledger.append_connector_receipt(self._receipt(envelope, receipt_id=f"{envelope.command_id}-ack", index=1, status="ACKNOWLEDGED", observed_at_ms=now_ms, thread_id=thread_id, observed_root_digest=verified_root_digest))
            return HQConnectorResult("PENDING", envelope.digest, thread_id, attention="HOST_TURN_OUTCOME_PENDING")
        return self._append_complete(envelope, ledger, now_ms=now_ms, thread_id=thread_id, turn_id=turn_id, observed_root_digest=verified_root_digest, ack_exists=ack is not None)

    def execute(self, envelope: HQCommandEnvelope, authorization: HQAuthorizationReceipt | HQAutoGrant, ledger: object, *, now_ms: int, observed_project_id: str, observed_root_digest: str) -> HQConnectorResult:
        if not isinstance(envelope, HQCommandEnvelope):
            raise InvariantError("connector requires a typed command envelope")
        if (observed_project_id, _digest(observed_root_digest, "observed HQ root")) != (envelope.project_id, envelope.root_digest):
            raise InvariantError("HQ observed project root conflicts")
        command = self._receipt(envelope, receipt_id=f"{envelope.command_id}-command", index=0, status="COMMAND", observed_at_ms=envelope.submitted_at_ms)
        retained = ledger.replay().get("connector_receipts", {}).get(envelope.idempotency_key)
        if retained is not None:
            reservation = ledger.reserve_connector_command(command, expected_revision=envelope.expected_ledger_revision)
            if reservation["status"] == "REPLAY":
                return self._reconcile(envelope, ledger, reservation["command"], now_ms=now_ms)
            raise InvariantError("HQ command reservation conflicts")
        self._validate_authorization(envelope, authorization, now_ms)
        material = self.material_resolver.resolve(envelope)
        if not isinstance(material, HQDispatchMaterial) or material.digest != envelope.payload_digest:
            raise InvariantError("HQ dispatch material does not match the authorized digest")
        self._verify_cwd_root(envelope, material.cwd)
        reservation = ledger.reserve_connector_command(command, expected_revision=envelope.expected_ledger_revision)
        if reservation["status"] == "REPLAY":
            return self._reconcile(envelope, ledger, reservation["command"], now_ms=now_ms)
        if reservation["status"] != "APPENDED":
            raise InvariantError("HQ command reservation conflicts")
        capabilities, _ = HQ_ACTION_CAPABILITIES[envelope.action]
        if capabilities == ("local",):
            return HQConnectorResult("LOCAL_PLAN", envelope.digest, local_plan={"command_id": envelope.command_id, "project_id": envelope.project_id, "root_digest": envelope.root_digest})
        plan = self.adapter.plan_hq(envelope)
        if not plan.ready:
            ledger.append_connector_receipt(self._receipt(envelope, receipt_id=f"{envelope.command_id}-unsupported", index=1, status="UNSUPPORTED", observed_at_ms=now_ms))
            return HQConnectorResult("UNSUPPORTED", envelope.digest)
        first_capability = "thread.start" if envelope.target_intent is HQTargetIntent.NEW_THREAD else "thread.resume"
        try:
            started = self.adapter.dispatch(envelope, material, first_capability, thread_id=envelope.target_thread_id)
            thread_id, premature_turn_id, verified_root_digest = self._require_root_bound_thread(started, envelope, thread_id=envelope.target_thread_id)
            if premature_turn_id:
                raise InvariantError("Codex thread response cannot claim a turn result")
        except Exception:
            return HQConnectorResult("PENDING", envelope.digest, envelope.target_thread_id, attention="HOST_THREAD_OUTCOME_PENDING")
        ledger.append_connector_receipt(self._receipt(envelope, receipt_id=f"{envelope.command_id}-ack", index=1, status="ACKNOWLEDGED", observed_at_ms=now_ms, thread_id=thread_id, observed_root_digest=verified_root_digest))
        try:
            turn_capability = "turn.steer" if envelope.action is HQCommandAction.REPAIR else "turn.start"
            response = self.adapter.dispatch(envelope, material, turn_capability, thread_id=thread_id)
            thread_id, turn_id, _ = self._require_host_binding(response, envelope, thread_id=thread_id, require_turn=True)
        except Exception:
            return HQConnectorResult("PENDING", envelope.digest, thread_id, attention="HOST_TURN_OUTCOME_PENDING")
        ledger.append_connector_receipt(self._receipt(envelope, receipt_id=f"{envelope.command_id}-result", index=2, status="RESULT", observed_at_ms=now_ms, thread_id=thread_id, turn_id=turn_id, observed_root_digest=verified_root_digest))
        return HQConnectorResult("RESULT", envelope.digest, thread_id, turn_id)


@dataclass(frozen=True)
class HostChatGPTCapability:
    """One host-observed ChatGPT surface; SWARM never discovers or invokes it."""

    surface: str
    capability_id: str
    receipt_id: str
    workspace_id: str = ""
    supports_model_selection: bool = False
    supports_reasoning_selection: bool = False

    def __post_init__(self) -> None:
        if self.surface not in {"chat", "image", "work"}:
            raise InvariantError("ChatGPT capability surface must be chat, image, or work")
        _text(self.capability_id, "ChatGPT capability id")
        _text(self.receipt_id, "ChatGPT capability receipt")
        if self.surface == "work" and not self.workspace_id:
            raise InvariantError("ChatGPT Work capability requires an exact host workspace")
        if self.workspace_id:
            _text(self.workspace_id, "ChatGPT workspace id")
        if not isinstance(self.supports_model_selection, bool) or not isinstance(self.supports_reasoning_selection, bool):
            raise InvariantError("ChatGPT model selection support must be host-observed booleans")


@dataclass(frozen=True)
class ChatGPTRoutingPlan:
    status: ChatGPTRouteStatus
    surface: str
    adapter_id: str
    capability_id: str = ""
    capability_receipt_id: str = ""
    workspace_id: str = ""
    model: str = ""
    reasoning: str = ""
    reason: str = ""
    claim_limit: str = (
        "ChatGPT output is untrusted advice or a provider-owned image artifact; local mutation, proof, review, and acceptance remain SWARM/Codex-owned."
    )


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
    _authority: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _text(self.method, "adapter event method")
        if self.evidence_digest:
            object.__setattr__(self, "evidence_digest", _digest(self.evidence_digest, "adapter event evidence"))


class ExecutionDispatchState(StrEnum):
    QUEUED = "queued"
    DEFERRED = "deferred"
    ACTIVE = "active"
    CHECKPOINTED = "checkpointed"
    MATERIAL_RECEIPT = "material_receipt"
    INDEPENDENT_REVIEW = "independent_review"
    COMPLETE = "complete"
    UNVERIFIED = "unverified"


class ExecutionFailureKind(StrEnum):
    SILENCE = "silence"
    EMPTY = "empty"
    UNREADABLE = "unreadable"
    TIMEOUT = "timeout"
    BAD_REQUEST = "http_400_bad_request"
    HOST_FAILED = "host_failed"


class ServiceTierTruth(StrEnum):
    CONFIRMED = "confirmed"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class ExecutionConfigGeneration:
    """Host-observed dispatch preference; it is not a served-tier receipt."""

    generation_id: str
    fast_mode: bool
    model: str
    effort: str
    changed_at_ms: int
    host_receipt_id: str

    def __post_init__(self) -> None:
        _text(self.generation_id, "execution config generation id")
        if not isinstance(self.fast_mode, bool):
            raise InvariantError("execution config generation requires boolean fast_mode")
        for value, label in ((self.model, "execution config model"), (self.effort, "execution config effort")):
            if value:
                _text(value, label)
        if not isinstance(self.changed_at_ms, int) or isinstance(self.changed_at_ms, bool) or self.changed_at_ms < 0:
            raise InvariantError("execution config generation requires a nonnegative changed-at timestamp")
        _text(self.host_receipt_id, "execution config host receipt")

    @property
    def digest(self) -> str:
        return _canonical_digest((self.generation_id, self.fast_mode, self.model, self.effort, self.changed_at_ms, self.host_receipt_id))

    @property
    def requested_service_tier(self) -> str:
        """Translate the sole SWARM mode authority into one host request value."""
        return "fast" if self.fast_mode else "default"

    @property
    def host_features(self) -> dict[str, bool]:
        return {"fast_mode": self.fast_mode}


@dataclass(frozen=True)
class HostServiceTierReceipt:
    request_digest: str
    actual_service_tier: str
    receipt_id: str
    observed_at_ms: int
    _authority: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_digest", _digest(self.request_digest, "served-tier request"))
        if self.actual_service_tier not in {"default", "fast", "priority"}:
            raise InvariantError("served-tier receipt requires default, fast, or priority")
        _text(self.receipt_id, "served-tier host receipt")
        if not isinstance(self.observed_at_ms, int) or isinstance(self.observed_at_ms, bool) or self.observed_at_ms < 0:
            raise InvariantError("served-tier receipt requires a nonnegative observation time")


@dataclass(frozen=True)
class ContinuationSnapshot:
    """Content-free compaction receipt for one bounded retry."""

    digest: str
    source_bytes: int
    compacted_bytes: int
    observed_at_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "digest", _digest(self.digest, "continuation snapshot"))
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in (self.source_bytes, self.compacted_bytes, self.observed_at_ms)):
            raise InvariantError("continuation snapshot requires nonnegative integer sizes and time")
        if self.source_bytes <= 0 or self.compacted_bytes >= self.source_bytes or self.compacted_bytes > 16384:
            raise InvariantError("continuation snapshot must be provably smaller and bounded to 16 KiB")


@dataclass
class ExecutionReservation:
    reservation_id: str
    task_id: str
    owner_id: str
    artifact: ArtifactIdentity
    state: ExecutionDispatchState = ExecutionDispatchState.QUEUED
    request_digest: str = ""
    request_bytes: int = 0
    generation_id: str = ""
    requested_fast_mode: bool = False
    requested_service_tier: str = ""
    requested_model: str = ""
    requested_effort: str = ""
    actual_service_tier: str = ""
    service_tier_truth: ServiceTierTruth = ServiceTierTruth.UNVERIFIED
    next_generation_id: str = ""
    host_thread_id: str = ""
    host_turn_id: str = ""
    host_completed: bool = False
    material_receipt_id: str = ""
    failure_kind: ExecutionFailureKind | None = None
    retry_count: int = 0
    snapshot_digest: str = ""
    updated_at_ms: int = 0

    def __post_init__(self) -> None:
        for value, label in ((self.reservation_id, "execution reservation id"), (self.task_id, "execution task id"), (self.owner_id, "execution owner id")):
            _text(value, label)
        if not isinstance(self.artifact, ArtifactIdentity) or not isinstance(self.state, ExecutionDispatchState):
            raise InvariantError("execution reservation requires exact artifact and typed state")
        if self.request_digest:
            self.request_digest = _digest(self.request_digest, "retained execution request")
        if not isinstance(self.request_bytes, int) or isinstance(self.request_bytes, bool) or self.request_bytes < 0:
            raise InvariantError("execution reservation request size must be nonnegative")
        if self.requested_service_tier and self.requested_service_tier not in {"default", "fast", "priority"}:
            raise InvariantError("retained requested service tier is invalid")
        if not isinstance(self.requested_fast_mode, bool) or self.requested_fast_mode != (self.requested_service_tier in {"fast", "priority"}):
            raise InvariantError("retained requested Fast flag must be derived from requested service tier")
        if self.actual_service_tier and self.actual_service_tier not in {"default", "fast", "priority"}:
            raise InvariantError("retained actual service tier is invalid")
        if not isinstance(self.service_tier_truth, ServiceTierTruth) or self.service_tier_truth is ServiceTierTruth.CONFIRMED and not self.actual_service_tier:
            raise InvariantError("retained served-tier truth requires exact host metadata")
        if self.failure_kind is not None and not isinstance(self.failure_kind, ExecutionFailureKind):
            raise InvariantError("retained execution failure must be typed")
        if not isinstance(self.host_completed, bool):
            raise InvariantError("retained host completion state must be boolean")
        if not isinstance(self.retry_count, int) or isinstance(self.retry_count, bool) or not 0 <= self.retry_count <= 1:
            raise InvariantError("execution reservation permits at most one retry")
        if self.snapshot_digest:
            self.snapshot_digest = _digest(self.snapshot_digest, "retained continuation snapshot")
        if not isinstance(self.updated_at_ms, int) or isinstance(self.updated_at_ms, bool) or self.updated_at_ms < 0:
            raise InvariantError("execution reservation requires a nonnegative update time")

    def snapshot(self) -> dict[str, object]:
        return {
            "reservation_id": self.reservation_id,
            "task_id": self.task_id,
            "owner_id": self.owner_id,
            "artifact": {
                "base": self.artifact.base,
                "revision": self.artifact.revision,
                "purpose": self.artifact.purpose,
                "observables": self.artifact.observables,
                "observed_paths": self.artifact.observed_paths,
            },
            "state": self.state.value,
            "request_digest": self.request_digest,
            "request_bytes": self.request_bytes,
            "generation_id": self.generation_id,
            "requested_fast_mode": self.requested_fast_mode,
            "requested_service_tier": self.requested_service_tier,
            "requested_model": self.requested_model,
            "requested_effort": self.requested_effort,
            "actual_service_tier": self.actual_service_tier,
            "service_tier_truth": self.service_tier_truth.value,
            "next_generation_id": self.next_generation_id,
            "host_thread_id": self.host_thread_id,
            "host_turn_id": self.host_turn_id,
            "host_completed": self.host_completed,
            "material_receipt_id": self.material_receipt_id,
            "failure_kind": None if self.failure_kind is None else self.failure_kind.value,
            "retry_count": self.retry_count,
            "snapshot_digest": self.snapshot_digest,
            "updated_at_ms": self.updated_at_ms,
        }

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, object]) -> "ExecutionReservation":
        artifact_payload = payload.get("artifact")
        if not isinstance(artifact_payload, Mapping):
            raise InvariantError("execution reservation snapshot requires an artifact")
        artifact = ArtifactIdentity(
            str(artifact_payload.get("base") or ""),
            str(artifact_payload.get("revision") or ""),
            str(artifact_payload.get("purpose") or ""),
            tuple(tuple(item) for item in artifact_payload.get("observables", ())),  # type: ignore[arg-type]
            tuple(str(item) for item in artifact_payload.get("observed_paths", ())),  # type: ignore[arg-type]
        )
        failure = payload.get("failure_kind")
        requested_service_tier = str(payload.get("requested_service_tier") or "")
        requested_fast_mode = payload.get("requested_fast_mode")
        if requested_fast_mode is None:
            requested_fast_mode = requested_service_tier in {"fast", "priority"}
        return cls(
            reservation_id=str(payload.get("reservation_id") or ""),
            task_id=str(payload.get("task_id") or ""),
            owner_id=str(payload.get("owner_id") or ""),
            artifact=artifact,
            state=ExecutionDispatchState(str(payload.get("state") or "")),
            request_digest=str(payload.get("request_digest") or ""),
            request_bytes=int(payload.get("request_bytes") or 0),
            generation_id=str(payload.get("generation_id") or ""),
            requested_fast_mode=requested_fast_mode,  # type: ignore[arg-type]
            requested_service_tier=requested_service_tier,
            requested_model=str(payload.get("requested_model") or ""),
            requested_effort=str(payload.get("requested_effort") or ""),
            actual_service_tier=str(payload.get("actual_service_tier") or ""),
            service_tier_truth=ServiceTierTruth(str(payload.get("service_tier_truth") or "unverified")),
            next_generation_id=str(payload.get("next_generation_id") or ""),
            host_thread_id=str(payload.get("host_thread_id") or ""),
            host_turn_id=str(payload.get("host_turn_id") or ""),
            host_completed=payload.get("host_completed", False),  # type: ignore[arg-type]
            material_receipt_id=str(payload.get("material_receipt_id") or ""),
            failure_kind=None if failure in (None, "") else ExecutionFailureKind(str(failure)),
            retry_count=int(payload.get("retry_count") or 0),
            snapshot_digest=str(payload.get("snapshot_digest") or ""),
            updated_at_ms=int(payload.get("updated_at_ms") or 0),
        )


class ExecutionDispatchLedger:
    """Exactly-once local reservation ledger; host transport remains external."""

    def __init__(self, *, generations: tuple[ExecutionConfigGeneration, ...] = (), reservations: tuple[ExecutionReservation, ...] = (), event_digests: tuple[str, ...] = ()) -> None:
        self._generations: dict[str, ExecutionConfigGeneration] = {}
        self._reservations: dict[str, ExecutionReservation] = {}
        self._task_reservations: dict[str, str] = {}
        self._event_digests = {_digest(value, "execution event") for value in event_digests}
        for generation in sorted(generations, key=lambda item: (item.changed_at_ms, item.generation_id)):
            self.observe_generation(generation)
        for reservation in reservations:
            self._add_reservation(reservation)

    @property
    def generations(self) -> tuple[ExecutionConfigGeneration, ...]:
        return tuple(sorted(self._generations.values(), key=lambda item: (item.changed_at_ms, item.generation_id)))

    @property
    def reservations(self) -> tuple[ExecutionReservation, ...]:
        return tuple(sorted(self._reservations.values(), key=lambda item: item.reservation_id))

    @property
    def event_digests(self) -> tuple[str, ...]:
        return tuple(sorted(self._event_digests))

    @property
    def latest_generation(self) -> ExecutionConfigGeneration | None:
        return max(self._generations.values(), key=lambda item: (item.changed_at_ms, item.generation_id), default=None)

    def observe_generation(self, generation: ExecutionConfigGeneration) -> None:
        if not isinstance(generation, ExecutionConfigGeneration):
            raise InvariantError("execution config observation must be typed")
        existing = self._generations.get(generation.generation_id)
        if existing is not None and existing != generation:
            raise InvariantError("execution config generation identity conflicts with retained state")
        latest = self.latest_generation
        if latest is not None and existing is None and generation.changed_at_ms <= latest.changed_at_ms:
            raise InvariantError("stale or ambiguously ordered execution config generation cannot become current")
        self._generations[generation.generation_id] = generation
        if latest is None or (generation.changed_at_ms, generation.generation_id) > (latest.changed_at_ms, latest.generation_id):
            for reservation in self._reservations.values():
                if reservation.state is ExecutionDispatchState.ACTIVE:
                    reservation.next_generation_id = generation.generation_id

    def _add_reservation(self, reservation: ExecutionReservation) -> None:
        if not isinstance(reservation, ExecutionReservation):
            raise InvariantError("execution reservation must be typed")
        if reservation.reservation_id in self._reservations or reservation.task_id in self._task_reservations:
            raise InvariantError("execution reservation or task already exists")
        self._reservations[reservation.reservation_id] = reservation
        self._task_reservations[reservation.task_id] = reservation.reservation_id

    def reserve(self, reservation_id: str, task_id: str, owner_id: str, artifact: ArtifactIdentity, *, observed_at_ms: int) -> ExecutionReservation:
        if reservation_id in self._reservations or task_id in self._task_reservations:
            raise InvariantError("duplicate dispatch reservation is prohibited")
        reservation = ExecutionReservation(reservation_id, task_id, owner_id, artifact, updated_at_ms=observed_at_ms)
        self._add_reservation(reservation)
        return reservation

    def reservation(self, reservation_id: str) -> ExecutionReservation:
        try:
            return self._reservations[reservation_id]
        except KeyError as error:
            raise InvariantError("execution reservation is not observed") from error

    def defer(self, reservation_id: str, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if reservation.state is not ExecutionDispatchState.QUEUED:
            raise InvariantError("only queued work can be deferred without dispatch")
        reservation.state = ExecutionDispatchState.DEFERRED
        reservation.updated_at_ms = observed_at_ms
        return reservation

    def dispatch(self, reservation_id: str, request_digest: str, request_bytes: int, *, observed_at_ms: int, direct_user_keep_out: bool = False, retry: bool = False) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if direct_user_keep_out:
            raise InvariantError("direct-user CTRL keep-out blocks delegated dispatch")
        generation = self.latest_generation
        if generation is None:
            raise InvariantError("latest host execution config is unavailable; dispatch remains UNVERIFIED")
        if reservation.state is ExecutionDispatchState.ACTIVE:
            raise InvariantError("duplicate dispatch is prohibited while the reservation is active")
        if reservation.state is ExecutionDispatchState.COMPLETE:
            raise InvariantError("completed execution cannot dispatch again")
        if retry and (reservation.failure_kind is not ExecutionFailureKind.BAD_REQUEST or reservation.retry_count != 0):
            raise InvariantError("only one resolved Bad Request may retry")
        if not retry and reservation.state is ExecutionDispatchState.UNVERIFIED and reservation.failure_kind is not None:
            raise InvariantError("failed execution requires an explicit permitted recovery path")
        digest = _digest(request_digest, "execution request")
        if not isinstance(request_bytes, int) or isinstance(request_bytes, bool) or request_bytes <= 0:
            raise InvariantError("execution request requires a positive bounded byte count")
        reservation.request_digest = digest
        reservation.request_bytes = request_bytes
        reservation.generation_id = generation.generation_id
        reservation.requested_service_tier = generation.requested_service_tier
        reservation.requested_fast_mode = reservation.requested_service_tier in {"fast", "priority"}
        reservation.requested_model = generation.model
        reservation.requested_effort = generation.effort
        reservation.actual_service_tier = ""
        reservation.service_tier_truth = ServiceTierTruth.UNVERIFIED
        reservation.next_generation_id = ""
        reservation.host_completed = False
        reservation.failure_kind = None
        reservation.state = ExecutionDispatchState.ACTIVE
        reservation.updated_at_ms = observed_at_ms
        if retry:
            reservation.retry_count += 1
        return reservation

    def checkpoint(self, reservation_id: str, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if reservation.state is not ExecutionDispatchState.ACTIVE or not reservation.next_generation_id:
            raise InvariantError("only running work with a fresher host generation can checkpoint")
        reservation.state = ExecutionDispatchState.CHECKPOINTED
        reservation.generation_id = ""
        reservation.requested_fast_mode = False
        reservation.requested_service_tier = ""
        reservation.requested_model = ""
        reservation.requested_effort = ""
        reservation.actual_service_tier = ""
        reservation.service_tier_truth = ServiceTierTruth.UNVERIFIED
        reservation.updated_at_ms = observed_at_ms
        return reservation

    def observe_event(self, reservation_id: str, event: AdapterEvent, *, observed_at_ms: int, served_tier: HostServiceTierReceipt | None = None) -> bool:
        reservation = self.reservation(reservation_id)
        if not isinstance(event, AdapterEvent) or event._authority is not _HOST_EVENT_AUTHORITY or not event.evidence_digest:
            raise InvariantError("host observation requires a typed readable event digest")
        if event.evidence_digest in self._event_digests:
            return False
        if reservation.state is not ExecutionDispatchState.ACTIVE:
            raise InvariantError("host events require an active retained reservation")
        self._event_digests.add(event.evidence_digest)
        reservation.host_thread_id = event.thread_id or reservation.host_thread_id
        reservation.host_turn_id = event.turn_id or reservation.host_turn_id
        status = event.status.casefold()
        if status in {"failed", "error", "cancelled", "canceled"}:
            reservation.failure_kind = ExecutionFailureKind.HOST_FAILED
            reservation.state = ExecutionDispatchState.UNVERIFIED
        elif status in {"completed", "complete"}:
            reservation.host_completed = True
        if served_tier is not None and served_tier._authority is _HOST_RESPONSE_AUTHORITY:
            expected = reservation.requested_service_tier
            actual_ok = served_tier.actual_service_tier == expected or expected == "fast" and served_tier.actual_service_tier == "priority"
            if served_tier.request_digest == reservation.request_digest and actual_ok:
                reservation.actual_service_tier = served_tier.actual_service_tier
                reservation.service_tier_truth = ServiceTierTruth.CONFIRMED
        reservation.updated_at_ms = observed_at_ms
        return True

    def fail_transport(self, reservation_id: str, kind: ExecutionFailureKind, *, observed_at_ms: int, http_status: int = 0, detail: str = "") -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if reservation.state is not ExecutionDispatchState.ACTIVE or not isinstance(kind, ExecutionFailureKind):
            raise InvariantError("transport failure requires an active reservation and typed outcome")
        if kind is ExecutionFailureKind.BAD_REQUEST and (http_status != 400 or detail != "Bad Request"):
            raise InvariantError("Bad Request classification requires exact HTTP 400 detail")
        reservation.failure_kind = kind
        reservation.state = ExecutionDispatchState.UNVERIFIED
        reservation.actual_service_tier = ""
        reservation.service_tier_truth = ServiceTierTruth.UNVERIFIED
        reservation.updated_at_ms = observed_at_ms
        return reservation

    def retry_smaller(self, reservation_id: str, snapshot: ContinuationSnapshot, request_digest: str, request_bytes: int, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if not isinstance(snapshot, ContinuationSnapshot) or snapshot.observed_at_ms < reservation.updated_at_ms or snapshot.source_bytes != reservation.request_bytes or request_bytes >= reservation.request_bytes or request_bytes > snapshot.compacted_bytes:
            raise InvariantError("Bad Request retry requires a fresh provably smaller bounded snapshot")
        if request_digest == reservation.request_digest:
            raise InvariantError("Bad Request retry must be freshly generated")
        reservation.snapshot_digest = snapshot.digest
        return self.dispatch(
            reservation_id,
            request_digest,
            request_bytes,
            observed_at_ms=observed_at_ms,
            retry=True,
        )

    def record_material_receipt(self, reservation_id: str, receipt: DelegatedReturnReceipt, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if not isinstance(receipt, DelegatedReturnReceipt):
            raise InvariantError("material progress requires an active reservation and typed readable receipt")
        if reservation.state is ExecutionDispatchState.MATERIAL_RECEIPT and reservation.material_receipt_id == receipt.receipt_id:
            return reservation
        if reservation.state is not ExecutionDispatchState.ACTIVE:
            raise InvariantError("material progress requires an active reservation and typed readable receipt")
        if receipt.verdict is not DelegatedReceiptVerdict.ACCEPT or receipt.task_id != reservation.task_id or receipt.owner_id != reservation.owner_id or receipt.artifact != reservation.artifact:
            raise InvariantError("material receipt must be readable ACCEPT bound to the exact task, owner, and artifact")
        if reservation.material_receipt_id and reservation.material_receipt_id != receipt.receipt_id:
            raise InvariantError("conflicting material receipt cannot replace retained evidence")
        reservation.material_receipt_id = receipt.receipt_id
        reservation.state = ExecutionDispatchState.MATERIAL_RECEIPT
        reservation.updated_at_ms = observed_at_ms
        return reservation

    def record_independent_review(self, reservation_id: str, runtime: Swarm, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        task = runtime.tasks.get(reservation.task_id) if isinstance(runtime, Swarm) else None
        if reservation.state is not ExecutionDispatchState.MATERIAL_RECEIPT or task is None or task.owner != reservation.owner_id or task.acceptance_contract is None or task.acceptance_contract.artifact != reservation.artifact or runtime.proof_state(reservation.task_id) is not ProofState.ACCEPTED:
            raise InvariantError("independent review requires current runtime-issued exact-artifact acceptance")
        reservation.state = ExecutionDispatchState.INDEPENDENT_REVIEW
        reservation.updated_at_ms = observed_at_ms
        return reservation

    def record_complete(self, reservation_id: str, runtime: Swarm, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        task = runtime.tasks.get(reservation.task_id) if isinstance(runtime, Swarm) else None
        if reservation.state is not ExecutionDispatchState.INDEPENDENT_REVIEW or not reservation.host_completed or task is None or task.state is not TaskState.COMPLETE or runtime.proof_state(reservation.task_id) is not ProofState.ACCEPTED:
            raise InvariantError("completion requires consumed host completion plus current independent runtime acceptance")
        reservation.state = ExecutionDispatchState.COMPLETE
        reservation.updated_at_ms = observed_at_ms
        return reservation


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

    def __init__(self, *, enabled: bool = True, transport: CodexAppServerTransport | None = None) -> None:
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
                AdapterCapability("swarm.topology_dispatch", AdapterCapabilityState.INSTRUCTION_ONLY, "TopologyDispatchPacket", "The current Codex host thread creation API cannot consume or enforce the typed ready-wave packet."),
                AdapterCapability("model.instructions", AdapterCapabilityState.INSTRUCTION_ONLY, "model input", "Instructions guide behavior but do not enforce ownership, proof, or policy."),
                AdapterCapability("review.acceptance", AdapterCapabilityState.UNSUPPORTED, "SWARM review contract", "Adapter output cannot independently review or accept its own artifact."),
                AdapterCapability("host.task_mutation", AdapterCapabilityState.UNSUPPORTED, "SWARM user-custody contract", "No title, pin, folder, order, archive, or other host task mutation is exposed."),
            ),
        )
        super().__init__(matrix, entrypoint=(), protocol="json-rpc-2.0-jsonl", enabled=enabled)
        self.transport = transport

    def plan_hq(self, envelope: HQCommandEnvelope) -> AdapterExecutionPlan:
        if not isinstance(envelope, HQCommandEnvelope):
            raise InvariantError("Codex HQ plan requires a typed envelope")
        capabilities, _ = HQ_ACTION_CAPABILITIES[envelope.action]
        if not self.enabled or self.transport is None:
            return AdapterExecutionPlan(AdapterPlanStatus.DISABLED, self.matrix.adapter_id, envelope.digest, self.matrix.digest(), blocker="Codex App Server adapter is disabled or unavailable")
        unsupported = tuple(capability for capability in capabilities if capability != "local" and self.matrix.state_for(capability) is not AdapterCapabilityState.NATIVE)
        if unsupported:
            return AdapterExecutionPlan(AdapterPlanStatus.BLOCKED, self.matrix.adapter_id, envelope.digest, self.matrix.digest(), blocker=f"required capability is unavailable: {unsupported[0]}")
        return AdapterExecutionPlan(AdapterPlanStatus.READY, self.matrix.adapter_id, envelope.digest, self.matrix.digest(), self.entrypoint, self.protocol)

    def dispatch(self, envelope: HQCommandEnvelope, material: HQDispatchMaterial, capability: str, *, thread_id: str = "") -> Mapping[str, object]:
        if not self.plan_hq(envelope).ready or self.transport is None:
            raise InvariantError("Codex App Server transport is unavailable")
        if not isinstance(material, HQDispatchMaterial) or material.digest != envelope.payload_digest:
            raise InvariantError("Codex App Server dispatch material does not match the command")
        capabilities, _ = HQ_ACTION_CAPABILITIES[envelope.action]
        if capability not in capabilities or capability == "local":
            raise InvariantError("Codex App Server capability does not match the command action")
        if capability == "thread.start":
            wire = self._thread_wire_request(cwd=material.cwd)
        elif capability == "thread.resume":
            wire = self._thread_wire_request(cwd=material.cwd, thread_id=thread_id)
        elif capability in {"turn.start", "turn.steer"}:
            wire = self._turn_wire_request(
                thread_id=thread_id,
                instruction=material.instruction,
                instruction_digest=envelope.payload_digest,
                cwd=material.cwd,
                method=capability.replace(".", "/"),
                expected_turn_id=envelope.target_turn_id,
            )
        else:
            raise InvariantError("Codex App Server capability is not dispatchable")
        return self.transport.request(str(wire["method"]), wire["params"])

    def reconcile(self, envelope: HQCommandEnvelope, *, thread_id: str = "") -> Mapping[str, object] | None:
        if not self.plan_hq(envelope).ready or self.transport is None:
            raise InvariantError("Codex App Server reconciliation is unavailable")
        response = self.transport.reconcile(envelope.command_id, envelope.action.value, thread_id)
        if response is not None and not isinstance(response, Mapping):
            raise InvariantError("Codex App Server reconciliation must return an object or null")
        return response

    @staticmethod
    def initialize_request(client_name: str, *, request_id: int = 0) -> dict[str, object]:
        name = _text(client_name, "Codex adapter client name")
        if not isinstance(request_id, int) or request_id < 0:
            raise InvariantError("Codex adapter request id must be non-negative")
        return {"method": "initialize", "id": request_id, "params": {"clientInfo": {"name": name, "title": name, "version": "1"}}}

    @staticmethod
    def initialized_notification() -> dict[str, object]:
        return {"method": "initialized", "params": {}}

    def plan_topology_dispatch(self, packet: TopologyDispatchPacket) -> AdapterExecutionPlan:
        """Expose the exact host boundary without emitting a create-thread call."""
        if not isinstance(packet, TopologyDispatchPacket):
            raise InvariantError("Codex topology dispatch requires a typed ready-wave packet")
        return AdapterExecutionPlan(
            AdapterPlanStatus.BLOCKED,
            self.matrix.adapter_id,
            packet.packet_digest,
            self.matrix.digest(),
            blocker="required capability is instruction-only: swarm.topology_dispatch",
            claim_limit=packet.claim_limit,
        )

    def thread_request(self, plan: AdapterExecutionPlan, request: ExecutionAdapterRequest, *, request_id: int = 1, thread_id: str = "") -> dict[str, object]:
        self._require_ready(plan, request)
        return self._thread_wire_request(
            cwd=request.cwd,
            request_id=request_id,
            thread_id=thread_id,
            model=request.model,
            approval_policy=request.approval_policy,
            sandbox=request.sandbox,
        )

    @staticmethod
    def _thread_wire_request(*, cwd: str, request_id: int = 1, thread_id: str = "", model: str = "", approval_policy: str = "", sandbox: str = "") -> dict[str, object]:
        if not isinstance(request_id, int) or request_id < 0:
            raise InvariantError("Codex adapter request id must be non-negative")
        params: dict[str, object] = {}
        if thread_id:
            params["threadId"] = _text(thread_id, "Codex thread id")
            method = "thread/resume"
        else:
            method = "thread/start"
            params["cwd"] = _text(cwd, "Codex cwd")
        if model:
            params["model"] = model
        if approval_policy:
            params["approvalPolicy"] = approval_policy
        if sandbox:
            params["sandbox"] = sandbox
        return {"method": method, "id": request_id, "params": params}

    def turn_request(self, plan: AdapterExecutionPlan, request: ExecutionAdapterRequest, *, thread_id: str, instruction: str, request_id: int = 2) -> dict[str, object]:
        self._require_ready(plan, request)
        return self._turn_wire_request(
            thread_id=thread_id,
            instruction=instruction,
            instruction_digest=request.instruction_digest,
            cwd=request.cwd,
            request_id=request_id,
            model=request.model,
            approval_policy=request.approval_policy,
        )

    @staticmethod
    def _turn_wire_request(*, thread_id: str, instruction: str, instruction_digest: str, cwd: str, request_id: int = 2, model: str = "", approval_policy: str = "", method: str = "turn/start", expected_turn_id: str = "") -> dict[str, object]:
        target = _text(thread_id, "Codex thread id")
        if not isinstance(instruction, str) or sha256(instruction.encode("utf-8")).hexdigest() != instruction_digest:
            raise InvariantError("Codex turn instruction does not match the authorized request digest")
        if not isinstance(request_id, int) or request_id < 0:
            raise InvariantError("Codex adapter request id must be non-negative")
        if method not in {"turn/start", "turn/steer"}:
            raise InvariantError("Codex turn method is unsupported")
        params: dict[str, object] = {"threadId": target, "input": [{"type": "text", "text": instruction, "text_elements": []}]}
        if method == "turn/start":
            params["cwd"] = _text(cwd, "Codex cwd")
            if expected_turn_id:
                raise InvariantError("Codex turn start cannot name an active turn")
        else:
            params["expectedTurnId"] = _text(expected_turn_id, "Codex expected turn id")
        if model:
            params["model"] = model
        if approval_policy:
            params["approvalPolicy"] = approval_policy
        return {"method": method, "id": request_id, "params": params}

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
        event = AdapterEvent(
            method=method,
            thread_id=str(body.get("threadId") or thread.get("id") or ""),
            turn_id=str(body.get("turnId") or turn.get("id") or ""),
            item_id=str(body.get("itemId") or item.get("id") or ""),
            status=str(body.get("status") or turn.get("status") or item.get("status") or ""),
            evidence_digest=digest,
        )
        object.__setattr__(event, "_authority", _HOST_EVENT_AUTHORITY)
        return event

    @staticmethod
    def translate_service_tier_receipt(message: Mapping[str, object], *, request_digest: str, observed_at_ms: int) -> HostServiceTierReceipt:
        if not isinstance(message, Mapping):
            raise InvariantError("Codex served-tier response must be a JSON object")
        result = message.get("result")
        body = result if isinstance(result, Mapping) else {}
        tier = str(body.get("service_tier") or body.get("serviceTier") or "")
        receipt = HostServiceTierReceipt(request_digest, tier, _canonical_digest(message), observed_at_ms)
        object.__setattr__(receipt, "_authority", _HOST_RESPONSE_AUTHORITY)
        return receipt

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

    def plan_chatgpt(
        self,
        surface: str,
        capabilities: tuple[HostChatGPTCapability, ...],
        *,
        enabled: bool,
        workspace_id: str = "",
        explicit_model: str = "",
        explicit_reasoning: str = "",
    ) -> ChatGPTRoutingPlan:
        """Select an exact host-owned ChatGPT surface or fall back to local Codex."""
        if surface not in {"chat", "image", "work"}:
            raise InvariantError("ChatGPT route surface must be chat, image, or work")
        if any(not isinstance(item, HostChatGPTCapability) for item in capabilities):
            raise InvariantError("ChatGPT routing requires typed host capabilities")
        if len({(item.surface, item.capability_id) for item in capabilities}) != len(capabilities):
            raise InvariantError("ChatGPT host capabilities must be distinct")
        if explicit_model:
            _text(explicit_model, "explicit ChatGPT model")
        if explicit_reasoning:
            _text(explicit_reasoning, "explicit ChatGPT reasoning")
        if workspace_id:
            _text(workspace_id, "requested ChatGPT workspace")
        if not enabled:
            return ChatGPTRoutingPlan(
                ChatGPTRouteStatus.FALLBACK, surface, CodexAppServerAdapter.ADAPTER_ID,
                reason="ChatGPT routing is disabled; use the existing local Codex route.",
            )
        matches = tuple(
            item for item in capabilities
            if item.surface == surface and (surface != "work" or item.workspace_id == workspace_id)
        )
        if len(matches) != 1:
            state = ChatGPTRouteStatus.FALLBACK if not matches else ChatGPTRouteStatus.UNAVAILABLE
            reason = (
                "No exact callable host ChatGPT capability is available; use the existing local Codex route."
                if not matches else "Host ChatGPT capability identity is ambiguous; do not dispatch."
            )
            return ChatGPTRoutingPlan(state, surface, CodexAppServerAdapter.ADAPTER_ID, reason=reason)
        capability = matches[0]
        if explicit_model and not capability.supports_model_selection:
            return ChatGPTRoutingPlan(
                ChatGPTRouteStatus.FALLBACK, surface, CodexAppServerAdapter.ADAPTER_ID,
                reason="The host capability cannot preserve the explicit model; use the existing local Codex route.",
            )
        if explicit_reasoning and not capability.supports_reasoning_selection:
            return ChatGPTRoutingPlan(
                ChatGPTRouteStatus.FALLBACK, surface, CodexAppServerAdapter.ADAPTER_ID,
                reason="The host capability cannot preserve explicit reasoning; use the existing local Codex route.",
            )
        return ChatGPTRoutingPlan(
            status=ChatGPTRouteStatus.READY,
            surface=surface,
            adapter_id=capability.capability_id,
            capability_id=capability.capability_id,
            capability_receipt_id=capability.receipt_id,
            workspace_id=capability.workspace_id,
            model=explicit_model,
            reasoning=explicit_reasoning,
        )
