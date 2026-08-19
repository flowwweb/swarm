"""Deterministic policy for optional visible ChatGPT advisory consultations.

The transport is intentionally host-owned. SWARM decides whether a bounded
consult is eligible; a visible browser bridge must still provide the session,
configuration, user confirmation, and execution receipt.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from hashlib import sha256
import math
from pathlib import Path
import re
from typing import Callable, Protocol

from .chat_relay_usage import ChatRelayUsageLedger


class ChatRelayPurpose(StrEnum):
    PLAN = "plan"
    RESEARCH = "research"
    REVIEW = "review"
    TESTING = "testing"
    IMAGEGEN = "imagegen"
    IMPLEMENTATION = "implementation"
    COMMAND = "command"


class ChatRelaySurface(StrEnum):
    CHAT = "chat"


class ChatRelayOffloadLevel(StrEnum):
    """How broadly eligible advisory work may use the visible Chat surface."""

    LIGHT = "light"
    BALANCED = "balanced"
    HIGH = "high"
    MAX = "max"


class ChatRelayRoutingMode(StrEnum):
    """Where eligible advisory work is allowed to run."""

    AUTO = "auto"
    ALWAYS_LOCAL = "always_local"
    ALWAYS_CLOUD = "always_cloud"


class ChatRelayRoute(StrEnum):
    LOCAL_CODEX = "local_codex"
    VISIBLE_CHAT = "visible_chat"


class ChatRelayBlocker(StrEnum):
    DISABLED = "disabled"
    MUTATION_INTENT = "mutation_intent"
    CONSEQUENCE_TOO_HIGH = "consequence_too_high"
    VISIBLE_SESSION_REQUIRED = "visible_session_required"
    BROWSER_BRIDGE_REQUIRED = "browser_bridge_required"
    HOST_CONFIG_REQUIRED = "host_config_required"
    USER_CONFIRMATION_REQUIRED = "user_confirmation_required"
    OFFLOAD_LEVEL_SELECTION = "offload_level_selection"
    ROUTING_MODE_LOCAL = "routing_mode_local"
    LOCAL_BOUNDARY_REQUIRED = "local_boundary_required"
    PROVIDER_ARTIFACT_REQUIRED = "provider_artifact_required"
    PROVIDER_ADAPTER_REQUIRED = "provider_adapter_required"
    PROVIDER_ARTIFACT_UNAVAILABLE = "provider_artifact_unavailable"
    PROVIDER_RESPONSE_UNAVAILABLE = "provider_response_unavailable"


_SAFE_PROVIDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CONSULT_TIERS = frozenset({"T0", "T1"})
_CHAT_RELAY_MODELS = frozenset({"gpt-5.6-luna", "gpt-5.6-sol", "pro"})
_CHAT_RELAY_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh", "max", "ultra", "pro"})
_OBSERVED_MODEL_ALIASES = {
    "gpt-5.6-luna": "gpt-5.6-luna",
    "gpt5.6luna": "gpt-5.6-luna",
    "gpt-5.6-sol": "gpt-5.6-sol",
    "gpt5.6sol": "gpt-5.6-sol",
    "pro": "pro",
}
_OBSERVED_EFFORT_ALIASES = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "extrahigh": "xhigh",
    "max": "xhigh",
    "ultra": "xhigh",
    "pro": "pro",
}
_MAX_CONTEXT_FILE_BYTES = 32 * 1024
_MAX_CONTEXT_PACKET_BYTES = 96 * 1024
_SENSITIVE_NAMES = frozenset({
    ".env", ".env.local", ".env.production", ".env.development",
    "credentials", "credentials.json", "secrets", "secrets.json",
    "id_rsa", "id_ed25519", "private.key", "private.pem",
})
_SENSITIVE_PARTS = frozenset({".git", ".ssh", ".aws", ".azure", ".config", ".codex"})


def _require_safe_provider(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_PROVIDER.fullmatch(value):
        raise ValueError("chat relay provider must be a safe ASCII identifier")
    return value


def _require_receipt(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("chat relay capability requires a non-empty host receipt")
    return value


def _require_observation(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(character in value for character in "\r\n"):
        raise ValueError(f"chat relay capability requires observed {label}")
    return value.strip()


def _require_selection(value: str, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"chat relay {label} must be one of: {choices}")
    return value


def _normalize_observed(value: str, aliases: dict[str, str]) -> str:
    """Normalize known visible labels without accepting unknown selections."""

    compact = re.sub(r"[\s_-]+", "", value.strip().casefold())
    return aliases.get(compact, "")


def _observed_selection_matches(*, requested_model: str, requested_effort: str, capability: "ChatRelayCapability") -> bool:
    observed_model = _normalize_observed(capability.observed_model, _OBSERVED_MODEL_ALIASES)
    observed_effort = _normalize_observed(capability.observed_effort, _OBSERVED_EFFORT_ALIASES)
    effort_matches = observed_effort == requested_effort
    if requested_effort in {"xhigh", "max", "ultra"}:
        effort_matches = observed_effort == "xhigh"
    return observed_model == requested_model and effort_matches


def _safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("chat relay context paths must be non-empty strings")
    candidate = value.replace("\\", "/").strip()
    path = Path(candidate)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("chat relay context paths must stay repo-relative")
    parts = tuple(part.casefold() for part in path.parts)
    if any(part in _SENSITIVE_PARTS for part in parts) or parts[-1] in _SENSITIVE_NAMES:
        raise ValueError("chat relay context refuses sensitive paths")
    return "/".join(path.parts)


@dataclass(frozen=True)
class ChatRelayPolicy:
    """The safe, opt-in policy for visible ChatGPT consultations."""

    enabled: bool = False
    provider: str = "codex-chatgpt-control"
    surface: ChatRelaySurface = ChatRelaySurface.CHAT
    mode: str = "consult"
    routing_mode: ChatRelayRoutingMode = ChatRelayRoutingMode.AUTO
    offload_level: ChatRelayOffloadLevel = ChatRelayOffloadLevel.BALANCED
    default_model: str = "gpt-5.6-luna"
    default_effort: str = "xhigh"
    challenging_model: str = "pro"
    challenging_effort: str = "pro"

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("chat relay enabled must be true or false")
        _require_safe_provider(self.provider)
        if self.surface is not ChatRelaySurface.CHAT:
            raise ValueError("chat relay only supports the visible Chat surface")
        if self.mode != "consult":
            raise ValueError("chat relay only supports advisory consult mode")
        if not isinstance(self.routing_mode, ChatRelayRoutingMode):
            raise ValueError("chat relay routing mode must be auto, always_local, or always_cloud")
        if not isinstance(self.offload_level, ChatRelayOffloadLevel):
            raise ValueError("chat relay offload level must be light, balanced, high, or max")
        _require_selection(self.default_model, _CHAT_RELAY_MODELS, "default_model")
        _require_selection(self.default_effort, _CHAT_RELAY_EFFORTS, "default_effort")
        _require_selection(self.challenging_model, _CHAT_RELAY_MODELS, "challenging_model")
        _require_selection(self.challenging_effort, _CHAT_RELAY_EFFORTS, "challenging_effort")

    @classmethod
    def from_config(cls, values: dict[str, object]) -> "ChatRelayPolicy":
        if not isinstance(values, dict):
            raise ValueError("chat relay configuration must be a table")
        return cls(
            enabled=values.get("enabled", False),
            provider=values.get("provider", "codex-chatgpt-control"),
            surface=ChatRelaySurface(values.get("surface", "chat")),
            mode=values.get("mode", "consult"),
            routing_mode=ChatRelayRoutingMode(values.get("routing_mode", "auto")),
            offload_level=ChatRelayOffloadLevel(values.get("offload_level", "balanced")),
            default_model=values.get("default_model", "gpt-5.6-luna"),
            default_effort=values.get("default_effort", "xhigh"),
            challenging_model=values.get("challenging_model", "pro"),
            challenging_effort=values.get("challenging_effort", "pro"),
        )


@dataclass(frozen=True)
class ChatRelayCapability:
    """Host-observed capability needed before a visible Chat consult."""

    visible_session: bool
    browser_bridge: bool
    user_confirmed: bool
    receipt: str
    observed_model: str = ""
    observed_effort: str = ""

    def __post_init__(self) -> None:
        if not all(isinstance(value, bool) for value in (self.visible_session, self.browser_bridge, self.user_confirmed)):
            raise ValueError("chat relay capability flags must be boolean")
        _require_receipt(self.receipt)
        if self.observed_model:
            _require_observation(self.observed_model, "model")
        if self.observed_effort:
            _require_observation(self.observed_effort, "reasoning effort")


class ChatRelayAdapter(Protocol):
    """Host-owned transport for an already-visible ChatGPT session."""

    def capability(self) -> ChatRelayCapability:
        """Inspect the visible session immediately before a possible send."""

    def send_consult(self, prompt: str, *, model: str, effort: str) -> "ChatRelayResponse":
        """Send one user-confirmed advisory prompt through the visible host."""


class ChatRelayTransportError(RuntimeError):
    """A host transport failure that can safely fall back to local SWARM."""

    def __init__(self, message: str, *, blocker: ChatRelayBlocker) -> None:
        super().__init__(message)
        self.blocker = blocker


@dataclass(frozen=True)
class ChatRelayTransportReceipt:
    """Provider/bridge fields preserved without inventing missing receipts."""

    transport: str = "visible_chat"
    client_thread_id: str = ""
    thread_id: str = ""
    request_id: str = ""
    response_id: str = ""
    asset_ids: tuple[str, ...] = ()
    model: str = ""
    latency_ms: float | None = None
    latency_source: str = "unavailable"
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    usage_status: str = "unavailable"
    usage_reason: str = "provider did not expose a usage object"

    def __post_init__(self) -> None:
        for label, value in (
            ("transport", self.transport),
            ("client thread id", self.client_thread_id),
            ("thread id", self.thread_id),
            ("request id", self.request_id),
            ("response id", self.response_id),
            ("model", self.model),
            ("latency source", self.latency_source),
            ("usage reason", self.usage_reason),
        ):
            if not isinstance(value, str) or any(character in value for character in "\r\n"):
                raise ValueError(f"chat relay transport {label} must be a single-line string")
        if not isinstance(self.asset_ids, tuple) or any(
            not isinstance(value, str) or not value or any(character in value for character in "\r\n")
            for value in self.asset_ids
        ):
            raise ValueError("chat relay transport asset ids must be a tuple of non-empty strings")
        if self.latency_ms is not None and (
            isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, (int, float))
            or not math.isfinite(self.latency_ms)
            or self.latency_ms < 0
        ):
            raise ValueError("chat relay transport latency must be a non-negative number")
        token_values = (self.input_tokens, self.output_tokens, self.total_tokens)
        if any(value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0) for value in token_values):
            raise ValueError("chat relay transport tokens must be non-negative integers or unavailable")
        expected_status = "reported" if all(value is not None for value in token_values) else "partial" if any(value is not None for value in token_values) else "unavailable"
        if self.usage_status != expected_status:
            raise ValueError(f"chat relay transport usage status must be {expected_status}")
        if self.usage_status != "reported" and not self.usage_reason.strip():
            raise ValueError("chat relay transport must explain unavailable or partial usage")


@dataclass(frozen=True)
class ChatRelayResponse:
    """A transient advisory response returned by the visible host."""

    text: str
    host_receipt: str
    observed_model: str
    observed_effort: str
    advisory_only: bool = True
    acceptance_authority: bool = False
    transport: ChatRelayTransportReceipt = field(default_factory=ChatRelayTransportReceipt)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("chat relay responses require text")
        _require_receipt(self.host_receipt)
        _require_observation(self.observed_model, "model")
        _require_observation(self.observed_effort, "reasoning effort")
        if not isinstance(self.transport, ChatRelayTransportReceipt):
            raise ValueError("chat relay responses require a typed transport receipt")
        if not self.advisory_only or self.acceptance_authority:
            raise ValueError("chat relay responses cannot own acceptance")


@dataclass(frozen=True)
class ChatRelayConsultation:
    """The routing receipt and optional transient response from one consult."""

    decision: ChatRelayDecision
    response: ChatRelayResponse | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ChatRelayDecision):
            raise ValueError("chat relay consultations require a typed decision")
        if self.decision.route is ChatRelayRoute.VISIBLE_CHAT and self.response is None:
            raise ValueError("visible Chat consultations require a host response")
        if self.decision.route is ChatRelayRoute.LOCAL_CODEX and self.response is not None:
            raise ValueError("local Chat relay fallbacks cannot carry a host response")


@dataclass(frozen=True)
class ChatRelayContextFile:
    """One explicitly selected, transient text file for a Chat consultation."""

    path: str
    content: str
    digest: str

    def __post_init__(self) -> None:
        if _safe_relative_path(self.path) != self.path:
            raise ValueError("chat relay context file path must be normalized")
        if not isinstance(self.content, str) or not self.content:
            raise ValueError("chat relay context files require text content")
        if len(self.content.encode("utf-8")) > _MAX_CONTEXT_FILE_BYTES:
            raise ValueError("chat relay context file exceeds the per-file limit")
        expected = sha256(self.content.encode("utf-8")).hexdigest()
        if self.digest != expected:
            raise ValueError("chat relay context file digest does not match content")


def _render_context(objective: str, files: tuple[ChatRelayContextFile, ...]) -> str:
    sections = ["SWARM_CHAT_CONTEXT_V1", f"OBJECTIVE: {objective.strip()}"]
    for item in files:
        sections.extend((f"FILE: {item.path} SHA256: {item.digest}", item.content, "END_FILE"))
    sections.append("END_SWARM_CHAT_CONTEXT")
    return "\n".join(sections)


@dataclass(frozen=True)
class ChatRelayContextPacket:
    """Bounded, repo-relative context prepared before any host send action."""

    objective: str
    files: tuple[ChatRelayContextFile, ...]
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.objective, str) or not self.objective.strip():
            raise ValueError("chat relay context requires a non-empty objective")
        if not isinstance(self.files, tuple) or not self.files:
            raise ValueError("chat relay context requires at least one selected file")
        if any(not isinstance(item, ChatRelayContextFile) for item in self.files):
            raise ValueError("chat relay context files must be typed")
        if tuple(item.path for item in self.files) != tuple(sorted(item.path for item in self.files)):
            raise ValueError("chat relay context files must be sorted")
        if len({item.path for item in self.files}) != len(self.files):
            raise ValueError("chat relay context files cannot repeat")
        rendered = self.render()
        if len(rendered.encode("utf-8")) > _MAX_CONTEXT_PACKET_BYTES:
            raise ValueError("chat relay context exceeds the total payload limit")
        if self.digest != sha256(rendered.encode("utf-8")).hexdigest():
            raise ValueError("chat relay context digest does not match rendered packet")

    def render(self) -> str:
        return _render_context(self.objective, self.files)


def build_chat_relay_context(
    *,
    repo_root: str | Path,
    objective: str,
    relative_paths: tuple[str, ...],
) -> ChatRelayContextPacket:
    """Read only the caller's explicit UTF-8 file allowlist, without discovery."""

    if not isinstance(relative_paths, tuple) or not relative_paths:
        raise ValueError("chat relay context requires a tuple of explicit repo-relative paths")
    root = Path(repo_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("chat relay repo root must be a directory")
    selected: list[ChatRelayContextFile] = []
    for raw_path in relative_paths:
        normalized = _safe_relative_path(raw_path)
        target = (root / Path(normalized)).resolve(strict=True)
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("chat relay context path escapes the repository") from exc
        if not target.is_file():
            raise ValueError("chat relay context paths must name regular files")
        if target.stat().st_size > _MAX_CONTEXT_FILE_BYTES:
            raise ValueError("chat relay context file exceeds the per-file limit")
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"chat relay context file is not readable UTF-8: {normalized}") from exc
        selected.append(
            ChatRelayContextFile(
                path=normalized,
                content=content,
                digest=sha256(content.encode("utf-8")).hexdigest(),
            )
        )
    files = tuple(sorted(selected, key=lambda item: item.path))
    rendered = _render_context(objective, files)
    if len(rendered.encode("utf-8")) > _MAX_CONTEXT_PACKET_BYTES:
        raise ValueError("chat relay context exceeds the total payload limit")
    return ChatRelayContextPacket(
        objective=objective,
        files=files,
        digest=sha256(rendered.encode("utf-8")).hexdigest(),
    )


