"""Small, local-only ledger for successful ChatGPT relay transport receipts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .chat_relay import ChatRelayResponse


SCHEMA_VERSION = 2
MAX_EVENTS = 100
USAGE_LOG_NAME = "chat-relay-usage.json"
CLAIM_LIMIT = "No savings claim: this ledger records provider usage only and has no equivalent local baseline."


def default_chat_relay_usage_path() -> Path:
    return Path.home() / ".agents" / "swarm" / USAGE_LOG_NAME


@dataclass(frozen=True)
class ChatRelayUsageEvent:
    recorded_at: str
    task_id: str
    purpose: str
    model: str
    effort: str
    host_receipt: str
    transport: str
    client_thread_id: str
    thread_id: str
    request_id: str
    response_id: str
    asset_ids: tuple[str, ...]
    latency_ms: float | None
    latency_source: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    usage_status: str
    usage_reason: str


def _empty_payload() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "events": []}


def _valid_non_negative_int(value: object) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)


def _valid_non_negative_number(value: object) -> bool:
    return value is None or (
        isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
    )


def _safe_events(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        return []
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        return []
    events: list[dict[str, Any]] = []
    required_strings = (
        "recorded_at", "task_id", "purpose", "model", "effort", "host_receipt",
        "transport", "client_thread_id", "thread_id", "request_id", "response_id",
        "latency_source", "usage_status", "usage_reason",
    )
    for raw in raw_events[-MAX_EVENTS:]:
        if not isinstance(raw, dict) or not all(isinstance(raw.get(key), str) for key in required_strings):
            continue
        if raw["usage_status"] not in {"reported", "partial", "unavailable"}:
            continue
        if not all(_valid_non_negative_int(raw.get(key)) for key in ("input_tokens", "output_tokens", "total_tokens")):
            continue
        if not _valid_non_negative_number(raw.get("latency_ms")):
            continue
        asset_ids = raw.get("asset_ids")
        if not isinstance(asset_ids, list) or not all(isinstance(item, str) and item for item in asset_ids):
            continue
        events.append({
            key: raw[key]
            for key in (
                *required_strings,
                "asset_ids", "latency_ms", "input_tokens", "output_tokens", "total_tokens",
            )
        })
    return events


def read_chat_relay_usage(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else default_chat_relay_usage_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8")) if target.exists() else _empty_payload()
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = _empty_payload()
    events = _safe_events(payload)
    task_ids = {event["task_id"] for event in events if event["task_id"]}
    reported_events = [event for event in events if event["usage_status"] == "reported"]
    partial_events = [event for event in events if event["usage_status"] == "partial"]
    return {
        "schema_version": SCHEMA_VERSION,
        "consultations": len(events),
        "routed_tasks": len(task_ids),
        "reported_usage_consultations": len(reported_events),
        "partial_usage_consultations": len(partial_events),
        "unavailable_usage_consultations": len(events) - len(reported_events) - len(partial_events),
        "reported_input_tokens": sum(event["input_tokens"] or 0 for event in events),
        "reported_output_tokens": sum(event["output_tokens"] or 0 for event in events),
        "reported_total_tokens": sum(event["total_tokens"] or 0 for event in events),
        "savings_status": "unavailable",
        "legacy_estimates_discarded": isinstance(payload, dict) and payload.get("schema_version") == 1,
        "events": events[-20:],
        "claim_limit": CLAIM_LIMIT,
    }


class ChatRelayUsageLedger:
    """Best-effort atomic persistence; telemetry must never block a relay."""

    def __init__(self, path: str | Path | None = None, *, max_events: int = MAX_EVENTS) -> None:
        self.path = Path(path) if path is not None else default_chat_relay_usage_path()
        self.max_events = max(1, min(int(max_events), MAX_EVENTS))

    def record(
        self,
        *,
        task_id: str,
        purpose: str,
        response: "ChatRelayResponse",
    ) -> None:
        """Persist only host receipts and provider-reported usage, never text."""

        receipt = response.transport
        event = ChatRelayUsageEvent(
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            task_id=task_id.strip(),
            purpose=purpose,
            model=receipt.model or response.observed_model,
            effort=response.observed_effort,
            host_receipt=response.host_receipt,
            transport=receipt.transport,
            client_thread_id=receipt.client_thread_id,
            thread_id=receipt.thread_id,
            request_id=receipt.request_id,
            response_id=receipt.response_id,
            asset_ids=receipt.asset_ids,
            latency_ms=receipt.latency_ms,
            latency_source=receipt.latency_source,
            input_tokens=receipt.input_tokens,
            output_tokens=receipt.output_tokens,
            total_tokens=receipt.total_tokens,
            usage_status=receipt.usage_status,
            usage_reason=receipt.usage_reason,
        )
        existing = read_chat_relay_usage(self.path)
        events = [*existing["events"], asdict(event)][-self.max_events:]
        payload = {"schema_version": SCHEMA_VERSION, "events": events}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                temporary = handle.name
            Path(temporary).replace(self.path)
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
