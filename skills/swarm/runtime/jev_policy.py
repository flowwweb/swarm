"""One decision in, advice and a separate telemetry event out. No execution authority."""

import copy
import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass, fields

from .jev_questions import QUESTIONS

MODEL = "jev-1.13.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
POLICY = "swarm-jev-v1"
TARIFF = "2026-09-19:USD0.042-per-million-input"
RATE = 0.042 / 1_000_000
TIMEOUT = 12.0
MAX_BYTES = 8192
MAX_RESPONSE_BYTES = 16384
# Conservative per-attempt reservation using the documented full context ceiling.
# This is not an account budget ledger; the host owns cumulative reservations.
RESERVATION_USD = 65536 * RATE
EPS = 1e-6
ID = re.compile(r"[a-z0-9_]{1,64}\Z")
LIMITS = dict(objective_summary=400, work_summary=600, milestone_summary=300,
              block_summary=400, claim_summary=300, evidence_summary=600,
              findings_summary=600)
STATE_FIELDS = {
    "work_partition.v1": {"task_kind", "objective_summary", "work_summary"},
    "host_fit.v1": {"task_kind", "objective_summary", "work_summary"},
    "model_profile.v1": {"task_kind", "work_summary", "eligible_profile_ids"},
    "stall.v1": {"objective_summary", "progress_summaries"},
    "ready_relevance.v1": {"milestone_summary", "block_summary"},
    "evidence_relevance.v1": {"claim_summary", "evidence_summary", "proof_layer"},
    "review_class.v1": {"claim_summary", "findings_summary", "proof_layer"},
}
ROUTING = {"work_partition.v1", "host_fit.v1", "model_profile.v1"}
# A conservative lexical barrier, not a universal classifier for secrets or raw prose.
FORBIDDEN = re.compile(
    r"[/\\@`$%={}<>|;\x00-\x1f\x7f]|[A-Za-z]:|\bwww\.|"
    r"\b[\w.-]+\.(?:com|net|org|io|ai|dev|py|js|json|txt|png|jpg|env)\b|"
    r"\b(?:api[ _-]?key|password|credential|secret|bearer|authorization|"
    r"screenshot|base64|powershell|cmd|curl|wget|npm|npx|sudo|bash|"
    r"get-content|invoke-expression|def\s+\w+|import\s+\w+|"
    r"git\s+\w+|python\s+\w+|node\s+\w+|INFO|DEBUG|WARN|ERROR|TRACE)\b|"
    r"\bprint\s*\(|"
    r"(?:sk|ghp|github_pat|ts)[_-][A-Za-z0-9_-]+|[A-Za-z0-9_+-]{32,}", re.I
)
REASONS = frozenset({"redaction_rejected", "size_limit", "invalid_context", "no_ambiguity",
                     "invalid_response", "model_mismatch", "tie", "credential_unavailable",
                     "transport_failure", "invalid_json", "budget_exhausted", "already_reserved",
                     "decision_conflict", "budget_scope_mismatch", "budget_state_invalid"})


class Rejected(ValueError):
    """Only a fixed reason code may escape the boundary."""


def require(condition, reason="invalid_response"):
    if not condition:
        raise Rejected(reason)


def exact(value, keys, reason="invalid_response"):
    require(type(value) is dict and set(value) == set(keys), reason)


def number(value, low=0, high=1):
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def parse_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "invalid_json")
            result[key] = value
        return result

    def invalid_constant(_):
        raise Rejected("invalid_json")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid_constant)


@dataclass(frozen=True)
class Config:
    mode: str = "off"
    model: str = MODEL
    live_budget_usd: float = 0.0
    allow_live: bool = False

    def __post_init__(self):
        require(self.mode in ("off", "shadow", "advisory"), "invalid_config")
        require(self.model == MODEL, "invalid_config")
        require(number(self.live_budget_usd, 0, 1_000_000), "invalid_config")
        require(self.allow_live is False and self.live_budget_usd == 0, "live_unavailable")


