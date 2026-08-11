"""Deterministic SWARM state transitions; host task storage remains external."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    CTRL="CTRL"; MOTHER="MOTHER"; ARCHITECT="ARCHITECT"; LEAD="LEAD"; DOER="DOER"; EXPERT="EXPERT"; REVIEW="REVIEW"
class TaskState(StrEnum):
    ACTIVE="ACTIVE"; WAITING="WAITING"; REVIEW="REVIEW"; COMPLETE="COMPLETE"; STALE="STALE"; ARCHIVED="ARCHIVED"; ARCHIVED_STALE="ARCHIVED_STALE"; BACKLOG="BACKLOG"
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
class SubagentException(StrEnum):
    CAPACITY="capacity"; COLLISION="collision"; SAFETY="safety"; WHOLE_TASK_COST="whole_task_cost"

class InvariantError(ValueError): pass

def heartbeat_action(*, owner_update:bool, material_change:bool, unchanged_updates:int, recovery_attempts:int, stall_after_updates:int) -> str:
    """Single pure heartbeat classifier shared by runtime compatibility adapters."""
    if material_change or not owner_update or unchanged_updates < stall_after_updates: return "observe"
    return "recover" if recovery_attempts==0 else "release"

@dataclass(frozen=True)
class VersionedReference:
    name:str; version:int; kind:str
@dataclass(frozen=True)
class ArtifactIdentity:
    base:str; revision:str; purpose:str
    def __post_init__(self):
        if not all(isinstance(value,str) and value.strip() for value in (self.base,self.revision,self.purpose)): raise InvariantError("artifact identity fields must be nonempty")
    def key(self)->str: return f"{self.base}@{self.revision}:{self.purpose}"
@dataclass(frozen=True)
class ArtifactProvenance:
    id:str; source:str
    def __post_init__(self):
        if not all(isinstance(value,str) and value.strip() for value in (self.id,self.source)): raise InvariantError("artifact provenance fields must be nonempty")
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
    dependency_edges:tuple[tuple[str,str],...]=(); cross_lane_integration:bool=False; portfolio_acceptance:bool=False; ctrl_can_cheaply_accept:bool=True; architecture_gate:bool=False
    def __post_init__(self):
        if not self.objective.strip() or not self.accepting_route.strip() or not self.artifacts or not self.mutable_surfaces or not self.ownership_lanes: raise InvariantError("topology facts require objective, artifact, mutable surface, accepting route, and owner")
        lanes=set(self.ownership_lanes)
        if any(left not in lanes or right not in lanes or left==right for left,right in self.dependency_edges): raise InvariantError("dependency edges require distinct declared owners")
    def same_ownership_route(self, other:"TopologyFacts") -> bool:
        return (self.objective,frozenset(item.key() for item in self.artifacts),frozenset(self.mutable_surfaces),self.accepting_route)==(other.objective,frozenset(item.key() for item in other.artifacts),frozenset(other.mutable_surfaces),other.accepting_route)
    def requires_mother(self) -> bool:
        return len(set(self.ownership_lanes))>1 and bool(self.dependency_edges) and self.cross_lane_integration and self.portfolio_acceptance and not self.ctrl_can_cheaply_accept
class ReviewStrategy(StrEnum): LIGHT="light"; STANDARD="standard"; ADVERSARIAL="adversarial"; SPECIALIST="specialist"
@dataclass(frozen=True)
class ReviewEvidence:
    strategy:ReviewStrategy; reviewer:str; independent:bool; artifact:ArtifactIdentity|None; findings:tuple[str,...]=(); receipt:tuple[tuple[str,str],...]=()
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
    ATOMIC="CTRL_DOER"; SIMPLE="CTRL_MOTHER_DOER"; WORKSTREAM="CTRL_MOTHER_LEAD_DOER"; PROJECT="CTRL_MOTHER_ARCHITECT_LEADS_DOERS"
class EfficiencyMode(StrEnum): CONSERVE="CONSERVE"; BALANCED="BALANCED"; FAST="FAST"; MAX="MAX"
MODE_POLICY={EfficiencyMode.CONSERVE:{"parallel":1,"depth_bias":1,"review_floor":ReviewStrategy.LIGHT},EfficiencyMode.BALANCED:{"parallel":2,"depth_bias":2,"review_floor":ReviewStrategy.LIGHT},EfficiencyMode.FAST:{"parallel":3,"depth_bias":3,"review_floor":ReviewStrategy.STANDARD},EfficiencyMode.MAX:{"parallel":4,"depth_bias":4,"review_floor":ReviewStrategy.STANDARD}}

def initial_tier(*, risk:int, uncertainty:int, blast_radius:int, family:str="general", mode:EfficiencyMode=EfficiencyMode.BALANCED) -> int:
    weight=risk+uncertainty+blast_radius+({"security":2,"architecture":1}.get(family,0))
    bias={EfficiencyMode.CONSERVE:0,EfficiencyMode.BALANCED:1,EfficiencyMode.FAST:2,EfficiencyMode.MAX:3}[mode]
    return min(3, max(1, 1 + int(weight>=3) + int(weight+bias>=6)))

def choose_depth(facts:TopologyFacts) -> Depth:
    """Materialize portfolio authority only when the portfolio predicate is true."""
    if not facts.requires_mother(): return Depth.ATOMIC
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
    completed_at: int|None=None; stale_at: int|None=None; archived_at: int|None=None; stale_reason: str|None=None; superseded_by: str|None=None; promoted: list[str]=field(default_factory=list); extensions: int=0; review_passed: bool=False; risk:int=1; review_strategy:str="light"; architecture_review_floor:ReviewStrategy=ReviewStrategy.LIGHT; security_review_floor:ReviewStrategy=ReviewStrategy.LIGHT; artifacts:dict[ArtifactIdentity|str,str]=field(default_factory=dict); artifact_justifications:dict[str,ArtifactJustification]=field(default_factory=dict); artifact_provenance:dict[str,ArtifactProvenance]=field(default_factory=dict); archive:dict[str,object]=field(default_factory=dict); active_goal:bool=False; handoff_active:bool=False; correction_pending:bool=False; user_choice_pending:bool=False; ambiguous:bool=False; topology_receipt:tuple[str,...]=(); ctrl_event_receipt:tuple[str,str]|None=None; subagent_receipt:str=""; subagent_exception:SubagentException|None=None; subagent_exception_reason:str=""

@dataclass
class Worker:
    id: str; lead: str; lane: int; state: WorkerState=WorkerState.SPAWNED; task_ids: set[str]=field(default_factory=set); archive: dict[str, object]=field(default_factory=dict); context:dict[str,object]=field(default_factory=dict)

@dataclass
class Swarm:
    architecture_version: int=1; contract_versions: dict[str,int]=field(default_factory=dict); topology: set[str]=field(default_factory=set)
    workers: dict[str,Worker]=field(default_factory=dict); tasks: dict[str,Task]=field(default_factory=dict); leases: dict[str,str]=field(default_factory=dict); events: list[tuple[str,str]]=field(default_factory=list); telemetry: dict[str,object]=field(default_factory=dict); telemetry_events:list[dict[str,object]]=field(default_factory=list); artifact_index:dict[str,str]=field(default_factory=dict); provenance_index:dict[str,str]=field(default_factory=dict); ctrl_evidence_ledger:dict[str,CtrlEvidence]=field(default_factory=dict); ctrl_decision_sets:dict[str,CtrlDecisionSet]=field(default_factory=dict); ctrl_phase:str="intake"; hive:dict[str,HiveRecord]=field(default_factory=dict); hive_enabled:bool=True; heartbeat_enabled:bool=True; heartbeat_stall_after:int=2; heartbeat_latch:set[str]=field(default_factory=set); correction_receipts:dict[str,None]=field(default_factory=dict); lane_width:int=3; wip_limit:int=3; efficiency_ledger:list[dict[str,str]]=field(default_factory=list); mode:EfficiencyMode=EfficiencyMode.BALANCED
    @classmethod
    def from_config(cls, config: dict) -> "Swarm":
        return cls(lane_width=config["coordination"]["preferred_lane_width"], wip_limit=config["efficiency"]["doer_wip_limit"], mode=EfficiencyMode(config["efficiency"]["mode"]), hive_enabled=config.get("hive",{}).get("enabled",True), heartbeat_enabled=config["monitoring"].get("heartbeat_enabled",True), heartbeat_stall_after=config["recovery"]["stall_after_updates"])

    def _role(self, actor: Role, allowed: set[Role]) -> None:
        if actor not in allowed: raise InvariantError(f"{actor} cannot perform this transition")
    def _worker_identity(self, worker_id:str) -> None:
        if not isinstance(worker_id,str) or not worker_id.strip(): raise InvariantError("mutable worker identity is required")
        if worker_id.strip().upper() in {role.value for role in Role}: raise InvariantError("authority role identity cannot own mutable worker execution")
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
    def add_lead(self, actor: Role, lead: str) -> None:
        self._role(actor,{Role.MOTHER}); self.topology.add(lead)
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
        self._role(actor,{Role.CTRL}); self._require_subagent_contract(task); self._worker_identity(task.owner)
        if task.owner in self.workers or task.id in self.tasks: raise InvariantError("atomic ownership already exists")
        task.topology_receipt=("CTRL","DOER","atomic:isolated"); self.workers[task.owner]=Worker(task.owner,"CTRL",1,WorkerState.ACTIVE,{task.id}); self.tasks[task.id]=task
    def start_simple(self, actor:Role, task:Task) -> None:
        """MOTHER may add stateful direct DOER ownership without a LEAD."""
        self._role(actor,{Role.MOTHER}); self._require_subagent_contract(task); self._worker_identity(task.owner)
        if task.owner in self.workers or task.id in self.tasks: raise InvariantError("simple ownership already exists")
        task.topology_receipt=("CTRL","MOTHER","DOER","simple:stateful"); self.workers[task.owner]=Worker(task.owner,"MOTHER",1,WorkerState.ACTIVE,{task.id}); self.tasks[task.id]=task
    def reuse_warm(self, actor:Role, task:Task, *, architecture:dict[str,int], affinity:int) -> str|None:
        self._role(actor,{Role.LEAD,Role.MOTHER,Role.CTRL}); self._require_subagent_contract(task)
        for worker in self.workers.values():
            self._worker_identity(worker.id)
            context=worker.context
            if worker.state==WorkerState.WARM and context.get("affinity",0)>=affinity and context.get("architecture",architecture)==architecture:
                worker.state=WorkerState.ACTIVE; worker.task_ids.add(task.id); task.owner=worker.id; self.tasks[task.id]=task; return worker.id
        return None
    def package_context(self, actor:Role, worker_id:str, package:ContextPackage) -> None:
        self._role(actor,{Role.LEAD}); worker=self.workers[worker_id]
        hive=package.hive if self.hive_enabled else ()
        worker.context={"goal":package.goal,"architecture":package.architecture,"dependencies":package.dependencies,"artifacts":package.artifacts,"acceptance":package.acceptance,"history":package.history,"hive":hive,"transfer_cost":package.transfer_cost-len(package.hive)+len(hive),"affinity":worker.context.get("affinity",1),"bloat":False,"stale":False,"stalls":0}
    def remember(self, actor:Role, record:HiveRecord, now:int) -> str|None:
        self._role(actor,{Role.MOTHER,Role.ARCHITECT,Role.LEAD,Role.DOER})
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
        if not base or not revision or not purpose: raise InvariantError("artifact identity must be complete")
        return ArtifactIdentity(base,revision,purpose)
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
        self._role(actor,{Role.LEAD}); self._require_subagent_contract(task); self._worker_identity(task.owner); w=self.workers.get(task.owner)
        if not w or w.state==WorkerState.RETIRED or len(w.task_ids)>=self.wip_limit: raise InvariantError("owner unavailable or at WIP limit")
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
    def heartbeat(self, actor:Role, task_id:str, *, meaningful_progress:bool, owner_update:bool=True, unchanged_updates:int=1, recovery_attempts:int|None=None, enabled:bool|None=None) -> str|None:
        self._role(actor,{Role.MOTHER}); t=self.tasks[task_id]
        enabled=self.heartbeat_enabled if enabled is None else enabled
        if not enabled or meaningful_progress: self.heartbeat_latch.discard(task_id); return None
        if t.user_choice_pending or t.state in {TaskState.WAITING,TaskState.REVIEW,TaskState.COMPLETE,TaskState.ARCHIVED,TaskState.ARCHIVED_STALE,TaskState.BACKLOG}: return None
        if t.state!=TaskState.ACTIVE: return None
        action=heartbeat_action(owner_update=owner_update,material_change=False,unchanged_updates=unchanged_updates,recovery_attempts=t.recovery_attempts,stall_after_updates=self.heartbeat_stall_after)
        if action=="observe": return None
        if action=="release": self._record("events",("RELEASE",f"{task_id}:unchanged blocker")); return f"{task_id}:release/blocker"
        if task_id in self.heartbeat_latch: return None
        self.heartbeat_latch.add(task_id); self._record("events",("MOTHER_WAKE",f"{task_id}:stall/actionable")); return f"{task_id}:stall/actionable"
    def context_decision(self, *, affinity:int|None=None, bloat:bool|None=None, stale:bool|None=None, stalls:int|None=None, worker_id:str|None=None, replacement:str|None=None) -> str:
        context=self.workers[worker_id].context if worker_id else {}; affinity=context.get("affinity",affinity or 0); bloat=context.get("bloat",bloat or False); stale=context.get("stale",stale or False); stalls=context.get("stalls",stalls or 0)
        result="retire" if bloat or stale or stalls>1 or affinity==0 else "reuse"; self._record("efficiency_ledger",{"kind":"context","decision":result,"reason":"bounded_spine"})
        if result=="retire" and worker_id: self.retire(Role.LEAD,worker_id,replacement)
        return result
    def change_architecture(self, actor: Role, contracts: dict[str,int], now:int=0) -> None:
        self._role(actor,{Role.ARCHITECT}); self.architecture_version+=1; self.contract_versions.update(contracts)
        for task in self.tasks.values():
            if task.state not in {TaskState.COMPLETE,TaskState.BACKLOG,TaskState.ARCHIVED,TaskState.ARCHIVED_STALE} and (task.architecture_version != self.architecture_version or any(task.contracts.get(k,0)!=v for k,v in contracts.items())): task.state=TaskState.STALE; task.stale_reason="architecture or contract version changed"; task.stale_at=now
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
        self._role(actor,{Role.LEAD,Role.MOTHER}); t=self.tasks[task_id]
        if not dimension or t.recovery_attempts>=1: raise InvariantError("recovery budget exhausted; release blocker")
        t.recovery_dimensions.add(dimension); t.recovery_attempts=1; self._record("events",("RECOVERY",task_id))
    def scope_finding(self, actor:Role, task_id:str, evidence:str, *, material:bool) -> bool:
        """Preserve a direct invariant violation; unrelated opportunity changes nothing."""
        self._role(actor,{Role.DOER,Role.LEAD,Role.ARCHITECT,Role.MOTHER}); t=self.tasks[task_id]
        if not material: return False
        if not evidence: raise InvariantError("material scope finding needs evidence")
        t.findings.append(f"scope:{evidence}"); t.correction_pending=True; t.state=TaskState.WAITING; self._record("events",("SCOPE_ESCALATION",task_id)); return True
    def expert(self, actor: Role, task_id: str) -> None:
        self._role(actor,{Role.DOER,Role.LEAD,Role.ARCHITECT,Role.MOTHER}); self._record("events",("EXPERT",task_id))
    def set_intelligence_floor(self, actor: Role, task_id: str, tier: int) -> None:
        self._role(actor,{Role.ARCHITECT}); self.tasks[task_id].contracts["intelligence_floor"]=tier
    def complexity_mismatch(self, actor: Role, task_id: str, observed_tier: int) -> None:
        self._role(actor,{Role.DOER}); self.tasks[task_id].contracts["complexity_mismatch"]=observed_tier; self._record("events",("MISMATCH",task_id))
    def add_artifact(self, actor: Role, task_id: str, artifact: ArtifactIdentity, risk: str="", *, source:str|None=None, justification:ArtifactJustification|None=None, provenance:ArtifactProvenance|None=None) -> None:
        self._role(actor,{Role.DOER}); t=self.tasks[task_id]
        identity=self._register_artifact(t,artifact,source,justification,provenance); t.evidence.append(identity); t.findings.extend([risk] if risk else [])
    def register_ctrl_evidence(self, actor:Role, task_id:str, evidence_id:str, kind:str, locator:str, *, material:bool=True, steering:bool=True) -> str:
        """Register each reviewable result; a path is provenance, never a surface receipt."""
        self._role(actor,{Role.CTRL,Role.MOTHER,Role.ARCHITECT,Role.LEAD,Role.DOER,Role.REVIEW})
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
    def review(self, actor: Role, task_id: str, evidence: ReviewEvidence|str, passed: bool, finding:str="") -> None:
        self._role(actor,{Role.REVIEW}); t=self.tasks[task_id]
        if isinstance(evidence,str):
            legacy_strategy=ReviewStrategy(finding) if finding in {item.value for item in ReviewStrategy} else ReviewStrategy.LIGHT
            evidence=ReviewEvidence(legacy_strategy,evidence,True,ArtifactIdentity("legacy","v1","review"),(finding,) if finding else ())
        if not evidence.independent or evidence.reviewer in {t.creator,t.owner}: raise InvariantError("creator cannot be sole independent reviewer")
        if evidence.strategy in {ReviewStrategy.ADVERSARIAL,ReviewStrategy.SPECIALIST} and (not isinstance(evidence.artifact,ArtifactIdentity) or not evidence.artifact.base or not evidence.artifact.revision): raise InvariantError("strong review evidence requires typed artifact identity")
        if evidence.strategy==ReviewStrategy.SPECIALIST and not dict(evidence.receipt).get("specialist"): raise InvariantError("specialist review requires specialist receipt")
        levels={ReviewStrategy.LIGHT:1,ReviewStrategy.STANDARD:2,ReviewStrategy.ADVERSARIAL:3,ReviewStrategy.SPECIALIST:4}
        required=max((ReviewStrategy(self.review_depth(t.risk)),t.architecture_review_floor,t.security_review_floor,MODE_POLICY[self.mode]["review_floor"]),key=levels.get); t.review_strategy=required.value
        if passed and levels[evidence.strategy]<levels[required]: raise InvariantError("review evidence does not meet required strategy")
        t.reviewer=evidence.reviewer
        if passed: t.review_passed=True; t.state=TaskState.REVIEW
        else: t.state=TaskState.ACTIVE; t.findings.extend(evidence.findings or ("review failed",))
    def lease(self, actor: Role, surface: str, holder: str) -> None:
        self._role(actor,{Role.MOTHER})
        if surface in self.leases and self.leases[surface]!=holder: raise InvariantError("surface already leased")
        self.leases[surface]=holder
    def retire(self, actor: Role, worker_id: str, replacement: str|None=None, *, lessons:list[HiveRecord]|None=None, now:int=0) -> None:
        self._role(actor,{Role.LEAD}); w=self.workers[worker_id]
        if w.task_ids and (not replacement or replacement not in self.workers or self.workers[replacement].state==WorkerState.RETIRED): raise InvariantError("retirement needs a live replacement for owned tasks")
        flushed=(lessons or [])[:3] if self.hive_enabled else []
        for lesson in flushed: self.remember(Role.LEAD,lesson,now)
        if replacement:
            target=self.workers[replacement]
            if len(target.task_ids)+len(w.task_ids)>self.wip_limit: raise InvariantError("replacement WIP limit")
            for task_id in w.task_ids: self.tasks[task_id].owner=replacement; target.task_ids.add(task_id)
        w.state=WorkerState.RETIRED; w.archive={"tasks":sorted(w.task_ids),"lane":w.lane,"hive_flush":[item.id for item in flushed]}; w.task_ids.clear()
        if self.hive_enabled: self.telemetry["hive_retirement_flushes"]=self.telemetry.get("hive_retirement_flushes",0)+len(flushed)
    def collapse(self, actor: Role, lead: str) -> Depth:
        """Retire idle capacity and remove a lead when only one isolated task remains."""
        self._role(actor,{Role.MOTHER}); active=[t for t in self.tasks.values() if t.state not in {TaskState.COMPLETE,TaskState.BACKLOG,TaskState.ARCHIVED,TaskState.ARCHIVED_STALE}]
        if len(active) > 1: return Depth.WORKSTREAM
        for worker in self.workers.values():
            if worker.lead == lead and not worker.task_ids and worker.state != WorkerState.RETIRED:
                worker.state=WorkerState.RETIRED; worker.archive={"tasks":[],"lane":worker.lane}
        if len(active) <= 1: self.topology.discard(lead); return Depth.ATOMIC if not active else Depth.SIMPLE
        return Depth.WORKSTREAM
    def complete(self, actor: Role, task_id: str, integration_ok: bool, architecture_ok: bool, now: int) -> None:
        self._role(actor,{Role.MOTHER}); t=self.tasks[task_id]
        self._require_subagent_contract(t)
        pending=self._open_ctrl_evidence(task_id)
        if pending: raise InvariantError(f"open CTRL evidence acceptance failure: {','.join(pending)}")
        decisions=self._open_ctrl_decision_sets(task_id)
        if decisions: raise InvariantError(f"open CTRL decision gallery acceptance failure: {','.join(decisions)}")
        uncovered=self._uncovered_ctrl_decision_candidates(task_id)
        if uncovered: raise InvariantError(f"material CTRL decision candidates require one surfaced final gallery: {','.join(uncovered)}")
        if not t.review_passed or not t.reviewer or not integration_ok or not architecture_ok: raise InvariantError("completion requires independent review and integration/architecture gates")
        t.state=TaskState.COMPLETE; t.completed_at=now
        for waiter in self.tasks.values():
            if waiter.state==TaskState.WAITING and waiter.waiting_on==task_id: waiter.state=TaskState.ACTIVE; waiter.waiting_on=None; self.heartbeat_latch.discard(waiter.id)
        worker=self.workers.get(t.owner)
        if worker and worker.context.get("affinity",0)>0 and all(self.tasks[item].state in {TaskState.COMPLETE,TaskState.ARCHIVED,TaskState.ARCHIVED_STALE} for item in worker.task_ids): worker.state=WorkerState.WARM
        if worker: worker.task_ids.discard(task_id)
    def stale(self, actor: Role, task_id: str, reason: str, *, now: int=0, superseded_by: str|None=None, promote: list[str]|None=None) -> None:
        self._role(actor,{Role.MOTHER,Role.ARCHITECT,Role.LEAD}); t=self.tasks[task_id]
        if not reason: raise InvariantError("stale tasks require reason provenance")
        t.state=TaskState.STALE; t.stale_at=now; t.stale_reason=reason; t.superseded_by=superseded_by; t.promoted.extend(promote or [])
    def groom(self, actor: Role, now: int, policy: dict[str,int]) -> list[str]:
        """Mechanical archive only; archive preserves task provenance and knowledge."""
        self._role(actor,{Role.MOTHER}); archived=[]
        delays={ReviewValue.NONE:policy["no_review_archive_delay"],ReviewValue.LOW:policy["low_review_retention"],ReviewValue.HIGH:policy["high_review_retention"]}
        for t in self.tasks.values():
            if not self.archive_eligible(t): continue
            has_active_dependent=any(other.waiting_on==t.id and other.state in {TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW} for other in self.tasks.values())
            if t.state==TaskState.STALE and not has_active_dependent and t.stale_at is not None and now-t.stale_at >= policy["stale_task_archive_delay"]:
                t.state=TaskState.ARCHIVED_STALE; t.archived_at=now; archived.append(t.id)
            elif t.state==TaskState.COMPLETE and t.completed_at is not None and now-t.completed_at >= delays[t.review_value]:
                t.state=TaskState.ARCHIVED; t.archived_at=now; archived.append(t.id)
        reasons={"completed":0,"stale":0}; ages={"fresh":0,"aged":0}
        for task_id in archived:
            t=self.tasks[task_id]; started=t.completed_at if t.completed_at is not None else t.stale_at if t.stale_at is not None else now; reasons["stale" if t.state==TaskState.ARCHIVED_STALE else "completed"]+=1; ages["fresh" if now-started<30 else "aged"]+=1
        self.telemetry.update({"archived":self.telemetry.get("archived",0)+len(archived),"pins":sum(t.review_value==ReviewValue.PINNED for t in self.tasks.values()),"active":sum(t.state in {TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW} for t in self.tasks.values()),"stale":sum(t.state==TaskState.STALE for t in self.tasks.values()),"restores":self.telemetry.get("restores",0),"extensions":sum(t.extensions for t in self.tasks.values()),"completion_to_archive":{task_id:now-(self.tasks[task_id].completed_at if self.tasks[task_id].completed_at is not None else self.tasks[task_id].stale_at if self.tasks[task_id].stale_at is not None else now) for task_id in archived},"archive_reasons":reasons,"age_buckets":ages}); return archived
    def archive_eligible(self, task:Task) -> bool:
        owner=self.workers.get(task.owner)
        return not self._open_ctrl_evidence(task.id) and not self._open_ctrl_decision_sets(task.id) and not self._uncovered_ctrl_decision_candidates(task.id) and task.review_value!=ReviewValue.PINNED and not any((task.active_goal,task.handoff_active,task.correction_pending,task.user_choice_pending,task.ambiguous,task.state==TaskState.REVIEW,owner is not None and owner.state!=WorkerState.RETIRED and task.id in owner.task_ids)) and not any(other.waiting_on==task.id and other.state in {TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW} for other in self.tasks.values())
    def restore(self, actor:Role, task_id:str, reason:str) -> None:
        self._role(actor,{Role.MOTHER,Role.LEAD}); t=self.tasks[task_id]
        if t.state not in {TaskState.ARCHIVED,TaskState.ARCHIVED_STALE} or not reason: raise InvariantError("restore requires archived task and provenance")
        history=t.archive or {}; history.setdefault("archive_history",[]).append({"archived_at":t.archived_at,"reason":reason,"state":t.state.value}); t.archive=history; t.state=TaskState.ACTIVE; t.archived_at=None; t.findings.append(f"restored:{reason}"); self.telemetry["restores"]=self.telemetry.get("restores",0)+1
    def groom_hive(self, actor:Role, now:int, *, orphaned_sources:set[str]|None=None) -> None:
        """Mechanical compact-memory lifecycle; PURGED records retain provenance only."""
        self._role(actor,{Role.MOTHER}); orphaned_sources=orphaned_sources or set()
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
            if event in {"PROGRESS","HEARTBEAT","MOTHER_WAKE","RECOVERY"}: raise InvariantError("coordination-only telemetry cannot enter the CTRL feed")
            return None
        task=self.tasks.get(task_id)
        if task is None: raise InvariantError("CTRL event requires a canonical task")
        evidence=self.ctrl_evidence_ledger.get(evidence_id)
        if not outcome.strip() or evidence is None or evidence.task_id!=task_id or evidence.disposition!=EvidenceDisposition.SURFACED or not evidence.caption or not evidence.claim_limit or not evidence.receipt: raise InvariantError("CTRL event requires a surfaced proof and human-readable outcome")
        if category=="blocker" and not next_checkpoint.strip(): raise InvariantError("blocker CTRL event requires an exact recovery checkpoint")
        receipt=(category,str(material_revision))
        if task.ctrl_event_receipt==receipt: return None
        task.ctrl_event_receipt=receipt
        rendered=f"{outcome.strip()} Proof: {evidence.caption} Claim limit: {evidence.claim_limit}"
        return f"{rendered} Next: {next_checkpoint.strip()}" if next_checkpoint.strip() else rendered
    def project_complete(self, actor: Role, integration_ok: bool, architecture_ok: bool) -> bool:
        self._role(actor,{Role.MOTHER})
        return not self._open_ctrl_evidence() and not self._open_ctrl_decision_sets() and not self._uncovered_ctrl_decision_candidates() and integration_ok and architecture_ok and all(t.state in {TaskState.COMPLETE,TaskState.ARCHIVED,TaskState.BACKLOG} or (t.state==TaskState.ARCHIVED_STALE and t.superseded_by in self.tasks and self.tasks[t.superseded_by].state==TaskState.COMPLETE) for t in self.tasks.values())
