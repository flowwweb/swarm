"""Optional adapter for the visible codex-chatgpt-control backend.

This module never installs the third-party package and never invents host
receipts. Construct it only from an explicitly configured host, then pass its
``confirm_prompt`` callback to ``consult_chat_relay``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import time

from .chat_relay import ChatRelayCapability, ChatRelayResponse, ChatRelayTransportReceipt


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
    raw = _first_value(result, ("asset_ids", "assetIds", "assets"))
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, Mapping):
        raw = (raw,)
    if not isinstance(raw, Sequence):
        return ()
    values: list[str] = []
    for item in raw:
        value = item if isinstance(item, str) else _first_value(item, ("id", "asset_id", "assetId"))
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
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
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("visible Chat adapter requires a non-empty prompt")
        agent = self._agent_factory(
            name="swarm-advisory-consult",
            instructions="Return advisory Markdown only. Do not execute, write, upload, or accept work.",
        )
        runner = getattr(self._runner, "run_sync", None)
        if not callable(runner):
            raise TypeError("visible Chat adapter runner must expose run_sync")
        started = time.perf_counter()
        # The routing decision already observed and matched the visible model
        # and effort. Re-applying configuration here is a second UI mutation,
        # and current Chat surfaces may reject it even when the selection is
        # already correct. Reuse the verified host state and let a mismatch
        # fall back locally before this method is called.
        result = runner(
            agent,
            {
                "input": prompt,
                "thread": {"type": "new"},
                "experience": "chat",
                "response": {"format": "markdown"},
            },
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        text = _value(result, "output_text")
        receipt = _value(result, "receipt") or _value(result, "run_id") or _value(result, "id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("visible Chat adapter returned no advisory text")
        if not isinstance(receipt, str) or not receipt.strip():
            raise ValueError("visible Chat adapter returned no host receipt")
        capability = self.capability()
        thread = _first_value(result, ("thread", "conversation"))
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

    def __enter__(self) -> "CodexChatGPTControlAdapter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
