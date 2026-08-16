"""Deterministic SWARM state transitions; host task storage remains external."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import platform
import secrets
import signal
import subprocess
import sys
import time
import weakref
from .incidents import IncidentLedger, IncidentRecord
from .request_ledger import RequestStore, RequestStoreError


class Role(StrEnum):
    CTRL="CTRL"; SPECIALIST="SPECIALIST"; ARCHITECT="ARCHITECT"; LEAD="LEAD"; DOER="DOER"; EXPERT="EXPERT"; REVIEW="REVIEW"

BUILT_IN_SPECIALISTS = frozenset({"MOTHER", "ARCHITECT", "ENGINEER", "DEVELOPER", "DESIGNER", "RESEARCHER", "ANALYST", "STRATEGIST"})
class TaskState(StrEnum):
    REQUEST_PENDING="REQUEST_PENDING"; ACTIVE="ACTIVE"; WAITING="WAITING"; REVIEW="REVIEW"; COMPLETE="COMPLETE"; STALE="STALE"; ARCHIVED="ARCHIVED"; ARCHIVED_STALE="ARCHIVED_STALE"; BACKLOG="BACKLOG"
class ReviewValue(StrEnum): NONE="NONE"; LOW="LOW"; HIGH="HIGH"; PINNED="PINNED"
class WorkerState(StrEnum):
    SPAWNED="SPAWNED"; ACTIVE="ACTIVE"; WARM="WARM"; DRAINING="DRAINING"; RETIRED="RETIRED"
class HiveStatus(StrEnum): ACTIVE="ACTIVE"; ARCHIVED="ARCHIVED"; PURGEABLE="PURGEABLE"; PURGED="PURGED"
class DedupDecision(StrEnum): REUSE="REUSE"; EXECUTE="EXECUTE"
class ArtifactJustification(StrEnum): VERIFICATION="verification"; UNCERTAINTY="uncertainty"
class CorrectionDecision(StrEnum): CONTINUE="CONTINUE"; FIX_FORWARD="FIX_FORWARD"; ESCALATE="ESCALATE"; REOPEN_TOPOLOGY="REOPEN_TOPOLOGY"
class EvidenceDisposition(StrEnum): PENDING="PENDING"; SURFACED="SURFACED"; WITHHELD="WITHHELD"
class WithholdBasis(StrEnum): OBJECTIVE_DEFECT="objective-defect"; DUPLICATE="duplicate"; AUTHORITY="authority"
class CtrlSurfaceKind(StrEnum):
    INLINE_IMAGE="inline_image"; INLINE_RECORDING="inline_recording"; INLINE_COMPARISON="inline_comparison"; INLINE_TABLE="inline_table"; INLINE_EXCERPT="inline_excerpt"; INLINE_RECEIPT="inline_receipt"; EXACT_BLOCKER="exact_blocker"
class CtrlFeedPart(StrEnum):
    OUTCOME="outcome"; PROOF="proof"; RISK="risk"; CHECKPOINT="checkpoint"; ORCHESTRATION="orchestration"; TASK_CHATTER="task_chatter"; ACTIVITY="activity"; MOTHER_DETAIL="mother_detail"
class CtrlFeedEventKind(StrEnum):
    RESULT="result"; DECISION="decision"; BLOCKER="blocker"; ACCEPTANCE="acceptance"; RELEASE="release"; HANDOFF="handoff"
class SubagentException(StrEnum):
    CAPACITY="capacity"; HOST_GATE="host_gate"; COLLISION="collision"; SAFETY="safety"; WHOLE_TASK_COST="whole_task_cost"
class HostTaskCapacity(StrEnum): AVAILABLE="available"; UNAVAILABLE="unavailable"; REJECTED="rejected"; USAGE_LIMITED="usage_limited"
class ExecutionRoute(StrEnum): NORMAL_SUBAGENT="normal_subagent"; NORMAL_TASK="normal_task"; DEGRADED_SUBAGENT="degraded_subagent"; HARD_BLOCKED="hard_blocked"
class DegradedCapacityException(StrEnum): TASK_UNAVAILABLE="task_unavailable"; TASK_REJECTED="task_rejected"; TASK_USAGE_LIMITED="task_usage_limited"
class RoutingEvidenceBasis(StrEnum): OBSERVED="observed"; CONSERVATIVE_ASSUMPTION="conservative_assumption"
class WorkSize(StrEnum): SMALL="small"; MEDIUM="medium"; LARGE="large"
class HandsOffEventKind(StrEnum):
    USER_DIRECTION="user_direction"; MATERIAL_HANDOFF_REVIEW="material_handoff_review"; STOPPING_CONDITION="stopping_condition"; HUMAN_AUTHORITY_BLOCKER="human_authority_blocker"; USAGE_SIGNAL="usage_signal"; MODEL_MESSAGE="model_message"; TASK_MESSAGE="task_message"; ROUTINE_STATUS="routine_status"
class CtrlMode(StrEnum): DIRECT="CTRL_DIRECT"; DELEGATED="CTRL_DELEGATED"
class WatchdogSignal(StrEnum): CLEAR="CLEAR"; ATTENTION="ATTENTION"; BLOCKER="BLOCKER"
class WatchdogEvidenceKind(StrEnum): GENERAL="GENERAL"; USAGE_CAPACITY="USAGE_CAPACITY"
class WatchdogScope(StrEnum):
    TRAJECTORY="TRAJECTORY"; FLOW_INTEGRITY="FLOW_INTEGRITY"; OUTCOME_INTEGRITY="OUTCOME_INTEGRITY"
class WatchdogRouteRole(StrEnum):
    CTRL="CTRL"; LEAD="LEAD"; SPECIALIST="SPECIALIST"; ARCHITECT="ARCHITECT"; REVIEW="REVIEW"; HUMAN="HUMAN"
class ReviewScope(StrEnum): PLAN="PLAN"; SOURCE_SEMANTICS="SOURCE_SEMANTICS"; ACCEPTANCE="ACCEPTANCE"; COMPOSED="COMPOSED"
class ProofOutcome(StrEnum): PASS="PASS"; FAIL="FAIL"; TIMEOUT="TIMEOUT"
class ProofStability(StrEnum): STABLE="STABLE"; UNSTABLE="UNSTABLE"
class ProofState(StrEnum): UNPLANNED="UNPLANNED"; PLAN_REVIEW="PLAN_REVIEW"; READY="READY"; RUNNING="RUNNING"; ESCALATE="ESCALATE"; PROOF_READY="PROOF_READY"; ACCEPTANCE_REVIEW="ACCEPTANCE_REVIEW"; ACCEPTED="ACCEPTED"; BLOCKED="BLOCKED"
class ConsequenceTier(StrEnum): T0="T0"; T1="T1"; T2="T2"; T3="T3"; T4="T4"
class ChangedSurfaceKind(StrEnum): DOCS="DOCS"; RUNTIME="RUNTIME"; CONTRACT="CONTRACT"; CONFIG="CONFIG"; VISUAL="VISUAL"; BROWSER="BROWSER"; AUTH="AUTH"; DATA="DATA"; PROVIDER="PROVIDER"; SECURITY="SECURITY"; PACKAGING="PACKAGING"; RELEASE="RELEASE"
class ProofClass(StrEnum): SOURCE_STATIC="SOURCE_STATIC"; LOCAL_UNIT="LOCAL_UNIT"; LOCAL_INTEGRATION="LOCAL_INTEGRATION"; EMULATOR="EMULATOR"; BROWSER_LOCAL="BROWSER_LOCAL"; BROWSER_AUTHENTICATED="BROWSER_AUTHENTICATED"; PROVIDER="PROVIDER"; DEPLOYED="DEPLOYED"; DEVICE="DEVICE"; HUMAN="HUMAN"; PACKAGE="PACKAGE"
class GateExecutor(StrEnum): COMMAND="COMMAND"; BROWSER="BROWSER"; PROVIDER="PROVIDER"; HUMAN="HUMAN"
class CachePolicy(StrEnum): NEVER="NEVER"; EXACT_INPUTS="EXACT_INPUTS"; EXTERNAL_FRESH="EXTERNAL_FRESH"
class FlakePolicy(StrEnum): NO_RETRY="NO_RETRY"; TYPED_TRANSIENT_ONCE="TYPED_TRANSIENT_ONCE"
class ClaimStatus(StrEnum): REQUIRED="REQUIRED"; VERIFIED="VERIFIED"; UNVERIFIED="UNVERIFIED"
class CtrlOperation(StrEnum): CREATE="CREATE"; FORK="FORK"; PROMOTE="PROMOTE"; REPLACE="REPLACE"; RENAME="RENAME"; SUCCESSOR="SUCCESSOR"; RECOVER_AS_NEW="RECOVER_AS_NEW"
class LaneKind(StrEnum): CODE="CODE"; NON_CODE="NON_CODE"; OTHER="OTHER"
class RequestState(StrEnum): OPEN="OPEN"; BLOCKED="BLOCKED"; COMPLETED="COMPLETED"; SUPERSEDED="SUPERSEDED"; CANCELLED="CANCELLED"
class RequestOutcomeKind(StrEnum): ARTIFACT="ARTIFACT"; NON_ARTIFACT="NON_ARTIFACT"
class RequestStageState(StrEnum): PROVISIONAL="PROVISIONAL"; ACCEPTED="ACCEPTED"; ROLLED_BACK="ROLLED_BACK"

class InvariantError(ValueError): pass

@dataclass(frozen=True)
class RoutingEconomics:
    critical_path_savings_ms:int; task_start_ms:int; worktree_ms:int; coordination_ms:int; handoff_ms:int; integration_ms:int; review_ms:int
    basis:RoutingEvidenceBasis; receipts:tuple[str,...]=(); assumptions:tuple[str,...]=()
    def __post_init__(self):
        values=(self.critical_path_savings_ms,self.task_start_ms,self.worktree_ms,self.coordination_ms,self.handoff_ms,self.integration_ms,self.review_ms)
        if any(not isinstance(value,int) or value<0 for value in values): raise InvariantError("routing economics require nonnegative integer milliseconds")
        if not isinstance(self.basis,RoutingEvidenceBasis): raise InvariantError("routing economics require a typed evidence basis")
        if self.basis is RoutingEvidenceBasis.OBSERVED and not self.receipts: raise InvariantError("observed routing economics require host receipts")
        if self.basis is RoutingEvidenceBasis.CONSERVATIVE_ASSUMPTION and not self.assumptions: raise InvariantError("conservative routing economics require explicit assumptions")
        if any(not isinstance(value,str) or not value.strip() for value in (*self.receipts,*self.assumptions)): raise InvariantError("routing evidence must be nonempty")
    @property
    def task_overhead_ms(self)->int: return self.task_start_ms+self.worktree_ms+self.coordination_ms+self.handoff_ms+self.integration_ms+self.review_ms

@dataclass(frozen=True)
class WorkRoutingFacts:
    size:WorkSize; bounded:bool; low_risk:bool; mutable_surface_count:int; independent_work:bool=False; independent_acceptance:bool=False; separate_handoff:bool=False; useful_durable_boundary:bool=False; interruption_safe_resumption:bool=False; worktree_isolation:bool=False; independent_review:bool=False
    def __post_init__(self):
        if not isinstance(self.size,WorkSize) or not isinstance(self.mutable_surface_count,int) or self.mutable_surface_count<1: raise InvariantError("routing facts require typed size and at least one mutable surface")
    def requires_durable_lane(self)->bool: return self.size is WorkSize.LARGE or any((self.independent_acceptance,self.separate_handoff,self.useful_durable_boundary,self.interruption_safe_resumption,self.worktree_isolation,self.independent_review))

@dataclass(frozen=True)
class HostCapacityEvidence:
    task_status:HostTaskCapacity; subagents_available:bool; receipt:str
    def __post_init__(self):
        if not isinstance(self.task_status,HostTaskCapacity) or not isinstance(self.subagents_available,bool) or not isinstance(self.receipt,str) or not self.receipt.strip(): raise InvariantError("host capacity requires typed availability and an exact receipt")

@dataclass(frozen=True)
class ExecutionRoutingDecision:
    route:ExecutionRoute; accountable_owner:str; authority_chain:tuple[str,...]; reason:str; host_receipt:str; economics:RoutingEconomics
    degraded_exception:DegradedCapacityException|None=None; immutable_checkpoint:str=""; resumption_marker:str=""; unverified_gates:tuple[str,...]=(); pending_route:ExecutionRoute|None=None
    @property
    def subagent_authoritative(self)->bool: return False

def _route_candidate(*, facts:WorkRoutingFacts, economics:RoutingEconomics, capacity:HostCapacityEvidence, accountable_owner:str, lead_owner:str, immutable_checkpoint:str, resumption_marker:str, affected_gates:tuple[str,...]) -> ExecutionRoutingDecision:
    owner=accountable_owner.strip() if isinstance(accountable_owner,str) else ""; lead=lead_owner.strip() if isinstance(lead_owner,str) else ""
    if not owner: raise InvariantError("routing requires an explicit accountable owner")
    required=facts.requires_durable_lane()
    economic_task=facts.independent_work and economics.critical_path_savings_ms>economics.task_overhead_ms
    prefer_task=required or economic_task
    if prefer_task and capacity.task_status is HostTaskCapacity.AVAILABLE:
        if not lead or lead.upper()==Role.CTRL.value: raise InvariantError("delegated task routing requires CTRL -> LEAD -> DOER authority")
        reason="required durable ownership boundary" if required else "parallel savings exceed measured task overhead"
        return ExecutionRoutingDecision(ExecutionRoute.NORMAL_TASK,lead,(Role.CTRL.value,Role.LEAD.value,Role.DOER.value),reason,capacity.receipt,economics)
    if prefer_task and capacity.subagents_available:
        if not all(isinstance(value,str) and value.strip() for value in (immutable_checkpoint,resumption_marker)) or not affected_gates: raise InvariantError("degraded subagent routing requires an immutable checkpoint, resumption marker, and unverified gates")
        exception={HostTaskCapacity.UNAVAILABLE:DegradedCapacityException.TASK_UNAVAILABLE,HostTaskCapacity.REJECTED:DegradedCapacityException.TASK_REJECTED,HostTaskCapacity.USAGE_LIMITED:DegradedCapacityException.TASK_USAGE_LIMITED}.get(capacity.task_status)
        if exception is None: raise InvariantError("degraded subagent routing requires an exact task-capacity failure")
        return ExecutionRoutingDecision(ExecutionRoute.DEGRADED_SUBAGENT,owner,(owner,"SUBAGENT"),"task lane required but host capacity forced bounded non-authoritative help",capacity.receipt,economics,exception,immutable_checkpoint,resumption_marker,affected_gates)
    normal_subagent=facts.size in {WorkSize.SMALL,WorkSize.MEDIUM} and facts.bounded and facts.low_risk and facts.mutable_surface_count==1 and not facts.requires_durable_lane() and economics.critical_path_savings_ms<=economics.task_overhead_ms
    if not prefer_task and normal_subagent and capacity.subagents_available:
        return ExecutionRoutingDecision(ExecutionRoute.NORMAL_SUBAGENT,owner,(owner,"SUBAGENT"),"bounded small-to-medium slice costs less inside the accountable owner",capacity.receipt,economics)
    if capacity.task_status is HostTaskCapacity.AVAILABLE:
        if not lead or lead.upper()==Role.CTRL.value: raise InvariantError("delegated task routing requires CTRL -> LEAD -> DOER authority")
        return ExecutionRoutingDecision(ExecutionRoute.NORMAL_TASK,lead,(Role.CTRL.value,Role.LEAD.value,Role.DOER.value),"task lane is the only viable permitted structure",capacity.receipt,economics)
    return ExecutionRoutingDecision(ExecutionRoute.HARD_BLOCKED,owner,(owner,),"no permitted task or subagent structure can progress",capacity.receipt,economics)

def route_execution(*, facts:WorkRoutingFacts, economics:RoutingEconomics, capacity:HostCapacityEvidence, accountable_owner:str, lead_owner:str="", immutable_checkpoint:str="", resumption_marker:str="", affected_gates:tuple[str,...]=(), current:ExecutionRoutingDecision|None=None, safe_boundary:bool=True) -> ExecutionRoutingDecision:
    candidate=_route_candidate(facts=facts,economics=economics,capacity=capacity,accountable_owner=accountable_owner,lead_owner=lead_owner,immutable_checkpoint=immutable_checkpoint,resumption_marker=resumption_marker,affected_gates=affected_gates)
    if current is not None and candidate.route is not current.route and not safe_boundary:
        return replace(current,reason="topology change deferred until the next safe boundary",pending_route=candidate.route)
    return candidate

def hands_off_interrupt(kind:HandsOffEventKind, *, hard_blocked:bool=False)->bool:
    if not isinstance(kind,HandsOffEventKind): raise InvariantError("hands-off events require a typed kind")
    if kind in {HandsOffEventKind.USER_DIRECTION,HandsOffEventKind.MATERIAL_HANDOFF_REVIEW,HandsOffEventKind.STOPPING_CONDITION,HandsOffEventKind.HUMAN_AUTHORITY_BLOCKER}: return True
    return kind is HandsOffEventKind.USAGE_SIGNAL and hard_blocked

def _safe_token(value:str, *, prefix:str="") -> str:
    if not isinstance(value,str) or not value or prefix and not value.startswith(prefix) or value.startswith(("AKIA","ASIA")) and len(value)==20 or any(c.isspace() or c in "/\\:" or ord(c)<32 or not c.isascii() or not (c.isalnum() or c in "_-") for c in value) or any(token in value.casefold() for token in ("password","secret","api_key","apikey","access_key","token=","bearer")): raise InvariantError("request identity must be a safe ASCII runtime token")
    return value

def _safe_receipt(value:str, prefix:str="") -> str:
    if isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value): return value
    if not isinstance(value,str) or not 12<=len(value)<=52 or prefix and not value.startswith(prefix) or not prefix and not any(value.startswith(kind) for kind in ("usr-","srf-","msg-","evt-","evd-","rev-")): raise InvariantError("request receipt has an invalid typed prefix or length")
    return _safe_token(value)

@dataclass(frozen=True)
class RequestDue:
    event:str; at:int
    def __post_init__(self):
        _safe_token(self.event)
        if not isinstance(self.at,int) or self.at<0: raise InvariantError("request due requires a nonnegative event time")
@dataclass(frozen=True)
class RequestOutcomeIdentity:
    kind:RequestOutcomeKind; digest:str
    def __post_init__(self):
        if not isinstance(self.kind,RequestOutcomeKind) or not isinstance(self.digest,str) or len(self.digest)!=64 or any(c not in "0123456789abcdef" for c in self.digest): raise InvariantError("request outcome requires a typed SHA-256 identity")
@dataclass(frozen=True)
class RequestStage:
    id:str; task_id:str; owner:str; contract_digest:str; state:RequestStageState=RequestStageState.PROVISIONAL; request_id:str=""; history:tuple[tuple[str,str],...]=()
    def __post_init__(self):
        _safe_token(self.id,prefix="stg-"); _safe_token(self.task_id); _safe_token(self.owner); _safe_token(self.request_id,prefix="req-")
        if not isinstance(self.state,RequestStageState) or len(self.contract_digest)!=64 or any(c not in "0123456789abcdef" for c in self.contract_digest): raise InvariantError("request stage requires safe typed identity")
        expected=(("PROVISIONAL",self.contract_digest),) if self.state is RequestStageState.PROVISIONAL else (("PROVISIONAL",self.contract_digest),(self.state.value,self.history[-1][1] if len(self.history)==2 else ""))
        if self.history!=expected or self.state is not RequestStageState.PROVISIONAL and not self.history[-1][1].startswith("evt-"): raise InvariantError("request stage has invalid transition history")
@dataclass(frozen=True)
class RequestEventCursor:
    event_receipt:str; message_id:str; surface_receipt:str; feed_sequence:int
    def __post_init__(self):
        _safe_receipt(self.event_receipt,"evt-"); _safe_receipt(self.message_id,"msg-"); _safe_receipt(self.surface_receipt,"srf-")
        if not isinstance(self.feed_sequence,int) or self.feed_sequence<1: raise InvariantError("request event cursor requires a positive feed sequence")
@dataclass(frozen=True)
class RequestTransition:
    state:RequestState; kind:CtrlFeedEventKind; cursor:RequestEventCursor
_REQUEST_EDGES=frozenset({(RequestState.OPEN,CtrlFeedEventKind.RESULT,RequestState.OPEN),(RequestState.OPEN,CtrlFeedEventKind.HANDOFF,RequestState.OPEN),(RequestState.OPEN,CtrlFeedEventKind.BLOCKER,RequestState.BLOCKED),(RequestState.BLOCKED,CtrlFeedEventKind.BLOCKER,RequestState.BLOCKED),(RequestState.BLOCKED,CtrlFeedEventKind.DECISION,RequestState.OPEN),(RequestState.OPEN,CtrlFeedEventKind.DECISION,RequestState.CANCELLED),(RequestState.BLOCKED,CtrlFeedEventKind.DECISION,RequestState.CANCELLED),(RequestState.OPEN,CtrlFeedEventKind.DECISION,RequestState.SUPERSEDED),(RequestState.BLOCKED,CtrlFeedEventKind.DECISION,RequestState.SUPERSEDED),(RequestState.OPEN,CtrlFeedEventKind.ACCEPTANCE,RequestState.COMPLETED)})
@dataclass(frozen=True)
class RequestRecord:
    id:str; goal_id:str; task_id:str; accepted_owner:str; outcome_identity:RequestOutcomeIdentity; accepting_route:tuple[str,...]; accepted_at:int; next_due_event:str; next_due_at:int; evidence_receipts:tuple[str,...]=field(repr=False); transitions:tuple[RequestTransition,...]=field(repr=False); successor_id:str=""; state:RequestState=field(init=False)
    def __post_init__(self):
        object.__setattr__(self,"state",self.transitions[-1].state if self.transitions else None)
        _safe_token(self.id,prefix="req-"); _safe_token(self.goal_id); _safe_token(self.task_id); _safe_token(self.accepted_owner)
        if not self.accepting_route or any(_safe_token(v) != v for v in self.accepting_route) or not isinstance(self.state,RequestState) or not isinstance(self.accepted_at,int) or self.accepted_at<0: raise InvariantError("request requires a typed state and accepting route")
        RequestDue(self.next_due_event,self.next_due_at)
        for receipt in self.evidence_receipts: _safe_receipt(receipt)
        if not self.transitions or any(not isinstance(item.state,RequestState) or not isinstance(item.kind,CtrlFeedEventKind) or not isinstance(item.cursor,RequestEventCursor) for item in self.transitions) or self.transitions[0].state is not RequestState.OPEN or self.transitions[0].kind is not CtrlFeedEventKind.DECISION or any((left.state,right.kind,right.state) not in _REQUEST_EDGES or left.cursor.feed_sequence>=right.cursor.feed_sequence for left,right in zip(self.transitions,self.transitions[1:])) or len({item.cursor.event_receipt for item in self.transitions})!=len(self.transitions) or (self.state is RequestState.SUPERSEDED) != bool(self.successor_id) or self.successor_id==self.id: raise InvariantError("request record has invalid typed lifecycle history")
        if self.successor_id: _safe_token(self.successor_id,prefix="req-")
@dataclass(frozen=True)
class RequestView:
    sequence:int; digest:str; record:RequestRecord
@dataclass(frozen=True)
class RequestIntegritySignal:
    request_id:str; scope:WatchdogScope=WatchdogScope.FLOW_INTEGRITY; signal:WatchdogSignal=WatchdogSignal.BLOCKER; route:Role=Role.CTRL
    def __post_init__(self):
        if _safe_token(self.request_id,prefix="req-")!=self.request_id or self.scope is not WatchdogScope.FLOW_INTEGRITY or self.signal is not WatchdogSignal.BLOCKER or self.route is not Role.CTRL: raise InvariantError("orphan integrity signal is fixed alert-only CTRL routing")
@dataclass(frozen=True)
class RequestAudit:
    sequence:int; digest:str; records:tuple[RequestRecord,...]; unresolved_ids:tuple[str,...]; orphaned_ids:tuple[str,...]; unsurfaced_ids:tuple[str,...]; idle_ids:tuple[str,...]; blocked_ids:tuple[str,...]; provisional_stage_ids:tuple[str,...]; integrity_signals:tuple[RequestIntegritySignal,...]


def _observable_pairs(values: object, *, label: str) -> tuple[tuple[str,str],...]:
    """Normalize small, inspectable state without inventing repository-specific keys."""
    try: pairs=tuple(values)  # type: ignore[arg-type]
    except TypeError as error: raise InvariantError(f"{label} must be key/value pairs") from error
    if any(not isinstance(item,tuple) or len(item)!=2 or not all(isinstance(value,str) and value.strip() for value in item) for item in pairs):
        raise InvariantError(f"{label} must contain nonempty string key/value pairs")
    keys=tuple(key for key,_ in pairs)
    if len(set(keys))!=len(keys): raise InvariantError(f"{label} keys must be distinct")
    return tuple(sorted(((key.strip(),value.strip()) for key,value in pairs),key=lambda item:item[0]))


def _path_observation(path:Path, root:Path) -> str:
    if path.is_symlink(): return f"link:{sha256(os.readlink(path).encode('utf-8')).hexdigest()}"
    try: path.resolve().relative_to(root)
    except ValueError as error: raise InvariantError("artifact observed path resolves outside its local root") from error
    if not path.exists(): return "missing"
    if path.is_file():
        digest=sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
        return f"file:{digest.hexdigest()}"
    raise InvariantError("artifact observation accepts explicit files, missing paths, or safe symlinks only")

@dataclass(frozen=True)
class CtrlFeedMessage:
    """One user-visible CTRL message, classified before a heartbeat audit."""
    id:str; parts:tuple[tuple[CtrlFeedPart,str],...]; proof_receipts:tuple[str,...]=(); task_id:str=""; surface_receipt:str=""; event_receipt:str=""
    def __post_init__(self):
        if not self.id.strip() or not self.parts or any(not isinstance(kind,CtrlFeedPart) or not text.strip() for kind,text in self.parts): raise InvariantError("CTRL feed messages require an identity and nonempty classified parts")
        if any(not isinstance(receipt,str) or not receipt.strip() for receipt in self.proof_receipts) or len(set(self.proof_receipts))!=len(self.proof_receipts): raise InvariantError("CTRL feed proof receipts must be distinct nonempty strings")

@dataclass(frozen=True)
class CtrlFeedEvent:
    """A new material result, decision, blocker, acceptance, release, or handoff."""
    receipt:str; task_id:str; kind:CtrlFeedEventKind; proof_receipts:tuple[str,...]; request_ids:tuple[str,...]=()
    def __post_init__(self):
        if not self.receipt.strip() or not self.task_id.strip() or not isinstance(self.kind,CtrlFeedEventKind) or not self.proof_receipts: raise InvariantError("CTRL feed event requires identity, task, kind, and proof")
        if any(not item.strip() for item in self.proof_receipts) or len(set(self.proof_receipts))!=len(self.proof_receipts): raise InvariantError("CTRL feed event proof receipts must be distinct nonempty strings")
        if self.request_ids and (tuple(sorted(self.request_ids)) != self.request_ids or len(set(self.request_ids)) != len(self.request_ids)):
            raise InvariantError("CTRL feed event request identities must be sorted and distinct")

@dataclass(frozen=True)
class CtrlFeedAudit:
    violations:tuple[str,...]=()
    @property
    def compliant(self)->bool: return not self.violations

def audit_ctrl_feed(messages:tuple[CtrlFeedMessage,...]) -> CtrlFeedAudit:
    """Enforce feed semantics and proof binding without arbitrary content caps."""
    violations=[]
    expected=(CtrlFeedPart.OUTCOME,CtrlFeedPart.PROOF,CtrlFeedPart.RISK,CtrlFeedPart.CHECKPOINT)
    forbidden={CtrlFeedPart.ORCHESTRATION,CtrlFeedPart.TASK_CHATTER,CtrlFeedPart.ACTIVITY,CtrlFeedPart.MOTHER_DETAIL}
    for message in messages:
        kinds=tuple(kind for kind,_ in message.parts)
        bad=tuple(kind.value for kind in kinds if kind in forbidden)
        if bad: violations.append(f"{message.id}:internal:{','.join(bad)}")
        material=tuple(kind for kind in kinds if kind in expected)
        if material:
            required=(CtrlFeedPart.OUTCOME,CtrlFeedPart.PROOF)
            missing=tuple(kind.value for kind in required if kind not in material)
            if missing: violations.append(f"{message.id}:missing:{','.join(missing)}")
            ordered=tuple(kind for kind in expected if kind in material)
            if material!=ordered or len(material)!=len(set(material)): violations.append(f"{message.id}:hierarchy")
            if not message.proof_receipts: violations.append(f"{message.id}:proof-unbound")
            if not message.event_receipt.strip(): violations.append(f"{message.id}:event-unbound")
        elif not bad:
            violations.append(f"{message.id}:activity-only")
    return CtrlFeedAudit(tuple(dict.fromkeys(violations)))

def ctrl_mode(*, outcomes:int, mutable_surfaces:int, cross_lane_dependency:bool, risk:int, measurable_minutes:int, direct_horizon_minutes:int) -> CtrlMode:
    if min(outcomes,mutable_surfaces,risk,measurable_minutes,direct_horizon_minutes)<0: raise InvariantError("CTRL mode inputs must be nonnegative")
    direct=outcomes==1 and mutable_surfaces==1 and not cross_lane_dependency and risk<=1 and 0<measurable_minutes<=direct_horizon_minutes
    return CtrlMode.DIRECT if direct else CtrlMode.DELEGATED

@dataclass(frozen=True)
class VersionedReference:
    name:str; version:int; kind:str
@dataclass(frozen=True)
class ArtifactIdentity:
    base:str; revision:str; purpose:str; observables:tuple[tuple[str,str],...]=(); observed_paths:tuple[str,...]=()
    def __post_init__(self):
        if not all(isinstance(value,str) and value.strip() for value in (self.base,self.revision,self.purpose)): raise InvariantError("artifact identity fields must be nonempty")
        object.__setattr__(self,"observables",_observable_pairs(self.observables,label="artifact observables"))
        try: paths=tuple(self.observed_paths)
        except TypeError as error: raise InvariantError("artifact observed paths must be a tuple") from error
        if paths:
            normalized=[]
            for raw in paths:
                if not isinstance(raw,str) or not raw.strip(): raise InvariantError("artifact observed paths must be nonempty strings")
                relative=PurePosixPath(raw.replace("\\","/"))
                if relative.is_absolute() or ".." in relative.parts or Path(raw).is_absolute(): raise InvariantError("artifact observed paths must be portable relative paths")
                normalized.append(relative.as_posix())
            if len(set(normalized))!=len(normalized): raise InvariantError("artifact observed paths must be distinct")
            object.__setattr__(self,"observed_paths",tuple(sorted(normalized)))
    def key(self)->str:
        legacy=f"{self.base}@{self.revision}:{self.purpose}"
        if not self.observables and not self.observed_paths: return legacy
        payload={"observables":self.observables,"paths":self.observed_paths}
        encoded=json.dumps(payload,separators=(",",":"),ensure_ascii=True).encode("utf-8").hex()
        return f"{legacy}#obs={encoded}"
    @classmethod
    def capture(cls, base:str, revision:str, purpose:str, *, root:str, paths:tuple[str,...]) -> "ArtifactIdentity":
        probe=cls(base,revision,purpose,(),paths)
        return cls(base,revision,purpose,probe.current_observables(root),probe.observed_paths)
    def current_observables(self, root:str) -> tuple[tuple[str,str],...]:
        if not root or not self.observed_paths: raise InvariantError("artifact identity has no runtime-observable paths")
        local_root=Path(root).resolve()
        try: return tuple((relative,_path_observation(local_root/Path(relative),local_root)) for relative in self.observed_paths)
        except OSError as error: raise InvariantError(f"artifact observation failed: {error}") from error
    def reobserve(self, root:str) -> "ArtifactIdentity":
        return ArtifactIdentity(self.base,self.revision,self.purpose,self.current_observables(root),self.observed_paths)
@dataclass(frozen=True)
class ArtifactProvenance:
    id:str; source:str
    def __post_init__(self):
        if not all(isinstance(value,str) and value.strip() for value in (self.id,self.source)): raise InvariantError("artifact provenance fields must be nonempty")

def _sha256_text(value:str) -> str: return sha256(value.encode("utf-8")).hexdigest()
def _require_digest(value:str, label:str) -> str:
    normalized=value.strip().lower() if isinstance(value,str) else ""
    if len(normalized)!=64 or any(character not in "0123456789abcdef" for character in normalized): raise InvariantError(f"{label} must be a SHA-256 digest")
    return normalized

_HOST_AUTHORITY_PRIME=int("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA051015728E5A8AACAA68FFFFFFFFFFFFFFFF",16)
_HOST_AUTHORITY_GENERATOR=2
def _authority_message(kind:str, values:tuple[object,...]) -> bytes: return json.dumps((kind,values),separators=(",",":"),ensure_ascii=True).encode("utf-8")
def _authority_sign(private_key:int, message:bytes) -> str:
    nonce=secrets.randbelow(_HOST_AUTHORITY_PRIME-2)+1; commitment=pow(_HOST_AUTHORITY_GENERATOR,nonce,_HOST_AUTHORITY_PRIME); challenge=int.from_bytes(sha256(commitment.to_bytes((_HOST_AUTHORITY_PRIME.bit_length()+7)//8,"big")+message).digest(),"big"); response=(nonce+challenge*private_key)%(_HOST_AUTHORITY_PRIME-1); return f"{commitment:x}:{response:x}"
def _authority_verify(public_key:int|None, message:bytes, signature:str) -> bool:
    if not isinstance(public_key,int) or public_key<=1 or public_key>=_HOST_AUTHORITY_PRIME or not isinstance(signature,str): return False
    try: commitment_text,response_text=signature.split(":",1); commitment=int(commitment_text,16); response=int(response_text,16)
    except (ValueError,TypeError): return False
    if not 1<=commitment<_HOST_AUTHORITY_PRIME or not 0<=response<_HOST_AUTHORITY_PRIME-1: return False
    challenge=int.from_bytes(sha256(commitment.to_bytes((_HOST_AUTHORITY_PRIME.bit_length()+7)//8,"big")+message).digest(),"big")
    return pow(_HOST_AUTHORITY_GENERATOR,response,_HOST_AUTHORITY_PRIME)==commitment*pow(public_key,challenge,_HOST_AUTHORITY_PRIME)%_HOST_AUTHORITY_PRIME

def _runtime_environment_fingerprint(environment:dict[str,str]|None=None) -> str:
    environment=dict(os.environ) if environment is None else environment
    facts=(os.name,sys.platform,platform.system(),platform.release(),platform.machine(),platform.python_implementation(),platform.python_version(),str(Path(sys.executable).resolve()),str(Path(sys.prefix).resolve()),tuple(sorted(environment.items())))
    return _sha256_text(json.dumps(facts,separators=(",",":"),ensure_ascii=True))

def _run_bounded_process(command:tuple[str,...], *, cwd:Path, timeout:int, environment:dict[str,str]) -> int:
    """Run one gate in its own process group so timeout cleans up descendants."""
    windows=os.name=="nt"
    process=subprocess.Popen(command,cwd=str(cwd),env=environment,shell=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=not windows,creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0) if windows else 0)
    try:
        process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if windows:
            subprocess.run(("taskkill","/PID",str(process.pid),"/T","/F"),shell=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        else:
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
        if process.poll() is None: process.kill()
        process.communicate()
        raise
    return int(process.returncode)

@dataclass(frozen=True)
class ChangedSurface:
    kind:ChangedSurfaceKind; paths:tuple[str,...]; public:bool=False; consequence:int=0
    def __post_init__(self):
        if not isinstance(self.kind,ChangedSurfaceKind) or not isinstance(self.consequence,int) or not 0<=self.consequence<=4: raise InvariantError("changed surface requires a typed kind and consequence from 0 to 4")
        normalized=tuple(sorted(dict.fromkeys(PurePosixPath(path.replace("\\","/")).as_posix() for path in self.paths if isinstance(path,str) and path.strip())))
        if not normalized or len(normalized)!=len(self.paths) or any(path.startswith("/") or ".." in PurePosixPath(path).parts for path in normalized): raise InvariantError("changed surface paths must be distinct portable relative paths")
        object.__setattr__(self,"paths",normalized)

@dataclass(frozen=True)
class ProofClaim:
    name:str; proof_class:ProofClass
    def __post_init__(self):
        if not isinstance(self.name,str) or not self.name.strip() or not isinstance(self.proof_class,ProofClass): raise InvariantError("proof claim requires a name and typed proof class")
        object.__setattr__(self,"name",self.name.strip())

@dataclass(frozen=True)
class AuthorityBoundary:
    name:str; consequential:bool=False
    def __post_init__(self):
        if not isinstance(self.name,str) or not self.name.strip(): raise InvariantError("authority boundary requires a name")
        object.__setattr__(self,"name",self.name.strip())

@dataclass(frozen=True)
class DependencyReach:
    impacted_tests:tuple[str,...]=(); shared_core:bool=False; toolchain_changed:bool=False; known:bool=False
    def __post_init__(self):
        values=tuple(sorted(dict.fromkeys(value.strip() for value in self.impacted_tests if isinstance(value,str) and value.strip())))
        if len(values)!=len(self.impacted_tests): raise InvariantError("impacted tests must be distinct nonempty names")
        object.__setattr__(self,"impacted_tests",values)

@dataclass(frozen=True)
class IncidentMatch:
    id:str; detector_gate:str
    def __post_init__(self):
        if not all(isinstance(value,str) and value.strip() for value in (self.id,self.detector_gate)): raise InvariantError("incident match requires identity and detector gate")

@dataclass(frozen=True)
class RuntimeSignal:
    kind:str; gate:str=""
    def __post_init__(self):
        if not isinstance(self.kind,str) or not self.kind.strip(): raise InvariantError("runtime signal requires a kind")

@dataclass(frozen=True)
class RepoProofCapabilities:
    fast_contract_gate:str="contracts-fast"; impacted_gate:str="impacted-tests"; broad_gate:str="contracts-full"; browser_gate:str="console-browser"; provider_gate:str="provider-proof"; package_gate:str="package-integrity"; release_gate:str="release-parity"; gate_commands:tuple[tuple[str,tuple[str,...]],...]=(); environment_fingerprint:str=field(default_factory=_runtime_environment_fingerprint)
    def __post_init__(self):
        values=(self.fast_contract_gate,self.impacted_gate,self.broad_gate,self.browser_gate,self.provider_gate,self.package_gate,self.release_gate)
        if any(not isinstance(value,str) or not value.strip() for value in values) or len(set(values))!=len(values): raise InvariantError("repository proof capabilities require distinct gate names")
        commands=dict(self.gate_commands)
        if len(commands)!=len(self.gate_commands) or any(gate not in values or not argv or any(not isinstance(part,str) or not part for part in argv) for gate,argv in self.gate_commands): raise InvariantError("repository proof commands must bind distinct declared gates to exact argv")
        object.__setattr__(self,"gate_commands",tuple(sorted((gate,tuple(argv)) for gate,argv in commands.items()))); object.__setattr__(self,"environment_fingerprint",_require_digest(self.environment_fingerprint,"repository environment"))
    def command_for(self, gate:str) -> tuple[str,...]: return dict(self.gate_commands).get(gate,())

@dataclass(frozen=True)
class GateSpec:
    id:str; proof_class:ProofClass; executor:GateExecutor=GateExecutor.COMMAND; argv:tuple[str,...]=(); working_scope:str=""; input_closure_digest:str=""; environment_fingerprint:str=""; dependencies:tuple[str,...]=(); cache_policy:CachePolicy=CachePolicy.EXACT_INPUTS; freshness_seconds:int|None=None; flake_policy:FlakePolicy=FlakePolicy.NO_RETRY; timeout_seconds:int=120
    def __post_init__(self):
        if not isinstance(self.id,str) or not self.id.strip() or not isinstance(self.proof_class,ProofClass) or not isinstance(self.executor,GateExecutor): raise InvariantError("gate spec requires identity, proof class, and executor")
        if self.input_closure_digest: object.__setattr__(self,"input_closure_digest",_require_digest(self.input_closure_digest,"gate input closure"))
        if self.environment_fingerprint: object.__setattr__(self,"environment_fingerprint",_require_digest(self.environment_fingerprint,"gate environment"))
        if not isinstance(self.timeout_seconds,int) or self.timeout_seconds<1: raise InvariantError("gate timeout must be a positive integer")
        if self.freshness_seconds is not None and (not isinstance(self.freshness_seconds,int) or self.freshness_seconds<1): raise InvariantError("external freshness must be a positive integer")
        if self.cache_policy is CachePolicy.EXTERNAL_FRESH and self.freshness_seconds is None: raise InvariantError("external proof reuse requires bounded freshness")
        if self.executor is GateExecutor.COMMAND and self.argv and (not isinstance(self.argv,tuple) or not self.argv[0] or any(not isinstance(part,str) for part in self.argv)): raise InvariantError("command gate argv must be a tuple of strings")

@dataclass(frozen=True)
class ReviewRequirement:
    scope:ReviewScope; combined_with:tuple[ReviewScope,...]=(); reason:str=""
    def __post_init__(self):
        if not isinstance(self.scope,ReviewScope) or any(not isinstance(item,ReviewScope) for item in self.combined_with) or self.scope in self.combined_with: raise InvariantError("review requirement must use distinct typed scopes")

@dataclass(frozen=True)
class ClaimCoverage:
    claim:ProofClaim; status:ClaimStatus
    def __post_init__(self):
        if not isinstance(self.claim,ProofClaim) or not isinstance(self.status,ClaimStatus): raise InvariantError("claim coverage requires typed claim and status")

@dataclass(frozen=True)
class PlanReason:
    item:str; reason:str; selected:bool=True
    def __post_init__(self):
        if not all(isinstance(value,str) and value.strip() for value in (self.item,self.reason)): raise InvariantError("proof-plan reasons must be nonempty")

@dataclass(frozen=True)
class EarlyStopPolicy:
    stop_on_required_failure:bool=True; stop_when_sufficient:bool=True; optional_confidence_gates:bool=False

@dataclass(frozen=True)
class ProofInputs:
    artifact:ArtifactIdentity; changed_surfaces:tuple[ChangedSurface,...]; declared_claims:tuple[ProofClaim,...]=(); authority_boundaries:tuple[AuthorityBoundary,...]=(); dependency_reach:DependencyReach=field(default_factory=DependencyReach); incident_matches:tuple[IncidentMatch,...]=(); runtime_signals:tuple[RuntimeSignal,...]=(); repo_capabilities:RepoProofCapabilities=field(default_factory=RepoProofCapabilities); policy_version:str="lean-v1"; self_acceptance_risk:bool=True
    def __post_init__(self):
        if not isinstance(self.artifact,ArtifactIdentity) or not self.changed_surfaces or any(not isinstance(item,ChangedSurface) for item in self.changed_surfaces): raise InvariantError("proof inputs require an exact artifact and changed surfaces")
        if any(not isinstance(item,kind) for values,kind in ((self.declared_claims,ProofClaim),(self.authority_boundaries,AuthorityBoundary),(self.incident_matches,IncidentMatch),(self.runtime_signals,RuntimeSignal)) for item in values): raise InvariantError("proof inputs contain an untyped item")
        if not isinstance(self.dependency_reach,DependencyReach) or not isinstance(self.repo_capabilities,RepoProofCapabilities) or not self.policy_version.strip(): raise InvariantError("proof inputs require dependency reach, repository capabilities, and policy version")

@dataclass(frozen=True)
class ProofPlan:
    schema_version:int; planner_version:str; plan_digest:str; tier:ConsequenceTier; artifact:ArtifactIdentity; gates:tuple[GateSpec,...]; reviews:tuple[ReviewRequirement,...]; claim_matrix:tuple[ClaimCoverage,...]; reasons:tuple[PlanReason,...]; early_stop:EarlyStopPolicy=field(default_factory=EarlyStopPolicy); legacy:bool=False
    def __post_init__(self):
        if self.schema_version!=2 or not self.planner_version.strip() or not isinstance(self.tier,ConsequenceTier) or not isinstance(self.artifact,ArtifactIdentity): raise InvariantError("proof plan requires schema v2, planner version, tier, and artifact")
        if len({gate.id for gate in self.gates})!=len(self.gates) or any(not isinstance(gate,GateSpec) for gate in self.gates): raise InvariantError("proof plan gates must be distinct typed specs")
        payload={"schema":self.schema_version,"planner":self.planner_version,"tier":self.tier.value,"artifact":self.artifact.key(),"gates":[(gate.id,gate.proof_class.value,gate.executor.value,gate.argv,gate.working_scope,gate.input_closure_digest,gate.environment_fingerprint,gate.dependencies,gate.cache_policy.value,gate.freshness_seconds,gate.flake_policy.value,gate.timeout_seconds) for gate in self.gates],"reviews":[(item.scope.value,tuple(value.value for value in item.combined_with),item.reason) for item in self.reviews],"claims":[(item.claim.name,item.claim.proof_class.value,item.status.value) for item in self.claim_matrix],"reasons":[(item.item,item.reason,item.selected) for item in self.reasons],"early":(self.early_stop.stop_on_required_failure,self.early_stop.stop_when_sufficient,self.early_stop.optional_confidence_gates),"legacy":self.legacy}
        expected=sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("utf-8")).hexdigest()
        if self.plan_digest and self.plan_digest!=expected: raise InvariantError("proof plan digest does not match its canonical inputs")
        object.__setattr__(self,"plan_digest",expected)

    @classmethod
    def legacy_plan(cls, artifact:ArtifactIdentity, gates:tuple[str,...]) -> "ProofPlan":
        specs=tuple(GateSpec(gate,ProofClass.LOCAL_INTEGRATION,cache_policy=CachePolicy.NEVER) for gate in gates)
        return cls(2,"legacy-v1","",ConsequenceTier.T3,artifact,specs,(ReviewRequirement(ReviewScope.ACCEPTANCE,reason="legacy contracts retain independent acceptance"),),(),tuple(PlanReason(gate,"legacy declared gate",True) for gate in gates),legacy=True)

_TIER_ORDER={ConsequenceTier.T0:0,ConsequenceTier.T1:1,ConsequenceTier.T2:2,ConsequenceTier.T3:3,ConsequenceTier.T4:4}
def _tier_max(left:ConsequenceTier, right:ConsequenceTier) -> ConsequenceTier: return left if _TIER_ORDER[left]>=_TIER_ORDER[right] else right

def plan_proof(inputs:ProofInputs) -> ProofPlan:
    """Compile the minimum sufficient monotonic proof plan; uncertainty only broadens it."""
    if not isinstance(inputs,ProofInputs): raise InvariantError("proof planning requires typed inputs")
    tier=ConsequenceTier.T0; reasons:list[PlanReason]=[]
    surface_floor={ChangedSurfaceKind.DOCS:ConsequenceTier.T0,ChangedSurfaceKind.RUNTIME:ConsequenceTier.T1,ChangedSurfaceKind.CONTRACT:ConsequenceTier.T1,ChangedSurfaceKind.CONFIG:ConsequenceTier.T1,ChangedSurfaceKind.VISUAL:ConsequenceTier.T2,ChangedSurfaceKind.BROWSER:ConsequenceTier.T2,ChangedSurfaceKind.AUTH:ConsequenceTier.T3,ChangedSurfaceKind.DATA:ConsequenceTier.T3,ChangedSurfaceKind.PROVIDER:ConsequenceTier.T3,ChangedSurfaceKind.SECURITY:ConsequenceTier.T3,ChangedSurfaceKind.PACKAGING:ConsequenceTier.T4,ChangedSurfaceKind.RELEASE:ConsequenceTier.T4}
    for surface in inputs.changed_surfaces:
        floor=surface_floor[surface.kind]
        if surface.public and _TIER_ORDER[floor]<_TIER_ORDER[ConsequenceTier.T1]: floor=ConsequenceTier.T1
        floor=_tier_max(floor,ConsequenceTier(f"T{surface.consequence}"))
        tier=_tier_max(tier,floor); reasons.append(PlanReason(surface.kind.value,f"changed surface sets a {floor.value} consequence floor"))
    claim_floor={ProofClass.BROWSER_LOCAL:ConsequenceTier.T2,ProofClass.BROWSER_AUTHENTICATED:ConsequenceTier.T2,ProofClass.PROVIDER:ConsequenceTier.T3,ProofClass.DEPLOYED:ConsequenceTier.T4,ProofClass.DEVICE:ConsequenceTier.T4,ProofClass.HUMAN:ConsequenceTier.T4,ProofClass.PACKAGE:ConsequenceTier.T4}
    for claim in inputs.declared_claims:
        if claim.proof_class in claim_floor:
            floor=claim_floor[claim.proof_class]; tier=_tier_max(tier,floor); reasons.append(PlanReason(claim.name,f"declared {claim.proof_class.value} claim requires {floor.value}"))
    if any(boundary.consequential for boundary in inputs.authority_boundaries):
        tier=_tier_max(tier,ConsequenceTier.T3); reasons.append(PlanReason("authority","consequential authority boundary requires plan and final review"))
    broad=not inputs.dependency_reach.known or inputs.dependency_reach.shared_core or inputs.dependency_reach.toolchain_changed or tier is ConsequenceTier.T4
    if not inputs.dependency_reach.known: reasons.append(PlanReason("dependency-reach","unknown dependency reach broadens proof"))
    if inputs.incident_matches or inputs.runtime_signals:
        broad=True; reasons.append(PlanReason("runtime-escalation","incident or runtime signal requires the nearest broad detector"))
    caps=inputs.repo_capabilities; artifact_digest=_sha256_text(inputs.artifact.key()); path_digest=_sha256_text(json.dumps(tuple(surface.paths for surface in inputs.changed_surfaces),separators=(",",":")))
    gate_ids:list[tuple[str,ProofClass,CachePolicy,int|None]]=[]
    def add(identity:str, proof_class:ProofClass, cache_policy:CachePolicy=CachePolicy.EXACT_INPUTS, freshness:int|None=None) -> None:
        if identity not in {item[0] for item in gate_ids}: gate_ids.append((identity,proof_class,cache_policy,freshness))
    add(caps.fast_contract_gate,ProofClass.SOURCE_STATIC)
    if _TIER_ORDER[tier]>=1:
        add(caps.broad_gate if broad else caps.impacted_gate,ProofClass.LOCAL_INTEGRATION if broad else ProofClass.LOCAL_UNIT)
    browser_required=any(surface.kind in {ChangedSurfaceKind.VISUAL,ChangedSurfaceKind.BROWSER} for surface in inputs.changed_surfaces) or any(claim.proof_class in {ProofClass.BROWSER_LOCAL,ProofClass.BROWSER_AUTHENTICATED} for claim in inputs.declared_claims)
    if browser_required: add(caps.browser_gate,ProofClass.BROWSER_LOCAL,CachePolicy.EXTERNAL_FRESH,86400)
    if _TIER_ORDER[tier]>=3 and (inputs.authority_boundaries or any(claim.proof_class in {ProofClass.PROVIDER,ProofClass.BROWSER_AUTHENTICATED} for claim in inputs.declared_claims)): add(caps.provider_gate,ProofClass.PROVIDER,CachePolicy.EXTERNAL_FRESH,3600)
    if tier is ConsequenceTier.T4:
        add(caps.broad_gate,ProofClass.LOCAL_INTEGRATION); add(caps.package_gate,ProofClass.PACKAGE,CachePolicy.EXACT_INPUTS); add(caps.release_gate,ProofClass.PACKAGE,CachePolicy.NEVER)
    for incident in inputs.incident_matches: add(incident.detector_gate,ProofClass.LOCAL_INTEGRATION)
    for index,claim in enumerate(inputs.declared_claims):
        if claim.proof_class not in {proof_class for _,proof_class,_,_ in gate_ids}: add(f"claim-{index+1}-{claim.proof_class.value.lower()}",claim.proof_class,CachePolicy.EXTERNAL_FRESH if claim.proof_class in {ProofClass.BROWSER_LOCAL,ProofClass.BROWSER_AUTHENTICATED,ProofClass.PROVIDER,ProofClass.DEPLOYED,ProofClass.DEVICE,ProofClass.HUMAN} else CachePolicy.EXACT_INPUTS,3600 if claim.proof_class in {ProofClass.PROVIDER,ProofClass.DEPLOYED,ProofClass.DEVICE,ProofClass.HUMAN} else 86400 if claim.proof_class in {ProofClass.BROWSER_LOCAL,ProofClass.BROWSER_AUTHENTICATED} else None)
    executor_for=lambda proof_class: GateExecutor.BROWSER if proof_class in {ProofClass.BROWSER_LOCAL,ProofClass.BROWSER_AUTHENTICATED} else GateExecutor.PROVIDER if proof_class in {ProofClass.PROVIDER,ProofClass.DEPLOYED,ProofClass.DEVICE} else GateExecutor.HUMAN if proof_class is ProofClass.HUMAN else GateExecutor.COMMAND
    gates=tuple(GateSpec(identity,proof_class,executor=executor_for(proof_class),argv=caps.command_for(identity),input_closure_digest=_sha256_text(f"{artifact_digest}:{path_digest}:{identity}"),environment_fingerprint=caps.environment_fingerprint,cache_policy=policy,freshness_seconds=freshness) for identity,proof_class,policy,freshness in gate_ids)
    if tier is ConsequenceTier.T0:
        reviews=(ReviewRequirement(ReviewScope.ACCEPTANCE,combined_with=(ReviewScope.SOURCE_SEMANTICS,),reason="light independent acceptance prevents caller-asserted self-acceptance"),)
    elif tier in {ConsequenceTier.T1,ConsequenceTier.T2}:
        reviews=(ReviewRequirement(ReviewScope.ACCEPTANCE,combined_with=(ReviewScope.SOURCE_SEMANTICS,),reason="one combined exact-artifact review"),)
    elif tier is ConsequenceTier.T3:
        reviews=(ReviewRequirement(ReviewScope.PLAN,reason="consequential plan gate"),ReviewRequirement(ReviewScope.ACCEPTANCE,combined_with=(ReviewScope.SOURCE_SEMANTICS,),reason="independent final acceptance"))
    else:
        reviews=(ReviewRequirement(ReviewScope.COMPOSED,combined_with=(ReviewScope.SOURCE_SEMANTICS,),reason="one composed release review reuses unchanged accepted lanes"),)
    selected={gate.id for gate in gates}
    reasons.extend(PlanReason(identity,"minimum sufficient gate selected",identity in selected) for identity in (caps.fast_contract_gate,caps.impacted_gate,caps.broad_gate,caps.browser_gate,caps.provider_gate,caps.package_gate,caps.release_gate) if identity not in {reason.item for reason in reasons})
    claims=tuple(ClaimCoverage(claim,ClaimStatus.REQUIRED) for claim in inputs.declared_claims)
    return ProofPlan(2,inputs.policy_version,"",tier,inputs.artifact,gates,reviews,claims,tuple(reasons))

@dataclass(frozen=True)
class AcceptanceContract:
    artifact:ArtifactIdentity|None; required_gates:tuple[str,...]=(); explicitly_empty:bool=False; observation_root:str=field(default="",compare=False,repr=False); proof_plan:ProofPlan|None=None
    def __post_init__(self):
        if self.artifact is None and not self.explicitly_empty: raise InvariantError("acceptance contract requires an exact artifact or explicit empty contract")
        if self.explicitly_empty and (self.artifact is not None or self.required_gates or self.proof_plan is not None): raise InvariantError("empty acceptance contract cannot declare artifact, gates, or proof plan")
        if any(not isinstance(gate,str) or not gate.strip() for gate in self.required_gates) or len(set(self.required_gates))!=len(self.required_gates): raise InvariantError("acceptance gates must be distinct nonempty names")
        if self.proof_plan is not None:
            if not isinstance(self.proof_plan,ProofPlan) or self.proof_plan.artifact!=self.artifact: raise InvariantError("acceptance proof plan must bind the exact contract artifact")
            planned=tuple(gate.id for gate in self.proof_plan.gates)
            if self.required_gates and self.required_gates!=planned: raise InvariantError("acceptance gates must match the proof plan")
            object.__setattr__(self,"required_gates",planned)
        elif self.artifact is not None:
            object.__setattr__(self,"proof_plan",ProofPlan.legacy_plan(self.artifact,self.required_gates))
        if self.observation_root: object.__setattr__(self,"observation_root",str(Path(self.observation_root).resolve()))
    @classmethod
    def empty(cls) -> "AcceptanceContract": return cls(None,(),True)

def _gate_spec_digest(spec:GateSpec) -> str:
    return _sha256_text(json.dumps((spec.id,spec.proof_class.value,spec.executor.value,spec.argv,spec.working_scope,spec.input_closure_digest,spec.environment_fingerprint,spec.dependencies,spec.cache_policy.value,spec.freshness_seconds,spec.flake_policy.value,spec.timeout_seconds),separators=(",",":"),ensure_ascii=True))

@dataclass(frozen=True)
class GateReceipt:
    """Inspectable gate evidence; only Swarm.run_gate makes it authoritative."""
    gate:str; artifact:ArtifactIdentity; outcome:ProofOutcome; command:tuple[str,...]; before:tuple[tuple[str,str],...]; after:tuple[tuple[str,str],...]; returncode:int|None
    plan_digest:str=""; gate_spec_digest:str=""; artifact_digest:str=""; input_closure_digest:str=""; environment_fingerprint:str=""; started_at:int=0; finished_at:int=0; attempts:tuple[ProofOutcome,...]=(); stability:ProofStability=ProofStability.STABLE; proof_class:ProofClass=ProofClass.LOCAL_INTEGRATION; authority_context_digest:str=""; evidence_digest:str=""
    _authority:object|None=field(default=None,init=False,repr=False,compare=False); _bound_task_id:str=field(default="",init=False,repr=False,compare=False)
    def __post_init__(self):
        if not self.gate.strip() or not isinstance(self.artifact,ArtifactIdentity) or not isinstance(self.outcome,ProofOutcome): raise InvariantError("gate receipt requires gate, artifact, and typed outcome")
        object.__setattr__(self,"gate",self.gate.strip())
        try: command=tuple(self.command)
        except TypeError as error: raise InvariantError("gate receipt command must be an argv tuple") from error
        if not command or not isinstance(command[0],str) or not command[0] or any(not isinstance(part,str) for part in command): raise InvariantError("gate receipt command must be argv with a nonempty executable")
        before=_observable_pairs(self.before,label="gate receipt pre-observation"); after=_observable_pairs(self.after,label="gate receipt post-observation")
        if self.returncode is not None and not isinstance(self.returncode,int): raise InvariantError("gate receipt return code must be an integer or absent")
        for value,label in ((self.plan_digest,"gate plan"),(self.gate_spec_digest,"gate spec"),(self.artifact_digest,"gate artifact"),(self.input_closure_digest,"gate input closure"),(self.authority_context_digest,"gate authority context")):
            if value: _require_digest(value,label)
        if self.evidence_digest: object.__setattr__(self,"evidence_digest",_require_digest(self.evidence_digest,"gate evidence"))
        if not isinstance(self.started_at,int) or not isinstance(self.finished_at,int) or min(self.started_at,self.finished_at)<0 or self.finished_at and self.finished_at<self.started_at: raise InvariantError("gate timing must be monotonic nonnegative seconds")
        attempts=self.attempts or (self.outcome,)
        if any(not isinstance(item,ProofOutcome) for item in attempts) or attempts[-1] is not self.outcome or len(attempts)>2: raise InvariantError("gate attempts must preserve one or two typed outcomes ending in the final outcome")
        if not isinstance(self.stability,ProofStability) or not isinstance(self.proof_class,ProofClass): raise InvariantError("gate receipt requires typed stability and proof class")
        object.__setattr__(self,"command",command); object.__setattr__(self,"before",before); object.__setattr__(self,"after",after)
        object.__setattr__(self,"attempts",attempts)
    def current_for(self, authority:object, task_id:str, gate:str, artifact:ArtifactIdentity, current:ArtifactIdentity, plan:ProofPlan, spec:GateSpec, now:int) -> bool:
        fresh=spec.cache_policy is not CachePolicy.EXTERNAL_FRESH or bool(self.finished_at and spec.freshness_seconds is not None and 0<=now-self.finished_at<=spec.freshness_seconds)
        expected_command=spec.argv if spec.argv else ("external-observation",spec.executor.value)
        command_matches=plan.legacy or self.command==expected_command
        external_evidence=plan.legacy or bool(spec.argv) or bool(self.evidence_digest)
        environment_matches=plan.legacy or spec.environment_fingerprint==_runtime_environment_fingerprint()
        return self._authority is authority and self._bound_task_id==task_id and self.gate==gate==spec.id and self.artifact==artifact==current and self.outcome is ProofOutcome.PASS and self.stability is ProofStability.STABLE and self.before==artifact.observables==self.after and self.plan_digest==plan.plan_digest and self.gate_spec_digest==_gate_spec_digest(spec) and self.artifact_digest==_sha256_text(artifact.key()) and self.input_closure_digest==spec.input_closure_digest and self.environment_fingerprint==spec.environment_fingerprint and environment_matches and self.proof_class is spec.proof_class and bool(self.authority_context_digest) and command_matches and external_evidence and fresh
@dataclass(frozen=True)
class WatchdogBinding:
    """Optional alert route for one explicitly owned durable goal."""
    watched_role:Role; watched_owner:str; alert_route:tuple[tuple[WatchdogRouteRole,str],...]; owner_integrity_route:tuple[tuple[WatchdogRouteRole,str],...]
    def __post_init__(self):
        if self.watched_role not in {Role.LEAD,Role.SPECIALIST,Role.ARCHITECT}: raise InvariantError("watchdog may bind only a durable LEAD or persistent specialist goal")
        if not isinstance(self.watched_owner,str) or not self.watched_owner.strip() or not self.alert_route or not self.owner_integrity_route: raise InvariantError("watchdog binding requires an explicit watched owner plus ordinary and owner-integrity routes")
        def normalize(route:tuple[tuple[WatchdogRouteRole,str],...], label:str)->tuple[tuple[WatchdogRouteRole,str],...]:
            normalized=[]
            for item in route:
                if not isinstance(item,tuple) or len(item)!=2 or not isinstance(item[0],WatchdogRouteRole) or not isinstance(item[1],str) or not item[1].strip(): raise InvariantError(f"watchdog {label} route requires typed role and identity hops")
                normalized.append((item[0],item[1].strip()))
            identities=[identity.casefold() for _,identity in normalized]
            if len(set((role.value,identity.casefold()) for role,identity in normalized))!=len(normalized) or len(set(identities))!=len(identities): raise InvariantError(f"watchdog {label} route must be acyclic")
            return tuple(normalized)
        ordinary=normalize(self.alert_route,"ordinary alert"); integrity=normalize(self.owner_integrity_route,"owner-integrity")
        watched=self.watched_owner.strip().casefold()
        expected_role=WatchdogRouteRole(self.watched_role.value)
        if ordinary[0]!=(expected_role,self.watched_owner.strip()): raise InvariantError("ordinary watchdog alerts must first be heard by the watched owner in its bound role")
        if watched in {identity.casefold() for _,identity in integrity}: raise InvariantError("watchdog owner-integrity route must skip the watched owner")
        object.__setattr__(self,"watched_owner",self.watched_owner.strip()); object.__setattr__(self,"alert_route",ordinary); object.__setattr__(self,"owner_integrity_route",integrity)

@dataclass(frozen=True)
class WatchdogEvidence:
    task_id:str; goal_id:str; watched_owner:str; scope:WatchdogScope; signal:WatchdogSignal; evidence_digest:str; evidence:str; owner_integrity:bool=False; kind:WatchdogEvidenceKind=WatchdogEvidenceKind.GENERAL; declared_watched_role:Role|None=None
    def __post_init__(self):
        if not all(isinstance(value,str) and value.strip() for value in (self.task_id,self.goal_id,self.watched_owner,self.evidence_digest,self.evidence)): raise InvariantError("watchdog evidence requires exact task, goal, owner, evidence, and digest")
        if not isinstance(self.scope,WatchdogScope) or not isinstance(self.signal,WatchdogSignal): raise InvariantError("watchdog evidence requires one declared scope and CLEAR, ATTENTION, or BLOCKER")
        if not isinstance(self.kind,WatchdogEvidenceKind): raise InvariantError("watchdog evidence requires a typed evidence kind")
        if self.kind is WatchdogEvidenceKind.USAGE_CAPACITY and self.declared_watched_role is not Role.LEAD: raise InvariantError("usage capacity evidence may declare only an accountable LEAD")
        if self.kind is WatchdogEvidenceKind.GENERAL and self.declared_watched_role is not None: raise InvariantError("general watchdog evidence cannot declare a usage watcher role")
        if not isinstance(self.owner_integrity,bool) or (self.owner_integrity and self.scope is not WatchdogScope.OUTCOME_INTEGRITY): raise InvariantError("owner-integrity routing is valid only for outcome integrity evidence")
        digest=self.evidence_digest.strip().lower()
        if len(digest)!=64 or any(character not in "0123456789abcdef" for character in digest): raise InvariantError("watchdog evidence digest must be a SHA-256 hex digest")
        if digest!=sha256(self.evidence.encode("utf-8")).hexdigest(): raise InvariantError("watchdog evidence digest must match the evidence UTF-8 bytes")
        object.__setattr__(self,"evidence_digest",digest)

@dataclass(frozen=True)
class UsageCapacitySnapshot:
    remaining_percent:int; task_status:HostTaskCapacity; decision_owner:str; receipt:str; observed_at:int
    def __post_init__(self):
        if not isinstance(self.remaining_percent,int) or not 0<=self.remaining_percent<=100 or not isinstance(self.task_status,HostTaskCapacity) or not isinstance(self.observed_at,int) or self.observed_at<0 or not all(isinstance(value,str) and value.strip() for value in (self.decision_owner,self.receipt)): raise InvariantError("usage snapshot requires bounded host receipt, percent, capacity, owner, and time")

def usage_watchdog_evidence(*, task_id:str, goal_id:str, watched_role:Role, watched_owner:str, current:UsageCapacitySnapshot, previous:UsageCapacitySnapshot|None=None, viable_routes:int=1, thresholds:tuple[int,...]=(5,2,1)) -> WatchdogEvidence:
    if watched_role is not Role.LEAD: raise InvariantError("usage capacity evidence may bind only to an accountable LEAD")
    if not isinstance(viable_routes,int) or viable_routes<0 or any(not isinstance(value,int) or not 0<=value<=100 for value in thresholds): raise InvariantError("usage watchdog requires viable-route count and bounded thresholds")
    crossed=previous is not None and any(previous.remaining_percent>value>=current.remaining_percent for value in thresholds)
    changed=previous is not None and (previous.task_status is not current.task_status or previous.decision_owner!=current.decision_owner)
    signal=WatchdogSignal.BLOCKER if viable_routes==0 else WatchdogSignal.ATTENTION if crossed or changed else WatchdogSignal.CLEAR
    payload={"receipt":current.receipt,"remaining_percent":current.remaining_percent,"task_status":current.task_status.value,"decision_owner":current.decision_owner,"signal":signal.value}
    evidence=json.dumps(payload,sort_keys=True,separators=(",",":"))
    return WatchdogEvidence(task_id,goal_id,watched_owner,WatchdogScope.FLOW_INTEGRITY,signal,sha256(evidence.encode("utf-8")).hexdigest(),evidence,kind=WatchdogEvidenceKind.USAGE_CAPACITY,declared_watched_role=watched_role)

@dataclass(frozen=True)
class WatchdogReceipt:
    task_id:str; goal_id:str; watched_owner:str; scope:WatchdogScope; signal:WatchdogSignal; evidence_digest:str; evidence:str; decision_owner:str; alert_route:tuple[tuple[WatchdogRouteRole,str],...]; observed_at:int; _authority:object|None=field(default=None,init=False,repr=False,compare=False)
@dataclass(frozen=True)
class WatchdogChangeReview: task_id:str; watched_owner:str; evidence_digests:tuple[str,...]; cause:str; uncertainty:str; counterfactual:str; smallest_response:str; reversal_condition:str; urgent_safety:bool=False; expected_benefit:int=0; total_change_cost:int=0; _owner_authority:object|None=field(default=None,init=False,repr=False,compare=False); _decision:tuple[str,str]|None=field(default=None,init=False,repr=False,compare=False)

@dataclass
class CtrlEvidence:
    id:str; task_id:str; kind:str; locator:str; material:bool=True; steering:bool=True
    disposition:EvidenceDisposition=EvidenceDisposition.PENDING; caption:str=""; claim_limit:str=""; reason:str=""; withhold_basis:WithholdBasis|None=None; receipt:str=""; surface_kind:CtrlSurfaceKind|None=None
    def __post_init__(self):
        if not all(isinstance(value,str) and value.strip() for value in (self.id,self.task_id,self.kind,self.locator)): raise InvariantError("CTRL evidence identity, task, kind, and locator are required")
@dataclass
class CtrlDecisionSet:
    id:str; task_id:str; candidate_ids:tuple[str,...]; user_requested_all:bool=False
    receipt:str=""; embedded_ids:tuple[str,...]=(); complete_inventory:tuple[str,...]=(); labels_defects:dict[str,str]=field(default_factory=dict); omissions:dict[str,str]=field(default_factory=dict)
    def __post_init__(self):
        if not self.id.strip() or not self.task_id.strip() or len(self.candidate_ids)<2 or len(set(self.candidate_ids))!=len(self.candidate_ids): raise InvariantError("CTRL decision set requires an identity, task, and distinct candidate set")
    @property
    def surfaced(self)->bool: return bool(self.receipt)
@dataclass(frozen=True)
class TopologyFacts:
    objective:str; artifacts:tuple[ArtifactIdentity,...]; mutable_surfaces:tuple[str,...]; accepting_route:str; ownership_lanes:tuple[str,...]
    dependency_edges:tuple[tuple[str,str],...]=(); cross_lane_integration:bool=False; portfolio_acceptance:bool=False; architecture_gate:bool=False
    def __post_init__(self):
        if not self.objective.strip() or not self.accepting_route.strip() or not self.artifacts or not self.mutable_surfaces or not self.ownership_lanes: raise InvariantError("topology facts require objective, artifact, mutable surface, accepting route, and owner")
        lanes=set(self.ownership_lanes)
        if any(left not in lanes or right not in lanes or left==right for left,right in self.dependency_edges): raise InvariantError("dependency edges require distinct declared owners")
    def same_ownership_route(self, other:"TopologyFacts") -> bool:
        return (self.objective,frozenset(item.key() for item in self.artifacts),frozenset(self.mutable_surfaces),self.accepting_route)==(other.objective,frozenset(item.key() for item in other.artifacts),frozenset(other.mutable_surfaces),other.accepting_route)
    def requires_coordination(self) -> bool:
        return len(set(self.ownership_lanes))>1 and bool(self.dependency_edges) and self.cross_lane_integration and self.portfolio_acceptance
@dataclass(frozen=True)
class WorkflowNode:
    id:str; kind:str; state:str=""; owner:str=""; acceptance:str="UNVERIFIED"
@dataclass(frozen=True)
class WorkflowEdge:
    source:str; target:str; kind:str
@dataclass(frozen=True)
class WorkflowGraph:
    nodes:tuple[WorkflowNode,...]; edges:tuple[WorkflowEdge,...]; diagnostics:tuple[str,...]=()
    def canonical_bytes(self)->bytes: return json.dumps({"nodes":[{"id":n.id,"kind":n.kind,"state":n.state,"owner":n.owner,"acceptance":n.acceptance} for n in sorted(self.nodes,key=lambda x:x.id)],"edges":[{"source":e.source,"target":e.target,"kind":e.kind} for e in sorted(self.edges,key=lambda x:(x.source,x.target,x.kind))],"diagnostics":sorted(self.diagnostics)},sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("utf-8")
    def digest(self)->str: return sha256(self.canonical_bytes()).hexdigest()
class ReviewStrategy(StrEnum): LIGHT="light"; STANDARD="standard"; ADVERSARIAL="adversarial"; SPECIALIST="specialist"
@dataclass(frozen=True)
class ReviewEvidence:
    strategy:ReviewStrategy; reviewer:str; independent:bool; artifact:ArtifactIdentity|None; findings:tuple[str,...]=(); receipt:tuple[tuple[str,str],...]=(); scope:ReviewScope=ReviewScope.SOURCE_SEMANTICS; plan_digest:str=""
    def __post_init__(self):
        if self.plan_digest: object.__setattr__(self,"plan_digest",_require_digest(self.plan_digest,"review proof plan"))
@dataclass
class HiveRecord:
    id:str; content:str=""; reference:str=""; source:str=""; source_version:str=""; applicability:dict[str,int]=field(default_factory=dict); created_at:int=0; last_used_at:int|None=None; value:str="useful"; retention:str="adaptive"; status:HiveStatus=HiveStatus.ACTIVE; provenance:dict[str,str]=field(default_factory=dict)

@dataclass(frozen=True)
class ContextPackage:
    goal:str; architecture:dict[str,int]; dependencies:tuple[str,...]; artifacts:tuple[str,...]; acceptance:tuple[str,...]; history:tuple[str,...]; transfer_cost:int; hive:tuple[str,...]=()
    @classmethod
    def build(cls, *, goal:str, architecture:dict[str,int], dependencies:list[VersionedReference|str], artifacts:list[VersionedReference|str], acceptance:list[str], history:list[VersionedReference|str], budget:int, hive:list[HiveRecord]|None=None) -> "ContextPackage":
        if budget < 1: raise InvariantError("context budget must be positive")
        current=lambda item: not isinstance(item,VersionedReference) or architecture.get(item.name,item.version)==item.version
        dependencies=[item for item in dependencies if current(item)]; artifacts=[item for item in artifacts if current(item)]; history=[item for item in history if current(item)]
        render=lambda item: f"{item.name}:v{item.version}" if isinstance(item,VersionedReference) else item
        dependencies=[render(item) for item in dependencies]; artifacts=[render(item) for item in artifacts]; history=[render(item) for item in history]
        hive=[record.id for record in (hive or []) if record.status==HiveStatus.ACTIVE and all(architecture.get(k,v)==v for k,v in record.applicability.items())]
        spine=[goal,*acceptance]; optional=[*dependencies,*artifacts,*hive,*history]
        if len(spine)>budget: raise InvariantError("budget cannot admit canonical spine")
        kept=optional[:max(0,budget-len(spine))]
        return cls(goal,architecture,tuple(x for x in dependencies if x in kept),tuple(x for x in artifacts if x in kept),tuple(acceptance),tuple(x for x in history if x in kept),len(spine)+len(architecture)+len(kept),tuple(x for x in hive if x in kept))

class Depth(StrEnum):
    ATOMIC="CTRL_DOER"; WORKSTREAM="CTRL_LEAD_DOER"; PROJECT="CTRL_SPECIALIST_LEADS_DOERS"
class EfficiencyMode(StrEnum): CONSERVE="CONSERVE"; BALANCED="BALANCED"; FAST="FAST"; MAX="MAX"
MODE_POLICY={EfficiencyMode.CONSERVE:{"parallel":1,"depth_bias":1,"review_floor":ReviewStrategy.LIGHT},EfficiencyMode.BALANCED:{"parallel":2,"depth_bias":2,"review_floor":ReviewStrategy.LIGHT},EfficiencyMode.FAST:{"parallel":3,"depth_bias":3,"review_floor":ReviewStrategy.STANDARD},EfficiencyMode.MAX:{"parallel":4,"depth_bias":4,"review_floor":ReviewStrategy.STANDARD}}

def initial_tier(*, risk:int, uncertainty:int, blast_radius:int, family:str="general", mode:EfficiencyMode=EfficiencyMode.BALANCED) -> int:
    weight=risk+uncertainty+blast_radius+({"security":2,"architecture":1}.get(family,0))
    bias={EfficiencyMode.CONSERVE:0,EfficiencyMode.BALANCED:1,EfficiencyMode.FAST:2,EfficiencyMode.MAX:3}[mode]
    return min(3, max(1, 1 + int(weight>=3) + int(weight+bias>=6)))

def choose_depth(facts:TopologyFacts) -> Depth:
    """Materialize coordination depth without delegating CTRL authority."""
    if not facts.requires_coordination(): return Depth.ATOMIC
    return Depth.PROJECT if facts.architecture_gate else Depth.WORKSTREAM

def correction_decision(*, material:bool, authority_failure:bool=False, ownership_failure:bool=False, acceptance_failure:bool=False, expected_future_cost:int=0, correction_cost:int=0, fix_forward_consumed:bool=False) -> CorrectionDecision:
    """Pay coordination cost only when it lowers expected future cost, delay, or risk."""
    if material and any((authority_failure,ownership_failure,acceptance_failure)): return CorrectionDecision.REOPEN_TOPOLOGY
    if min(expected_future_cost,correction_cost)<0: raise InvariantError("correction costs must be nonnegative")
    if expected_future_cost<=correction_cost: return CorrectionDecision.CONTINUE
    if fix_forward_consumed: return CorrectionDecision.ESCALATE if material else CorrectionDecision.CONTINUE
    return CorrectionDecision.FIX_FORWARD

@dataclass
class Task:
    id: str; owner: str; creator: str; architecture_version: int; contracts: dict[str,int]
    state: TaskState=TaskState.ACTIVE; waiting_on: str|None=None; reviewer: str|None=None; findings: list[str]=field(default_factory=list)
    evidence: list[str]=field(default_factory=list); recovery_dimensions: set[str]=field(default_factory=set); recovery_attempts:int=0; review_value: ReviewValue=ReviewValue.NONE
    completed_at: int|None=None; stale_at: int|None=None; archived_at: int|None=None; stale_reason: str|None=None; superseded_by: str|None=None; promoted: list[str]=field(default_factory=list); extensions: int=0; review_passed: bool=False; risk:int=1; review_strategy:str="light"; architecture_review_floor:ReviewStrategy=ReviewStrategy.LIGHT; security_review_floor:ReviewStrategy=ReviewStrategy.LIGHT; artifacts:dict[ArtifactIdentity|str,str]=field(default_factory=dict); artifact_justifications:dict[str,ArtifactJustification]=field(default_factory=dict); artifact_provenance:dict[str,ArtifactProvenance]=field(default_factory=dict); archive:dict[str,object]=field(default_factory=dict); active_goal:bool=False; handoff_active:bool=False; correction_pending:bool=False; user_choice_pending:bool=False; ambiguous:bool=False; topology_receipt:tuple[str,...]=(); ctrl_event_receipt:tuple[str,str]|None=None; subagent_receipt:str=""; subagent_exception:SubagentException|None=None; subagent_exception_reason:str=""; goal_id:str=""; objective_version:int=1; milestone:str=""; review_horizon_minutes:int=30; milestone_started_at:int=0; milestone_history:list[tuple[int,str,str]]=field(default_factory=list); ctrl_feed_drift_count:int=0; superseded_ctrl_feed_ids:list[str]=field(default_factory=list); last_ctrl_feed_correction_id:str=""

    ctrl_mode:CtrlMode=CtrlMode.DELEGATED; milestone_proof_kind:str=""; architecture_goal_id:str=""; architecture_map_version:int=0; architecture_receipts:list[tuple[int,str,str]]=field(default_factory=list); specialist_professions:dict[str,str]=field(default_factory=dict); specialist_goal_ids:dict[str,str]=field(default_factory=dict); specialist_map_versions:dict[str,int]=field(default_factory=dict); specialist_receipts:dict[str,list[tuple[int,str,str]]]=field(default_factory=dict)
    lane_kind:LaneKind=LaneKind.OTHER; owning_lead_id:str=""; acceptance_contract:AcceptanceContract|None=None; gate_receipts:dict[str,GateReceipt]=field(default_factory=dict); unverified_gate_receipts:dict[str,GateReceipt]=field(default_factory=dict); plan_review_receipt:ReviewEvidence|None=None; acceptance_review_receipt:ReviewEvidence|None=None; incident_consultation_receipt:str=""; watchdog_binding:WatchdogBinding|None=None; watchdog_receipts:list[WatchdogReceipt]=field(default_factory=list)

@dataclass(frozen=True)
class HostUserEvent:
    receipt:str; operation:CtrlOperation; source_ctrl_id:str; target_objective_digest:str; target_scope_digest:str; target_identity:str; issued_at:int; event_digest:str
    _signature:str=field(default="",init=False,repr=False,compare=False)
    def __post_init__(self):
        _safe_receipt(self.receipt,"usr-"); _safe_token(self.source_ctrl_id); _safe_token(self.target_identity)
        object.__setattr__(self,"target_objective_digest",_require_digest(self.target_objective_digest,"CTRL target objective")); object.__setattr__(self,"target_scope_digest",_require_digest(self.target_scope_digest,"CTRL target scope")); object.__setattr__(self,"event_digest",_require_digest(self.event_digest,"host user event"))
        if not isinstance(self.operation,CtrlOperation) or not isinstance(self.issued_at,int) or self.issued_at<0: raise InvariantError("host user event requires a typed operation and nonnegative issuance time")

@dataclass(frozen=True)
class UserCtrlAuthorization:
    receipt:str; operation:CtrlOperation; source_ctrl_id:str; target_objective_digest:str; target_scope_digest:str; target_identity:str; issued_at:int; host_event_digest:str
    _authority:object|None=field(default=None,init=False,repr=False,compare=False)
    def __post_init__(self):
        _safe_receipt(self.receipt,"usr-"); _safe_token(self.source_ctrl_id); _safe_token(self.target_identity)
        object.__setattr__(self,"target_objective_digest",_require_digest(self.target_objective_digest,"CTRL target objective")); object.__setattr__(self,"target_scope_digest",_require_digest(self.target_scope_digest,"CTRL target scope")); object.__setattr__(self,"host_event_digest",_require_digest(self.host_event_digest,"CTRL host event"))
        if not isinstance(self.operation,CtrlOperation) or not isinstance(self.issued_at,int) or self.issued_at<0: raise InvariantError("CTRL authorization requires a typed operation and nonnegative issuance time")

@dataclass(frozen=True)
class CtrlMaterializationIntent:
    authorization_receipt:str; operation:CtrlOperation; source_ctrl_id:str; target_objective_digest:str; target_scope_digest:str; target_identity:str; intent_digest:str
    _authority:object|None=field(default=None,init=False,repr=False,compare=False)
    def __post_init__(self):
        _safe_receipt(self.authorization_receipt,"usr-"); _safe_token(self.source_ctrl_id); _safe_token(self.target_identity); _require_digest(self.target_objective_digest,"CTRL intent objective"); _require_digest(self.target_scope_digest,"CTRL intent scope"); _require_digest(self.intent_digest,"CTRL materialization intent")

@dataclass
class Worker:
    id: str; lead: str; lane: int; state: WorkerState=WorkerState.SPAWNED; task_ids: set[str]=field(default_factory=set); archive: dict[str, object]=field(default_factory=dict); context:dict[str,object]=field(default_factory=dict)

@dataclass
class Swarm:
    architecture_version: int=1; contract_versions: dict[str,int]=field(default_factory=dict); topology: set[str]=field(default_factory=set)
    workers: dict[str,Worker]=field(default_factory=dict); tasks: dict[str,Task]=field(default_factory=dict); leases: dict[str,str]=field(default_factory=dict); events: list[tuple[str,str]]=field(default_factory=list); telemetry: dict[str,object]=field(default_factory=dict); telemetry_events:list[dict[str,object]]=field(default_factory=list); artifact_index:dict[str,str]=field(default_factory=dict); provenance_index:dict[str,str]=field(default_factory=dict); ctrl_evidence_ledger:dict[str,CtrlEvidence]=field(default_factory=dict); ctrl_decision_sets:dict[str,CtrlDecisionSet]=field(default_factory=dict); ctrl_phase:str="intake"; hive:dict[str,HiveRecord]=field(default_factory=dict); hive_enabled:bool=True; heartbeat_stall_after:int=2; correction_receipts:dict[str,None]=field(default_factory=dict); lane_width:int=3; wip_limit:int=3; efficiency_ledger:list[dict[str,str]]=field(default_factory=list); mode:EfficiencyMode=EfficiencyMode.BALANCED; default_review_horizon:int=30; max_review_horizon:int=60; direct_work_horizon:int=20
    scheduled_wakeups:dict[str,int]=field(default_factory=dict); ctrl_feed_messages:list[CtrlFeedMessage]=field(default_factory=list); ctrl_feed_cursor:int=0; ctrl_feed_superseded_by:dict[str,str]=field(default_factory=dict); ctrl_feed_events:dict[str,CtrlFeedEvent]=field(default_factory=dict); ctrl_feed_consumed_events:set[str]=field(default_factory=set); ctrl_authorizations:dict[str,UserCtrlAuthorization]=field(default_factory=dict); ctrl_materialization_intents:dict[str,CtrlMaterializationIntent]=field(default_factory=dict); consumed_ctrl_authorizations:set[str]=field(default_factory=set); consumed_ctrl_intents:set[str]=field(default_factory=set); proof_policy_version:str="lean-v1"; proof_impacted_selection:bool=True; proof_receipt_reuse:bool=True; proof_gate_timeout_seconds:int=120; proof_browser_freshness_seconds:int=86400; proof_provider_freshness_seconds:int=3600; proof_transient_retry_limit:int=1; request_store:RequestStore|None=field(default=None,repr=False,compare=False); request_continuity_enabled:bool=False; request_feed_sequence_floor:int=0; _host_authority_public_key:int|None=field(default=None,repr=False,compare=False); _gate_capability:object=field(default_factory=object,init=False,repr=False,compare=False); _watchdog_capability:object=field(default_factory=object,init=False,repr=False,compare=False); _owner_context_capability:object=field(default_factory=object,init=False,repr=False,compare=False); _ctrl_authority_capability:object=field(default_factory=object,init=False,repr=False,compare=False)
    def __setattr__(self, name:str, value:object) -> None:
        if name=="_host_authority_public_key" and name in self.__dict__: raise InvariantError("host authority verifier is immutable after Swarm construction")
        object.__setattr__(self,name,value)
    @classmethod
    def with_host_authority(cls, **kwargs:object) -> tuple["Swarm","_HostAuthorityBroker"]:
        """Composition-root factory: lane state receives only a verifier; host retains signer."""
        private_key=secrets.randbelow(_HOST_AUTHORITY_PRIME-3)+2; public_key=pow(_HOST_AUTHORITY_GENERATOR,private_key,_HOST_AUTHORITY_PRIME); swarm=cls(_host_authority_public_key=public_key,**kwargs); return swarm,_HostAuthorityBroker(swarm,private_key)
    @classmethod
    def from_config(cls, config: dict, *, _host_authority_public_key:int|None=None) -> "Swarm":
        monitoring=config["monitoring"]
        proof=config.get("proof",{})
        return cls(lane_width=config["coordination"]["preferred_lane_width"], wip_limit=config["efficiency"]["doer_wip_limit"], mode=EfficiencyMode(config["efficiency"]["mode"]), hive_enabled=config.get("hive",{}).get("enabled",True), heartbeat_stall_after=config["recovery"]["stall_after_updates"], default_review_horizon=monitoring.get("default_review_horizon_minutes",monitoring.get("heartbeat_minutes",30)), max_review_horizon=monitoring.get("max_review_horizon_minutes",60), direct_work_horizon=config["coordination"].get("ctrl_direct_horizon_minutes",20), proof_policy_version=proof.get("policy_version","lean-v1"), proof_impacted_selection=proof.get("impacted_selection",True), proof_receipt_reuse=proof.get("receipt_reuse",True), proof_gate_timeout_seconds=proof.get("gate_timeout_seconds",120), proof_browser_freshness_seconds=proof.get("browser_freshness_seconds",86400), proof_provider_freshness_seconds=proof.get("provider_freshness_seconds",3600), proof_transient_retry_limit=proof.get("transient_retry_limit",1), _host_authority_public_key=_host_authority_public_key)
    @classmethod
    def from_config_with_host_authority(cls, config:dict) -> tuple["Swarm","_HostAuthorityBroker"]:
        private_key=secrets.randbelow(_HOST_AUTHORITY_PRIME-3)+2; public_key=pow(_HOST_AUTHORITY_GENERATOR,private_key,_HOST_AUTHORITY_PRIME); swarm=cls.from_config(config,_host_authority_public_key=public_key); return swarm,_HostAuthorityBroker(swarm,private_key)

    def plan_proof(self, inputs:ProofInputs) -> ProofPlan:
        reach=inputs.dependency_reach if self.proof_impacted_selection else replace(inputs.dependency_reach,known=False)
        planned=plan_proof(replace(inputs,dependency_reach=reach,policy_version=self.proof_policy_version))
        gates=[]
        for gate in planned.gates:
            freshness=self.proof_browser_freshness_seconds if gate.proof_class in {ProofClass.BROWSER_LOCAL,ProofClass.BROWSER_AUTHENTICATED} else self.proof_provider_freshness_seconds if gate.proof_class is ProofClass.PROVIDER else gate.freshness_seconds
            cache=gate.cache_policy if self.proof_receipt_reuse else CachePolicy.NEVER
            flake=FlakePolicy.TYPED_TRANSIENT_ONCE if self.proof_transient_retry_limit else FlakePolicy.NO_RETRY
            gates.append(replace(gate,cache_policy=cache,freshness_seconds=freshness,flake_policy=flake,timeout_seconds=self.proof_gate_timeout_seconds))
        return ProofPlan(planned.schema_version,planned.planner_version,"",planned.tier,planned.artifact,tuple(gates),planned.reviews,planned.claim_matrix,planned.reasons,planned.early_stop,planned.legacy)

    def proof_state(self, task_id:str) -> ProofState:
        task=self.tasks[task_id]; contract=task.acceptance_contract
        if contract is None or contract.explicitly_empty: return ProofState.UNPLANNED if contract is None else ProofState.ACCEPTED
        plan=contract.proof_plan
        if plan is None: return ProofState.UNPLANNED
        if any(requirement.scope is ReviewScope.PLAN for requirement in plan.reviews) and (task.plan_review_receipt is None or task.plan_review_receipt.artifact!=contract.artifact or dict(task.plan_review_receipt.receipt).get("plan")!=plan.plan_digest): return ProofState.PLAN_REVIEW
        receipts=tuple(task.gate_receipts.values())
        if any(receipt.outcome is not ProofOutcome.PASS or receipt.stability is not ProofStability.STABLE for receipt in receipts): return ProofState.ESCALATE
        if self.open_gates(task_id) or self.open_claims(task_id): return ProofState.RUNNING if receipts else ProofState.READY
        final_scopes={requirement.scope for requirement in plan.reviews if requirement.scope in {ReviewScope.ACCEPTANCE,ReviewScope.COMPOSED}}
        if final_scopes and (task.acceptance_review_receipt is None or task.acceptance_review_receipt.scope not in final_scopes): return ProofState.ACCEPTANCE_REVIEW
        return ProofState.ACCEPTED

    def attach_request_store(self, repo_root:Path|str) -> RequestAudit:
        root=Path(repo_root)
        if not root.is_absolute(): raise InvariantError("request continuity requires an explicit absolute repo root")
        self.request_continuity_enabled=True; self.request_store=RequestStore(root.resolve()); audit=self.request_audit(0); self.request_feed_sequence_floor=max((record.transitions[-1].cursor.feed_sequence for record in audit.records),default=0); return audit
    enable_request_continuity=attach_request_store
    def _request_store(self) -> RequestStore:
        if self.request_store is None: raise InvariantError("durable request store is not attached")
        return self.request_store
    @staticmethod
    def _record_to_raw(record:RequestRecord) -> dict:
        return {"id":record.id,"goal_id":record.goal_id,"task_id":record.task_id,"accepted_owner":record.accepted_owner,"outcome_kind":record.outcome_identity.kind.value,"outcome_digest":record.outcome_identity.digest,"accepting_route":list(record.accepting_route),"accepted_at":record.accepted_at,"next_due_event":record.next_due_event,"next_due_at":record.next_due_at,"evidence_receipts":list(record.evidence_receipts),"transitions":[{"state":item.state.value,"kind":item.kind.value,"cursor":{"event_receipt":item.cursor.event_receipt,"message_id":item.cursor.message_id,"surface_receipt":item.cursor.surface_receipt,"feed_sequence":item.cursor.feed_sequence}} for item in record.transitions],"successor_id":record.successor_id}
    @staticmethod
    def _raw_to_record(raw:dict) -> RequestRecord:
        if set(raw)!={"id","goal_id","task_id","accepted_owner","outcome_kind","outcome_digest","accepting_route","accepted_at","next_due_event","next_due_at","evidence_receipts","transitions","successor_id"} or any(set(item)!={"state","kind","cursor"} or set(item["cursor"])!={"event_receipt","message_id","surface_receipt","feed_sequence"} for item in raw["transitions"]): raise InvariantError("request record has an invalid schema")
        transitions=tuple(RequestTransition(RequestState(item["state"]),CtrlFeedEventKind(item["kind"]),RequestEventCursor(**item["cursor"])) for item in raw["transitions"])
        return RequestRecord(raw["id"],raw["goal_id"],raw["task_id"],raw["accepted_owner"],RequestOutcomeIdentity(RequestOutcomeKind(raw["outcome_kind"]),raw["outcome_digest"]),tuple(raw["accepting_route"]),raw["accepted_at"],raw["next_due_event"],raw["next_due_at"],tuple(raw["evidence_receipts"]),transitions,raw["successor_id"])
    @staticmethod
    def _raw_to_stage(identity:str, raw:dict) -> RequestStage:
        if set(raw)!={"task_id","owner","contract_digest","state","request_id","history"}: raise InvariantError("request stage has invalid schema")
        return RequestStage(identity,raw["task_id"],raw["owner"],raw["contract_digest"],RequestStageState(raw["state"]),raw["request_id"],tuple(tuple(item) for item in raw["history"]))
    def _validate_request_state(self, state:dict) -> tuple[RequestRecord,...]:
        records=tuple(self._raw_to_record(state["requests"][identity]) for identity in state["order"])
        stages=tuple(self._raw_to_stage(identity,raw) for identity,raw in state["stages"].items())
        accepted={stage.request_id:stage for stage in stages if stage.state is RequestStageState.ACCEPTED}
        if len({stage.request_id for stage in stages})!=len(stages) or len(accepted)!=sum(stage.state is RequestStageState.ACCEPTED for stage in stages) or set(accepted)!=set(state["requests"]) or any(accepted[record.id].task_id!=record.task_id or accepted[record.id].owner!=record.accepted_owner or accepted[record.id].history[-1][1]!=record.transitions[0].cursor.event_receipt for record in records): raise InvariantError("accepted request stage does not match its record")
        return records
    def _request_snapshot(self) -> tuple[dict,str,tuple[RequestRecord,...]]:
        state,digest=self._request_store().read(); return state,digest,self._validate_request_state(state)
    def _request_route(self, task:Task) -> tuple[str,...]:
        if task.ctrl_mode is CtrlMode.DIRECT: return ("INDEPENDENT_REVIEW","CTRL")
        if not task.owning_lead_id: raise InvariantError("request requires a bound owning LEAD")
        return (task.owning_lead_id,"INDEPENDENT_REVIEW","CTRL")
    def _request_outcome_identity(self, task:Task, request_id:str) -> RequestOutcomeIdentity:
        contract=task.acceptance_contract
        if contract is not None and contract.artifact is not None:
            data=json.dumps((contract.artifact.base,contract.artifact.revision,contract.artifact.purpose,contract.artifact.observables,contract.artifact.observed_paths),separators=(",",":"),ensure_ascii=True).encode(); return RequestOutcomeIdentity(RequestOutcomeKind.ARTIFACT,sha256(data).hexdigest())
        if task.lane_kind is not LaneKind.NON_CODE or contract is None or not contract.explicitly_empty: raise InvariantError("non-artifact request requires explicit NON_CODE empty contract")
        return RequestOutcomeIdentity(RequestOutcomeKind.NON_ARTIFACT,sha256(f"non-code:{task.id}:{request_id}".encode()).hexdigest())
    def _request_contract_digest(self, task:Task, request_id:str) -> str:
        owner=Role.CTRL.value if task.ctrl_mode is CtrlMode.DIRECT else task.owning_lead_id
        for value in (task.id,task.goal_id,owner): _safe_token(value)
        outcome=self._request_outcome_identity(task,request_id)
        return sha256(json.dumps((task.id,task.goal_id,owner,self._request_route(task),outcome.kind.value,outcome.digest),separators=(",",":")).encode()).hexdigest()
    def _request_matches_live(self, state:dict, record:RequestRecord) -> bool:
        task=self.tasks.get(record.task_id); stage=next((raw for raw in state["stages"].values() if raw["request_id"]==record.id and raw["state"]=="ACCEPTED"),None)
        if task is None or stage is None: return False
        owner=Role.CTRL.value if task.ctrl_mode is CtrlMode.DIRECT else task.owning_lead_id
        if not (task.goal_id==record.goal_id and record.accepted_owner==owner==stage["owner"] and (owner=="CTRL" or owner in self.topology) and record.accepting_route==self._request_route(task) and record.outcome_identity==self._request_outcome_identity(task,record.id) and stage["task_id"]==task.id and stage["contract_digest"]==self._request_contract_digest(task,record.id)): return False
        if record.state in {RequestState.OPEN,RequestState.BLOCKED}: return task.state in {TaskState.REQUEST_PENDING,TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW,TaskState.COMPLETE}
        transition=record.transitions[-1]
        try: event,_=self._published_request_event(record.id,transition.cursor.event_receipt,{transition.kind},transition.cursor)
        except InvariantError: return False
        review=task.acceptance_review_receipt
        if record.state is RequestState.COMPLETED: return task.completed_at is not None and (task.state is TaskState.COMPLETE or task.state is TaskState.ARCHIVED and task.archived_at is not None) and self._acceptance_ready(task) and review is not None and dict(review.receipt).get("acceptance") in event.proof_receipts and set(event.proof_receipts).issubset(record.evidence_receipts)
        return any(value.startswith("usr-") for value in event.proof_receipts) and (record.state is RequestState.CANCELLED or record.successor_id in state["requests"])
    def _mutate_request(self, callback, *, expected:tuple[int,str]|None=None):
        def validated(value): self._validate_request_state(value); result=callback(value); self._validate_request_state(value); return result
        try: return self._request_store()._mutate_validated(validated,expected)
        except RequestStoreError as error: raise InvariantError(str(error)) from error
    def stage_request_task(self, actor:Role, task:Task) -> RequestStage:
        self._role(actor,{Role.CTRL}); self._require_subagent_contract(task); self._validate_task_acceptance(task)
        existing=self.tasks.get(task.id); task=existing or task; self._require_subagent_contract(task); self._validate_task_acceptance(task)
        owner=Role.CTRL.value if task.ctrl_mode is CtrlMode.DIRECT else task.owning_lead_id
        if not owner or owner!="CTRL" and owner not in self.topology or existing is not None and existing.state not in {TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW}: raise InvariantError("request staging requires a live task and accountable owner")
        state,digest,_=self._request_snapshot(); request_id=f"req-{state['sequence']+1:012d}"; stage_id=f"stg-{state['sequence']+1:012d}"; contract=self._request_contract_digest(task,request_id); stage=RequestStage(stage_id,task.id,owner,contract,request_id=request_id,history=(("PROVISIONAL",contract),))
        def write(value): value["stages"][stage_id]={"task_id":task.id,"owner":owner,"contract_digest":contract,"state":"PROVISIONAL","request_id":request_id,"history":[["PROVISIONAL",contract]]}
        self._mutate_request(write,expected=(state["sequence"],digest));
        task.state=TaskState.REQUEST_PENDING; self.tasks[task.id]=task
        worker=self.workers.get(task.owner)
        if worker: worker.task_ids.discard(task.id)
        return stage
    def _published_request_event(self, request_id:str, receipt:str, kinds:set[CtrlFeedEventKind], expected:RequestEventCursor|None=None) -> tuple[CtrlFeedEvent,RequestEventCursor]:
        _safe_receipt(receipt,"evt-"); event=self.ctrl_feed_events.get(receipt); messages=[m for m in self.ctrl_feed_messages if m.event_receipt==receipt]
        if event is None or event.kind not in kinds or request_id not in event.request_ids or len(messages)!=1 or messages[0].task_id!=event.task_id or messages[0].proof_receipts!=event.proof_receipts or not audit_ctrl_feed((messages[0],)).compliant or messages[0].id in self.ctrl_feed_superseded_by: raise InvariantError("request transition requires a current compliant published request-bound event")
        message=messages[0]; cursor=RequestEventCursor(event.receipt,_safe_receipt(message.id,"msg-"),_safe_receipt(message.surface_receipt,"srf-"),self.request_feed_sequence_floor+self.ctrl_feed_messages.index(message)+1)
        if expected is not None and cursor!=expected: raise InvariantError("request transition cursor does not match its current published event")
        for value in event.proof_receipts: _safe_receipt(value)
        return event,cursor
    def accept_request(self, actor:Role, stage_id:str, decision_event_receipt:str, *, accepted_at:int, due:RequestDue) -> RequestView:
        self._role(actor,{Role.CTRL}); state,digest,_=self._request_snapshot(); stage=state["stages"].get(stage_id)
        if not stage or stage["state"]!="PROVISIONAL": raise InvariantError("request stage is not provisional")
        task=self.tasks.get(stage["task_id"]); event,cursor=self._published_request_event(stage["request_id"],decision_event_receipt,{CtrlFeedEventKind.DECISION})
        if task is None or task.state is not TaskState.REQUEST_PENDING or stage["contract_digest"]!=self._request_contract_digest(task,stage["request_id"]) or stage["owner"]!=(Role.CTRL.value if task.ctrl_mode is CtrlMode.DIRECT else task.owning_lead_id) or event.task_id!=task.id or not any(value.startswith("usr-") for value in event.proof_receipts): raise InvariantError("request registration requires its current staged contract, owner, route, and user decision")
        record=RequestRecord(stage["request_id"],task.goal_id,task.id,stage["owner"],self._request_outcome_identity(task,stage["request_id"]),self._request_route(task),accepted_at,due.event,due.at,event.proof_receipts,(RequestTransition(RequestState.OPEN,event.kind,cursor),))
        def write(value): value["requests"][record.id]=self._record_to_raw(record); value["order"].append(record.id); value["stages"][stage_id].update(state="ACCEPTED",history=[*stage["history"],["ACCEPTED",event.receipt]])
        final_state,final,_=self._mutate_request(write,expected=(state["sequence"],digest)); return RequestView(final_state["sequence"],final,record)
    def rollback_request_stage(self, actor:Role, stage_id:str, blocker_event_receipt:str) -> RequestStage:
        self._role(actor,{Role.CTRL}); state,digest,_=self._request_snapshot(); raw=state["stages"].get(stage_id)
        if not raw or raw["state"]!="PROVISIONAL": raise InvariantError("rollback requires a registered provisional stage")
        task=self.tasks.get(raw["task_id"]); event,_=self._published_request_event(raw["request_id"],blocker_event_receipt,{CtrlFeedEventKind.BLOCKER})
        if task is None or task.state not in {TaskState.REQUEST_PENDING,TaskState.ACTIVE} or event.task_id!=task.id: raise InvariantError("rollback requires its current task and blocker")
        def write(value): value["stages"][stage_id].update(state="ROLLED_BACK",history=[*raw["history"],["ROLLED_BACK",event.receipt]])
        history=tuple(map(tuple,[*raw["history"],["ROLLED_BACK",event.receipt]])); self._mutate_request(write,expected=(state["sequence"],digest));
        if task.state is TaskState.REQUEST_PENDING:
            active=any(record.task_id==task.id and record.state in {RequestState.OPEN,RequestState.BLOCKED} for record in self._request_snapshot()[2])
            task.state=TaskState.ACTIVE if active else TaskState.BACKLOG
            if active and task.owner in self.workers: self.workers[task.owner].task_ids.add(task.id)
        return RequestStage(stage_id,task.id,raw["owner"],raw["contract_digest"],RequestStageState.ROLLED_BACK,raw["request_id"],history)
    def activate_accepted_task(self, actor:Role, task_id:str, request_id:str) -> None:
        self._role(actor,{Role.LEAD,Role.CTRL})
        state,_,records=self._request_snapshot(); record=next((item for item in records if item.id==request_id),None); task=self.tasks.get(task_id); stage=next((self._raw_to_stage(identity,raw) for identity,raw in state["stages"].items() if raw["request_id"]==request_id),None)
        if record is None or stage is None or stage.state is not RequestStageState.ACCEPTED or record.task_id!=task_id or record.state is not RequestState.OPEN or task is None or task.state is not TaskState.REQUEST_PENDING or record.outcome_identity!=self._request_outcome_identity(task,request_id) or record.accepting_route!=self._request_route(task): raise InvariantError("accepted request activation requires matching stage, task, owner, route, and outcome")
        if actor is Role.LEAD and task.owning_lead_id!=record.accepted_owner: raise InvariantError("only accepted owning LEAD may activate request")
        if actor is Role.CTRL and task.ctrl_mode is not CtrlMode.DIRECT: raise InvariantError("CTRL activation requires CTRL_DIRECT")
        if task.ctrl_mode is CtrlMode.DIRECT: task.state=TaskState.ACTIVE; return
        worker=self.workers.get(task.owner)
        if worker is None or worker.lead!=task.owning_lead_id or worker.state is WorkerState.RETIRED: raise InvariantError("accepted request has no matching live worker")
        task.state=TaskState.ACTIVE
        worker.task_ids.add(task_id)
    def request_audit(self, now:int) -> RequestAudit:
        state,digest,records=self._request_snapshot(); return self._request_audit_from(state,digest,records,now)
    def _request_audit_from(self, state:dict, digest:str, records:tuple[RequestRecord,...], now:int) -> RequestAudit:
        unresolved=tuple(item.id for item in records if item.state in {RequestState.OPEN,RequestState.BLOCKED}); orphaned=[]; unsurfaced=[]; idle=[]; blocked=[]
        for item in records:
            is_orphan=not self._request_matches_live(state,item)
            if is_orphan: orphaned.append(item.id)
            if item.id not in unresolved: continue
            progressed=len(item.transitions)>1
            if item.state is RequestState.OPEN and now>=item.next_due_at and not progressed: unsurfaced.append(item.id)
            if now>=item.next_due_at and (item.state is RequestState.BLOCKED or progressed): idle.append(item.id)
            if item.state is RequestState.BLOCKED: blocked.append(item.id)
        return RequestAudit(state["sequence"],digest,records,unresolved,tuple(orphaned),tuple(unsurfaced),tuple(idle),tuple(blocked),tuple(identity for identity,stage in state["stages"].items() if stage.get("state")=="PROVISIONAL"),tuple(RequestIntegritySignal(identity) for identity in orphaned))
    def _request_guard(self, *, task_id:str="", owner:str="", all_open:bool=False, require_accepted:bool=False, action=lambda:None):
        if self.request_store is None:
            if self.request_continuity_enabled: raise InvariantError("request continuity is enabled but unattached")
            return action()
        state,digest,records=self._request_snapshot()
        def check(value):
            stages=[stage for stage in value["stages"].values() if stage["state"]=="PROVISIONAL" and (not task_id or stage["task_id"]==task_id) and (not owner or stage["owner"]==owner)]; open_records=[record for record in records if record.state in {RequestState.OPEN,RequestState.BLOCKED} and (all_open or not task_id or record.task_id==task_id) and (not owner or record.accepted_owner==owner)]
            if require_accepted:
                related={record.id for record in records if record.task_id==task_id}; audit=self._request_audit_from(value,digest,records,0)
                if stages or not open_records or related.intersection(audit.orphaned_ids): raise InvariantError("completion requires a current accepted unresolved request and no provisional or orphaned request state")
            elif stages or open_records: raise InvariantError("request ledger blocks this lifecycle change")
            return action()
        try: return self._request_store().with_current((state["sequence"],digest),check)[2]
        except RequestStoreError as error: raise InvariantError(str(error)) from error
    def _request_record(self, request_id:str, prior:set[RequestState])->tuple[dict,str,RequestRecord,Task]:
        state,digest,records=self._request_snapshot(); record=next((item for item in records if item.id==request_id),None)
        if record is None or record.state not in prior or not self._request_matches_live(state,record): raise InvariantError("request transition requires its current task, stage, goal, owner, route, and outcome")
        return state,digest,record,self.tasks[record.task_id]
    def _request_transition(self, actor:Role, request_id:str, prior:set[RequestState], event_receipt:str, kinds:set[CtrlFeedEventKind], *, next_state:RequestState|None=None, successor_id:str="", due:RequestDue|None=None, owner:bool=True, user:bool=False, fresh_proof:bool=True, append_evidence:bool=True):
        state,digest,record,task=self._request_record(request_id,prior)
        if owner and actor is not (Role.CTRL if record.accepted_owner=="CTRL" else Role.LEAD): raise InvariantError("request transition requires its current accepted owner")
        event,cursor=self._published_request_event(request_id,event_receipt,kinds)
        if event.task_id!=task.id: raise InvariantError("request event does not match its current task")
        if event.receipt in {item.cursor.event_receipt for item in record.transitions} or cursor.feed_sequence<=record.transitions[-1].cursor.feed_sequence: raise InvariantError("request transition requires a later unused published event")
        if due is not None and due.at<=record.next_due_at: raise InvariantError("request transition must advance its due event")
        if fresh_proof and set(event.proof_receipts).issubset(record.evidence_receipts): raise InvariantError("request transition requires new surfaced proof")
        if user and not any(value.startswith("usr-") for value in event.proof_receipts): raise InvariantError("request transition requires explicit user direction")
        if successor_id and not any(item.id==successor_id and item.state in {RequestState.OPEN,RequestState.BLOCKED} for item in self._validate_request_state(state)): raise InvariantError("supersession requires an accepted unresolved successor")
        evidence=record.evidence_receipts+tuple(value for value in event.proof_receipts if append_evidence and value not in record.evidence_receipts)
        return state,digest,replace(record,evidence_receipts=evidence,transitions=record.transitions+(RequestTransition(next_state or record.state,event.kind,cursor),),successor_id=successor_id or record.successor_id),task,event
    def _write_request(self,state:dict,digest:str,record:RequestRecord)->RequestView:
        def write(value): value["requests"][record.id]=self._record_to_raw(record)
        final_state,final,_=self._mutate_request(write,expected=(state["sequence"],digest)); return RequestView(final_state["sequence"],final,record)
    def advance_request(self, actor:Role, request_id:str, event_receipt:str, due:RequestDue) -> RequestView:
        state,digest,record,_,_=self._request_transition(actor,request_id,{RequestState.OPEN},event_receipt,{CtrlFeedEventKind.RESULT,CtrlFeedEventKind.HANDOFF},due=due); return self._write_request(state,digest,replace(record,next_due_event=due.event,next_due_at=due.at))
    def block_request(self, actor:Role, request_id:str, event_receipt:str, due:RequestDue) -> RequestView:
        state,digest,record,_,_=self._request_transition(actor,request_id,{RequestState.OPEN},event_receipt,{CtrlFeedEventKind.BLOCKER},next_state=RequestState.BLOCKED,due=due); return self._write_request(state,digest,replace(record,next_due_event=due.event,next_due_at=due.at))
    def refresh_blocked_request(self, actor:Role, request_id:str, event_receipt:str, due:RequestDue) -> RequestView:
        state,digest,record,_,_=self._request_transition(actor,request_id,{RequestState.BLOCKED},event_receipt,{CtrlFeedEventKind.BLOCKER},due=due)
        return self._write_request(state,digest,replace(record,next_due_event=due.event,next_due_at=due.at))
    def resume_request(self, actor:Role, request_id:str, event_receipt:str, due:RequestDue) -> RequestView:
        self._role(actor,{Role.CTRL}); state,digest,record,_,event=self._request_transition(actor,request_id,{RequestState.BLOCKED},event_receipt,{CtrlFeedEventKind.DECISION},next_state=RequestState.OPEN,due=due,owner=False,user=True)
        return self._write_request(state,digest,replace(record,next_due_event=due.event,next_due_at=due.at))
    def supersede_request(self, actor:Role, request_id:str, successor_id:str, event_receipt:str) -> RequestView:
        self._role(actor,{Role.CTRL}); state,digest,record,_,_=self._request_transition(actor,request_id,{RequestState.OPEN,RequestState.BLOCKED},event_receipt,{CtrlFeedEventKind.DECISION},next_state=RequestState.SUPERSEDED,successor_id=successor_id,owner=False,user=True); return self._write_request(state,digest,record)
    def cancel_request(self, actor:Role, request_id:str, event_receipt:str) -> RequestView:
        self._role(actor,{Role.CTRL}); state,digest,record,_,event=self._request_transition(actor,request_id,{RequestState.OPEN,RequestState.BLOCKED},event_receipt,{CtrlFeedEventKind.DECISION},next_state=RequestState.CANCELLED,owner=False,user=True)
        return self._write_request(state,digest,record)
    def complete_request(self, actor:Role, request_id:str, event_receipt:str, review_receipt:str) -> RequestView:
        state,digest,record,task,event=self._request_transition(actor,request_id,{RequestState.OPEN},event_receipt,{CtrlFeedEventKind.ACCEPTANCE},next_state=RequestState.COMPLETED,fresh_proof=False,append_evidence=False); review=task.acceptance_review_receipt
        if task.state is not TaskState.COMPLETE or not self._acceptance_ready(task) or review is None or dict(review.receipt).get("acceptance")!=review_receipt or review_receipt not in event.proof_receipts or not set(event.proof_receipts).issubset(record.evidence_receipts): raise InvariantError("request completion requires current exact acceptance proof")
        return self._write_request(state,digest,record)
    def reprioritize_requests(self, actor:Role, unresolved_ids:tuple[str,...]) -> RequestAudit:
        self._role(actor,{Role.CTRL})
        def write(payload:dict):
            current=tuple(identity for identity in payload["order"] if payload["requests"][identity]["transitions"][-1]["state"] in {"OPEN","BLOCKED"})
            if set(current)!=set(unresolved_ids) or len(current)!=len(unresolved_ids): raise InvariantError("reprioritization requires an exact unresolved permutation")
            terminal=[identity for identity in payload["order"] if identity not in current]; payload["order"]=[*unresolved_ids,*terminal]
        self._mutate_request(write); return self.request_audit(0)
    def request_watchdog_evidence(self, now:int) -> tuple[WatchdogEvidence,...]:
        audit=self.request_audit(now); rows=[]
        for scope,signal,ids in ((WatchdogScope.OUTCOME_INTEGRITY,WatchdogSignal.ATTENTION,audit.unsurfaced_ids),(WatchdogScope.TRAJECTORY,WatchdogSignal.ATTENTION,audit.idle_ids)):
            for request_id in ids:
                record=next(item for item in audit.records if item.id==request_id); task=self.tasks.get(record.task_id)
                binding=None if task is None else task.watchdog_binding
                if task is None or binding is None or binding.watched_role not in {Role.LEAD,Role.SPECIALIST,Role.ARCHITECT} or binding.watched_owner!=record.accepted_owner or record.id in audit.orphaned_ids: continue
                text=f"request:{request_id}:{scope.value}"; rows.append(WatchdogEvidence(task.id,record.goal_id,task.watchdog_binding.watched_owner,scope,signal,sha256(text.encode()).hexdigest(),text))
        return tuple(rows)

    def _role(self, actor: Role, allowed: set[Role]) -> None:
        if actor not in allowed: raise InvariantError(f"{actor} cannot perform this transition")
    def _worker_identity(self, worker_id:str) -> None:
        if not isinstance(worker_id,str) or not worker_id.strip(): raise InvariantError("mutable worker identity is required")
        if worker_id.strip().upper()=="WATCHDOG": raise InvariantError("WATCHDOG is a reserved sensor identity, not a mutable worker")
        if worker_id.strip().upper() in ({role.value for role in Role}|BUILT_IN_SPECIALISTS): raise InvariantError("authority or specialist role identity cannot own mutable worker execution")
    def _known_watchdog_identity(self, task:Task, role:WatchdogRouteRole, identity:str) -> bool:
        if role is WatchdogRouteRole.CTRL: return identity=="CTRL"
        if role is WatchdogRouteRole.REVIEW: return identity=="INDEPENDENT_REVIEW"
        if role is WatchdogRouteRole.HUMAN: return identity=="HUMAN"
        if role is WatchdogRouteRole.LEAD: return identity in self.topology or identity==task.owning_lead_id
        profession=task.specialist_professions.get(identity,"")
        return bool(profession) and (role is WatchdogRouteRole.SPECIALIST or profession=="ARCHITECT")
    def _validate_watchdog_binding(self, actor:Role, task:Task, binding:WatchdogBinding) -> None:
        if actor is not binding.watched_role: raise InvariantError("watchdog binding role must match the durable goal owner role")
        if actor is Role.LEAD:
            valid=bool(task.owning_lead_id) and binding.watched_owner==task.owning_lead_id
        else:
            profession=task.specialist_professions.get(binding.watched_owner,"")
            valid=bool(profession) and (actor is Role.SPECIALIST or profession=="ARCHITECT")
        if not valid: raise InvariantError("watchdog watched owner is missing, fabricated, or not the actual accountable lane owner")
        if any(not self._known_watchdog_identity(task,role,identity) for route in (binding.alert_route,binding.owner_integrity_route) for role,identity in route): raise InvariantError("watchdog alert route contains a fabricated or wrong-scope identity")
    def propose_milestone(self, actor:Role, task_id:str, *, goal_id:str, milestone:str, proof_kind:str, horizon_minutes:int, now:int, watchdog:WatchdogBinding|None=None) -> None:
        self._role(actor,{Role.CTRL,Role.SPECIALIST,Role.ARCHITECT,Role.LEAD}); t=self.tasks[task_id]
        if not goal_id.strip() or not milestone.strip() or proof_kind not in {"artifact","test","dependency","integration","review","blocker"} or not 1<=horizon_minutes<=self.max_review_horizon: raise InvariantError("active goal requires a measurable proof kind, milestone, and review horizon within configured maximum")
        if t.goal_id and t.goal_id!=goal_id: raise InvariantError("durable goal history cannot be renamed or reset")
        if task_id in self.scheduled_wakeups: raise InvariantError("milestone already has one scheduled watchdog wakeup")
        if watchdog is not None: self._validate_watchdog_binding(actor,t,watchdog)
        t.goal_id=goal_id; t.milestone=milestone; t.milestone_proof_kind=proof_kind; t.review_horizon_minutes=horizon_minutes; t.milestone_started_at=now; t.active_goal=True; t.watchdog_binding=watchdog
        if watchdog is not None: self.scheduled_wakeups[task_id]=now+horizon_minutes
    def amend_objective(self, actor:Role, task_id:str, *, version:int, authority:str, reason:str, requirements_delta:str, new_baseline:str, prior_miss_relevance:str) -> None:
        self._role(actor,{Role.CTRL}); t=self.tasks[task_id]
        receipt=(authority,reason,requirements_delta,new_baseline,prior_miss_relevance)
        if version!=t.objective_version+1 or not all(item.strip() for item in receipt): raise InvariantError("objective amendment requires next version, authority, reason, requirements delta, baseline, and prior-miss relevance")
        t.objective_version=version; t.milestone_history.append((version,"AMEND","|".join(receipt)))
    def record_user_ctrl_authorization(self, actor:Role, host_event:HostUserEvent|None) -> UserCtrlAuthorization:
        """Consume one opaque host-minted user event; CTRL feed receipts are insufficient."""
        self._role(actor,{Role.CTRL})
        message=b"" if host_event is None else _authority_message("CTRL_USER_EVENT",(host_event.receipt,host_event.operation.value,host_event.source_ctrl_id,host_event.target_objective_digest,host_event.target_scope_digest,host_event.target_identity,host_event.issued_at,host_event.event_digest))
        if host_event is None or not _authority_verify(self._host_authority_public_key,message,host_event._signature): raise InvariantError("HUMAN_AUTHORITY_BLOCKER: CTRL materialization requires host-validated user authorization")
        if host_event.receipt in self.ctrl_authorizations or host_event.receipt in self.consumed_ctrl_authorizations: raise InvariantError("HUMAN_AUTHORITY_BLOCKER: CTRL authorization is single-use")
        authorization=UserCtrlAuthorization(host_event.receipt,host_event.operation,host_event.source_ctrl_id,host_event.target_objective_digest,host_event.target_scope_digest,host_event.target_identity,host_event.issued_at,host_event.event_digest); object.__setattr__(authorization,"_authority",self._ctrl_authority_capability); self.ctrl_authorizations[host_event.receipt]=authorization; return authorization
    def plan_ctrl_materialization(self, actor:Role, authorization:UserCtrlAuthorization|None, *, operation:CtrlOperation, source_ctrl_id:str, target_objective_digest:str, target_scope_digest:str, target_identity:str) -> CtrlMaterializationIntent:
        """Fail closed before any host create/fork/promote/replace/rename call."""
        self._role(actor,{Role.CTRL})
        expected=(operation,source_ctrl_id,target_objective_digest,target_scope_digest,target_identity)
        actual=None if authorization is None else (authorization.operation,authorization.source_ctrl_id,authorization.target_objective_digest,authorization.target_scope_digest,authorization.target_identity)
        if authorization is None or authorization._authority is not self._ctrl_authority_capability or self.ctrl_authorizations.get(authorization.receipt) is not authorization or authorization.receipt in self.consumed_ctrl_authorizations or actual!=expected: raise InvariantError("HUMAN_AUTHORITY_BLOCKER: missing, mismatched, replayed, or non-user CTRL authorization")
        if any(intent.authorization_receipt==authorization.receipt for intent in self.ctrl_materialization_intents.values()): raise InvariantError("HUMAN_AUTHORITY_BLOCKER: CTRL authorization already has a pending intent")
        digest=sha256(json.dumps((authorization.receipt,operation.value,source_ctrl_id,target_objective_digest,target_scope_digest,target_identity),separators=(",",":"),ensure_ascii=True).encode("utf-8")).hexdigest()
        intent=CtrlMaterializationIntent(authorization.receipt,operation,source_ctrl_id,target_objective_digest,target_scope_digest,target_identity,digest); object.__setattr__(intent,"_authority",self._ctrl_authority_capability); self.ctrl_materialization_intents[digest]=intent; self.telemetry["ctrl_materialization_authorized"]=self.telemetry.get("ctrl_materialization_authorized",0)+1; return intent
    def consume_ctrl_materialization_intent(self, intent:CtrlMaterializationIntent) -> str:
        """In-process requests are never host authority, even when cooperatively signed."""
        raise InvariantError("HUMAN_AUTHORITY_BLOCKER: the Codex host must independently consume a host-owned user receipt; plugin-runtime intents are non-authoritative")
    def restore_same_ctrl_identity(self, actor:Role, archived_identity:str, target_identity:str, *, provenance_receipt:str) -> str:
        self._role(actor,{Role.CTRL}); _safe_token(archived_identity); _safe_token(target_identity); _safe_receipt(provenance_receipt)
        if archived_identity!=target_identity: raise InvariantError("HUMAN_AUTHORITY_BLOCKER: replacement identity is RECOVER_AS_NEW and requires explicit user authorization")
        return provenance_receipt
    def link_successor(self, actor:Role, prior_task_id:str, successor_task_id:str, *, authorization:UserCtrlAuthorization|None=None, evidence:str="") -> None:
        self._role(actor,{Role.CTRL}); prior=self.tasks[prior_task_id]; successor=self.tasks[successor_task_id]
        if not prior.goal_id or not successor.goal_id or prior.goal_id==successor.goal_id: raise InvariantError("genuinely new project requires a distinct successor goal")
        objective_digest=_sha256_text(successor.goal_id); scope_digest=_sha256_text(successor_task_id)
        intent=self.plan_ctrl_materialization(actor,authorization,operation=CtrlOperation.SUCCESSOR,source_ctrl_id=prior_task_id,target_objective_digest=objective_digest,target_scope_digest=scope_digest,target_identity=successor_task_id); self.consume_ctrl_materialization_intent(intent)
        successor.milestone_history.append((successor.objective_version,"SUCCESSOR",f"{prior.goal_id}:{intent.intent_digest}"))
    def watchdog_check(self, task_id:str, *, observer_role:WatchdogRouteRole, observer_id:str, now:int, evidence:WatchdogEvidence) -> WatchdogReceipt:
        t=self.tasks[task_id]; binding=t.watchdog_binding; due=self.scheduled_wakeups.get(task_id)
        if binding is None or due is None: raise InvariantError("unbound goal has no watchdog clock, check, receipt, or alert")
        if now<due: raise InvariantError("watchdog check requires due evidence")
        if evidence.kind is WatchdogEvidenceKind.USAGE_CAPACITY and (evidence.declared_watched_role is not Role.LEAD or binding.watched_role is not Role.LEAD): raise InvariantError("usage capacity evidence requires the actual WatchdogBinding role to be LEAD")
        selected_route=binding.owner_integrity_route if evidence.owner_integrity else binding.alert_route
        first_role,first_id=selected_route[0]
        if observer_role is not first_role or observer_id.strip()!=first_id: raise InvariantError("watchdog observation must come from the selected bound route")
        if (evidence.task_id,evidence.goal_id,evidence.watched_owner)!=(task_id,t.goal_id,binding.watched_owner): raise InvariantError("watchdog evidence is outside its bound task, goal, or owner scope")
        decision_owner=first_id
        key=(evidence.evidence_digest,evidence.signal.value,decision_owner,evidence.scope.value)
        existing=next((receipt for receipt in reversed(t.watchdog_receipts) if (receipt.evidence_digest,receipt.signal.value,receipt.decision_owner,receipt.scope.value)==key),None)
        if existing is not None: self.scheduled_wakeups[task_id]=now+t.review_horizon_minutes; return existing
        route=() if evidence.signal is WatchdogSignal.CLEAR else selected_route
        receipt=WatchdogReceipt(task_id,t.goal_id,binding.watched_owner,evidence.scope,evidence.signal,evidence.evidence_digest,evidence.evidence,decision_owner,route,now); object.__setattr__(receipt,"_authority",self._watchdog_capability); t.watchdog_receipts.append(receipt)
        if len(t.watchdog_receipts)>64: del t.watchdog_receipts[:-64]
        self.scheduled_wakeups[task_id]=now+t.review_horizon_minutes; return receipt
    def watchdog_owner_context(self, actor:Role, task_id:str, *, actor_id:str, evidence_digests:tuple[str,...], cause:str, uncertainty:str, same_constraints_counterfactual:str, smallest_reversible_response:str, reversal_condition:str, urgent_safety:bool=False) -> WatchdogChangeReview:
        t=self.tasks[task_id]; binding=t.watchdog_binding
        if binding is None or actor is not binding.watched_role or actor_id!=binding.watched_owner: raise InvariantError("watchdog change review requires the exact accountable owner to be heard")
        if len(set(evidence_digests))<2 or len(receipts:=[r for r in t.watchdog_receipts if r._authority is self._watchdog_capability and r.signal is not WatchdogSignal.CLEAR and r.evidence_digest in evidence_digests])!=len(set(evidence_digests)) or len({receipt.scope for receipt in receipts})!=1: raise InvariantError("permanent change requires two distinct comparable runtime alert receipts")
        if not all(isinstance(value,str) and value.strip() for value in (cause,uncertainty,same_constraints_counterfactual,smallest_reversible_response,reversal_condition)): raise InvariantError("owner context requires cause, uncertainty, same-constraints counterfactual, smallest reversible response, and reversal condition")
        review=WatchdogChangeReview(task_id,binding.watched_owner,tuple(evidence_digests),cause,uncertainty,same_constraints_counterfactual,smallest_reversible_response,reversal_condition,urgent_safety); object.__setattr__(review,"_owner_authority",self._owner_context_capability); return review
    def authorize_watchdog_change(self, actor:Role, review:WatchdogChangeReview, *, target_kind:str, target_id:str, expected_benefit:int, total_change_cost:int) -> WatchdogChangeReview:
        self._role(actor,{Role.CTRL})
        if review._owner_authority is not self._owner_context_capability or target_kind not in {"retire","collapse"} or not target_id.strip(): raise InvariantError("CTRL change decision requires exact owner context and bounded target")
        if review.urgent_safety: raise InvariantError("urgent safety containment is temporary and cannot authorize permanent topology change")
        if not isinstance(expected_benefit,int) or not isinstance(total_change_cost,int) or expected_benefit<=total_change_cost or total_change_cost<0: raise InvariantError("expected benefit must exceed total change cost")
        object.__setattr__(review,"expected_benefit",expected_benefit); object.__setattr__(review,"total_change_cost",total_change_cost); object.__setattr__(review,"_decision",(target_kind,target_id)); return review
    def _require_watchdog_change(self, tasks:list[Task], kind:str, target:str, review:WatchdogChangeReview|None) -> None:
        if not (owners:={r.watched_owner for task in tasks for r in task.watchdog_receipts if r._authority is self._watchdog_capability and r.signal is not WatchdogSignal.CLEAR}): return
        if len(owners)!=1 or review is None or review._owner_authority is not self._owner_context_capability or review._decision!=(kind,target) or review.watched_owner!=next(iter(owners)) or review.task_id not in {task.id for task in tasks}: raise InvariantError("alerted permanent change requires exact owner-heard CTRL review")
    def _record(self, target:str, item:object) -> None:
        """Keep machine receipts inspectable without retaining an event transcript."""
        entries=getattr(self,target); entries.append(item)
        if len(entries)>64: del entries[:-64]
    def _require_subagent_contract(self, task:Task) -> None:
        receipt=task.subagent_receipt.strip()
        exception=task.subagent_exception
        reason=task.subagent_exception_reason.strip()
        if receipt and (exception is not None or reason): raise InvariantError("task must record a subagent receipt or one typed exception, not both")
        if receipt:
            if not receipt.startswith("host:thread:") or len(receipt)==len("host:thread:"): raise InvariantError("subagent receipt must record the caller-declared host thread identity")
            return
        if not isinstance(exception,SubagentException) or not reason: raise InvariantError("every SWARM task requires a host subagent receipt or typed exact exception")
    def _validate_task_acceptance(self, task:Task) -> None:
        if not isinstance(task.lane_kind,LaneKind): raise InvariantError("task requires a typed lane kind")
        empty=task.acceptance_contract is not None and task.acceptance_contract.explicitly_empty
        if empty and task.lane_kind is not LaneKind.NON_CODE: raise InvariantError("empty acceptance contracts are allowed only for NON_CODE lanes")
        if task.lane_kind is LaneKind.CODE and (task.acceptance_contract is None or empty or not task.acceptance_contract.required_gates): raise InvariantError("CODE lanes require an exact acceptance contract with at least one named gate")
        if task.artifacts and (task.acceptance_contract is None or empty): raise InvariantError("artifact-producing lanes cannot use an empty acceptance contract")
    def _bind_task_lead(self, task:Task, worker:Worker) -> None:
        if task.owning_lead_id and task.owning_lead_id!=worker.lead: raise InvariantError("task owning LEAD identity must match the assigned worker lead")
        task.owning_lead_id=worker.lead
    def _require_lane_actor(self, task:Task, actor:Role, actor_id:str) -> None:
        identity=actor_id.strip()
        if actor is Role.LEAD and (not task.owning_lead_id or identity!=task.owning_lead_id): raise InvariantError("lane transition requires the bound owning LEAD identity")
        if actor is Role.CTRL:
            owner=self.workers.get(task.owner)
            direct=task.ctrl_mode is CtrlMode.DIRECT or (owner is not None and owner.lead==Role.CTRL.value)
            if identity!=Role.CTRL.value or not direct or task.owning_lead_id: raise InvariantError("CTRL completion is limited to direct CTRL-bound work")
    def add_lead(self, actor: Role, lead: str) -> None:
        self._role(actor,{Role.CTRL}); self.topology.add(lead)
    def add_worker(self, actor: Role, worker: Worker) -> None:
        self._role(actor,{Role.LEAD});
        self._worker_identity(worker.id)
        if worker.id in self.workers: raise InvariantError("duplicate worker identity")
        if worker.lead not in self.topology or not 1 <= worker.lane <= self.lane_width: raise InvariantError("worker requires a known lead and configured lane")
        if any(item.lead==worker.lead and item.lane==worker.lane and item.state!=WorkerState.RETIRED for item in self.workers.values()): raise InvariantError("duplicate active lane ownership")
        if sum(w.lead==worker.lead and w.state!=WorkerState.RETIRED for w in self.workers.values()) >= self.lane_width: raise InvariantError("lead capacity reached")
        self.workers[worker.id]=worker
    def start_atomic(self, actor:Role, task:Task) -> None:
        """CTRL may create exactly one direct DOER ownership path for atomic work."""
        self._role(actor,{Role.CTRL}); self._require_subagent_contract(task); self._validate_task_acceptance(task); self._worker_identity(task.owner)
        if task.owner in self.workers or task.id in self.tasks: raise InvariantError("atomic ownership already exists")
        task.topology_receipt=("CTRL","DOER","atomic:isolated"); self.workers[task.owner]=Worker(task.owner,"CTRL",1,WorkerState.ACTIVE,{task.id}); self.tasks[task.id]=task
    def start_ctrl_direct(self, actor:Role, task:Task, *, outcomes:int, mutable_surfaces:int, cross_lane_dependency:bool, measurable_minutes:int) -> None:
        self._role(actor,{Role.CTRL}); self._require_subagent_contract(task); self._validate_task_acceptance(task)
        if ctrl_mode(outcomes=outcomes,mutable_surfaces=mutable_surfaces,cross_lane_dependency=cross_lane_dependency,risk=task.risk,measurable_minutes=measurable_minutes,direct_horizon_minutes=self.direct_work_horizon) is not CtrlMode.DIRECT: raise InvariantError("CTRL_DIRECT predicate failed; hire a LEAD")
        if task.owner.strip().upper()!=Role.CTRL.value or task.id in self.tasks: raise InvariantError("CTRL_DIRECT requires the sole CTRL owner and a new atomic task")
        task.ctrl_mode=CtrlMode.DIRECT; task.topology_receipt=("CTRL_DIRECT","atomic:one-surface"); self.tasks[task.id]=task
    def reuse_warm(self, actor:Role, task:Task, *, architecture:dict[str,int], affinity:int) -> str|None:
        self._role(actor,{Role.LEAD,Role.CTRL}); self._require_subagent_contract(task); self._validate_task_acceptance(task)
        for worker in self.workers.values():
            self._worker_identity(worker.id)
            context=worker.context
            if worker.state==WorkerState.WARM and context.get("affinity",0)>=affinity and context.get("architecture",architecture)==architecture:
                self._bind_task_lead(task,worker); worker.state=WorkerState.ACTIVE; worker.task_ids.add(task.id); task.owner=worker.id; self.tasks[task.id]=task; return worker.id
        return None
    def package_context(self, actor:Role, worker_id:str, package:ContextPackage) -> None:
        self._role(actor,{Role.LEAD}); worker=self.workers[worker_id]
        hive=package.hive if self.hive_enabled else ()
        worker.context={"goal":package.goal,"architecture":package.architecture,"dependencies":package.dependencies,"artifacts":package.artifacts,"acceptance":package.acceptance,"history":package.history,"hive":hive,"transfer_cost":package.transfer_cost-len(package.hive)+len(hive),"affinity":worker.context.get("affinity",1),"bloat":False,"stale":False,"stalls":0}
    def remember(self, actor:Role, record:HiveRecord, now:int) -> str|None:
        self._role(actor,{Role.SPECIALIST,Role.ARCHITECT,Role.LEAD,Role.DOER})
        if not self.hive_enabled: return None
        if not record.id or (not record.content and not record.reference) or len(record.content)>280 or record.value in {"noise","low"}: raise InvariantError("HIVE stores only compact future-useful lessons")
        if record.source in {"repository","canonical"} and record.content: raise InvariantError("reference durable truth instead of copying it")
        for old in self.hive.values():
            if old.status==HiveStatus.ACTIVE and (old.id==record.id or (old.source,old.source_version,old.content or old.reference)==(record.source,record.source_version,record.content or record.reference)):
                old.last_used_at=now; self.telemetry["hive_reused"]=self.telemetry.get("hive_reused",0)+1; return old.id
            if old.status==HiveStatus.ACTIVE and old.source==record.source and old.applicability==record.applicability and old.source_version!=record.source_version:
                old.status=HiveStatus.ARCHIVED; old.provenance["superseded_by"]=record.id; self.telemetry["hive_superseded"]=self.telemetry.get("hive_superseded",0)+1
        if len([item for item in self.hive.values() if item.status==HiveStatus.ACTIVE])>=64: raise InvariantError("HIVE active record bound reached")
        record.created_at=now; self.hive[record.id]=record; self.telemetry["hive_created"]=self.telemetry.get("hive_created",0)+1; self._hive_counts(); return record.id
    def _hive_counts(self) -> None:
        self.telemetry.update({f"hive_{state.value.lower()}":sum(r.status==state for r in self.hive.values()) for state in HiveStatus})
    def hydrate_hive(self, query:str, architecture:dict[str,int], budget:int, now:int) -> list[HiveRecord]:
        if not query or budget<1 or not self.hive_enabled: return []
        matches=[r for r in self.hive.values() if r.status==HiveStatus.ACTIVE and all(architecture.get(k,v)==v for k,v in r.applicability.items()) and query.lower() in f"{r.content} {r.reference} {r.source}".lower()][:budget]
        for record in matches: record.last_used_at=now
        self.telemetry.update({"hive_hydration_count":len(matches),"hive_hydration_size":sum(len(r.content)+len(r.reference) for r in matches)})
        return matches
    def _artifact(self, artifact:ArtifactIdentity|str) -> ArtifactIdentity:
        if isinstance(artifact,ArtifactIdentity): return artifact
        try:
            base,tail=artifact.rsplit("@",1); revision,purpose=tail.split(":",1)
        except ValueError as exc: raise InvariantError("artifact identity must be base@revision:purpose") from exc
        observables=(); paths=()
        if "#obs=" in purpose:
            purpose,encoded=purpose.rsplit("#obs=",1)
            try:
                payload=json.loads(bytes.fromhex(encoded).decode("utf-8"))
                observables=tuple(tuple(item) for item in payload["observables"]); paths=tuple(payload["paths"])
            except (ValueError,TypeError,KeyError,UnicodeDecodeError) as exc: raise InvariantError("observed artifact identity is malformed") from exc
        if not base or not revision or not purpose: raise InvariantError("artifact identity must be complete")
        return ArtifactIdentity(base,revision,purpose,observables,paths)
    def _check_artifact(self, task:Task, artifact:ArtifactIdentity|str, source:str|None, justification:ArtifactJustification|None, provenance:ArtifactProvenance|None=None, *, pending:set[str]|None=None, pending_provenance:set[str]|None=None) -> tuple[ArtifactIdentity,str]:
        identity=self._artifact(artifact); key=identity.key()
        if pending is None: pending=set()
        if pending_provenance is None: pending_provenance=set()
        if key in self.artifact_index or key in pending: raise InvariantError("canonical artifact identity already exists")
        if identity.purpose in {"verification","uncertainty"}:
            expected=ArtifactJustification(identity.purpose)
            if not source or justification is not expected or source not in self.artifact_index: raise InvariantError("justified duplicate requires typed reason, existing canonical source, and matching purpose")
            if not isinstance(provenance,ArtifactProvenance) or provenance.source!=source: raise InvariantError("justified duplicate requires typed provenance for its canonical source")
            if provenance.id in self.provenance_index or provenance.id in pending_provenance: raise InvariantError("artifact provenance identity already exists")
            source_identity=self._artifact(source)
            if source_identity.revision==identity.revision: raise InvariantError("justified duplicate requires distinct revision provenance")
        return identity,key
    def _register_artifact(self, task:Task, artifact:ArtifactIdentity|str, source:str|None, justification:ArtifactJustification|None, provenance:ArtifactProvenance|None=None) -> str:
        _,key=self._check_artifact(task,artifact,source,justification,provenance)
        self.artifact_index[key]=task.id; task.artifacts[key]=source or task.id
        if provenance is not None: self.provenance_index[provenance.id]=key; task.artifact_provenance[key]=provenance
        return key
    def assign(self, actor: Role, task: Task) -> None:
        self._role(actor,{Role.LEAD}); self._require_subagent_contract(task); self._validate_task_acceptance(task); self._worker_identity(task.owner); w=self.workers.get(task.owner)
        if not w or w.state==WorkerState.RETIRED or len(w.task_ids)>=self.wip_limit: raise InvariantError("owner unavailable or at WIP limit")
        self._bind_task_lead(task,w)
        staged=[]; pending=set(); pending_provenance=set()
        for artifact,source in task.artifacts.items():
            artifact_key=self._artifact(artifact).key(); provenance=task.artifact_provenance.get(artifact_key)
            identity,key=self._check_artifact(task,artifact,source,task.artifact_justifications.get(artifact_key),provenance,pending=pending,pending_provenance=pending_provenance); staged.append((identity,source,task.artifact_justifications.get(key),provenance)); pending.add(key)
            if provenance is not None: pending_provenance.add(provenance.id)
        task.artifacts={}
        task.artifact_provenance={}
        for artifact,source,justification,provenance in staged: self._register_artifact(task,artifact,source,justification,provenance)
        self.tasks[task.id]=task; w.task_ids.add(task.id)
    def should_spawn(self, *, independent: bool, critical_path: bool, duplicate_artifact: str|None=None, verification: bool=False, contention:bool=False) -> bool:
        allowed=independent and not contention and (critical_path or verification) and (not duplicate_artifact or verification) and sum(w.state!=WorkerState.RETIRED for w in self.workers.values()) < MODE_POLICY[self.mode]["parallel"]
        reason="allow:verification" if verification else "allow:critical_path" if allowed else "refuse:independent=false" if not independent else "refuse:contention" if contention else "refuse:duplicate" if duplicate_artifact else "refuse:noncritical"
        self._record("efficiency_ledger",{"kind":"spawn","decision":"allow" if allowed else "refuse","reason":reason})
        return allowed
    def route(self, *, family:str, risk:int, uncertainty:int, blast_radius:int, architect_floor:int=1, historical_floor:int=1, mode:EfficiencyMode|None=None) -> int:
        selected=mode or self.mode; tier=max(architect_floor,historical_floor,initial_tier(risk=risk,uncertainty=uncertainty,blast_radius=blast_radius,family=family,mode=selected)); self._record("efficiency_ledger",{"kind":"route","family":family,"tier":str(tier),"reason":"expected_total_accepted_cost"}); return tier
    def dedup(self, identity:str, *, verification:bool=False, uncertainty:bool=False) -> DedupDecision:
        found=bool(self.discover(identity)); decision=DedupDecision.EXECUTE if not found or verification or uncertainty else DedupDecision.REUSE; self._record("efficiency_ledger",{"kind":"dedup","decision":decision.value,"reason":"verification" if verification else "uncertainty" if uncertainty else "canonical_artifact"}); return decision
    def publish_ctrl_feed(self, actor:Role, message:CtrlFeedMessage) -> str:
        """Record the exact externally surfaced CTRL message for later heartbeat audit."""
        self._role(actor,{Role.CTRL})
        if not message.task_id or message.task_id not in self.tasks: raise InvariantError("CTRL feed message requires a canonical task identity")
        if not message.surface_receipt.strip(): raise InvariantError("CTRL feed message requires an external surface receipt")
        for existing in self.ctrl_feed_messages:
            if existing==message: return message.surface_receipt
            if existing.id==message.id or existing.surface_receipt==message.surface_receipt: raise InvariantError("CTRL feed message identity and surface receipt must be unique")
        self.ctrl_feed_messages.append(message); return message.surface_receipt
    def register_ctrl_feed_event(self, actor:Role, task_id:str, event_receipt:str, kind:CtrlFeedEventKind, proof_receipts:tuple[str,...], request_ids:tuple[str,...]=()) -> str:
        """Register semantic authority for one new user-visible feed event."""
        self._role(actor,{Role.CTRL});
        if task_id not in self.tasks: raise InvariantError("CTRL feed event requires a canonical task")
        if event_receipt in self.ctrl_feed_events: raise InvariantError("CTRL feed event receipt must be unique")
        surfaced={item.receipt for item in self.ctrl_evidence_ledger.values() if item.task_id==task_id and item.disposition==EvidenceDisposition.SURFACED}
        if any(receipt not in surfaced for receipt in proof_receipts): raise InvariantError("CTRL feed event proof must be surfaced for the same task")
        if request_ids:
            state,_,records=self._request_snapshot(); bound={record.id:record.task_id for record in records}; bound.update({stage["request_id"]:stage["task_id"] for stage in state["stages"].values() if stage["state"]=="PROVISIONAL"})
            if not event_receipt.startswith("evt-"): raise InvariantError("request-bound event needs an evt receipt")
            for value in (event_receipt,*proof_receipts): _safe_receipt(value)
            if any(bound.get(identity)!=task_id for identity in request_ids): raise InvariantError("CTRL feed event request binding must match an existing request or reserved stage")
        event=CtrlFeedEvent(event_receipt,task_id,kind,proof_receipts,request_ids); self.ctrl_feed_events[event_receipt]=event; return event_receipt
    def heartbeat(self, actor:Role, task_id:str, *, meaningful_progress:bool, recent_ctrl_feed:tuple[CtrlFeedMessage,...]=(), owner_update:bool=True, unchanged_updates:int=1, recovery_attempts:int|None=None, feed_correction:CtrlFeedMessage|None=None) -> str|None:
        self._role(actor,{Role.CTRL}); t=self.tasks[task_id]
        for message in recent_ctrl_feed: self.publish_ctrl_feed(Role.CTRL,message)
        pending=tuple(self.ctrl_feed_messages[self.ctrl_feed_cursor:]); audit=audit_ctrl_feed(pending)
        pending_events:set[str]=set()
        for message in pending:
            surfaced_receipts={item.receipt for item in self.ctrl_evidence_ledger.values() if item.task_id==message.task_id and item.disposition==EvidenceDisposition.SURFACED}
            unknown=tuple(receipt for receipt in message.proof_receipts if receipt not in surfaced_receipts)
            if unknown: audit=CtrlFeedAudit((*audit.violations,f"{message.id}:unknown-proof-receipt"))
            event=self.ctrl_feed_events.get(message.event_receipt)
            if event is None or event.task_id!=message.task_id or event.proof_receipts!=message.proof_receipts: audit=CtrlFeedAudit((*audit.violations,f"{message.id}:unknown-material-event"))
            elif message.event_receipt in self.ctrl_feed_consumed_events or message.event_receipt in pending_events: audit=CtrlFeedAudit((*audit.violations,f"{message.id}:repeated-material-event"))
            pending_events.add(message.event_receipt)
        reorientation=""
        if not audit.compliant:
            correction_audit=audit_ctrl_feed((feed_correction,)) if feed_correction is not None else CtrlFeedAudit(("missing-correction",))
            correction_receipts={item.receipt for item in self.ctrl_evidence_ledger.values() if feed_correction is not None and item.task_id==feed_correction.task_id and item.disposition==EvidenceDisposition.SURFACED}
            if feed_correction is not None and (not feed_correction.surface_receipt.strip() or feed_correction.task_id not in self.tasks): correction_audit=CtrlFeedAudit((*correction_audit.violations,f"{feed_correction.id}:unsurfaced-correction"))
            if feed_correction is not None and any(receipt not in correction_receipts for receipt in feed_correction.proof_receipts): correction_audit=CtrlFeedAudit((*correction_audit.violations,f"{feed_correction.id}:unknown-proof-receipt"))
            correction_event=self.ctrl_feed_events.get(feed_correction.event_receipt) if feed_correction is not None else None
            if feed_correction is not None and (correction_event is None or correction_event.task_id!=feed_correction.task_id or correction_event.proof_receipts!=feed_correction.proof_receipts or feed_correction.event_receipt in self.ctrl_feed_consumed_events): correction_audit=CtrlFeedAudit((*correction_audit.violations,f"{feed_correction.id}:unknown-material-event"))
            if not correction_audit.compliant: raise InvariantError(f"CTRL heartbeat found feed violations and requires one compliant correction: {','.join(audit.violations)}")
            self.publish_ctrl_feed(Role.CTRL,feed_correction)
            self.ctrl_feed_consumed_events.add(feed_correction.event_receipt)
            t.ctrl_feed_drift_count+=1; t.superseded_ctrl_feed_ids.extend(message.id for message in pending); t.last_ctrl_feed_correction_id=feed_correction.id
            self.ctrl_feed_superseded_by.update({message.id:feed_correction.id for message in pending}); self.ctrl_feed_cursor=len(self.ctrl_feed_messages)
            self._record("telemetry_events",{"kind":"ctrl_feed_audit","task_id":task_id,"violations":audit.violations,"correction":feed_correction.id,"drift_count":t.ctrl_feed_drift_count,"reorientation":"purpose-reset"})
            reorientation=f"{task_id}:feed-reoriented:{t.ctrl_feed_drift_count}:{feed_correction.id}"
        else:
            self.ctrl_feed_consumed_events.update(message.event_receipt for message in pending); self.ctrl_feed_cursor=len(self.ctrl_feed_messages)
        return reorientation or None
    def context_decision(self, *, affinity:int|None=None, bloat:bool|None=None, stale:bool|None=None, stalls:int|None=None, worker_id:str|None=None, replacement:str|None=None) -> str:
        context=self.workers[worker_id].context if worker_id else {}; affinity=context.get("affinity",affinity or 0); bloat=context.get("bloat",bloat or False); stale=context.get("stale",stale or False); stalls=context.get("stalls",stalls or 0)
        result="retire" if bloat or stale or stalls>1 or affinity==0 else "reuse"; self._record("efficiency_ledger",{"kind":"context","decision":result,"reason":"bounded_spine"})
        if result=="retire" and worker_id: self.retire(Role.LEAD,worker_id,replacement)
        return result
    def change_architecture(self, actor: Role, contracts: dict[str,int], now:int=0) -> None:
        self._role(actor,{Role.ARCHITECT}); self._request_guard(all_open=True); self.architecture_version+=1; self.contract_versions.update(contracts)
        for task in self.tasks.values():
            if task.state not in {TaskState.COMPLETE,TaskState.BACKLOG,TaskState.ARCHIVED,TaskState.ARCHIVED_STALE} and (task.architecture_version != self.architecture_version or any(task.contracts.get(k,0)!=v for k,v in contracts.items())): task.state=TaskState.STALE; task.stale_reason="architecture or contract version changed"; task.stale_at=now
    def architecture_event(self, actor:Role, task_id:str, *, goal_id:str, accepted_change:str, invalidates_map:bool, receipt:str, decision_or_blocker:str="") -> None:
        self._role(actor,{Role.ARCHITECT})
        self.specialist_event(Role.SPECIALIST,task_id,specialist_id="architect",profession="ARCHITECT",goal_id=goal_id,accepted_change=accepted_change,invalidates_map=invalidates_map,receipt=receipt,decision_or_blocker=decision_or_blocker)
        t=self.tasks[task_id]; t.architecture_goal_id=t.specialist_goal_ids["architect"]; t.architecture_map_version=t.specialist_map_versions["architect"]; t.architecture_receipts=t.specialist_receipts["architect"]
    def specialist_event(self, actor:Role, task_id:str, *, specialist_id:str, profession:str, goal_id:str, accepted_change:str, invalidates_map:bool, receipt:str, decision_or_blocker:str="") -> None:
        self._role(actor,{Role.SPECIALIST}); t=self.tasks[task_id]; identity=specialist_id.strip(); name=profession.strip().upper()
        if not identity or any(character in identity for character in "\r\n\t") or not name or any(character in name for character in "\r\n\t"): raise InvariantError("specialist requires a stable instance identity and concrete profession")
        if name=="MOTHER" and invalidates_map: raise InvariantError("MOTHER manager specialist is advisory and cannot invalidate architecture")
        if not all(item.strip() for item in (goal_id,accepted_change,receipt)) or (invalidates_map and not decision_or_blocker.strip()): raise InvariantError("specialist event requires durable goal, accepted change, receipt, and consequential decision when invalidated")
        existing_profession=t.specialist_professions.get(identity)
        if existing_profession and existing_profession!=name: raise InvariantError("specialist instance profession cannot change")
        existing=t.specialist_goal_ids.get(identity)
        if existing and existing!=goal_id: raise InvariantError("specialist durable goal cannot be replaced")
        t.specialist_professions[identity]=name; t.specialist_goal_ids[identity]=goal_id; version=t.specialist_map_versions.get(identity,0)+(1 if invalidates_map else 0); t.specialist_map_versions[identity]=version
        t.specialist_receipts.setdefault(identity,[]).append((version,"UPDATE" if invalidates_map else "NO_IMPACT",decision_or_blocker or receipt))
    def wait(self, actor: Role, task_id: str, dependency: str) -> None:
        self._role(actor,{Role.DOER}); t=self.tasks[task_id]
        if not dependency or dependency not in self.tasks: raise InvariantError("WAITING requires a named task dependency")
        t.state=TaskState.WAITING; t.waiting_on=dependency
        if self._cycle(task_id): self._record("events",("DEADLOCK",task_id))
    def _cycle(self, start: str) -> bool:
        seen=set(); current=start
        while current and current not in seen:
            seen.add(current); current=self.tasks[current].waiting_on if current in self.tasks else None
        return current==start
    def recover(self, actor: Role, task_id: str, dimension: str) -> None:
        self._role(actor,{Role.LEAD,Role.CTRL}); t=self.tasks[task_id]
        if not dimension or t.recovery_attempts>=1: raise InvariantError("recovery budget exhausted; release blocker")
        t.recovery_dimensions.add(dimension); t.recovery_attempts=1; self._record("events",("RECOVERY",task_id))
    def scope_finding(self, actor:Role, task_id:str, evidence:str, *, material:bool) -> bool:
        """Preserve a direct invariant violation; unrelated opportunity changes nothing."""
        self._role(actor,{Role.DOER,Role.LEAD,Role.SPECIALIST,Role.ARCHITECT}); t=self.tasks[task_id]
        if not material: return False
        if not evidence: raise InvariantError("material scope finding needs evidence")
        t.findings.append(f"scope:{evidence}"); t.correction_pending=True; t.state=TaskState.WAITING; self._record("events",("SCOPE_ESCALATION",task_id)); return True
    def expert(self, actor: Role, task_id: str) -> None:
        self._role(actor,{Role.DOER,Role.LEAD,Role.SPECIALIST,Role.ARCHITECT}); self._record("events",("EXPERT",task_id))
    def set_intelligence_floor(self, actor: Role, task_id: str, tier: int) -> None:
        self._role(actor,{Role.SPECIALIST,Role.ARCHITECT}); self.tasks[task_id].contracts["intelligence_floor"]=tier
    def complexity_mismatch(self, actor: Role, task_id: str, observed_tier: int) -> None:
        self._role(actor,{Role.DOER}); self.tasks[task_id].contracts["complexity_mismatch"]=observed_tier; self._record("events",("MISMATCH",task_id))
    def add_artifact(self, actor: Role, task_id: str, artifact: ArtifactIdentity, risk: str="", *, source:str|None=None, justification:ArtifactJustification|None=None, provenance:ArtifactProvenance|None=None) -> None:
        self._role(actor,{Role.DOER,Role.CTRL}); t=self.tasks[task_id]
        if actor is Role.CTRL and t.ctrl_mode is not CtrlMode.DIRECT: raise InvariantError("CTRL artifact mutation requires explicit CTRL_DIRECT mode")
        if t.acceptance_contract is None or t.acceptance_contract.explicitly_empty: raise InvariantError("artifact-producing lanes require an exact nonempty acceptance contract before artifact registration")
        identity=self._register_artifact(t,artifact,source,justification,provenance); t.evidence.append(identity); t.findings.extend([risk] if risk else [])
    def register_ctrl_evidence(self, actor:Role, task_id:str, evidence_id:str, kind:str, locator:str, *, material:bool=True, steering:bool=True) -> str:
        """Register each reviewable result; a path is provenance, never a surface receipt."""
        self._role(actor,{Role.CTRL,Role.SPECIALIST,Role.ARCHITECT,Role.LEAD,Role.DOER,Role.REVIEW})
        if task_id not in self.tasks: raise InvariantError("CTRL evidence requires a canonical task")
        if evidence_id in self.ctrl_evidence_ledger: raise InvariantError("duplicate CTRL evidence identity")
        self.ctrl_evidence_ledger[evidence_id]=CtrlEvidence(evidence_id,task_id,kind,locator,material,steering)
        return evidence_id
    def ctrl_feed_due(self, actor:Role, *, task_id:str|None=None) -> tuple[str,...]:
        """Return material work due at the next safe CTRL message boundary."""
        self._role(actor,{Role.CTRL})
        return tuple(item.id for item in self.ctrl_evidence_ledger.values() if item.material and item.disposition==EvidenceDisposition.PENDING and (task_id is None or item.task_id==task_id))
    def surface_ctrl_evidence(self, actor:Role, evidence_id:str, *, surface_kind:CtrlSurfaceKind, caption:str, claim_limit:str, surface_receipt:str) -> str:
        self._role(actor,{Role.CTRL}); item=self.ctrl_evidence_ledger[evidence_id]
        if item.disposition!=EvidenceDisposition.PENDING: raise InvariantError("CTRL evidence may be surfaced exactly once")
        if not isinstance(surface_kind,CtrlSurfaceKind): raise InvariantError("CTRL evidence requires an inline proof surface kind")
        visual=item.kind.lower() in {"imagegen","image","mockup","preview","screenshot","browser"} or item.locator.lower().endswith((".png",".jpg",".jpeg",".webp",".gif",".mp4",".webm"))
        if visual and surface_kind not in {CtrlSurfaceKind.INLINE_IMAGE,CtrlSurfaceKind.INLINE_RECORDING,CtrlSurfaceKind.INLINE_COMPARISON}: raise InvariantError("visual CTRL evidence requires an inline image, recording, or comparison")
        if not caption.strip() or not claim_limit.strip() or not surface_receipt.strip(): raise InvariantError("surfaced CTRL evidence requires a self-contained caption, claim limit, and external surface receipt")
        item.caption=caption.strip(); item.claim_limit=claim_limit.strip(); item.surface_kind=surface_kind; item.disposition=EvidenceDisposition.SURFACED; item.receipt=surface_receipt.strip()
        return item.receipt
    def withhold_ctrl_evidence(self, actor:Role, evidence_id:str, *, basis:WithholdBasis, reason:str) -> str:
        self._role(actor,{Role.CTRL}); item=self.ctrl_evidence_ledger[evidence_id]
        if item.disposition!=EvidenceDisposition.PENDING: raise InvariantError("CTRL evidence already has a disposition")
        if not isinstance(basis,WithholdBasis) or not reason.strip(): raise InvariantError("withheld CTRL evidence requires an objective basis and exact reason")
        item.withhold_basis=basis; item.reason=reason.strip(); item.disposition=EvidenceDisposition.WITHHELD; item.receipt=f"withheld:{basis.value}:{evidence_id}"
        return item.receipt
    def register_ctrl_decision_set(self, actor:Role, task_id:str, decision_id:str, candidate_ids:tuple[str,...], *, user_requested_all:bool=False) -> str:
        self._role(actor,{Role.CTRL})
        if task_id not in self.tasks: raise InvariantError("CTRL decision set requires a canonical task")
        if decision_id in self.ctrl_decision_sets: raise InvariantError("duplicate CTRL decision set identity")
        decision=CtrlDecisionSet(decision_id,task_id,candidate_ids,user_requested_all)
        if any(candidate not in self.ctrl_evidence_ledger or self.ctrl_evidence_ledger[candidate].task_id!=task_id or not self.ctrl_evidence_ledger[candidate].material for candidate in candidate_ids): raise InvariantError("CTRL decision candidates must be material evidence from the same task")
        self.ctrl_decision_sets[decision_id]=decision
        return decision_id
    def surface_ctrl_decision_gallery(self, actor:Role, decision_id:str, *, embedded_ids:tuple[str,...], labels_defects:dict[str,str], complete_inventory:tuple[str,...], omissions:dict[str,str]|None=None, surface_receipt:str) -> str:
        """Consolidate a decision set without treating its intentional final embeds as duplicates."""
        self._role(actor,{Role.CTRL}); decision=self.ctrl_decision_sets[decision_id]; omissions=omissions or {}
        if decision.surfaced: raise InvariantError("CTRL decision gallery may be surfaced exactly once")
        if not surface_receipt.strip().startswith("final:"): raise InvariantError("CTRL decision gallery requires a final-scoped external surface receipt")
        candidates=decision.candidate_ids; candidate_set=set(candidates); embedded_set=set(embedded_ids)
        if len(embedded_ids)!=len(embedded_set) or not embedded_set or not embedded_set.issubset(candidate_set): raise InvariantError("CTRL decision gallery embeds must be distinct candidates")
        if set(complete_inventory)!=candidate_set or len(complete_inventory)!=len(candidates): raise InvariantError("CTRL decision gallery requires the complete candidate inventory")
        if any(self.ctrl_evidence_ledger[candidate].disposition!=EvidenceDisposition.SURFACED for candidate in candidates): raise InvariantError("sequential candidate surfaces must exist before the final decision gallery")
        omitted=candidate_set-embedded_set
        representative_allowed=len(candidates)>12 and not decision.user_requested_all
        if omitted and not representative_allowed: raise InvariantError("CTRL decision gallery must embed every material candidate")
        if set(labels_defects)!=embedded_set or any(not value.strip() for value in labels_defects.values()): raise InvariantError("each embedded decision candidate requires a concise label and defect")
        if set(omissions)!=omitted or any(not value.strip() for value in omissions.values()): raise InvariantError("representative decision galleries require exact omissions")
        decision.embedded_ids=embedded_ids; decision.complete_inventory=complete_inventory; decision.labels_defects={key:value.strip() for key,value in labels_defects.items()}; decision.omissions={key:value.strip() for key,value in omissions.items()}; decision.receipt=surface_receipt.strip()
        return decision.receipt
    def advance_ctrl_phase(self, actor:Role, phase:str) -> None:
        self._role(actor,{Role.CTRL})
        if not phase.strip(): raise InvariantError("CTRL phase is required")
        pending=self.ctrl_feed_due(Role.CTRL)
        if pending: raise InvariantError(f"open CTRL evidence acceptance failure before phase advance: {','.join(pending)}")
        decisions=self._open_ctrl_decision_sets()
        if decisions: raise InvariantError(f"open CTRL decision gallery acceptance failure before phase advance: {','.join(decisions)}")
        uncovered=self._uncovered_ctrl_decision_candidates()
        if uncovered: raise InvariantError(f"material CTRL decision candidates require one surfaced final gallery before phase advance: {','.join(uncovered)}")
        self.ctrl_phase=phase.strip()
    def _open_ctrl_evidence(self, task_id:str|None=None) -> tuple[str,...]:
        return tuple(item.id for item in self.ctrl_evidence_ledger.values() if item.material and item.disposition==EvidenceDisposition.PENDING and (task_id is None or item.task_id==task_id))
    def _open_ctrl_decision_sets(self, task_id:str|None=None) -> tuple[str,...]:
        return tuple(item.id for item in self.ctrl_decision_sets.values() if not item.surfaced and (task_id is None or item.task_id==task_id))
    def _uncovered_ctrl_decision_candidates(self, task_id:str|None=None) -> tuple[str,...]:
        task_ids=(task_id,) if task_id is not None else tuple(dict.fromkeys(item.task_id for item in self.ctrl_evidence_ledger.values()))
        uncovered=[]
        for current_task_id in task_ids:
            candidates=tuple(item.id for item in self.ctrl_evidence_ledger.values() if item.task_id==current_task_id and item.material and item.steering and item.kind.lower() in {"imagegen","mockup","preview"})
            if len(candidates)<2: continue
            covered={candidate for decision in self.ctrl_decision_sets.values() if decision.task_id==current_task_id and decision.surfaced for candidate in decision.candidate_ids}
            uncovered.extend(candidate for candidate in candidates if candidate not in covered)
        return tuple(uncovered)
    def discover(self, artifact: str) -> list[str]:
        return [owner for identity,owner in self.artifact_index.items() if identity==artifact or identity.startswith(f"{artifact}@")]
    def review_depth(self, risk:int) -> str:
        base="light" if risk <= 1 else "standard" if risk <= 3 else "adversarial" if risk <= 4 else "specialist"
        return "standard" if base=="light" and self.mode==EfficiencyMode.MAX else base
    def record_telemetry(self, task_type:str, role:str, tier:int, outcome:str, *, model:str="", attempts:int=0, stalls:int=0, expert_uses:int=0, review_failures:int=0, review_cycles:int=0, productive:int=0, overhead:int=0, usage:int|None=None) -> None:
        self.telemetry.update({"tasks":self.telemetry.get("tasks",0)+1,"productive":self.telemetry.get("productive",0)+productive,"overhead":self.telemetry.get("overhead",0)+overhead})
        if usage is not None: self.telemetry["host_usage"]=self.telemetry.get("host_usage",0)+usage
        self._record("telemetry_events",{"task_type":task_type,"role":role,"tier":tier,"model":model,"attempts":attempts,"stalls":stalls,"expert_uses":expert_uses,"review_failures":review_failures,"review_cycles":review_cycles,"worker_count":len(self.workers),"outcome":outcome,"productive_execution":productive,"swarm_overhead":overhead,**({"host_usage":usage} if usage is not None else {})})
        self._record("events",("TELEMETRY",f"{task_type}:{role}:L{tier}:{outcome}"))
    def record_gate_receipt(self, actor:Role, task_id:str, receipt:GateReceipt, *, actor_id:str) -> None:
        """Retain external PASS/FAIL/TIMEOUT as UNVERIFIED; host supervision is not a runtime gate."""
        self._role(actor,{Role.LEAD}); t=self.tasks[task_id]; self._require_lane_actor(t,actor,actor_id); contract=t.acceptance_contract
        if not isinstance(receipt,GateReceipt): raise InvariantError("acceptance gates require a GateReceipt; watchdog alerts carry no authority")
        if contract is None: raise InvariantError("task requires an explicit acceptance contract")
        if contract.explicitly_empty: raise InvariantError("empty acceptance contract has no gates")
        if not t.incident_consultation_receipt: raise InvariantError("LEAD must consult matching unresolved incidents during the execution brief")
        if receipt.gate not in contract.required_gates: raise InvariantError("gate receipt must name a declared acceptance gate")
        if receipt.artifact!=contract.artifact: raise InvariantError("gate receipt artifact does not match acceptance contract")
        if receipt._authority is not None: raise InvariantError("runtime gate receipts cannot re-enter through the UNVERIFIED path")
        t.unverified_gate_receipts[receipt.gate]=receipt; t.gate_receipts.pop(receipt.gate,None)
        t.review_passed=False; t.acceptance_review_receipt=None; t.state=TaskState.ACTIVE
    def _gate_spec(self, contract:AcceptanceContract, gate:str) -> GateSpec:
        if contract.proof_plan is None: raise InvariantError("gate execution requires a proof plan")
        spec=next((item for item in contract.proof_plan.gates if item.id==gate),None)
        if spec is None: raise InvariantError("gate execution must name a declared proof-plan gate")
        return spec
    def run_gate(self, actor:Role, task_id:str, gate:str, argv:tuple[str,...], *, cwd:str, actor_id:str, timeout_seconds:int|None=None) -> GateReceipt:
        """Run a planned gate without a shell, preserving timeout and retry history."""
        self._role(actor,{Role.LEAD}); t=self.tasks[task_id]; self._require_lane_actor(t,actor,actor_id); contract=t.acceptance_contract
        if contract is None: raise InvariantError("task requires an explicit acceptance contract")
        if contract.explicitly_empty: raise InvariantError("empty acceptance contract has no gates")
        if not t.incident_consultation_receipt: raise InvariantError("LEAD must consult matching unresolved incidents during the execution brief")
        if gate not in contract.required_gates: raise InvariantError("gate execution must name a declared acceptance gate")
        if contract.artifact is None: raise InvariantError("gate execution requires an exact artifact")
        spec=self._gate_spec(contract,gate); plan=contract.proof_plan
        if plan is None: raise InvariantError("gate execution requires a proof plan")
        if any(requirement.scope is ReviewScope.PLAN for requirement in plan.reviews) and (t.plan_review_receipt is None or dict(t.plan_review_receipt.receipt).get("plan")!=plan.plan_digest): raise InvariantError("consequential proof requires PLAN PASS before gate execution")
        try: command=tuple(argv)
        except TypeError as error: raise InvariantError("gate execution requires argv") from error
        if not command or not isinstance(command[0],str) or not command[0] or any(not isinstance(part,str) for part in command): raise InvariantError("gate execution requires argv with a nonempty executable")
        if not plan.legacy and (not spec.argv or command!=spec.argv): raise InvariantError("gate execution argv must match the immutable proof-plan GateSpec")
        environment=dict(os.environ)
        if not plan.legacy and spec.environment_fingerprint!=_runtime_environment_fingerprint(environment): raise InvariantError("gate execution environment does not match the immutable proof plan")
        workdir=Path(cwd).resolve()
        if not workdir.is_dir(): raise InvariantError("gate execution directory must exist")
        before=contract.artifact.reobserve(contract.observation_root)
        if before!=contract.artifact: raise InvariantError("acceptance artifact changed before gate execution")
        timeout=spec.timeout_seconds if timeout_seconds is None else timeout_seconds
        if not isinstance(timeout,int) or timeout<1: raise InvariantError("gate timeout must be a positive integer")
        if not plan.legacy and timeout!=spec.timeout_seconds: raise InvariantError("gate timeout override does not match the immutable proof plan")
        started=int(time.time()); returncode=None; attempts:list[ProofOutcome]=[]; outcome=ProofOutcome.FAIL
        max_attempts=2 if spec.flake_policy is FlakePolicy.TYPED_TRANSIENT_ONCE else 1
        for attempt in range(max_attempts):
            infrastructure_failure=False
            try:
                returncode=_run_bounded_process(command,cwd=workdir,timeout=timeout,environment=environment); outcome=ProofOutcome.PASS if returncode==0 else ProofOutcome.FAIL
            except subprocess.TimeoutExpired: outcome=ProofOutcome.TIMEOUT; infrastructure_failure=True
            except OSError: outcome=ProofOutcome.FAIL; infrastructure_failure=True
            attempts.append(outcome)
            if outcome is ProofOutcome.PASS or not infrastructure_failure or attempt+1>=max_attempts: break
        after=contract.artifact.reobserve(contract.observation_root)
        if after!=before and outcome is ProofOutcome.PASS: outcome=ProofOutcome.FAIL
        if attempts[-1] is not outcome: attempts[-1]=outcome
        gate_spec_digest=_gate_spec_digest(spec)
        receipt=GateReceipt(gate,contract.artifact,outcome,command,before.observables,after.observables,returncode,plan.plan_digest,gate_spec_digest,_sha256_text(contract.artifact.key()),spec.input_closure_digest,spec.environment_fingerprint,started,int(time.time()),tuple(attempts),ProofStability.UNSTABLE if len(set(attempts))>1 else ProofStability.STABLE,spec.proof_class,_sha256_text(f"{task_id}:{actor_id}:{plan.plan_digest}"))
        object.__setattr__(receipt,"_authority",self._gate_capability); object.__setattr__(receipt,"_bound_task_id",task_id); t.gate_receipts[gate]=receipt; t.unverified_gate_receipts.pop(gate,None)
        if outcome is not ProofOutcome.PASS:
            t.review_passed=False; t.acceptance_review_receipt=None; t.state=TaskState.ACTIVE
        return receipt
    def _record_host_external_proof(self, actor:Role, task_id:str, gate:str, *, actor_id:str, evidence_digest:str, observed_at:int, host_signature:str) -> GateReceipt:
        """Host-adapter seam for provider, deployed, device, and human observations."""
        raise InvariantError("HOST_AUTHORITY_REQUIRED: external proof stays UNVERIFIED until an isolated host verifier records it")
    def adopt_gate_receipt(self, actor:Role, target_task_id:str, source_task_id:str, gate:str, *, actor_id:str) -> GateReceipt:
        """Adopt only a current runtime-authoritative receipt with the same exact proof key."""
        self._role(actor,{Role.LEAD}); target=self.tasks[target_task_id]; source=self.tasks[source_task_id]; self._require_lane_actor(target,actor,actor_id)
        target_contract=target.acceptance_contract; source_contract=source.acceptance_contract
        if target_contract is None or source_contract is None or target_contract.artifact is None or target_contract.proof_plan is None: raise InvariantError("receipt adoption requires exact planned contracts")
        receipt=source.gate_receipts.get(gate); target_spec=self._gate_spec(target_contract,gate)
        source_plan=source_contract.proof_plan; source_spec=self._gate_spec(source_contract,gate)
        if source_plan is None or target_spec.cache_policy is CachePolicy.NEVER: raise InvariantError("receipt adoption is disabled for this proof plan")
        source_current=source_contract.artifact.reobserve(source_contract.observation_root) if source_contract.artifact is not None else None
        if source_current is None or receipt is None or not receipt.current_for(self._gate_capability,source_task_id,gate,source_contract.artifact,source_current,source_plan,source_spec,int(time.time())): raise InvariantError("receipt adoption requires a current stable runtime PASS")
        if receipt.plan_digest!=target_contract.proof_plan.plan_digest or receipt.gate_spec_digest!=_gate_spec_digest(target_spec) or receipt.artifact!=target_contract.artifact or receipt.input_closure_digest!=target_spec.input_closure_digest or receipt.environment_fingerprint!=target_spec.environment_fingerprint or receipt.proof_class is not target_spec.proof_class: raise InvariantError("receipt adoption key does not match the target proof plan")
        current=target_contract.artifact.reobserve(target_contract.observation_root)
        if current!=target_contract.artifact or receipt.before!=current.observables or receipt.after!=current.observables: raise InvariantError("receipt adoption requires current exact artifact observations")
        adopted=replace(receipt,authority_context_digest=_sha256_text(f"{target_task_id}:{actor_id}:{target_contract.proof_plan.plan_digest}")); object.__setattr__(adopted,"_authority",self._gate_capability); object.__setattr__(adopted,"_bound_task_id",target_task_id); target.gate_receipts[gate]=adopted; target.unverified_gate_receipts.pop(gate,None); return adopted
    def consult_incidents(self, actor:Role, task_id:str, ledger:IncidentLedger, *, artifact:str, scope:str, actor_id:str) -> tuple[IncidentRecord,...]:
        self._role(actor,{Role.LEAD}); t=self.tasks[task_id]; self._require_lane_actor(t,actor,actor_id); incidents=ledger.unresolved(artifact=artifact,scope=scope); t.incident_consultation_receipt=f"{artifact}:{scope}:{','.join(item.incidentId for item in incidents) or 'none'}"; return incidents
    def record_post_handoff_incident(self, actor:Role, task_id:str, ledger:IncidentLedger, record:IncidentRecord, *, material:bool, actor_id:str) -> bool:
        self._role(actor,{Role.LEAD}); t=self.tasks[task_id]; self._require_lane_actor(t,actor,actor_id)
        if not material: return False
        ledger.append(record); t.correction_pending=True; t.findings.append(f"incident:{record.incidentId}"); return True
    def open_gates(self, task_id:str) -> tuple[str,...]:
        """Re-observe current state and return gates without runtime-executed PASS proof."""
        t=self.tasks[task_id]; self._validate_task_acceptance(t); contract=t.acceptance_contract
        if contract is None: raise InvariantError("task requires an explicit acceptance contract")
        if contract.explicitly_empty: return ()
        if contract.artifact is None: return contract.required_gates
        try: current=contract.artifact.reobserve(contract.observation_root)
        except InvariantError: return contract.required_gates
        plan=contract.proof_plan
        if plan is None: return contract.required_gates
        now=int(time.time())
        return tuple(gate for gate in contract.required_gates if (receipt:=t.gate_receipts.get(gate)) is None or not receipt.current_for(self._gate_capability,task_id,gate,contract.artifact,current,plan,self._gate_spec(contract,gate),now))
    def open_claims(self, task_id:str) -> tuple[str,...]:
        task=self.tasks[task_id]; contract=task.acceptance_contract
        if contract is None or contract.proof_plan is None or contract.artifact is None: return ()
        open_gates=set(self.open_gates(task_id)); current=tuple(receipt for gate,receipt in task.gate_receipts.items() if gate not in open_gates)
        return tuple(coverage.claim.name for coverage in contract.proof_plan.claim_matrix if not any(receipt.proof_class is coverage.claim.proof_class for receipt in current))
    def _acceptance_ready(self, task:Task) -> bool:
        evidence=task.acceptance_review_receipt; contract=task.acceptance_contract
        try: self._validate_task_acceptance(task)
        except InvariantError: return False
        if contract is None: return False
        if contract.explicitly_empty: return bool(task.review_passed and task.reviewer and evidence and evidence.scope is ReviewScope.ACCEPTANCE and evidence.reviewer==task.reviewer and evidence.artifact is None)
        if contract.proof_plan is None: return False
        final_scopes={requirement.scope for requirement in contract.proof_plan.reviews if requirement.scope in {ReviewScope.ACCEPTANCE,ReviewScope.COMPOSED}}
        review_ok=not final_scopes or bool(task.review_passed and task.reviewer and evidence and evidence.scope in final_scopes and evidence.reviewer==task.reviewer and evidence.artifact==contract.artifact and evidence.plan_digest in {"",contract.proof_plan.plan_digest})
        plan_required=any(requirement.scope is ReviewScope.PLAN for requirement in contract.proof_plan.reviews)
        plan_ok=not plan_required or bool(task.plan_review_receipt and task.plan_review_receipt.artifact==contract.artifact and dict(task.plan_review_receipt.receipt).get("plan")==contract.proof_plan.plan_digest)
        return bool(review_ok and plan_ok and not self.open_gates(task.id) and not self.open_claims(task.id))
    def review(self, actor: Role, task_id: str, evidence: ReviewEvidence|str, passed: bool, finding:str="") -> None:
        self._role(actor,{Role.REVIEW}); t=self.tasks[task_id]
        if isinstance(evidence,str):
            if passed: raise InvariantError("legacy passed=True cannot grant acceptance; submit typed ACCEPTANCE review evidence")
            legacy_strategy=ReviewStrategy(finding) if finding in {item.value for item in ReviewStrategy} else ReviewStrategy.LIGHT
            evidence=ReviewEvidence(legacy_strategy,evidence,True,None,(finding,) if finding else ())
        if not isinstance(evidence,ReviewEvidence): raise InvariantError("review requires ReviewEvidence; watchdog alerts carry no review authority")
        if not evidence.independent or evidence.reviewer in {t.creator,t.owner}: raise InvariantError("creator cannot be sole independent reviewer")
        if evidence.strategy in {ReviewStrategy.ADVERSARIAL,ReviewStrategy.SPECIALIST} and (not isinstance(evidence.artifact,ArtifactIdentity) or not evidence.artifact.base or not evidence.artifact.revision): raise InvariantError("strong review evidence requires typed artifact identity")
        if evidence.strategy==ReviewStrategy.SPECIALIST and not dict(evidence.receipt).get("specialist"): raise InvariantError("specialist review requires specialist receipt")
        levels={ReviewStrategy.LIGHT:1,ReviewStrategy.STANDARD:2,ReviewStrategy.ADVERSARIAL:3,ReviewStrategy.SPECIALIST:4}
        required=max((ReviewStrategy(self.review_depth(t.risk)),t.architecture_review_floor,t.security_review_floor,MODE_POLICY[self.mode]["review_floor"]),key=levels.get); t.review_strategy=required.value
        if passed and levels[evidence.strategy]<levels[required]: raise InvariantError("review evidence does not meet required strategy")
        t.reviewer=evidence.reviewer
        if passed and evidence.scope is ReviewScope.PLAN:
            self._validate_task_acceptance(t); contract=t.acceptance_contract
            if contract is None or contract.proof_plan is None or not any(requirement.scope is ReviewScope.PLAN for requirement in contract.proof_plan.reviews): raise InvariantError("plan review is not required by the current proof plan")
            if evidence.artifact!=contract.artifact or dict(evidence.receipt).get("plan")!=contract.proof_plan.plan_digest or evidence.plan_digest not in {"",contract.proof_plan.plan_digest}: raise InvariantError("PLAN PASS must bind the exact artifact and proof-plan digest")
            t.plan_review_receipt=evidence; t.review_passed=False; t.state=TaskState.ACTIVE
        elif passed and evidence.scope in {ReviewScope.ACCEPTANCE,ReviewScope.COMPOSED}:
            self._validate_task_acceptance(t)
            if t.acceptance_contract is None: raise InvariantError("acceptance review requires an explicit acceptance contract")
            if t.acceptance_contract.explicitly_empty:
                if evidence.scope is not ReviewScope.ACCEPTANCE or evidence.artifact is not None or not dict(evidence.receipt).get("acceptance"): raise InvariantError("empty NON_CODE acceptance requires an independent acceptance receipt without an artifact")
                t.review_passed=True; t.acceptance_review_receipt=evidence; t.state=TaskState.REVIEW
                return
            plan=t.acceptance_contract.proof_plan
            if plan is None: raise InvariantError("acceptance review requires a proof plan")
            allowed={requirement.scope for requirement in plan.reviews if requirement.scope in {ReviewScope.ACCEPTANCE,ReviewScope.COMPOSED}}
            if evidence.scope not in allowed: raise InvariantError("review scope is not required by the current proof plan")
            if any(requirement.scope is ReviewScope.PLAN for requirement in plan.reviews) and (t.plan_review_receipt is None or dict(t.plan_review_receipt.receipt).get("plan")!=plan.plan_digest): raise InvariantError("final acceptance requires current PLAN PASS")
            if evidence.artifact!=t.acceptance_contract.artifact: raise InvariantError("acceptance review artifact does not match acceptance contract")
            open_gates=self.open_gates(task_id)
            if open_gates: raise InvariantError(f"acceptance review requires PASS receipts for all gates: {','.join(open_gates)}")
            open_claims=self.open_claims(task_id)
            if open_claims: raise InvariantError(f"acceptance review requires current matching proof for declared claims: {','.join(open_claims)}")
            receipt_key="composed" if evidence.scope is ReviewScope.COMPOSED else "acceptance"
            if not dict(evidence.receipt).get(receipt_key): raise InvariantError("final review requires an independent exact-scope receipt")
            if evidence.plan_digest not in {"",plan.plan_digest}: raise InvariantError("final review proof-plan digest mismatch")
            t.review_passed=True; t.acceptance_review_receipt=evidence; t.state=TaskState.REVIEW
        elif passed:
            t.review_passed=False; t.acceptance_review_receipt=None; t.state=TaskState.ACTIVE
        else: t.review_passed=False; t.acceptance_review_receipt=None; t.state=TaskState.ACTIVE; t.findings.extend(evidence.findings or ("review failed",))
    def lease(self, actor: Role, surface: str, holder: str) -> None:
        self._role(actor,{Role.CTRL})
        if surface in self.leases and self.leases[surface]!=holder: raise InvariantError("surface already leased")
        self.leases[surface]=holder
    def retire(self, actor: Role, worker_id: str, replacement: str|None=None, *, lessons:list[HiveRecord]|None=None, now:int=0, watchdog_review:WatchdogChangeReview|None=None) -> None:
        self._role(actor,{Role.LEAD}); w=self.workers[worker_id]
        if not replacement or replacement not in self.workers or self.workers[replacement].lead!=w.lead: self._request_guard(owner=w.lead)
        self._require_watchdog_change([task for task in self.tasks.values() if task.owner==worker_id],"retire",worker_id,watchdog_review)
        if w.task_ids and (not replacement or replacement not in self.workers or self.workers[replacement].state==WorkerState.RETIRED): raise InvariantError("retirement needs a live replacement for owned tasks")
        flushed=(lessons or [])[:3] if self.hive_enabled else []
        for lesson in flushed: self.remember(Role.LEAD,lesson,now)
        if replacement:
            target=self.workers[replacement]
            if len(target.task_ids)+len(w.task_ids)>self.wip_limit: raise InvariantError("replacement WIP limit")
            for task_id in w.task_ids: self.tasks[task_id].owner=replacement; target.task_ids.add(task_id)
        w.state=WorkerState.RETIRED; w.archive={"tasks":sorted(w.task_ids),"lane":w.lane,"hive_flush":[item.id for item in flushed]}; w.task_ids.clear()
        if self.hive_enabled: self.telemetry["hive_retirement_flushes"]=self.telemetry.get("hive_retirement_flushes",0)+len(flushed)
    def collapse(self, actor: Role, lead: str, *, watchdog_review:WatchdogChangeReview|None=None) -> Depth:
        """Retire idle capacity and remove a lead when only one isolated task remains."""
        self._role(actor,{Role.CTRL}); active=[t for t in self.tasks.values() if t.state not in {TaskState.COMPLETE,TaskState.BACKLOG,TaskState.ARCHIVED,TaskState.ARCHIVED_STALE}]
        if len(active) > 1: return Depth.WORKSTREAM
        self._require_watchdog_change([task for task in self.tasks.values() if task.owning_lead_id==lead],"collapse",lead,watchdog_review)
        def shrink():
            for worker in self.workers.values():
                if worker.lead == lead and not worker.task_ids and worker.state != WorkerState.RETIRED:
                    worker.state=WorkerState.RETIRED; worker.archive={"tasks":[],"lane":worker.lane}
            self.topology.discard(lead)
        if len(active) <= 1: self._request_guard(owner=lead,action=shrink); return Depth.ATOMIC
        return Depth.WORKSTREAM
    def complete(self, actor: Role, task_id: str, integration_ok: bool, architecture_ok: bool, now: int, *, actor_id:str) -> None:
        self._role(actor,{Role.LEAD,Role.CTRL}); t=self.tasks[task_id]; self._require_lane_actor(t,actor,actor_id); self._validate_task_acceptance(t)
        self._require_subagent_contract(t)
        pending=self._open_ctrl_evidence(task_id)
        if pending: raise InvariantError(f"open CTRL evidence acceptance failure: {','.join(pending)}")
        decisions=self._open_ctrl_decision_sets(task_id)
        if decisions: raise InvariantError(f"open CTRL decision gallery acceptance failure: {','.join(decisions)}")
        uncovered=self._uncovered_ctrl_decision_candidates(task_id)
        if uncovered: raise InvariantError(f"material CTRL decision candidates require one surfaced final gallery: {','.join(uncovered)}")
        if not self._acceptance_ready(t) or not integration_ok or not architecture_ok: raise InvariantError("completion requires exact-artifact acceptance review and integration/architecture gates")
        def finish():
            t.state=TaskState.COMPLETE; t.completed_at=now
            for waiter in self.tasks.values():
                if waiter.state==TaskState.WAITING and waiter.waiting_on==task_id: waiter.state=TaskState.ACTIVE; waiter.waiting_on=None
            worker=self.workers.get(t.owner)
            if worker and worker.context.get("affinity",0)>0 and all(self.tasks[item].state in {TaskState.COMPLETE,TaskState.ARCHIVED,TaskState.ARCHIVED_STALE} for item in worker.task_ids): worker.state=WorkerState.WARM
            if worker: worker.task_ids.discard(task_id)
        self._request_guard(task_id=task_id,require_accepted=True,action=finish)
    def stale(self, actor: Role, task_id: str, reason: str, *, now: int=0, superseded_by: str|None=None, promote: list[str]|None=None) -> None:
        self._role(actor,{Role.CTRL,Role.ARCHITECT,Role.LEAD}); t=self.tasks[task_id]
        if not reason: raise InvariantError("stale tasks require reason provenance")
        def change(): t.__dict__.update(state=TaskState.STALE,stale_at=now,stale_reason=reason,superseded_by=superseded_by); t.promoted.extend(promote or [])
        self._request_guard(task_id=task_id,action=change)
    def groom(self, actor: Role, now: int, policy: dict[str,int]) -> list[str]:
        """Mechanical archive only; archive preserves task provenance and knowledge."""
        self._role(actor,{Role.CTRL}); archived=[]
        delays={ReviewValue.NONE:policy["no_review_archive_delay"],ReviewValue.LOW:policy["low_review_retention"],ReviewValue.HIGH:policy["high_review_retention"]}
        for t in self.tasks.values():
            if not self.archive_eligible(t): continue
            has_active_dependent=any(other.waiting_on==t.id and other.state in {TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW} for other in self.tasks.values())
            if t.state==TaskState.STALE and not has_active_dependent and t.stale_at is not None and now-t.stale_at >= policy["stale_task_archive_delay"]:
                self._request_guard(task_id=t.id,action=lambda:(setattr(t,"state",TaskState.ARCHIVED_STALE),setattr(t,"archived_at",now))); archived.append(t.id)
            elif t.state==TaskState.COMPLETE and t.completed_at is not None and now-t.completed_at >= delays[t.review_value]:
                self._request_guard(task_id=t.id,action=lambda:(setattr(t,"state",TaskState.ARCHIVED),setattr(t,"archived_at",now))); archived.append(t.id)
        reasons={"completed":0,"stale":0}; ages={"fresh":0,"aged":0}
        for task_id in archived:
            t=self.tasks[task_id]; started=t.completed_at if t.completed_at is not None else t.stale_at if t.stale_at is not None else now; reasons["stale" if t.state==TaskState.ARCHIVED_STALE else "completed"]+=1; ages["fresh" if now-started<30 else "aged"]+=1
        self.telemetry.update({"archived":self.telemetry.get("archived",0)+len(archived),"pins":sum(t.review_value==ReviewValue.PINNED for t in self.tasks.values()),"active":sum(t.state in {TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW} for t in self.tasks.values()),"stale":sum(t.state==TaskState.STALE for t in self.tasks.values()),"restores":self.telemetry.get("restores",0),"extensions":sum(t.extensions for t in self.tasks.values()),"completion_to_archive":{task_id:now-(self.tasks[task_id].completed_at if self.tasks[task_id].completed_at is not None else self.tasks[task_id].stale_at if self.tasks[task_id].stale_at is not None else now) for task_id in archived},"archive_reasons":reasons,"age_buckets":ages}); return archived
    def archive_eligible(self, task:Task) -> bool:
        owner=self.workers.get(task.owner)
        base=lambda: not self._open_ctrl_evidence(task.id) and not self._open_ctrl_decision_sets(task.id) and not self._uncovered_ctrl_decision_candidates(task.id) and task.review_value!=ReviewValue.PINNED and not any((task.active_goal,task.handoff_active,task.correction_pending,task.user_choice_pending,task.ambiguous,task.state==TaskState.REVIEW,owner is not None and owner.state!=WorkerState.RETIRED and task.id in owner.task_ids)) and not any(other.waiting_on==task.id and other.state in {TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW} for other in self.tasks.values())
        try: return bool(self._request_guard(task_id=task.id,action=base))
        except InvariantError: return False
    def restore(self, actor:Role, task_id:str, reason:str) -> None:
        self._role(actor,{Role.CTRL,Role.LEAD}); t=self.tasks[task_id]
        if t.state not in {TaskState.ARCHIVED,TaskState.ARCHIVED_STALE} or not reason: raise InvariantError("restore requires archived task and provenance")
        history=t.archive or {}; history.setdefault("archive_history",[]).append({"archived_at":t.archived_at,"reason":reason,"state":t.state.value}); t.archive=history; t.state=TaskState.ACTIVE; t.archived_at=None; t.findings.append(f"restored:{reason}"); self.telemetry["restores"]=self.telemetry.get("restores",0)+1
    def groom_hive(self, actor:Role, now:int, *, orphaned_sources:set[str]|None=None) -> None:
        """Mechanical compact-memory lifecycle; PURGED records retain provenance only."""
        self._role(actor,{Role.CTRL}); orphaned_sources=orphaned_sources or set()
        for record in self.hive.values():
            if record.status==HiveStatus.ACTIVE and (record.source in orphaned_sources or record.retention=="expired" or record.provenance.get("superseded_by")):
                record.status=HiveStatus.ARCHIVED; self.telemetry["hive_archived"]=self.telemetry.get("hive_archived",0)+1
            elif record.status==HiveStatus.ARCHIVED:
                record.status=HiveStatus.PURGEABLE; self.telemetry["hive_purgeable"]=self.telemetry.get("hive_purgeable",0)+1
            elif record.status==HiveStatus.PURGEABLE:
                record.status=HiveStatus.PURGED; record.content=""; record.reference=""; self.telemetry["hive_purged"]=self.telemetry.get("hive_purged",0)+1
        self._hive_counts()
    def correction(self, incident_id:str, **facts:object) -> CorrectionDecision:
        """Consume at most one fix-forward receipt for a stable correction incident."""
        if not incident_id.strip(): raise InvariantError("correction incident identity is required")
        decision=correction_decision(**facts,fix_forward_consumed=incident_id in self.correction_receipts)
        if decision==CorrectionDecision.FIX_FORWARD:
            if len(self.correction_receipts)>=64: return CorrectionDecision.ESCALATE if bool(facts.get("material")) else CorrectionDecision.CONTINUE
            self.correction_receipts[incident_id]=None
        return decision
    def ctrl_event(self, event: str, task_id: str, material_revision:str|int=0, *, outcome:str="", evidence_id:str="", next_checkpoint:str="") -> str|None:
        category={"RESULT":"result","DECISION":"decision","DEADLOCK":"blocker","REVIEW_FAIL":"blocker","SCOPE_ESCALATION":"blocker","RELEASE":"release","HANDOFF":"handoff","ACCEPTANCE":"acceptance"}.get(event)
        if not category:
            if event in {"PROGRESS","HEARTBEAT","RECOVERY"}: raise InvariantError("coordination-only telemetry cannot enter the CTRL feed")
            return None
        task=self.tasks.get(task_id)
        if task is None: raise InvariantError("CTRL event requires a canonical task")
        if category=="acceptance" and (task.state is not TaskState.COMPLETE or not self._acceptance_ready(task)): raise InvariantError("CTRL acceptance requires a completed exact-artifact acceptance receipt")
        evidence=self.ctrl_evidence_ledger.get(evidence_id)
        if not outcome.strip() or evidence is None or evidence.task_id!=task_id or evidence.disposition!=EvidenceDisposition.SURFACED or not evidence.caption or not evidence.claim_limit or not evidence.receipt: raise InvariantError("CTRL event requires a surfaced proof and human-readable outcome")
        if category=="blocker" and not next_checkpoint.strip(): raise InvariantError("blocker CTRL event requires an exact recovery checkpoint")
        receipt=(category,str(material_revision))
        if task.ctrl_event_receipt==receipt: return None
        task.ctrl_event_receipt=receipt
        rendered=f"{outcome.strip()} Proof: {evidence.caption} Claim limit: {evidence.claim_limit}"
        return f"{rendered} Next: {next_checkpoint.strip()}" if next_checkpoint.strip() else rendered
    def project_complete(self, actor: Role, integration_ok: bool, architecture_ok: bool) -> bool:
        self._role(actor,{Role.CTRL})
        terminal=lambda t: t.state==TaskState.BACKLOG or (t.state in {TaskState.COMPLETE,TaskState.ARCHIVED} and self._acceptance_ready(t)) or (t.state==TaskState.ARCHIVED_STALE and t.superseded_by in self.tasks and self.tasks[t.superseded_by].state==TaskState.COMPLETE and self._acceptance_ready(self.tasks[t.superseded_by]))
        try:
            audit=self.request_audit(0)
            return not audit.orphaned_ids and bool(self._request_guard(all_open=True,action=lambda:not self._open_ctrl_evidence() and not self._open_ctrl_decision_sets() and not self._uncovered_ctrl_decision_candidates() and integration_ok and architecture_ok and all(terminal(t) for t in self.tasks.values())))
        except (InvariantError,KeyError,TypeError,ValueError): return False


def derive_workflow_graph(swarm:Swarm) -> WorkflowGraph:
    """Project recorded runtime receipts without re-observing artifacts or granting authority."""
    nodes:dict[str,WorkflowNode]={"ctrl:CTRL":WorkflowNode("ctrl:CTRL","CTRL")}
    edges:set[tuple[str,str,str]]=set()
    diagnostics:set[str]=set()
    for lead in sorted(swarm.topology):
        node_id=f"lead:{lead}"; nodes[node_id]=WorkflowNode(node_id,"LEAD",owner="CTRL"); edges.add(("ctrl:CTRL",node_id,"routes"))
    for worker_id,worker in sorted(swarm.workers.items()):
        node_id=f"worker:{worker_id}"; nodes[node_id]=WorkflowNode(node_id,"WORKER",worker.state.value,worker.lead)
        source="ctrl:CTRL" if worker.lead==Role.CTRL.value else f"lead:{worker.lead}"
        if source not in nodes:
            nodes[source]=WorkflowNode(source,"LEAD",owner="CTRL"); diagnostics.add(f"implicit-recorded-lead:{worker.lead}")
        edges.add((source,node_id,"leads"))
    for task_id,task in sorted(swarm.tasks.items()):
        node_id=f"task:{task_id}"; proof_state="UNVERIFIED"
        nodes[node_id]=WorkflowNode(node_id,"TASK",task.state.value,task.owner,"UNVERIFIED")
        owner=f"worker:{task.owner}" if task.owner in swarm.workers else "ctrl:CTRL" if task.owner==Role.CTRL.value else ""
        if owner: edges.add((owner,node_id,"owns"))
        else: diagnostics.add(f"missing-owner:{task_id}:{task.owner}")
        if task.waiting_on:
            target=f"task:{task.waiting_on}"
            if task.waiting_on not in swarm.tasks: diagnostics.add(f"missing-dependency:{task_id}:{task.waiting_on}")
            else: edges.add((node_id,target,"waits_for"))
        contract=task.acceptance_contract
        if contract is not None and contract.artifact is not None:
            logical_identity=json.dumps((contract.artifact.base,contract.artifact.revision,contract.artifact.purpose),separators=(",",":"),ensure_ascii=True).encode("utf-8")
            artifact_node=f"artifact:{sha256(logical_identity).hexdigest()}"; nodes.setdefault(artifact_node,WorkflowNode(artifact_node,"ARTIFACT",contract.artifact.purpose,acceptance="UNVERIFIED")); edges.add((node_id,artifact_node,"accepts_artifact"))
        if contract is not None and contract.proof_plan is not None:
            plan=contract.proof_plan; plan_node=f"proof-plan:{task_id}:{plan.plan_digest}"; nodes[plan_node]=WorkflowNode(plan_node,"PROOF_PLAN",plan.tier.value,task.owning_lead_id,"UNVERIFIED"); edges.add((node_id,plan_node,"uses_plan"))
            for coverage in plan.claim_matrix:
                claim_id=_sha256_text(f"{coverage.claim.name}:{coverage.claim.proof_class.value}"); claim_node=f"claim:{task_id}:{claim_id}"; nodes[claim_node]=WorkflowNode(claim_node,"CLAIM",f"{coverage.claim.proof_class.value}:{coverage.status.value}",acceptance="UNVERIFIED"); edges.add((plan_node,claim_node,"covers_claim"))
        for gate in (() if contract is None else contract.required_gates):
            receipt=task.gate_receipts.get(gate); outcome=receipt.outcome.value if receipt is not None and receipt._authority is swarm._gate_capability else "UNVERIFIED"
            gate_node=f"gate:{task_id}:{gate}"; nodes[gate_node]=WorkflowNode(gate_node,"GATE",outcome,owner=task.owning_lead_id,acceptance="UNVERIFIED"); edges.add((node_id,gate_node,"has_gate"))
        if task.acceptance_review_receipt is not None:
            review=task.acceptance_review_receipt; review_node=f"review:{task_id}:{review.scope.value}"; nodes[review_node]=WorkflowNode(review_node,"REVIEW",review.scope.value,review.reviewer,"UNVERIFIED"); edges.add((node_id,review_node,"has_review"))
        if task.plan_review_receipt is not None:
            review=task.plan_review_receipt; review_node=f"review:{task_id}:{review.scope.value}"; nodes[review_node]=WorkflowNode(review_node,"REVIEW",review.scope.value,review.reviewer,"UNVERIFIED"); edges.add((node_id,review_node,"has_review"))
        for specialist_id,profession in sorted(task.specialist_professions.items()):
            specialist_node=f"specialist:{specialist_id}"; nodes.setdefault(specialist_node,WorkflowNode(specialist_node,profession,owner="CTRL")); edges.add((specialist_node,node_id,"advises"))
    if swarm.request_store is not None:
        try:
            audit=swarm.request_audit(0)
            for record in audit.records:
                node_id=f"request:{record.id}"; task_id=f"task:{record.task_id}"; nodes[node_id]=WorkflowNode(node_id,"REQUEST",record.state.value,record.accepted_owner,"UNVERIFIED"); edges.add((node_id,task_id,"tracks")) if task_id in nodes else diagnostics.add("request-missing-task")
            if audit.provisional_stage_ids: diagnostics.add("request-provisional-stage")
        except InvariantError: diagnostics.add("request-ledger-invalid")
    for start in sorted(swarm.tasks):
        path=[]; current=start
        while current in swarm.tasks and current not in path and swarm.tasks[current].waiting_on:
            path.append(current); current=swarm.tasks[current].waiting_on or ""
        if current in path:
            cycle=path[path.index(current):]
            rotations=[tuple(cycle[index:]+cycle[:index]) for index in range(len(cycle))]
            canonical=min(rotations); diagnostics.add(f"dependency-cycle:{'->'.join((*canonical,canonical[0]))}")
    graph_edges=tuple(WorkflowEdge(*edge) for edge in sorted(edges,key=lambda edge:(edge[0],edge[1],edge[2])))
    return WorkflowGraph(tuple(nodes[key] for key in sorted(nodes)),graph_edges,tuple(sorted(diagnostics)))

class _HostAuthorityBroker:
    """Host-owned signer; Swarm retains only the corresponding public verifier."""
    def __init__(self, swarm:Swarm, private_key:int): self._swarm_ref=weakref.ref(swarm); self.__private_key=private_key
    def _bound_swarm(self) -> Swarm|None: return self._swarm_ref()
    def mint_user_event(self, *, receipt:str, operation:CtrlOperation, source_ctrl_id:str, target_objective_digest:str, target_scope_digest:str, target_identity:str, issued_at:int, host_event_digest:str) -> HostUserEvent:
        event=HostUserEvent(receipt,operation,source_ctrl_id,target_objective_digest,target_scope_digest,target_identity,issued_at,host_event_digest); message=_authority_message("CTRL_USER_EVENT",(event.receipt,event.operation.value,event.source_ctrl_id,event.target_objective_digest,event.target_scope_digest,event.target_identity,event.issued_at,event.event_digest)); object.__setattr__(event,"_signature",_authority_sign(self.__private_key,message)); return event
    def record_external_proof(self, actor:Role, task_id:str, gate:str, *, actor_id:str, evidence_digest:str, observed_at:int) -> GateReceipt:
        swarm=self._bound_swarm()
        if swarm is None: raise InvariantError("host authority broker is detached")
        return swarm._record_host_external_proof(actor,task_id,gate,actor_id=actor_id,evidence_digest=evidence_digest,observed_at=observed_at,host_signature="")
