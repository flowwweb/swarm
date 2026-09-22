"""SWARM typed-decision adapter using the configured upstream Jev CLI.

Explicitly registered; not a Codex model or coding agent. Trusted host context
and configuration own eligibility. The CLI transport owns budget admission.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256

from .core import InvariantError
from .execution_adapters import (
    AdapterCapability, AdapterCapabilityMatrix, AdapterCapabilityState,
    AdapterPlanStatus, ExecutionAdapter,
)
from .jev_policy import Config, Context, MODEL, encode, evaluate
from .jev_transport import JevCliTransport


class JevDecisionAdapter(ExecutionAdapter):
    ADAPTER_ID = "jev-decision"

    def __init__(self, *, mode="off", mock_responses=None, transport=None):
        self.config = Config(mode=mode)
        if transport is not None and type(transport) is not JevCliTransport:
            raise InvariantError("Jev requires the configured upstream CLI transport")
        if transport is not None and mock_responses is not None:
            raise InvariantError("Jev transport and fixtures are mutually exclusive")
        self.transport = transport
        if mock_responses is not None and type(mock_responses) is not dict:
            raise InvariantError("Jev mock responses must be a local fixture mapping")
        self._responses = deepcopy(mock_responses)
        matrix = AdapterCapabilityMatrix(
            self.ADAPTER_ID, "typesafe-jev", True,
            (AdapterCapability(
                "decision.evaluate", AdapterCapabilityState.ENFORCED,
                "Closed Jev policy and pinned upstream CLI",
                "Typed advice only; no agent execution or acceptance authority.",
            ),),
        )
        super().__init__(matrix, entrypoint=(), protocol="jev-cli-json-v1", enabled=mode != "off")

    @staticmethod
    def material_digest(schema_id, state, context, final_decision=None):
        """Bind host context and baseline as well as the summarized decision input."""
        if type(context) is not Context:
            raise InvariantError("Jev requires trusted typed host context")
        return sha256(encode({"schema_id": schema_id, "state": state,
                              "context": asdict(context), "baseline": final_decision})).hexdigest()

    def plan(self, request):
        plan = super().plan(request)
        if not plan.ready:
            return plan
        blocker = ""
        if request.model != MODEL:
            blocker = "Jev requires the pinned decision model; host model choices are not replaced"
        elif request.required_capabilities != ("decision.evaluate",):
            blocker = "Jev requires exactly decision.evaluate"
        elif self._responses is None and (self.transport is None or self.transport.availability() != "available"):
            blocker = "Jev CLI transport is unavailable"
        if blocker:
            return replace(plan, status=AdapterPlanStatus.BLOCKED, blocker=blocker)
        return replace(plan, claim_limit="Typed decision only; availability is not provider connectivity proof.")

    def dispatch(self, request, *, schema_id, state, context, final_decision=None):
        """Return advice and a separate analyst event, preserving the baseline."""
        if not self.plan(request).ready:
            raise InvariantError("Jev decision adapter is disabled or unavailable")
        if request.instruction_digest != self.material_digest(schema_id, state, context, final_decision):
            raise InvariantError("Jev decision material does not match the authorized request")
        if self.transport is None and (context.privacy != "synthetic" or context.state_origin != "synthetic_fixture"):
            raise InvariantError("Jev native integration currently accepts synthetic fixtures only")

        def fixture(payload):
            if self.transport is not None:
                return self.transport.evaluate(payload, decision_id=request.request_id, material_digest=request.instruction_digest)
            return deepcopy(self._responses.get(schema_id))

        public, event = evaluate(
            schema_id, state, context=context, config=self.config, transport=fixture,
            decision_id="decision", final_decision=final_decision,
        )
        event["transport"] = "mock" if self.transport is None or self.transport.mock else "upstream_cli"
        event["execution_request_digest"] = request.request_digest
        return public, event

    def route_decision(self, schema_id, state, *, context, decision_id, final_decision=None):
        """Host decision seam: eligible judgment or unchanged baseline on absence/failure."""
        reason = self.transport.availability() if self.transport is not None else "transport_unavailable"
        digest = self.material_digest(schema_id, state, context, final_decision)

        def invoke(payload):
            return self.transport.evaluate(payload, decision_id=decision_id, material_digest=digest)

        public, event = evaluate(schema_id, state, context=context, config=self.config,
            transport=invoke if reason == "available" else None,
            decision_id=decision_id, final_decision=final_decision)
        if public["reason"] == "transport_unavailable":
            public["reason"] = event["abstention_reason"] = reason
        event["transport"] = "mock" if self.transport is not None and self.transport.mock else "upstream_cli"
        if self.transport is not None and self.transport.mock and event["resolved_model"]:
            event["resolved_model"] += "+mock"
        public["selected_provider"] = "jev" if public["status"] == "advisory" else "existing"
        return public, event
