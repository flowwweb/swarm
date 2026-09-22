"""Pinned upstream CLI transport and reservations in SWARM's private state.

Configuration is host-owned, never taken from the decision payload. This module
does not implement MCP framing, reset budgets, discover keys, or retry requests.
"""
import hashlib
import os
from pathlib import Path
import subprocess

from .private_state import LockedPrivateState
from .jev_policy import (MODEL, MAX_RESPONSE_BYTES, TIMEOUT, Rejected, encode,
                         parse_json, require, validate_response)

RATE_NANOUSD = 42
RESERVE_NANOUSD = 65536 * RATE_NANOUSD
TARIFF = "2026-09-19:jev-1.13.0:42-nanousd-input-token"


class JevBudget:
    """One explicit, non-resetting host scope. Unknown requests stay reserved."""
    def __init__(self, root, scope, cap_nanousd):
        require(Path(root).is_absolute() and type(scope) is str and 0 < len(scope) <= 100, "invalid_config")
        require(type(cap_nanousd) is int and 0 <= cap_nanousd <= 10**12, "invalid_config")
        self.store = LockedPrivateState(root, Path(".codex/swarm/jev-budget.json"))
        self.scope, self.cap = scope, cap_nanousd

    def _read(self):
        raw = self.store.read_bytes_unlocked()
        require(len(raw) <= 4 * 1024 * 1024, "budget_state_invalid")
        state = parse_json(raw) if raw else dict(version=1, scope=self.scope, cap_nanousd=self.cap,
                                               tariff=TARIFF, model=MODEL, reservations={})
        require(type(state) is dict and set(state) == {"version", "scope", "cap_nanousd", "tariff", "model", "reservations"}, "budget_state_invalid")
        require(state["version"] == 1 and state["scope"] == self.scope and state["cap_nanousd"] == self.cap
                and state["tariff"] == TARIFF and state["model"] == MODEL, "budget_scope_mismatch")
        rows = state["reservations"]
        require(type(rows) is dict and len(rows) <= 10000, "budget_state_invalid")
        for key, row in rows.items():
            require(type(key) is str and type(row) is dict and set(row) == {"material_digest", "status", "reserved_nanousd", "actual_nanousd", "input_tokens"}, "budget_state_invalid")
            require(type(row["material_digest"]) is str and len(row["material_digest"]) == 64
                    and row["reserved_nanousd"] == RESERVE_NANOUSD, "budget_state_invalid")
            if row["status"] == "reserved":
                require(row["actual_nanousd"] is None and row["input_tokens"] is None, "budget_state_invalid")
            else:
                require(row["status"] == "settled" and type(row["input_tokens"]) is int
                        and 0 <= row["input_tokens"] <= 65536 and type(row["actual_nanousd"]) is int
                        and row["actual_nanousd"] == row["input_tokens"] * RATE_NANOUSD, "budget_state_invalid")
        return state

    def reserve(self, decision_id, digest):
        require(type(decision_id) is str and 0 < len(decision_id) <= 64
                and all(c.isalnum() or c == "_" for c in decision_id), "invalid_request")
        require(type(digest) is str and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "invalid_request")
        with self.store.locked():
            state = self._read()
            rows = state["reservations"]
            if decision_id in rows:
                require(rows[decision_id]["material_digest"] == digest, "decision_conflict")
                raise Rejected("already_reserved")
            used = sum(row["actual_nanousd"] if row["status"] == "settled" else row["reserved_nanousd"] for row in rows.values())
            require(len(rows) < 10000 and used + RESERVE_NANOUSD <= self.cap, "budget_exhausted")
            rows[decision_id] = dict(material_digest=digest, status="reserved", reserved_nanousd=RESERVE_NANOUSD,
                                     actual_nanousd=None, input_tokens=None)
            self.store.replace_bytes_unlocked(encode(state))

    def settle(self, decision_id, digest, input_tokens):
        require(type(input_tokens) is int and 0 <= input_tokens <= 65536, "invalid_response")
        with self.store.locked():
            state = self._read()
            row = state["reservations"].get(decision_id)
            require(row is not None and row["material_digest"] == digest and row["status"] == "reserved", "decision_conflict")
            row.update(status="settled", input_tokens=input_tokens, actual_nanousd=input_tokens * RATE_NANOUSD)
            self.store.replace_bytes_unlocked(encode(state))


class JevCliTransport:
    """Calls the reviewed jev-mcp eval command once, with a hard process timeout."""
    def __init__(self, *, node, entrypoint, bundle_sha256, budget=None, mock=False):
        self.node, self.entrypoint = Path(node), Path(entrypoint)
        self.bundle_sha256, self.budget, self.mock = bundle_sha256, budget, mock
        require(type(mock) is bool and self.node.is_absolute() and self.entrypoint.is_absolute(), "invalid_config")

    def availability(self):
        if not self.node.is_file() or not self.entrypoint.is_file():
            return "transport_unavailable"
        # A reviewed CommonJS bundle has only Node builtins as external imports.
        # .cjs avoids package.json module-type/exports resolution at execution.
        if self.entrypoint.suffix != ".cjs" or hashlib.sha256(self.entrypoint.read_bytes()).hexdigest() != self.bundle_sha256:
            return "bundle_mismatch"
        if not self.mock and not os.environ.get("TYPESAFE_API_KEY", "").strip():
            return "credential_unavailable"
        if not self.mock and (self.budget is None or self.budget.cap < RESERVE_NANOUSD):
            return "budget_unavailable"
        return "available"

    def evaluate(self, request, *, decision_id, material_digest):
        require(self.availability() == "available", "transport_unavailable")
        if not self.mock:
            self.budget.reserve(decision_id, material_digest)
        child_env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        child_env.update(JEV_MCP_MODEL=MODEL, TYPESAFE_BASE_URL="https://api.typesafe.ai",
                         JEV_MCP_TIMEOUT_MS="10000", JEV_MCP_MOCK="1" if self.mock else "0")
        if not self.mock:
            child_env["TYPESAFE_API_KEY"] = os.environ["TYPESAFE_API_KEY"].strip()
        # Upstream output is bounded by closed questions and its response validator.
        # stderr is discarded: provider failures must never echo secrets or input.
        try:
            result = subprocess.run([str(self.node), str(self.entrypoint), "eval", "--stdin"],
                input=encode(request), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=TIMEOUT, env=child_env, cwd=self.entrypoint.parent,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
            require(result.returncode == 0 and len(result.stdout) <= MAX_RESPONSE_BYTES, "transport_failure")
            body = parse_json(result.stdout)
            require(type(body) is dict and set(body) == {"model", "answers", "usage", "truncated", "coverage"}
                    and body["truncated"] is False, "invalid_response")
            response = {k: body[k] for k in ("model", "answers", "usage")}
            _, usage = validate_response({**request, "model": MODEL + "+mock"} if self.mock else request, response)
            if self.mock:
                response["model"] = MODEL  # Synthetic adapter contract; telemetry retains +mock.
            if not self.mock:
                self.budget.settle(decision_id, material_digest, usage["input_tokens"])
            return response
        except subprocess.TimeoutExpired:
            raise TimeoutError("Jev process deadline") from None