def render_chat_relay_prompt(
    *, request: "ChatRelayRequest", context: ChatRelayContextPacket
) -> str:
    """Build the exact bounded prompt handed to a host adapter."""

    image_request = request.purpose is ChatRelayPurpose.IMAGEGEN

    return "\n".join(
        (
            "SWARM_PROVIDER_IMAGE_REQUEST_V1" if image_request else "SWARM_ADVISORY_CONSULT_V1",
            f"PURPOSE: {request.purpose.value}",
            f"REQUEST_DIGEST: {request.prompt_digest}",
            "RETURN_PROVIDER_ASSET: true" if image_request else "RETURN_ADVICE_ONLY: true",
            "DO_NOT_WRITE_OR_EXECUTE: true",
            context.render(),
            "END_SWARM_PROVIDER_IMAGE_REQUEST" if image_request else "END_SWARM_ADVISORY_CONSULT",
        )
    )


@dataclass(frozen=True)
class ChatRelayRequest:
    """A non-artifact request whose content stays outside SWARM state."""

    purpose: ChatRelayPurpose
    consequence_tier: str
    prompt_digest: str
    write_intent: bool = False
    artifact_production: bool = False
    provider_artifact_request: bool = False
    local_boundary: bool = False
    challenging: bool = False
    task_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, ChatRelayPurpose):
            raise ValueError("chat relay requests require a typed purpose")
        if self.consequence_tier not in {"T0", "T1", "T2", "T3", "T4"}:
            raise ValueError("chat relay requests require a typed consequence tier")
        if not isinstance(self.prompt_digest, str) or not _DIGEST.fullmatch(self.prompt_digest):
            raise ValueError("chat relay prompt identity must be a lowercase SHA-256 digest")
        if not all(isinstance(value, bool) for value in (self.write_intent, self.artifact_production, self.provider_artifact_request, self.local_boundary)):
            raise ValueError("chat relay request flags must be boolean")
        if not isinstance(self.challenging, bool):
            raise ValueError("chat relay challenging flag must be boolean")
        if not isinstance(self.task_id, str) or any(character in self.task_id for character in "\r\n"):
            raise ValueError("chat relay task identity must be a single line")