@dataclass(frozen=True)
class Context:
    """Trusted host facts. Never derive these from model output or arbitrary text."""

    work_class: str = "unknown"  # routine / atomic / system2 / protected
    privacy: str = "unknown"  # public / synthetic / approved_summary / private
    state_origin: str = "unknown"  # curated_summary / synthetic_fixture; raw input rejected
    local_required: bool = False
    tool_required: bool = False
    cloud_suitable: bool | None = None
    chat_available: bool = False
    worker_available: bool = False
    usage_saver: bool = False
    chat_relay_enabled: bool = False
    model_locked: bool = False
    waiting: bool = False
    prerequisites_verified: bool = False
    allowed_options: tuple = ()

    def __post_init__(self):
        require(self.work_class in ("unknown", "routine", "atomic", "system2", "protected"), "invalid_context")
        require(self.privacy in ("unknown", "public", "synthetic", "approved_summary", "private"), "invalid_context")
        require(self.state_origin in ("unknown", "curated_summary", "synthetic_fixture", "raw"), "invalid_context")
        for field in fields(self):
            if field.name not in ("work_class", "privacy", "state_origin", "cloud_suitable", "allowed_options"):
                require(type(getattr(self, field.name)) is bool, "invalid_context")
        require(self.cloud_suitable is None or type(self.cloud_suitable) is bool, "invalid_context")
        require(type(self.allowed_options) is tuple and len(self.allowed_options) <= 8, "invalid_context")
        require(all(type(x) is str and ID.fullmatch(x) for x in self.allowed_options), "invalid_context")
        require(len(set(self.allowed_options)) == len(self.allowed_options), "invalid_context")


def deterministic(schema_id, context):
    """Return a routing disposition only; never run or change a worker/model."""
    if schema_id == "model_profile.v1" and context.model_locked:
        return "unchanged", "model_locked"
    if context.work_class in ("system2", "protected"):
        return "astra", "authority"
    if context.work_class == "unknown" or context.privacy == "unknown":
        return "unchanged", "missing_context"
    if context.privacy == "private":
        return "codex", "privacy"
    if schema_id in ROUTING:
        if context.local_required or context.tool_required or context.cloud_suitable is False:
            return "codex_worker" if context.worker_available else "codex", "local_constraint"
        if context.cloud_suitable is True:
            if context.usage_saver and context.chat_relay_enabled:
                return ("chatgpt", "usage_saver") if context.chat_available else ("pending", "relay_unavailable")
            if context.work_class == "routine":
                if context.chat_available:
                    return "chatgpt", "routine"
                if context.worker_available:
                    return "codex_worker", "routine"
    if schema_id == "stall.v1" and context.waiting:
        return "unchanged", "legitimate_wait"
    if not context.prerequisites_verified:
        return "unchanged", "missing_context"
    return None


def text_summary(value, limit):
    require(type(value) is str and 0 < len(value) <= limit, "redaction_rejected")
    require(value == value.strip() and not FORBIDDEN.search(value), "redaction_rejected")
    # Reject literal environment values, without logging or returning them.
    require(not any(len(v) >= 4 and v in value for v in os.environ.values()), "redaction_rejected")
    return value


def sanitize(schema_id, state):
    exact(state, STATE_FIELDS[schema_id], "redaction_rejected")
    clean = {}
    for key, value in state.items():
        if key in LIMITS:
            clean[key] = text_summary(value, LIMITS[key])
        elif key == "progress_summaries":
            require(type(value) is list and 2 <= len(value) <= 3, "redaction_rejected")
            clean[key] = [text_summary(x, 200) for x in value]
        elif key == "eligible_profile_ids":
            require(type(value) is list and 2 <= len(value) <= 3, "redaction_rejected")
            require(all(type(x) is str and x in ("routine", "analysis", "astra") for x in value), "redaction_rejected")
            require(len(set(value)) == len(value), "redaction_rejected")
            clean[key] = value[:]
        else:
            choices = ("research", "documentation", "code", "review", "other") if key == "task_kind" else (
                "source", "local", "browser", "provider", "deployed", "human", "unknown")
            require(type(value) is str and value in choices, "redaction_rejected")
            clean[key] = value
    require(len(encode(clean)) <= MAX_BYTES, "size_limit")
    return clean


