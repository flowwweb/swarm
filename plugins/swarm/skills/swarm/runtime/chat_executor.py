"""Explicit, opt-in ChatGPT local-work executor boundary.

The existing :mod:`chat_relay` module is deliberately advisory-only. This
module is the separate contract for a host-owned local MCP bridge that can
read, edit, and run narrowly scoped work. SWARM selects the route and keeps
acceptance authority; the adapter owns the actual MCP transport and tool
enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Callable, Protocol

from .chat_relay import (
    ChatRelayBlocker,
    ChatRelayContextPacket,
    ChatRelayOffloadLevel,
    ChatRelayPolicy,
    ChatRelayPurpose,
    ChatRelayRequest,
    ChatRelayRoute,
    ChatRelayTransportError,
    ChatRelayTransportReceipt,
    _observed_selection_matches,
)
from .chat_relay_usage import ChatRelayUsageLedger


class ChatExecutorRoute(StrEnum):
    LOCAL_CODEX = "local_codex"
    CHATGPT_MCP = "chatgpt_mcp"


class ChatExecutorWriteMode(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE = "workspace"


class ChatExecutorCommandMode(StrEnum):
    NONE = "none"
    SAFE = "safe"


class ChatExecutorBlocker(StrEnum):
    DISABLED = "disabled"
    ROUTING_MODE_LOCAL = "routing_mode_local"
    LOCAL_BOUNDARY_REQUIRED = "local_boundary_required"
    CONSEQUENCE_TOO_HIGH = "consequence_too_high"
    OFFLOAD_LEVEL_SELECTION = "offload_level_selection"
    BRIDGE_NOT_CONNECTED = "bridge_not_connected"
    WORKSPACE_SCOPE_REQUIRED = "workspace_scope_required"
    READ_CAPABILITY_REQUIRED = "read_capability_required"
    WRITE_CAPABILITY_REQUIRED = "write_capability_required"
    COMMAND_CAPABILITY_REQUIRED = "command_capability_required"
    ARTIFACT_CAPABILITY_REQUIRED = "artifact_capability_required"
    CONFIRMATION_REQUIRED = "confirmation_required"
    HOST_CONFIG_REQUIRED = "host_config_required"
    PROVIDER_RESPONSE_UNAVAILABLE = "provider_response_unavailable"
    PROVIDER_ADAPTER_REQUIRED = "provider_adapter_required"


@dataclass(frozen=True)
class ChatExecutorPolicy:
    """Persisted preference for a local MCP executor, disabled by default."""

    enabled: bool = False
    write_mode: ChatExecutorWriteMode = ChatExecutorWriteMode.READ_ONLY
    command_mode: ChatExecutorCommandMode = ChatExecutorCommandMode.NONE
    require_confirmation: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("chat executor enabled must be true or false")
        if not isinstance(self.write_mode, ChatExecutorWriteMode):
            raise ValueError("chat executor write mode must be read_only or workspace")
        if not isinstance(self.command_mode, ChatExecutorCommandMode):
            raise ValueError("chat executor command mode must be none or safe")
        if not isinstance(self.require_confirmation, bool):
            raise ValueError("chat executor confirmation must be true or false")

    @classmethod
    def from_config(cls, values: dict[str, object]) -> "ChatExecutorPolicy":
        if not isinstance(values, dict):
            raise ValueError("chat executor configuration must be a table")
        return cls(
            enabled=values.get("executor_enabled", False),
            write_mode=ChatExecutorWriteMode(values.get("executor_write_mode", "read_only")),
            command_mode=ChatExecutorCommandMode(values.get("executor_command_mode", "none")),
            require_confirmation=values.get("executor_require_confirmation", True),
        )


@dataclass(frozen=True)
class ChatExecutorCapability:
    """Host-observed MCP scope and tools immediately before execution."""

    connected: bool
    provider: str
    receipt: str
    workspace_scope: str
    read_tools: bool = False
    write_tools: bool = False
    command_tools: bool = False
    artifact_tools: bool = False
    user_confirmed: bool = False
    observed_model: str = ""
    observed_effort: str = ""

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, bool)
            for value in (
                self.connected,
                self.read_tools,
                self.write_tools,
                self.command_tools,
                self.artifact_tools,
                self.user_confirmed,
            )
        ):
            raise ValueError("chat executor capability flags must be boolean")
        if not isinstance(self.provider, str) or not self.provider.strip() or any(
            character in self.provider for character in "\r\n"
        ):
            raise ValueError("chat executor capability requires a provider")
        if not isinstance(self.receipt, str) or not self.receipt.strip() or any(
            character in self.receipt for character in "\r\n"
        ):
            raise ValueError("chat executor capability requires a host receipt")
        if not isinstance(self.workspace_scope, str) or any(
            character in self.workspace_scope for character in "\r\n"
        ):
            raise ValueError("chat executor workspace scope must be a single line")
        for label, value in (("model", self.observed_model), ("effort", self.observed_effort)):
            if not isinstance(value, str) or any(character in value for character in "\r\n"):
                raise ValueError(f"chat executor observed {label} must be a single line")


class ChatExecutorAdapter(Protocol):
    """Host-owned transport for a connected, scope-limited local MCP bridge."""

    def capability(self) -> ChatExecutorCapability:
        """Inspect the connected bridge and its exact tool scope."""

    def execute_task(
        self,
        prompt: str,
        *,
        model: str,
        effort: str,
        write_mode: ChatExecutorWriteMode,
        command_mode: ChatExecutorCommandMode,
    ) -> "ChatExecutorResponse":
        """Run one task through host-enforced MCP tools."""


@dataclass(frozen=True)
class ChatExecutorResponse:
    """Transient host result; SWARM still owns verification and acceptance."""

    text: str
    host_receipt: str
    observed_model: str
    observed_effort: str
    changed_paths: tuple[str, ...] = ()
    acceptance_authority: bool = False
    transport: ChatRelayTransportReceipt = field(
        default_factory=lambda: ChatRelayTransportReceipt(transport="local_mcp")
    )

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("chat executor responses require text")
        if not isinstance(self.host_receipt, str) or not self.host_receipt.strip():
            raise ValueError("chat executor responses require a host receipt")
        if not isinstance(self.observed_model, str) or not self.observed_model.strip():
            raise ValueError("chat executor responses require an observed model")
        if not isinstance(self.observed_effort, str) or not self.observed_effort.strip():
            raise ValueError("chat executor responses require observed reasoning effort")
        if not isinstance(self.changed_paths, tuple) or any(
            not isinstance(path, str) or not path.strip() or any(character in path for character in "\r\n")
            for path in self.changed_paths
        ):
            raise ValueError("chat executor changed paths must be a tuple of single-line paths")
        if self.acceptance_authority:
            raise ValueError("chat executor responses cannot own acceptance")
        if not isinstance(self.transport, ChatRelayTransportReceipt):
            raise ValueError("chat executor responses require a typed transport receipt")


@dataclass(frozen=True)
class ChatExecutorRequest:
    """A task eligible for a connected local bridge, with explicit capabilities."""

    purpose: ChatRelayPurpose
    consequence_tier: str
    prompt_digest: str
    local_boundary: bool = False
    write_intent: bool = False
    command_intent: bool = False
    artifact_production: bool = False
    challenging: bool = False
    task_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, ChatRelayPurpose):
            raise ValueError("chat executor requests require a typed purpose")
        if self.consequence_tier not in {"T0", "T1", "T2", "T3", "T4"}:
            raise ValueError("chat executor requests require a typed consequence tier")
        if not isinstance(self.prompt_digest, str) or len(self.prompt_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.prompt_digest
        ):
            raise ValueError("chat executor prompt identity must be a lowercase SHA-256 digest")
        if not all(
            isinstance(value, bool)
            for value in (
                self.local_boundary,
                self.write_intent,
                self.command_intent,
                self.artifact_production,
                self.challenging,
            )
        ):
            raise ValueError("chat executor request flags must be boolean")
        if not isinstance(self.task_id, str) or any(character in self.task_id for character in "\r\n"):
            raise ValueError("chat executor task identity must be a single line")


@dataclass(frozen=True)
class ChatExecutorDecision:
    route: ChatExecutorRoute
    reason: str
    provider: str
    host_receipt: str
    workspace_scope: str = ""
    blocker: ChatExecutorBlocker | None = None
    acceptance_authority: bool = False
    observed_model: str = ""
    observed_effort: str = ""
    requested_model: str = ""
    requested_effort: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.route, ChatExecutorRoute):
            raise ValueError("chat executor decisions require a typed route")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("chat executor decisions require a reason")
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("chat executor decisions require a provider")
        if not isinstance(self.host_receipt, str) or not self.host_receipt.strip():
            raise ValueError("chat executor decisions require a host receipt")
        if self.acceptance_authority:
            raise ValueError("chat executor decisions cannot own acceptance")


@dataclass(frozen=True)
class ChatExecutorResult:
    decision: ChatExecutorDecision
    response: ChatExecutorResponse | None = None

    def __post_init__(self) -> None:
        if self.decision.route is ChatExecutorRoute.CHATGPT_MCP and self.response is None:
            raise ValueError("ChatGPT executor routes require a host response")
        if self.decision.route is ChatExecutorRoute.LOCAL_CODEX and self.response is not None:
            raise ValueError("local executor fallbacks cannot carry a host response")


class ChatExecutorTransportError(RuntimeError):
    """A bridge failure that safely returns ownership to local SWARM."""

    def __init__(self, message: str, *, blocker: ChatExecutorBlocker) -> None:
        super().__init__(message)
        self.blocker = blocker


def render_chat_executor_prompt(
    *, request: ChatExecutorRequest, context: ChatRelayContextPacket, capability: ChatExecutorCapability
) -> str:
    """Build an explicit, bounded task envelope for the MCP host."""

    return "\n".join(
        (
            "SWARM_CHATGPT_LOCAL_TASK_V1",
            f"PURPOSE: {request.purpose.value}",
            f"REQUEST_DIGEST: {request.prompt_digest}",
            f"WORKSPACE_SCOPE: {capability.workspace_scope}",
            f"ALLOW_WORKSPACE_WRITES: {str(request.write_intent or request.artifact_production).lower()}",
            f"ALLOW_SAFE_COMMANDS: {str(request.command_intent).lower()}",
            "RETURN_HOST_RECEIPT: true",
            "SWARM_REMAINS_ACCEPTANCE_OWNER: true",
            context.render(),
            "END_SWARM_CHATGPT_LOCAL_TASK",
        )
    )


def _offload_level_allows_executor(level: ChatRelayOffloadLevel, request: ChatExecutorRequest) -> bool:
    """Keep ordinary read-only work on the same four-stop slider as advisory work."""

    if request.write_intent or request.command_intent or request.artifact_production:
        return level is ChatRelayOffloadLevel.MAX
    if level is ChatRelayOffloadLevel.LIGHT:
        return request.purpose in {ChatRelayPurpose.PLAN, ChatRelayPurpose.RESEARCH} and request.consequence_tier == "T0"
    if level is ChatRelayOffloadLevel.BALANCED:
        return request.purpose in {ChatRelayPurpose.PLAN, ChatRelayPurpose.RESEARCH, ChatRelayPurpose.REVIEW} and request.consequence_tier in {"T0", "T1"}
    if level is ChatRelayOffloadLevel.HIGH:
        return request.purpose in {ChatRelayPurpose.PLAN, ChatRelayPurpose.RESEARCH, ChatRelayPurpose.REVIEW, ChatRelayPurpose.TESTING} and request.consequence_tier in {"T0", "T1"}
    return request.purpose in {ChatRelayPurpose.PLAN, ChatRelayPurpose.RESEARCH, ChatRelayPurpose.REVIEW, ChatRelayPurpose.TESTING, ChatRelayPurpose.IMAGEGEN} and request.consequence_tier in {"T0", "T1"}


def choose_chat_executor(
    *, policy: ChatExecutorPolicy, relay_policy: ChatRelayPolicy, request: ChatExecutorRequest, capability: ChatExecutorCapability
) -> ChatExecutorDecision:
    """Choose a local MCP route only when the host reports every needed tool."""

    requested_model = relay_policy.challenging_model if request.challenging else relay_policy.default_model
    requested_effort = relay_policy.challenging_effort if request.challenging else relay_policy.default_effort

    def local(reason: str, blocker: ChatExecutorBlocker | None = None) -> ChatExecutorDecision:
        return ChatExecutorDecision(
            ChatExecutorRoute.LOCAL_CODEX,
            reason,
            capability.provider,
            capability.receipt,
            blocker=blocker,
            requested_model=requested_model,
            requested_effort=requested_effort,
        )

    if not policy.enabled or not relay_policy.enabled:
        return local("ChatGPT local work is disabled", ChatExecutorBlocker.DISABLED)
    if relay_policy.routing_mode.value == "always_local":
        return local("routing mode is Always local", ChatExecutorBlocker.ROUTING_MODE_LOCAL)
    if not request.local_boundary:
        return local("local MCP execution requires an explicit local boundary", ChatExecutorBlocker.LOCAL_BOUNDARY_REQUIRED)
    if request.consequence_tier == "T4":
        return local("T4 work remains with local SWARM acceptance", ChatExecutorBlocker.CONSEQUENCE_TOO_HIGH)
    if not _offload_level_allows_executor(relay_policy.offload_level, request):
        return local(
            f"chat executor offload level {relay_policy.offload_level.value} keeps this work local",
            ChatExecutorBlocker.OFFLOAD_LEVEL_SELECTION,
        )
    if not capability.connected:
        return local("a connected local MCP bridge is required", ChatExecutorBlocker.BRIDGE_NOT_CONNECTED)
    if not capability.workspace_scope.strip():
        return local("the bridge must report an exact workspace scope", ChatExecutorBlocker.WORKSPACE_SCOPE_REQUIRED)
    if not capability.read_tools:
        return local("the bridge must report read tools", ChatExecutorBlocker.READ_CAPABILITY_REQUIRED)
    if (request.write_intent or request.artifact_production) and policy.write_mode is not ChatExecutorWriteMode.WORKSPACE:
        return local("workspace write access is disabled", ChatExecutorBlocker.WRITE_CAPABILITY_REQUIRED)
    if request.write_intent and not capability.write_tools:
        return local("the bridge did not report workspace write tools", ChatExecutorBlocker.WRITE_CAPABILITY_REQUIRED)
    if request.command_intent and policy.command_mode is not ChatExecutorCommandMode.SAFE:
        return local("safe command access is disabled", ChatExecutorBlocker.COMMAND_CAPABILITY_REQUIRED)
    if request.command_intent and not capability.command_tools:
        return local("the bridge did not report safe command tools", ChatExecutorBlocker.COMMAND_CAPABILITY_REQUIRED)
    if request.artifact_production and not capability.artifact_tools:
        return local("the bridge did not report artifact tools", ChatExecutorBlocker.ARTIFACT_CAPABILITY_REQUIRED)
    if not capability.observed_model or not capability.observed_effort:
        return local("the bridge must report the active model and reasoning effort", ChatExecutorBlocker.HOST_CONFIG_REQUIRED)
    if not _observed_selection_matches(
        requested_model=requested_model, requested_effort=requested_effort, capability=capability
    ):
        return local("the bridge model and reasoning effort do not match the requested profile", ChatExecutorBlocker.HOST_CONFIG_REQUIRED)
    if policy.require_confirmation and not capability.user_confirmed:
        return local("user confirmation is required before local ChatGPT work", ChatExecutorBlocker.CONFIRMATION_REQUIRED)
    return ChatExecutorDecision(
        ChatExecutorRoute.CHATGPT_MCP,
        "scoped ChatGPT local work may use the connected MCP bridge",
        capability.provider,
        capability.receipt,
        workspace_scope=capability.workspace_scope,
        observed_model=capability.observed_model,
        observed_effort=capability.observed_effort,
        requested_model=requested_model,
        requested_effort=requested_effort,
    )


def execute_chat_task(
    *,
    policy: ChatExecutorPolicy,
    relay_policy: ChatRelayPolicy,
    request: ChatExecutorRequest,
    context: ChatRelayContextPacket,
    adapter: ChatExecutorAdapter,
    confirm: Callable[[str], bool] | None = None,
    ledger: ChatRelayUsageLedger | None = None,
) -> ChatExecutorResult:
    """Execute one scoped task through an injected host adapter or fall back."""

    capability = adapter.capability()
    prompt = render_chat_executor_prompt(request=request, context=context, capability=capability)
    decision = choose_chat_executor(policy=policy, relay_policy=relay_policy, request=request, capability=capability)
    if decision.blocker is ChatExecutorBlocker.CONFIRMATION_REQUIRED and confirm is not None:
        if confirm(prompt) is True:
            capability = replace(capability, user_confirmed=True)
            decision = choose_chat_executor(policy=policy, relay_policy=relay_policy, request=request, capability=capability)
    if decision.route is ChatExecutorRoute.LOCAL_CODEX:
        return ChatExecutorResult(decision)
    try:
        response = adapter.execute_task(
            prompt,
            model=decision.requested_model,
            effort=decision.requested_effort,
            write_mode=policy.write_mode,
            command_mode=policy.command_mode,
        )
    except ChatExecutorTransportError as exc:
        return ChatExecutorResult(
            replace(decision, route=ChatExecutorRoute.LOCAL_CODEX, reason=str(exc), blocker=exc.blocker)
        )
    if response.observed_model != capability.observed_model or response.observed_effort != capability.observed_effort:
        raise ValueError("chat executor host configuration changed during execution")
    if ledger is not None:
        try:
            ledger.record(task_id=request.task_id, purpose=request.purpose.value, response=response)  # type: ignore[arg-type]
        except (OSError, TypeError, ValueError):
            pass
    return ChatExecutorResult(decision, response)