@dataclass(frozen=True)
class ChatRelayDecision:
    """A routing decision whose visible Chat result is always advisory."""

    route: ChatRelayRoute
    reason: str
    provider: str
    surface: ChatRelaySurface
    host_receipt: str
    blocker: ChatRelayBlocker | None = None
    advisory_only: bool = True
    acceptance_authority: bool = False
    observed_model: str = ""
    observed_effort: str = ""
    requested_model: str = ""
    requested_effort: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.route, ChatRelayRoute) or not isinstance(self.surface, ChatRelaySurface):
            raise ValueError("chat relay decisions require typed route and surface")
        _require_safe_provider(self.provider)
        _require_receipt(self.host_receipt)
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("chat relay decisions require a reason")
        if not self.advisory_only or self.acceptance_authority:
            raise ValueError("chat relay results cannot own acceptance")
        if self.route is ChatRelayRoute.VISIBLE_CHAT and self.blocker is not None:
            raise ValueError("visible Chat relay cannot carry a blocker")
        if self.observed_model:
            _require_observation(self.observed_model, "model")
        if self.observed_effort:
            _require_observation(self.observed_effort, "reasoning effort")


def _offload_level_allows(
    level: ChatRelayOffloadLevel,
    request: ChatRelayRequest,
) -> bool:
    """Expand the eligible advisory set as the user raises the slider."""

    if level is ChatRelayOffloadLevel.LIGHT:
        return request.purpose in {ChatRelayPurpose.PLAN, ChatRelayPurpose.RESEARCH} and request.consequence_tier == "T0" and not request.challenging
    if level is ChatRelayOffloadLevel.BALANCED:
        return (request.purpose in {ChatRelayPurpose.PLAN, ChatRelayPurpose.RESEARCH} and request.consequence_tier in {"T0", "T1"}) or (request.purpose is ChatRelayPurpose.REVIEW and request.consequence_tier == "T0" and not request.challenging) or (request.purpose is ChatRelayPurpose.TESTING and request.consequence_tier == "T0" and not request.challenging)
    if level is ChatRelayOffloadLevel.HIGH:
        return request.purpose in {ChatRelayPurpose.PLAN, ChatRelayPurpose.RESEARCH, ChatRelayPurpose.REVIEW, ChatRelayPurpose.TESTING} and request.consequence_tier in {"T0", "T1"} and not request.challenging
    return request.purpose in {ChatRelayPurpose.PLAN, ChatRelayPurpose.RESEARCH, ChatRelayPurpose.REVIEW, ChatRelayPurpose.TESTING, ChatRelayPurpose.IMAGEGEN} and request.consequence_tier in _CONSULT_TIERS