def build_request(schema_id, state, context, config):
    require(context.state_origin in ("curated_summary", "synthetic_fixture"), "redaction_rejected")
    clean = sanitize(schema_id, state)
    question = copy.deepcopy(QUESTIONS[schema_id])
    if schema_id in ROUTING:
        allowed = context.allowed_options
        require(all(x in question["criteria"] and x != "insufficient" for x in allowed), "invalid_context")
        # Host capabilities are a hard filter, independent of the semantic answer.
        require(not any(x in ("cloud", "mixed", "chatgpt") for x in allowed)
                or context.chat_available, "invalid_context")
        require("jev_only" not in allowed or context.work_class == "atomic", "invalid_context")
        if schema_id == "model_profile.v1":
            require(set(clean["eligible_profile_ids"]) == set(allowed), "invalid_context")
        require(len(allowed) >= 2, "no_ambiguity")
        question["criteria"] = {k: v for k, v in question["criteria"].items()
                                if k in allowed or k == "insufficient"}
    request = {"model": config.model, "state": clean, "questions": {schema_id: question}}
    require(len(encode(request)) <= MAX_BYTES, "size_limit")
    return request


def validate_response(request, response):
    exact(response, ("model", "answers", "usage"))
    require(response["model"] == request["model"], "model_mismatch")
    exact(response["answers"], request["questions"])
    exact(response["usage"], ("input_tokens", "output_tokens"))
    require(all(type(n) is int and 0 <= n <= 65536 for n in response["usage"].values()))
    schema_id, question = next(iter(request["questions"].items()))
    answer = response["answers"][schema_id]
    kind = question["type"]
    expected = {"noul": ("type", "noul"),
                "choice": ("type", "choice", "confidence", "probabilities"),
                "score": ("type", "score", "confidence", "legend", "probabilities")}[kind]
    exact(answer, expected)
    require(answer["type"] == kind)
    if kind == "noul":
        require(number(answer["noul"]))
    else:
        require(number(answer["confidence"]))
        criteria = question["criteria"]
        keys = set(criteria) if kind == "choice" else {str(i) for i in range(len(criteria))}
        probabilities = answer["probabilities"]
        exact(probabilities, keys)
        require(all(number(n) for n in probabilities.values()))
        require(abs(sum(probabilities.values()) - 1) <= EPS)
        if kind == "choice":
            require(type(answer["choice"]) is str and answer["choice"] in keys)
            ordered = sorted(probabilities.values(), reverse=True)
            require(ordered[0] == probabilities[answer["choice"]])
            require(ordered[0] != ordered[1], "tie")
        else:
            exact(answer["legend"], keys)
            require(answer["legend"] == {str(i): text for i, text in enumerate(criteria)})
            require(number(answer["score"], 0, len(criteria) - 1))
            require(abs(answer["score"] - sum(i * probabilities[str(i)]
                                             for i in range(len(criteria)))) <= EPS)
    return copy.deepcopy(answer), copy.deepcopy(response["usage"])


def qualifies(schema_id, answer):
    """Only called after strict validation against the server-owned question."""
    if answer["type"] == "noul":
        return answer["noul"] <= .10 or answer["noul"] >= .90
    if answer["type"] == "score":
        return answer["confidence"] >= (.85 if schema_id == "ready_relevance.v1" else .90)
    floor = .95 if schema_id == "review_class.v1" else .90
    probs = sorted(answer["probabilities"].values(), reverse=True)
    return (answer["choice"] != "insufficient" and answer["confidence"] >= floor
            and probs[0] >= floor and probs[0] - probs[1] >= .20)


def decision_value(schema_id, value):
    if value is None:
        return None
    question = QUESTIONS[schema_id]
    if question["type"] == "choice":
        require(type(value) is str and value in question["criteria"], "invalid_metadata")
    elif question["type"] == "score":
        require(number(value, 0, len(question["criteria"]) - 1), "invalid_metadata")
    else:
        require(type(value) is bool, "invalid_metadata")
    return value


