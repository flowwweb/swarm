"""Optional adapter for the visible codex-chatgpt-control backend.

This module never installs the third-party package and never invents host
receipts. Construct it only from an explicitly configured host, then pass its
``confirm_prompt`` callback to ``consult_chat_relay``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import time

from .chat_relay import (
    ChatRelayCapability,
    ChatRelayBlocker,
    ChatRelayResponse,
    ChatRelayTransportError,
    ChatRelayTransportReceipt,
)
from .chat_executor import (
    ChatExecutorBlocker,
    ChatExecutorCapability,
    ChatExecutorCommandMode,
    ChatExecutorResponse,
    ChatExecutorTransportError,
    ChatExecutorWriteMode,
)


DEFAULT_BACKEND_COMMAND = (
    "npx",
    "--yes",
    "--package",
    "codex-chatgpt-control@next",
    "codex-chatgpt-control-backend",
)

def _value(result: object, key: str) -> object:
    if isinstance(result, Mapping):
        return result.get(key)
    return getattr(result, key, None)


def _first_value(result: object, keys: tuple[str, ...]) -> object:
    for key in keys:
        value = _value(result, key)
        if value is not None:
            return value
    return None


def _asset_ids(result: object) -> tuple[str, ...]:
    values: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())

    def visit(value: object, *, asset_context: bool = False) -> None:
        if not isinstance(value, (Mapping, str, Sequence)):
            attributes = getattr(value, "__dict__", None)
            if isinstance(attributes, Mapping):
                visit(attributes, asset_context=asset_context)
            return
        if isinstance(value, Mapping):
            for key, child in value.items():
                if not isinstance(key, str):
                    continue
                normalized = key.replace("_", "").replace("-", "").casefold()
                if normalized in {"assetids", "artifactids"}:
                    if isinstance(child, str):
                        add(child)
                    elif isinstance(child, Mapping):
                        visit(child, asset_context=True)
                    elif isinstance(child, Sequence):
                        for item in child:
                            visit(item, asset_context=True)
                    continue
                if normalized in {"assets", "artifacts", "asset", "artifact"}:
                    visit(child, asset_context=True)
                    continue
                if asset_context and normalized in {"id", "assetid", "artifactid", "key", "artifactkey"}:
                    add(child)
                visit(child, asset_context=asset_context)
            return
        if isinstance(value, str):
            if asset_context:
                add(value)
            return
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            for item in value:
                visit(item, asset_context=asset_context)

    visit(result)
    return tuple(values)


def _usage_fields(result: object) -> tuple[int | None, int | None, int | None, str, str]:
    usage = _first_value(result, ("usage", "token_usage", "tokenUsage"))
    if usage is None:
        return None, None, None, "unavailable", "provider did not expose a usage object"
    fields = tuple(
        _first_value(usage, keys)
        for keys in (
            ("input_tokens", "inputTokens"),
            ("output_tokens", "outputTokens"),
            ("total_tokens", "totalTokens"),
        )
    )
    if not any(value is not None for value in fields):
        return None, None, None, "unavailable", "provider usage object did not expose input, output, or total token fields"
    if all(value is not None for value in fields):
        return (*fields, "reported", "")  # type: ignore[return-value]
    return (*fields, "partial", "provider exposed an incomplete token usage set")  # type: ignore[return-value]


def _blocker_message(result: object) -> str:
    blocker = _first_value(result, ("blocker", "error"))
    if blocker is None:
        return ""
    code = _first_value(blocker, ("code", "kind"))
    message = _first_value(blocker, ("message", "visibleText"))
    parts = [value.strip() for value in (code, message) if isinstance(value, str) and value.strip()]
    return ": ".join(parts)


def _run_receipt(result: object) -> object:
    """Read the host receipt from both JS-shaped and Python SDK-shaped runs."""

    direct = _first_value(result, ("receipt", "run_id", "runId", "id"))
    if direct is not None:
        return direct
    state = _value(result, "state")
    return _first_value(state, ("id", "receipt", "run_id", "runId"))


def _string_values(result: object, keys: tuple[str, ...]) -> tuple[str, ...]:
    raw = _first_value(result, keys)
    if isinstance(raw, str):
        return (raw,) if raw.strip() else ()
    if not isinstance(raw, Sequence) or isinstance(raw, (bytes, bytearray)):
        return ()
    values: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip() and item.strip() not in values:
            values.append(item.strip())
        elif isinstance(item, Mapping):
            value = _first_value(item, ("path", "relative_path", "relativePath", "file", "name"))
            if isinstance(value, str) and value.strip() and value.strip() not in values:
                values.append(value.strip())
    return tuple(values)


class CodexChatGPTControlAdapter:
    """Bridge SWARM's safe relay contract to the optional Python SDK facade."""

    def __init__(
        self,
        *,
        capability_reader: Callable[[], ChatRelayCapability],
        confirm_prompt: Callable[[str], bool],
        runner: object | None = None,
        agent_factory: Callable[..., object] | None = None,
        command: Sequence[str] = DEFAULT_BACKEND_COMMAND,
    ) -> None:
        if not callable(capability_reader) or not callable(confirm_prompt):
            raise TypeError("visible Chat adapter requires capability and confirmation callbacks")
        self._capability_reader = capability_reader
        self.confirm_prompt = confirm_prompt
        self._backend: object | None = None
        if runner is None:
            try:
                from codex_chatgpt_control import Agent, BackendClient, Runner, StdioBackendTransport
            except ImportError as exc:
                raise RuntimeError(
                    "codex-chatgpt-control is optional; install it explicitly before constructing this adapter"
                ) from exc
            self._backend = BackendClient(StdioBackendTransport(command=list(command)))
            self._runner = Runner(self._backend)
            self._agent_factory = Agent
        else:
            if not callable(agent_factory):
                raise TypeError("an injected runner requires an injected agent_factory")
            self._runner = runner
            self._agent_factory = agent_factory

    def capability(self) -> ChatRelayCapability:
        capability = self._capability_reader()
        if not isinstance(capability, ChatRelayCapability):
            raise TypeError("capability_reader must return ChatRelayCapability")
        return capability

    def send_consult(self, prompt: str, *, model: str, effort: str) -> ChatRelayResponse:
        return self._send(
            prompt,
            model=model,
            effort=effort,
            agent_name="swarm-advisory-consult",
            instructions="Return advisory Markdown only. Do not execute, write, upload, or accept work.",
            tools=None,
            require_asset=False,
        )

    def send_image(self, prompt: str, *, model: str, effort: str) -> ChatRelayResponse:
        """Request a provider-owned image and require its asset receipt."""

        return self._send(
            prompt,
            model=model,
            effort=effort,
            agent_name="swarm-provider-image",
            instructions="Create the requested image only. Do not execute commands, write files, upload files, or accept work.",
            tools=[{"tool": "create_image"}],
            require_asset=True,
        )

    def _send(
        self,
        prompt: str,
        *,
        model: str,
        effort: str,
        agent_name: str,
        instructions: str,
        tools: list[dict[str, str]] | None,
        require_asset: bool,
    ) -> ChatRelayResponse:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("visible Chat adapter requires a non-empty prompt")
        agent = self._agent_factory(name=agent_name, instructions=instructions)
        runner = getattr(self._runner, "run_sync", None)
        if not callable(runner):
            raise TypeError("visible Chat adapter runner must expose run_sync")
        started = time.perf_counter()
        # The routing decision already observed and matched the visible model
        # and effort. Re-applying configuration here is a second UI mutation,
        # and current Chat surfaces may reject it even when the selection is
        # already correct. Reuse the verified host state and let a mismatch
        # fall back locally before this method is called.
        request: dict[str, object] = {
            "input": prompt,
            "thread": {"type": "new"},
            "experience": "chat",
            "response": {"format": "markdown"},
        }
        if tools is not None:
            request["tools"] = tools
        result = runner(agent, request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        text = _value(result, "output_text")
        receipt = _run_receipt(result)
        assets = _asset_ids(result)
        blocker_message = _blocker_message(result)
        if require_asset and blocker_message:
            raise ChatRelayTransportError(
                f"provider image generation was unavailable: {blocker_message}",
                blocker=ChatRelayBlocker.PROVIDER_ARTIFACT_UNAVAILABLE,
            )
        if require_asset and not assets:
            raise ChatRelayTransportError(
                "provider image generation returned no asset receipt",
                blocker=ChatRelayBlocker.PROVIDER_ARTIFACT_UNAVAILABLE,
            )
        if not isinstance(text, str) or not text.strip():
            if require_asset and assets:
                text = "Provider image generated; see the asset receipt."
            else:
                blocker = ChatRelayBlocker.PROVIDER_ARTIFACT_UNAVAILABLE if require_asset else ChatRelayBlocker.PROVIDER_RESPONSE_UNAVAILABLE
                detail = f": {blocker_message}" if blocker_message else ""
                raise ChatRelayTransportError(
                    f"visible Chat adapter returned no response{detail}",
                    blocker=blocker,
                )
        if not isinstance(receipt, str) or not receipt.strip():
            raise ValueError("visible Chat adapter returned no host receipt")
        capability = self.capability()
        state = _value(result, "state")
        thread = _first_value(result, ("thread", "conversation")) or _first_value(state, ("thread", "conversation"))
        input_tokens, output_tokens, total_tokens, usage_status, usage_reason = _usage_fields(result)
        provider_latency = _first_value(result, ("latency_ms", "latencyMs"))
        if isinstance(provider_latency, (int, float)) and not isinstance(provider_latency, bool) and provider_latency >= 0:
            latency_ms = provider_latency
            latency_source = "provider_reported"
        else:
            latency_ms = elapsed_ms
            latency_source = "adapter_roundtrip"
        provider_model = _first_value(result, ("model", "model_version", "modelVersion"))
        return ChatRelayResponse(
            text=text,
            host_receipt=receipt,
            observed_model=capability.observed_model,
            observed_effort=capability.observed_effort,
            transport=ChatRelayTransportReceipt(
                client_thread_id=_first_value(result, ("client_thread_id", "clientThreadId")) or "",
                thread_id=_first_value(result, ("thread_id", "threadId")) or _value(thread, "id") or "",
                request_id=_first_value(result, ("request_id", "requestId")) or "",
                response_id=_first_value(result, ("response_id", "responseId")) or _value(result, "id") or "",
                asset_ids=assets,
                model=provider_model if isinstance(provider_model, str) else capability.observed_model,
                latency_ms=latency_ms,
                latency_source=latency_source,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                usage_status=usage_status,
                usage_reason=usage_reason,
            ),
        )

    def close(self) -> None:
        if self._backend is not None:
            close = getattr(self._backend, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> "CodexChatGPTControlAdapter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class CodexChatGPTControlExecutor:
    """Optional capability-driven actor adapter for SWARM's execution route.

    The external SDK and its browser-hosted tools stay outside the SWARM
    plugin. A caller supplies the fresh host capability and, when the provider
    needs custom tool descriptors, a builder for that provider's own schema.
    """

    def __init__(
        self,
        *,
        capability_reader: Callable[[], ChatExecutorCapability],
        runner: object | None = None,
        agent_factory: Callable[..., object] | None = None,
        tool_builder: Callable[[frozenset[str]], list[dict[str, object]]] | None = None,
        command: Sequence[str] = DEFAULT_BACKEND_COMMAND,
    ) -> None:
        if not callable(capability_reader):
            raise TypeError("ChatGPT executor requires a capability callback")
        self._capability_reader = capability_reader
        self._backend: object | None = None
        if runner is None:
            try:
                from codex_chatgpt_control import Agent, BackendClient, Runner, StdioBackendTransport
            except ImportError as exc:
                raise RuntimeError(
                    "codex-chatgpt-control is optional; install it explicitly before constructing this executor"
                ) from exc
            self._backend = BackendClient(StdioBackendTransport(command=list(command)))
            self._runner = Runner(self._backend)
            self._agent_factory = Agent
        else:
            if not callable(agent_factory):
                raise TypeError("an injected runner requires an injected agent_factory")
            self._runner = runner
            self._agent_factory = agent_factory
        self._tool_builder = tool_builder

    def capability(self) -> ChatExecutorCapability:
        capability = self._capability_reader()
        if not isinstance(capability, ChatExecutorCapability):
            raise TypeError("capability_reader must return ChatExecutorCapability")
        return capability

    def execute_task(
        self,
        prompt: str,
        *,
        model: str,
        effort: str,
        write_mode: ChatExecutorWriteMode,
        command_mode: ChatExecutorCommandMode,
    ) -> ChatExecutorResponse:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("ChatGPT executor requires a non-empty prompt")
        capability = self.capability()
        tools = self._tool_builder(capability.tool_capabilities) if self._tool_builder is not None else []
        agent = self._agent_factory(
            name="swarm-capability-driven-worker",
            instructions=(
                "Execute the SWARM task using only the provider-advertised tools. "
                f"Workspace scope: {capability.workspace_scope}. "
                f"Workspace writes: {write_mode.value}. Safe commands: {command_mode.value}. "
                "Return a host receipt and factual changed-path or asset evidence. "
                "SWARM remains the verification and acceptance owner."
            ),
            tools=tools,
        )
        runner = getattr(self._runner, "run_sync", None)
        if not callable(runner):
            raise TypeError("ChatGPT executor runner must expose run_sync")
        request: dict[str, object] = {
            "input": prompt,
            "thread": {"type": "new"},
            "experience": "chat",
            "response": {"format": "markdown"},
        }
        if tools:
            request["tools"] = tools
        result = runner(agent, request)
        text = _value(result, "output_text")
        receipt = _run_receipt(result)
        blocker_message = _blocker_message(result)
        if not isinstance(text, str):
            text = ""
        if not isinstance(receipt, str) or not receipt.strip():
            detail = f": {blocker_message}" if blocker_message else ""
            raise ChatExecutorTransportError(
                f"ChatGPT executor returned no host receipt{detail}",
                blocker=ChatExecutorBlocker.PROVIDER_RESPONSE_UNAVAILABLE,
            )
        if blocker_message:
            raise ChatExecutorTransportError(
                f"ChatGPT executor was blocked: {blocker_message}",
                blocker=ChatExecutorBlocker.PROVIDER_RESPONSE_UNAVAILABLE,
            )
        if not text.strip():
            text = "Provider completed the task; see the host receipt."
        input_tokens, output_tokens, total_tokens, usage_status, usage_reason = _usage_fields(result)
        provider_model = _first_value(result, ("model", "model_version", "modelVersion"))
        latency = _first_value(result, ("latency_ms", "latencyMs"))
        latency_ms = latency if isinstance(latency, (int, float)) and not isinstance(latency, bool) and latency >= 0 else None
        latency_source = "provider_reported" if latency_ms is not None else "unavailable"
        return ChatExecutorResponse(
            text=text,
            host_receipt=receipt,
            observed_model=capability.observed_model,
            observed_effort=capability.observed_effort,
            changed_paths=_string_values(result, ("changed_paths", "changedPaths", "files_changed", "filesChanged")),
            transport=ChatRelayTransportReceipt(
                transport=capability.transport.value,
                client_thread_id=_first_value(result, ("client_thread_id", "clientThreadId")) or "",
                thread_id=_first_value(result, ("thread_id", "threadId")) or "",
                request_id=_first_value(result, ("request_id", "requestId")) or "",
                response_id=_first_value(result, ("response_id", "responseId")) or "",
                asset_ids=_asset_ids(result),
                model=provider_model if isinstance(provider_model, str) else capability.observed_model,
                latency_ms=latency_ms,
                latency_source=latency_source,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                usage_status=usage_status,
                usage_reason=usage_reason,
            ),
        )

    def close(self) -> None:
        if self._backend is not None:
            close = getattr(self._backend, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> "CodexChatGPTControlExecutor":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