def choose_chat_relay(
    *,
    policy: ChatRelayPolicy,
    request: ChatRelayRequest,
    capability: ChatRelayCapability,
) -> ChatRelayDecision:
    """Choose visible Chat only for bounded, user-confirmed advisory work.

    A missing bridge or confirmation falls back to local Codex. This is an
    optional usage-saving tactic, not a hard dependency or a quota bypass.
    """

    requested_model = policy.challenging_model if request.challenging else policy.default_model
    requested_effort = policy.challenging_effort if request.challenging else policy.default_effort

    def local(reason: str, blocker: ChatRelayBlocker | None = None) -> ChatRelayDecision:
        return ChatRelayDecision(
            ChatRelayRoute.LOCAL_CODEX,
            reason,
            policy.provider,
            policy.surface,
            capability.receipt,
            blocker,
            requested_model=requested_model,
            requested_effort=requested_effort,
        )

    if not policy.enabled:
        return local("chat relay is disabled", ChatRelayBlocker.DISABLED)
    if request.purpose is ChatRelayPurpose.IMAGEGEN and not request.provider_artifact_request:
        return local(
            "image generation requires an explicit provider-owned artifact request",
            ChatRelayBlocker.PROVIDER_ARTIFACT_REQUIRED,
        )
    if request.provider_artifact_request and request.purpose is not ChatRelayPurpose.IMAGEGEN:
        return local(
            "provider-owned artifacts are limited to typed image-generation requests",
            ChatRelayBlocker.PROVIDER_ARTIFACT_REQUIRED,
        )
    if request.write_intent or request.artifact_production:
        return local(
            "chat relay is advisory-only and cannot own writes or artifacts",
            ChatRelayBlocker.MUTATION_INTENT,
        )
    if request.consequence_tier not in _CONSULT_TIERS:
        return local(
            "chat relay is limited to bounded T0/T1 consultation",
            ChatRelayBlocker.CONSEQUENCE_TOO_HIGH,
        )
    if request.local_boundary:
        return local(
            "repo, terminal, browser-state, test execution, write, and local artifact work must remain local",
            ChatRelayBlocker.LOCAL_BOUNDARY_REQUIRED,
        )
    if policy.routing_mode is ChatRelayRoutingMode.ALWAYS_LOCAL:
        return local(
            "routing mode is Always local",
            ChatRelayBlocker.ROUTING_MODE_LOCAL,
        )
    if policy.routing_mode is ChatRelayRoutingMode.AUTO and not _offload_level_allows(policy.offload_level, request):
        return local(
            f"chat relay offload level {policy.offload_level.value} keeps this request local",
            ChatRelayBlocker.OFFLOAD_LEVEL_SELECTION,
        )
    if not capability.visible_session:
        return local("a visible ChatGPT session is required", ChatRelayBlocker.VISIBLE_SESSION_REQUIRED)
    if not capability.browser_bridge:
        return local("a compatible visible browser bridge is required", ChatRelayBlocker.BROWSER_BRIDGE_REQUIRED)
    if not capability.observed_model or not capability.observed_effort:
        return local(
            "the visible model and reasoning effort must be observed before consultation",
            ChatRelayBlocker.HOST_CONFIG_REQUIRED,
        )
    if not _observed_selection_matches(
        requested_model=requested_model,
        requested_effort=requested_effort,
        capability=capability,
    ):
        return local(
            "the visible model and reasoning effort do not match the requested relay profile",
            ChatRelayBlocker.HOST_CONFIG_REQUIRED,
        )
    if not capability.user_confirmed:
        return local("user confirmation is required before sending the consult", ChatRelayBlocker.USER_CONFIRMATION_REQUIRED)
    return ChatRelayDecision(
        ChatRelayRoute.VISIBLE_CHAT,
        "bounded advisory consultation may use the visible Chat surface",
        policy.provider,
        policy.surface,
        capability.receipt,
        observed_model=capability.observed_model,
        observed_effort=capability.observed_effort,
        requested_model=requested_model,
        requested_effort=requested_effort,
    )