def evaluate(schema_id, state, *, context=None, config=None, transport=None,
             decision_id="decision", input_digest=None, final_decision=None, final_outcome=None):
    """Return (public_result, telemetry_event). Keep the event out of model context in shadow.

    Injected callables are trusted local test doubles; never accept one from tool input.
    No suggestion is applied: public decision always equals caller's final_decision.
    """
    context = context or Context()
    config = config or Config()
    require(type(context) is Context and type(config) is Config, "invalid_config")
    require(type(schema_id) is str and schema_id in QUESTIONS, "invalid_request")
    require(type(decision_id) is str and ID.fullmatch(decision_id), "invalid_metadata")
    decision_value(schema_id, final_decision)
    require(final_outcome in (None, "pending", "pass", "fail", "unknown"), "invalid_metadata")
    require(input_digest is None or (type(input_digest) is str and
            re.fullmatch(r"hmac-sha256:[0-9a-f]{64}", input_digest)), "invalid_metadata")
    started = time.monotonic()
    answer = usage = digest = resolved = None
    attempted = False

    def finish(status, reason, suggestion=None, route="unchanged"):
        latency = round((time.monotonic() - started) * 1000, 3)
        public = {"status": status, "reason": reason, "policy_route": route,
                  "suggestion": copy.deepcopy(suggestion), "decision": final_decision,
                  "decision_id": decision_id}
        value = None if answer is None else answer.get("choice", answer.get("score", answer.get("noul")))
        agreement = None
        if value is not None and final_decision is not None:
            if answer["type"] == "choice":
                agreement = value == final_decision
            elif answer["type"] == "noul" and qualifies(schema_id, answer):
                agreement = (value >= .90) == final_decision
        event = {"event_version": 1, "decision_id": decision_id, "schema_id": schema_id,
                 "policy_version": POLICY, "requested_model": config.model, "resolved_model": resolved,
                 "mode": config.mode, "status": status, "abstention_reason": reason,
                 "input_digest": digest, "suggestion": copy.deepcopy(answer),
                 "confidence": answer.get("confidence") if answer else None,
                 "probabilities": answer.get("probabilities") if answer else None,
                 "noul": answer.get("noul") if answer else None,
                 "latency_ms": latency, "usage": usage,
                 "estimated_cost_usd": usage["input_tokens"] * RATE if usage else None,
                 "tariff": TARIFF, "transport": "injected" if transport else "none",
                 "attempted": attempted, "cost_unknown": attempted and usage is None,
                 "final_decision": final_decision, "final_outcome": final_outcome, "agreement": agreement,
                 "score_distance": abs(value - final_decision) if answer and answer["type"] == "score"
                     and final_decision is not None else None}
        return public, event

    bypass = deterministic(schema_id, context)
    if bypass:
        route, reason = bypass
        return finish("pending" if route == "pending" else "deterministic", reason, route=route)
    if config.mode == "off":
        return finish("disabled", "off")
    try:
        request = build_request(schema_id, state, context, config)
        digest = input_digest or "sha256:" + hashlib.sha256(encode(request["state"])).hexdigest()
        if transport is None:
            return finish("abstain", "transport_unavailable")
        attempted = True
        response = transport(copy.deepcopy(request))
        if time.monotonic() - started > TIMEOUT:
            return finish("abstain", "timeout", route="astra")
        answer, usage = validate_response(request, response)
        resolved = response["model"]
        if config.mode == "shadow":
            return finish("shadow_recorded", "shadow")
        if not qualifies(schema_id, answer):
            return finish("abstain", "low_confidence", route="astra")
        value = answer.get("choice", answer.get("score", answer.get("noul")))
        if final_decision is not None:
            disagrees = (value != final_decision if answer["type"] == "choice" else
                         (value >= .90) != final_decision if answer["type"] == "noul" else
                         abs(value - final_decision) >= .50)
            if disagrees:
                return finish("abstain", "disagreement", route="astra")
        return finish("advisory", "ok", answer)
    except TimeoutError:
        return finish("abstain", "timeout", route="astra")
    except Rejected as exc:
        reason = str(exc) if str(exc) in REASONS else "transport_failure"
        return finish("abstain", reason, route="astra")
    except Exception:
        # Third-party transport exceptions may embed credentials or submitted text.
        return finish("abstain", "transport_failure", route="astra")
