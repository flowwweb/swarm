"""Optional adapter for the visible codex-chatgpt-control backend.

This module never installs the third-party package and never invents host
receipts. Construct it only from an explicitly configured host, then pass its
``confirm_prompt`` callback to ``consult_chat_relay``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from .chat_relay import ChatRelayCapability, ChatRelayResponse


DEFAULT_BACKEND_COMMAND = (
    "npx",
    "--yes",
    "--package",
    "codex-chatgpt-control@next",
    "codex-chatgpt-control-backend",
)

_CHAT_MODEL_LABELS = {
    "gpt-5.6-luna": "GPT-5.6 Luna",
    "pro": "Pro",
}
_CHAT_EFFORT_LABELS = {
    "minimal": "Minimal",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "Extra High",
    "max": "Extra High",
    "ultra": "Extra High",
    "pro": "Pro",
}


def _visible_configuration(model: str, effort: str) -> dict[str, str]:
    """Translate SWARM's stable policy names to visible ChatGPT controls."""

    if model not in _CHAT_MODEL_LABELS:
        raise ValueError(f"unsupported ChatGPT relay model: {model}")
    if effort not in _CHAT_EFFORT_LABELS:
        raise ValueError(f"unsupported ChatGPT relay effort: {effort}")
    if model == "pro" or effort == "pro":
        return {"intelligence": "Pro"}
    return {
        "modelVersion": _CHAT_MODEL_LABELS[model],
        "intelligence": _CHAT_EFFORT_LABELS[effort],
    }


def _value(result: object, key: str) -> object:
    if isinstance(result, Mapping):
        return result.get(key)
    return getattr(result, key, None)


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
        result = runner(
            agent,
            {
                "input": prompt,
                "thread": {"type": "new"},
                "experience": "chat",
                "configuration": _visible_configuration(model, effort),
                "response": {"format": "markdown"},
            },
        )
        text = _value(result, "output_text")
        receipt = _value(result, "receipt") or _value(result, "run_id") or _value(result, "id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("visible Chat adapter returned no advisory text")
        if not isinstance(receipt, str) or not receipt.strip():
            raise ValueError("visible Chat adapter returned no host receipt")
        capability = self.capability()
        return ChatRelayResponse(
            text=text,
            host_receipt=receipt,
            observed_model=capability.observed_model,
            observed_effort=capability.observed_effort,
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
