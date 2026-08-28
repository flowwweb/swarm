from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from .private_state import LockedPrivateState


class RequestStoreError(ValueError):
    pass


class RequestTransportSnapshot(dict):
    """Read-only path binding that lets compatibility readers project the canonical Ledger."""

    def __init__(self, value: dict, repo_root: Path):
        super().__init__(value)
        self.repo_root = repo_root


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _empty() -> dict:
    return {
        "version": 2,
        "sequence": 0,
        "order": [],
        "inbox": {},
        "acknowledgements": {},
        "stages": {},
    }


class RequestStore:
    """Transport inbox and Ledger acknowledgement journal; never lifecycle authority."""

    def __init__(self, repo_root: Path | str):
        self.repo_root = Path(repo_root).resolve()
        self.state = LockedPrivateState(self.repo_root, Path(".codex") / "swarm" / "requests.json")

    def _snapshot(self, value: dict) -> RequestTransportSnapshot:
        return RequestTransportSnapshot(deepcopy(value), self.repo_root)

    def decode(self, raw: bytes) -> dict:
        try:
            value = json.loads(raw.decode()) if raw else _empty()
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RequestStoreError("request transport state is corrupt") from error
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "sequence", "order", "inbox", "acknowledgements", "stages"}
            or value.get("version") != 2
            or not isinstance(value.get("sequence"), int)
            or value["sequence"] < 0
            or not isinstance(value.get("order"), list)
            or not isinstance(value.get("inbox"), dict)
            or not isinstance(value.get("acknowledgements"), dict)
            or not isinstance(value.get("stages"), dict)
            or len(value["order"]) != len(set(value["order"]))
            or set(value["order"]) != set(value["inbox"])
            or not set(value["acknowledgements"]).issubset(value["inbox"])
        ):
            raise RequestStoreError("request transport envelope is invalid")
        for request_id, acknowledgements in value["acknowledgements"].items():
            if not isinstance(request_id, str) or not isinstance(acknowledgements, list):
                raise RequestStoreError("request acknowledgement journal is invalid")
            event_ids: set[str] = set()
            for acknowledgement in acknowledgements:
                if (
                    not isinstance(acknowledgement, dict)
                    or set(acknowledgement) != {"event_id", "event_digest", "event_seq"}
                    or not isinstance(acknowledgement["event_id"], str)
                    or acknowledgement["event_id"] in event_ids
                    or not isinstance(acknowledgement["event_digest"], str)
                    or len(acknowledgement["event_digest"]) != 64
                    or any(character not in "0123456789abcdef" for character in acknowledgement["event_digest"])
                    or not isinstance(acknowledgement["event_seq"], int)
                    or acknowledgement["event_seq"] < 1
                ):
                    raise RequestStoreError("request acknowledgement journal is invalid")
                event_ids.add(acknowledgement["event_id"])
        return value

    def read(self) -> tuple[dict, str]:
        with self.state.locked():
            value = self.decode(self.state.read_bytes_unlocked())
            return self._snapshot(value), sha256(_canonical(value)).hexdigest()

    def peek(self) -> tuple[dict, str, bool]:
        if not self.state.path.exists():
            value = _empty()
            return self._snapshot(value), sha256(_canonical(value)).hexdigest(), False
        before = self.state.path.stat()
        raw = self.state.path.read_bytes()
        after = self.state.path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RequestStoreError("request transport state changed during read-only inspection")
        value = self.decode(raw)
        return self._snapshot(value), sha256(_canonical(value)).hexdigest(), True

    def _mutate_validated(self, callback, expected: tuple[int, str] | None = None) -> tuple[dict, str, object]:
        with self.state.locked():
            value = self.decode(self.state.read_bytes_unlocked())
            before = _canonical(value)
            digest = sha256(before).hexdigest()
            if expected is not None and expected != (value["sequence"], digest):
                raise RequestStoreError("stale request transport identity")
            candidate = deepcopy(value)
            result = callback(candidate)
            if candidate == value:
                return self._snapshot(value), digest, result
            candidate["sequence"] += 1
            payload = _canonical(self.decode(_canonical(candidate)))
            self.state.replace_bytes_unlocked(payload)
            return self._snapshot(candidate), sha256(payload).hexdigest(), result

    def with_current(self, expected: tuple[int, str] | None, callback):
        with self.state.locked():
            value = self.decode(self.state.read_bytes_unlocked())
            digest = sha256(_canonical(value)).hexdigest()
            if expected is not None and expected != (value["sequence"], digest):
                raise RequestStoreError("stale request transport identity")
            return self._snapshot(value), digest, callback(value)