def consult_chat_relay(
    *,
    policy: ChatRelayPolicy,
    request: ChatRelayRequest,
    context: ChatRelayContextPacket,
    adapter: ChatRelayAdapter,
    confirm: Callable[[str], bool] | None = None,
    ledger: ChatRelayUsageLedger | None = None,
) -> ChatRelayConsultation:
    """Route one bounded consult through a host adapter or fall back locally.

    The adapter is inspected immediately before the send. SWARM never supplies
    a default transport and never treats the returned text as execution or
    acceptance evidence.
    """

    prompt = render_chat_relay_prompt(request=request, context=context)
    capability = adapter.capability()
    decision = choose_chat_relay(policy=policy, request=request, capability=capability)
    if decision.blocker is ChatRelayBlocker.USER_CONFIRMATION_REQUIRED and confirm is not None:
        if confirm(prompt) is True:
            capability = replace(capability, user_confirmed=True)
            decision = choose_chat_relay(policy=policy, request=request, capability=capability)
    if decision.route is ChatRelayRoute.LOCAL_CODEX:
        return ChatRelayConsultation(decision)
    try:
        response = adapter.send_consult(
            prompt,
            model=decision.requested_model,
            effort=decision.requested_effort,
        ) if request.purpose is not ChatRelayPurpose.IMAGEGEN else _send_image(
            adapter,
            prompt,
            model=decision.requested_model,
            effort=decision.requested_effort,
        )
    except ChatRelayTransportError as exc:
        return ChatRelayConsultation(
            replace(
                decision,
                route=ChatRelayRoute.LOCAL_CODEX,
                reason=str(exc),
                blocker=exc.blocker,
            )
        )
    if response.observed_model != capability.observed_model or response.observed_effort != capability.observed_effort:
        raise ValueError("chat relay host configuration changed during consultation")
    if ledger is not None:
        try:
            ledger.record(
                task_id=request.task_id,
                purpose=request.purpose.value,
                response=response,
            )
        except (OSError, TypeError, ValueError):
            # Usage telemetry is deliberately non-blocking for the advisory route.
            pass
    return ChatRelayConsultation(decision, response)


def _send_image(
    adapter: ChatRelayAdapter,
    prompt: str,
    *,
    model: str,
    effort: str,
) -> ChatRelayResponse:
    """Send a provider-owned image request only through an image-capable adapter."""

    sender = getattr(adapter, "send_image", None)
    if not callable(sender):
        raise ChatRelayTransportError(
            "the configured ChatGPT adapter does not expose image generation",
            blocker=ChatRelayBlocker.PROVIDER_ADAPTER_REQUIRED,
        )
    try:
        response = sender(prompt, model=model, effort=effort)
    except ChatRelayTransportError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ChatRelayTransportError(
            f"provider image generation was unavailable: {exc}",
            blocker=ChatRelayBlocker.PROVIDER_ARTIFACT_UNAVAILABLE,
        ) from exc
    if not isinstance(response, ChatRelayResponse):
        raise ChatRelayTransportError(
            "provider image generation returned an invalid response",
            blocker=ChatRelayBlocker.PROVIDER_ARTIFACT_UNAVAILABLE,
        )
    if not response.transport.asset_ids:
        raise ChatRelayTransportError(
            "provider image generation returned no asset receipt",
            blocker=ChatRelayBlocker.PROVIDER_ARTIFACT_UNAVAILABLE,
        )
    return response
