"""Capability-driven ChatGPT actor routing for SWARM.

SWARM owns actor selection, task envelopes, scope, approvals, receipts, and
acceptance. A CodexPro, CCCC, or other MCP-compatible runtime remains an
external provider and owns its transport and host-enforced tool permissions.
The provider boundary is deliberately narrow so SWARM can use the full set of
capabilities a connected runtime advertises without bundling that runtime or
inventing an additional policy ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
import json
from pathlib import Path
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


class ChatGPTBridgeTransport(StrEnum):
    """Transport exposed by an external ChatGPT actor provider."""

    REMOTE_MCP = "remote_mcp"
    BROWSER_DELIVERY = "browser_delivery"


@dataclass(frozen=True)
class ChatGPTBridgeManifest:
    """Credential-free durable identity for an optional external provider."""

    provider_id: str
    actor_id: str
    transport: ChatGPTBridgeTransport
    workspace_scope: str = ""
    tool_capabilities: frozenset[str] = frozenset()
    endpoint: str = ""
    enabled: bool = True
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (("provider", self.provider_id), ("actor", self.actor_id), ("endpoint", self.endpoint)):
            if not isinstance(value, str) or any(character in value for character in "\r\n"):
                raise ValueError(f"ChatGPT bridge {label} must be a single line")
        if not self.provider_id.strip() or not self.actor_id.strip():
            raise ValueError("ChatGPT bridge manifest requires provider and actor identity")
        lowered_endpoint = self.endpoint.casefold()
        if any(marker in lowered_endpoint for marker in ("token=", "secret=", "apikey=", "api_key=", "authorization=")):
            raise ValueError("ChatGPT bridge manifest must not persist credentials in an endpoint")
        if not isinstance(self.transport, ChatGPTBridgeTransport):
            raise ValueError("ChatGPT bridge manifest requires a known transport")
        if not isinstance(self.workspace_scope, str) or any(character in self.workspace_scope for character in "\r\n"):
            raise ValueError("ChatGPT bridge manifest workspace scope must be a single line")
        if not isinstance(self.tool_capabilities, frozenset) or any(
            not isinstance(tool, str) or not tool.strip() or any(character in tool for character in "\r\n")
            for tool in self.tool_capabilities
        ):
            raise ValueError("ChatGPT bridge manifest tools must be single-line names")
        if not isinstance(self.enabled, bool) or self.schema_version != 1:
            raise ValueError("ChatGPT bridge manifest has unsupported schema or enabled value")

    @classmethod
    def from_actor(
        cls,
        actor: "ChatGPTActor",
        *,
        endpoint: str = "",
        enabled: bool = True,
    ) -> "ChatGPTBridgeManifest":
        return cls(
            provider_id=actor.provider,
            actor_id=actor.actor_id,
            transport=actor.transport,
            workspace_scope=actor.workspace_scope,
            tool_capabilities=actor.tool_capabilities,
            endpoint=endpoint,
            enabled=enabled,
        )

    @classmethod
    def from_dict(cls, value: object) -> "ChatGPTBridgeManifest":
        if not isinstance(value, dict):
            raise ValueError("ChatGPT bridge manifest entries must be objects")
        tools = value.get("tool_capabilities", ())
        if not isinstance(tools, (list, tuple)):
            raise ValueError("ChatGPT bridge manifest tools must be a list")
        return cls(
            provider_id=value.get("provider_id", ""),
            actor_id=value.get("actor_id", ""),
            transport=ChatGPTBridgeTransport(value.get("transport", "remote_mcp")),
            workspace_scope=value.get("workspace_scope", ""),
            tool_capabilities=frozenset(tools),
            endpoint=value.get("endpoint", ""),
            enabled=value.get("enabled", True),
            schema_version=value.get("schema_version", 1),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider_id": self.provider_id,
            "actor_id": self.actor_id,
            "transport": self.transport.value,
            "workspace_scope": self.workspace_scope,
            "tool_capabilities": sorted(self.tool_capabilities),
            "endpoint": self.endpoint,
            "enabled": self.enabled,
        }


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
    transport: ChatGPTBridgeTransport = ChatGPTBridgeTransport.REMOTE_MCP
    actor_id: str = ""
    tool_capabilities: frozenset[str] = frozenset()

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
        if not isinstance(self.transport, ChatGPTBridgeTransport):
            raise ValueError("chat executor capability requires a known bridge transport")
        if not isinstance(self.actor_id, str) or any(character in self.actor_id for character in "\r\n"):
            raise ValueError("chat executor actor identity must be a single line")
        if not isinstance(self.tool_capabilities, frozenset) or any(
            not isinstance(tool, str) or not tool.strip() or any(character in tool for character in "\r\n")
            for tool in self.tool_capabilities
        ):
            raise ValueError("chat executor tool capabilities must be single-line names")
        tools = set(self.tool_capabilities)
        tools.update(
            name
            for enabled, name in (
                (self.read_tools, "workspace.read"),
                (self.write_tools, "workspace.write"),
                (self.command_tools, "command.safe"),
                (self.artifact_tools, "artifact.create"),
            )
            if enabled
        )
        object.__setattr__(self, "tool_capabilities", frozenset(tools))


@dataclass(frozen=True)
class ChatGPTActor:
    """A registered external ChatGPT worker visible to SWARM."""

    actor_id: str
    provider: str
    transport: ChatGPTBridgeTransport
    workspace_scope: str
    tool_capabilities: frozenset[str]
    connected: bool
    host_receipt: str
    observed_model: str = ""
    observed_effort: str = ""
    user_confirmed: bool = False

    def __post_init__(self) -> None:
        for label, value in (("actor", self.actor_id), ("provider", self.provider), ("receipt", self.host_receipt)):
            if not isinstance(value, str) or not value.strip() or any(character in value for character in "\r\n"):
                raise ValueError(f"ChatGPT actor requires a valid {label}")
        if not isinstance(self.transport, ChatGPTBridgeTransport):
            raise ValueError("ChatGPT actor requires a known bridge transport")
        if not isinstance(self.workspace_scope, str) or any(character in self.workspace_scope for character in "\r\n"):
            raise ValueError("ChatGPT actor workspace scope must be a single line")
        if not isinstance(self.tool_capabilities, frozenset) or any(
            not isinstance(tool, str) or not tool.strip() for tool in self.tool_capabilities
        ):
            raise ValueError("ChatGPT actor tool capabilities must be non-empty names")
        if not isinstance(self.connected, bool) or not isinstance(self.user_confirmed, bool):
            raise ValueError("ChatGPT actor connection flags must be boolean")

    @classmethod
    def from_capability(cls, capability: ChatExecutorCapability) -> "ChatGPTActor":
        return cls(
            actor_id=capability.actor_id or capability.provider,
            provider=capability.provider,
            transport=capability.transport,
            workspace_scope=capability.workspace_scope,
            tool_capabilities=capability.tool_capabilities,
            connected=capability.connected,
            host_receipt=capability.receipt,
            observed_model=capability.observed_model,
            observed_effort=capability.observed_effort,
            user_confirmed=capability.user_confirmed,
        )


class ChatGPTBridgeProvider(Protocol):
    """External provider contract; the provider implementation is not bundled."""

    def capability(self) -> ChatExecutorCapability:
        """Return a fresh host-observed capability and scope receipt."""

    def execute_task(
        self,
        prompt: str,
        *,
        model: str,
        effort: str,
        write_mode: ChatExecutorWriteMode,
        command_mode: ChatExecutorCommandMode,
    ) -> "ChatExecutorResponse":
        """Execute one task using only host-enforced provider tools."""


# Compatibility name for existing integrations. New code should use the
# provider/actor vocabulary, while old adapters remain valid providers.
ChatExecutorAdapter = ChatGPTBridgeProvider


class ChatGPTBridgeRegistry:
    """Registry for optional providers plus a credential-free durable manifest."""

    def __init__(self, manifest_path: Path | None = None) -> None:
        self._providers: dict[str, ChatGPTBridgeProvider] = {}
        self._actors: dict[str, ChatGPTActor] = {}
        self._manifests: dict[str, ChatGPTBridgeManifest] = {}
        self.manifest_path = manifest_path

    def register(
        self,
        provider: ChatGPTBridgeProvider,
        *,
        manifest: ChatGPTBridgeManifest | None = None,
        persist: bool = False,
    ) -> ChatGPTActor:
        capability = provider.capability()
        actor = ChatGPTActor.from_capability(capability)
        if manifest is not None and (manifest.provider_id != actor.provider or manifest.actor_id != actor.actor_id):
            raise ValueError("ChatGPT bridge manifest does not match the provider capability")
        self._providers[actor.actor_id] = provider
        self._actors[actor.actor_id] = actor
        self._manifests[actor.actor_id] = ChatGPTBridgeManifest.from_actor(
            actor,
            endpoint=manifest.endpoint if manifest is not None else "",
            enabled=manifest.enabled if manifest is not None else True,
        )
        if persist:
            self.save()
        return actor

    def refresh(self, actor_id: str) -> ChatGPTActor:
        provider = self._providers.get(actor_id)
        if provider is None:
            raise KeyError(f"unknown ChatGPT actor: {actor_id}")
        actor = ChatGPTActor.from_capability(provider.capability())
        if actor.actor_id != actor_id:
            raise ValueError("provider changed its actor identity during refresh")
        self._actors[actor_id] = actor
        previous = self._manifests.get(actor_id)
        self._manifests[actor_id] = ChatGPTBridgeManifest.from_actor(
            actor,
            endpoint=previous.endpoint if previous is not None else "",
            enabled=previous.enabled if previous is not None else True,
        )
        return actor

    def actor(self, actor_id: str) -> ChatGPTActor | None:
        return self._actors.get(actor_id)

    def provider(self, actor_id: str) -> ChatGPTBridgeProvider | None:
        return self._providers.get(actor_id)

    def actors(self) -> tuple[ChatGPTActor, ...]:
        return tuple(self._actors[key] for key in sorted(self._actors))

    def manifests(self) -> tuple[ChatGPTBridgeManifest, ...]:
        return tuple(self._manifests[key] for key in sorted(self._manifests))

    def manifest(self, actor_id: str) -> ChatGPTBridgeManifest | None:
        return self._manifests.get(actor_id)

    def discover(self, path: Path | None = None) -> tuple[ChatGPTBridgeManifest, ...]:
        """Load durable provider identities without connecting or using a provider."""
        target = path or self.manifest_path
        if target is None or not target.exists():
            return self.manifests()
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"ChatGPT bridge manifest could not be read: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("ChatGPT bridge manifest store has unsupported schema")
        entries = payload.get("bridges", ())
        if not isinstance(entries, list):
            raise ValueError("ChatGPT bridge manifest store requires a bridges list")
        manifests = tuple(ChatGPTBridgeManifest.from_dict(entry) for entry in entries)
        self._manifests = {manifest.actor_id: manifest for manifest in manifests}
        return manifests

    def save(self, path: Path | None = None) -> Path:
        """Persist identities and capabilities, never credentials or live receipts."""
        target = path or self.manifest_path
        if target is None:
            raise ValueError("ChatGPT bridge manifest path is required for persistence")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "bridges": [manifest.to_dict() for manifest in self.manifests() if manifest.enabled],
        }
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(target)
        return target

    def remove(self, actor_id: str, *, persist: bool = False) -> None:
        self._providers.pop(actor_id, None)
        self._actors.pop(actor_id, None)
        self._manifests.pop(actor_id, None)
        if persist:
            self.save()


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
    """Build the provider-neutral task envelope sent to a registered actor."""

    return "\n".join(
        (
            "SWARM_CHATGPT_ACTOR_TASK_V2",
            f"ACTOR_ID: {capability.actor_id or capability.provider}",
            f"PROVIDER: {capability.provider}",
            f"TRANSPORT: {capability.transport.value}",
            f"PURPOSE: {request.purpose.value}",
            f"CONSEQUENCE_TIER: {request.consequence_tier}",
            f"TASK_ID: {request.task_id}",
            f"REQUEST_DIGEST: {request.prompt_digest}",
            f"WORKSPACE_SCOPE: {capability.workspace_scope}",
            f"ALLOW_WORKSPACE_WRITES: {str(request.write_intent or request.artifact_production).lower()}",
            f"ALLOW_SAFE_COMMANDS: {str(request.command_intent).lower()}",
            f"ADVERTISED_TOOLS: {','.join(sorted(capability.tool_capabilities))}",
            "RETURN_HOST_RECEIPT: true",
            "SWARM_REMAINS_ACCEPTANCE_OWNER: true",
            context.render(),
            "END_SWARM_CHATGPT_LOCAL_TASK",
        )
    )


def _offload_level_allows_executor(level: ChatRelayOffloadLevel, request: ChatExecutorRequest) -> bool:
    """Apply the user's breadth preference, not a hidden capability ceiling.

    Tool type and consequence are checked separately below. In particular,
    implementation, commands, artifacts, and T4 work are eligible at Max
    when the connected provider advertises the required capabilities. They are
    not forced local merely because they mutate or require acceptance.
    """

    if level is ChatRelayOffloadLevel.LIGHT:
        return request.purpose in {ChatRelayPurpose.PLAN, ChatRelayPurpose.RESEARCH} and request.consequence_tier == "T0"
    if level is ChatRelayOffloadLevel.BALANCED:
        return request.purpose in {
            ChatRelayPurpose.PLAN,
            ChatRelayPurpose.RESEARCH,
            ChatRelayPurpose.REVIEW,
            ChatRelayPurpose.TESTING,
            ChatRelayPurpose.IMAGEGEN,
        } and request.consequence_tier in {"T0", "T1"}
    if level is ChatRelayOffloadLevel.HIGH:
        return request.purpose in {
            ChatRelayPurpose.PLAN,
            ChatRelayPurpose.RESEARCH,
            ChatRelayPurpose.REVIEW,
            ChatRelayPurpose.TESTING,
            ChatRelayPurpose.IMAGEGEN,
        } and request.consequence_tier in {"T0", "T1", "T2", "T3"}
    return True


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
