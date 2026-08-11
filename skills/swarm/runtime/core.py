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
    SPAWNED="SPAWNED"; ACTIVE="ACTIVE"; DRAINING="DRAINING"; RETIRED="RETIRED"

class InvariantError(ValueError): pass

@dataclass(frozen=True)
class VersionedReference:
    name:str; version:int; kind:str
@dataclass(frozen=True)
class ArtifactIdentity:
    base:str; revision:str; purpose:str
    def key(self)->str: return f"{self.base}@{self.revision}:{self.purpose}"
class ReviewStrategy(StrEnum): LIGHT="light"; STANDARD="standard"; ADVERSARIAL="adversarial"; SPECIALIST="specialist"
@dataclass(frozen=True)
class ReviewEvidence:
    strategy:ReviewStrategy; reviewer:str; independent:bool; artifact:ArtifactIdentity|None; findings:tuple[str,...]=(); receipt:tuple[tuple[str,str],...]=()

@dataclass(frozen=True)
class ContextPackage:
    goal:str; architecture:dict[str,int]; dependencies:tuple[str,...]; artifacts:tuple[str,...]; acceptance:tuple[str,...]; history:tuple[str,...]; transfer_cost:int
    @classmethod
    def build(cls, *, goal:str, architecture:dict[str,int], dependencies:list[VersionedReference|str], artifacts:list[VersionedReference|str], acceptance:list[str], history:list[VersionedReference|str], budget:int) -> "ContextPackage":
        if budget < 1: raise InvariantError("context budget must be positive")
        current=lambda item: not isinstance(item,VersionedReference) or architecture.get(item.name,item.version)==item.version
        dependencies=[item for item in dependencies if current(item)]; artifacts=[item for item in artifacts if current(item)]; history=[item for item in history if current(item)]
        render=lambda item: f"{item.name}:v{item.version}" if isinstance(item,VersionedReference) else item
        dependencies=[render(item) for item in dependencies]; artifacts=[render(item) for item in artifacts]; history=[render(item) for item in history]
        spine=[goal,*acceptance]; optional=[*dependencies,*artifacts,*history]
        if len(spine)>budget: raise InvariantError("budget cannot admit canonical spine")
        kept=optional[:max(0,budget-len(spine))]
        return cls(goal,architecture,tuple(x for x in dependencies if x in kept),tuple(x for x in artifacts if x in kept),tuple(acceptance),tuple(x for x in history if x in kept),len(kept))

class Depth(StrEnum):
    ATOMIC="CTRL_DOER"; SIMPLE="CTRL_MOTHER_DOER"; WORKSTREAM="CTRL_MOTHER_LEAD_DOER"; PROJECT="CTRL_MOTHER_ARCHITECT_LEADS_DOERS"
class EfficiencyMode(StrEnum): CONSERVE="CONSERVE"; BALANCED="BALANCED"; FAST="FAST"; MAX="MAX"
MODE_POLICY={EfficiencyMode.CONSERVE:{"parallel":1,"depth_bias":1,"review_floor":ReviewStrategy.LIGHT},EfficiencyMode.BALANCED:{"parallel":2,"depth_bias":2,"review_floor":ReviewStrategy.LIGHT},EfficiencyMode.FAST:{"parallel":3,"depth_bias":3,"review_floor":ReviewStrategy.STANDARD},EfficiencyMode.MAX:{"parallel":4,"depth_bias":4,"review_floor":ReviewStrategy.STANDARD}}

def initial_tier(*, risk:int, uncertainty:int, blast_radius:int, family:str="general", mode:EfficiencyMode=EfficiencyMode.BALANCED) -> int:
    weight=risk+uncertainty+blast_radius+({"security":2,"architecture":1}.get(family,0))
    bias={EfficiencyMode.CONSERVE:0,EfficiencyMode.BALANCED:1,EfficiencyMode.FAST:2,EfficiencyMode.MAX:3}[mode]
    return min(3, max(1, 1 + int(weight>=3) + int(weight+bias>=6)))

def choose_depth(*, scope: int, architecture_impact: bool=False, independent_tasks: int=1, dependencies: int=0, uncertainty: int=0, blast_radius: int=0, specialisations: int=1, useful_parallelism: int=1, coordination_overhead: int=0, mode:EfficiencyMode=EfficiencyMode.BALANCED) -> Depth:
    """Choose infrastructure only when its reliability benefit exceeds its cost."""
    if scope <= 1 and independent_tasks <= 1 and not architecture_impact and dependencies == uncertainty == blast_radius == 0: return Depth.ATOMIC
    if architecture_impact and (independent_tasks >= 3 or specialisations >= 2): return Depth.PROJECT
    if independent_tasks >= 2 or dependencies >= 2 or specialisations >= 2 or useful_parallelism >= MODE_POLICY[mode]["parallel"]:
        return Depth.WORKSTREAM if coordination_overhead < 3 else Depth.SIMPLE
    return Depth.SIMPLE

@dataclass
class Task:
    id: str; owner: str; creator: str; architecture_version: int; contracts: dict[str,int]
    state: TaskState=TaskState.ACTIVE; waiting_on: str|None=None; reviewer: str|None=None; findings: list[str]=field(default_factory=list)
    evidence: list[str]=field(default_factory=list); recovery_dimensions: set[str]=field(default_factory=set); review_value: ReviewValue=ReviewValue.NONE
    completed_at: int|None=None; stale_at: int|None=None; archived_at: int|None=None; stale_reason: str|None=None; superseded_by: str|None=None; promoted: list[str]=field(default_factory=list); extensions: int=0; review_passed: bool=False; risk:int=1; review_strategy:str="light"; architecture_review_floor:ReviewStrategy=ReviewStrategy.LIGHT; security_review_floor:ReviewStrategy=ReviewStrategy.LIGHT; artifacts:dict[ArtifactIdentity|str,str]=field(default_factory=dict); artifact_justifications:dict[str,str]=field(default_factory=dict); archive:dict[str,object]=field(default_factory=dict)

@dataclass
class Worker:
    id: str; lead: str; lane: int; state: WorkerState=WorkerState.SPAWNED; task_ids: set[str]=field(default_factory=set); archive: dict[str, object]=field(default_factory=dict); context:dict[str,object]=field(default_factory=dict)

@dataclass
class Swarm:
    architecture_version: int=1; contract_versions: dict[str,int]=field(default_factory=dict); topology: set[str]=field(default_factory=set)
    workers: dict[str,Worker]=field(default_factory=dict); tasks: dict[str,Task]=field(default_factory=dict); leases: dict[str,str]=field(default_factory=dict); events: list[tuple[str,str]]=field(default_factory=list); telemetry: dict[str,object]=field(default_factory=dict); telemetry_events:list[dict[str,object]]=field(default_factory=list); artifact_index:dict[str,str]=field(default_factory=dict); lane_width:int=3; wip_limit:int=3; efficiency_ledger:list[dict[str,str]]=field(default_factory=list); mode:EfficiencyMode=EfficiencyMode.BALANCED
    @classmethod
    def from_config(cls, config: dict) -> "Swarm":
        return cls(lane_width=config["coordination"]["preferred_lane_width"], wip_limit=config["efficiency"]["doer_wip_limit"], mode=EfficiencyMode(config["efficiency"]["mode"]))

    def _role(self, actor: Role, allowed: set[Role]) -> None:
        if actor not in allowed: raise InvariantError(f"{actor} cannot perform this transition")
    def add_lead(self, actor: Role, lead: str) -> None:
        self._role(actor,{Role.MOTHER}); self.topology.add(lead)
    def add_worker(self, actor: Role, worker: Worker) -> None:
        self._role(actor,{Role.LEAD});
        if worker.lead not in self.topology or not 1 <= worker.lane <= self.lane_width: raise InvariantError("worker requires a known lead and configured lane")
        if sum(w.lead==worker.lead and w.state!=WorkerState.RETIRED for w in self.workers.values()) >= self.lane_width: raise InvariantError("lead capacity reached")
        self.workers[worker.id]=worker
    def package_context(self, actor:Role, worker_id:str, package:ContextPackage) -> None:
        self._role(actor,{Role.LEAD}); worker=self.workers[worker_id]
        worker.context={"goal":package.goal,"architecture":package.architecture,"dependencies":package.dependencies,"artifacts":package.artifacts,"acceptance":package.acceptance,"history":package.history,"transfer_cost":package.transfer_cost,"affinity":worker.context.get("affinity",1),"bloat":False,"stale":False,"stalls":0}
    def _artifact(self, artifact:ArtifactIdentity|str) -> ArtifactIdentity:
        if isinstance(artifact,ArtifactIdentity): return artifact
        try:
            base,tail=artifact.rsplit("@",1); revision,purpose=tail.split(":",1)
        except ValueError as exc: raise InvariantError("artifact identity must be base@revision:purpose") from exc
        if not base or not revision or not purpose: raise InvariantError("artifact identity must be complete")
        return ArtifactIdentity(base,revision,purpose)
    def _check_artifact(self, task:Task, artifact:ArtifactIdentity|str, source:str|None, justification:str|None, *, pending:set[str]|None=None) -> tuple[ArtifactIdentity,str]:
        identity=self._artifact(artifact); key=identity.key()
        if pending is None: pending=set()
        if key in self.artifact_index or key in pending: raise InvariantError("canonical artifact identity already exists")
        if identity.purpose in {"verification","uncertainty"} and (not source or justification!=identity.purpose): raise InvariantError("justified duplicate requires source and purpose")
        return identity,key
    def _register_artifact(self, task:Task, artifact:ArtifactIdentity|str, source:str|None, justification:str|None) -> str:
        _,key=self._check_artifact(task,artifact,source,justification)
        self.artifact_index[key]=task.id; task.artifacts[key]=source or task.id
        return key
    def assign(self, actor: Role, task: Task) -> None:
        self._role(actor,{Role.LEAD}); w=self.workers.get(task.owner)
        if not w or w.state==WorkerState.RETIRED or len(w.task_ids)>=self.wip_limit: raise InvariantError("owner unavailable or at WIP limit")
        staged=[]; pending=set()
        for artifact,source in task.artifacts.items():
            identity,key=self._check_artifact(task,artifact,source,task.artifact_justifications.get(self._artifact(artifact).key()),pending=pending); staged.append((identity,source,task.artifact_justifications.get(key))); pending.add(key)
        task.artifacts={}
        for artifact,source,justification in staged: self._register_artifact(task,artifact,source,justification)
        self.tasks[task.id]=task; w.task_ids.add(task.id)
    def should_spawn(self, *, independent: bool, critical_path: bool, duplicate_artifact: str|None=None, verification: bool=False, contention:bool=False) -> bool:
        allowed=independent and (critical_path or verification) and (not duplicate_artifact or verification) and sum(w.state!=WorkerState.RETIRED for w in self.workers.values()) < MODE_POLICY[self.mode]["parallel"]
        reason="allow:verification" if verification else "allow:critical_path" if allowed else "refuse:independent=false" if not independent else "refuse:contention" if contention else "refuse:duplicate" if duplicate_artifact else "refuse:noncritical"
        self.efficiency_ledger.append({"kind":"spawn","decision":"allow" if allowed else "refuse","reason":reason})
        return allowed
    def route(self, *, family:str, risk:int, uncertainty:int, blast_radius:int, architect_floor:int=1, historical_floor:int=1, mode:EfficiencyMode|None=None) -> int:
        selected=mode or self.mode; tier=max(architect_floor,historical_floor,initial_tier(risk=risk,uncertainty=uncertainty,blast_radius=blast_radius,family=family,mode=selected)); self.efficiency_ledger.append({"kind":"route","family":family,"tier":str(tier),"reason":"expected_total_accepted_cost"}); return tier
    def dedup(self, identity:str, *, verification:bool=False, uncertainty:bool=False) -> bool:
        found=bool(self.discover(identity)); allowed=not found or verification or uncertainty; self.efficiency_ledger.append({"kind":"dedup","decision":"reuse" if found and not allowed else "execute","reason":"verification" if verification else "uncertainty" if uncertainty else "canonical_artifact"}); return allowed
    def context_decision(self, *, affinity:int|None=None, bloat:bool|None=None, stale:bool|None=None, stalls:int|None=None, worker_id:str|None=None, replacement:str|None=None) -> str:
        context=self.workers[worker_id].context if worker_id else {}; affinity=context.get("affinity",affinity or 0); bloat=context.get("bloat",bloat or False); stale=context.get("stale",stale or False); stalls=context.get("stalls",stalls or 0)
        result="retire" if bloat or stale or stalls>1 or affinity==0 else "reuse"; self.efficiency_ledger.append({"kind":"context","decision":result,"reason":"bounded_spine"})
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
        if self._cycle(task_id): self.events.append(("DEADLOCK",task_id))
    def _cycle(self, start: str) -> bool:
        seen=set(); current=start
        while current and current not in seen:
            seen.add(current); current=self.tasks[current].waiting_on if current in self.tasks else None
        return current==start
    def recover(self, actor: Role, task_id: str, dimension: str) -> None:
        self._role(actor,{Role.LEAD}); t=self.tasks[task_id]
        if not dimension or dimension in t.recovery_dimensions: raise InvariantError("recovery must be bounded and materially changed")
        t.recovery_dimensions.add(dimension); self.events.append(("RECOVERY",task_id))
    def expert(self, actor: Role, task_id: str) -> None:
        self._role(actor,{Role.DOER,Role.LEAD,Role.ARCHITECT,Role.MOTHER}); self.events.append(("EXPERT",task_id))
    def set_intelligence_floor(self, actor: Role, task_id: str, tier: int) -> None:
        self._role(actor,{Role.ARCHITECT}); self.tasks[task_id].contracts["intelligence_floor"]=tier
    def complexity_mismatch(self, actor: Role, task_id: str, observed_tier: int) -> None:
        self._role(actor,{Role.DOER}); self.tasks[task_id].contracts["complexity_mismatch"]=observed_tier; self.events.append(("MISMATCH",task_id))
    def add_artifact(self, actor: Role, task_id: str, artifact: ArtifactIdentity, risk: str="", *, source:str|None=None, justification:str|None=None) -> None:
        self._role(actor,{Role.DOER}); t=self.tasks[task_id]
        identity=self._register_artifact(t,artifact,source,justification); t.evidence.append(identity); t.findings.extend([risk] if risk else [])
    def discover(self, artifact: str) -> list[str]:
        return [t.id for t in self.tasks.values() if any(item == artifact or item.startswith(f"{artifact}@") for item in t.evidence)]
    def review_depth(self, risk:int) -> str:
        base="light" if risk <= 1 else "standard" if risk <= 3 else "adversarial" if risk <= 4 else "specialist"
        return "standard" if base=="light" and self.mode==EfficiencyMode.MAX else base
    def record_telemetry(self, task_type:str, role:str, tier:int, outcome:str, *, model:str="", attempts:int=0, stalls:int=0, expert_uses:int=0, review_failures:int=0, review_cycles:int=0, productive:int=0, overhead:int=0, usage:int|None=None) -> None:
        self.telemetry.update({"tasks":self.telemetry.get("tasks",0)+1,"productive":self.telemetry.get("productive",0)+productive,"overhead":self.telemetry.get("overhead",0)+overhead})
        if usage is not None: self.telemetry["host_usage"]=self.telemetry.get("host_usage",0)+usage
        self.telemetry_events.append({"task_type":task_type,"role":role,"tier":tier,"model":model,"attempts":attempts,"stalls":stalls,"expert_uses":expert_uses,"review_failures":review_failures,"review_cycles":review_cycles,"worker_count":len(self.workers),"outcome":outcome,"productive_execution":productive,"swarm_overhead":overhead,**({"host_usage":usage} if usage is not None else {})})
        self.events.append(("TELEMETRY",f"{task_type}:{role}:L{tier}:{outcome}"))
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
    def retire(self, actor: Role, worker_id: str, replacement: str|None=None) -> None:
        self._role(actor,{Role.LEAD}); w=self.workers[worker_id]
        if w.task_ids and (not replacement or replacement not in self.workers or self.workers[replacement].state==WorkerState.RETIRED): raise InvariantError("retirement needs a live replacement for owned tasks")
        if replacement:
            target=self.workers[replacement]
            if len(target.task_ids)+len(w.task_ids)>self.wip_limit: raise InvariantError("replacement WIP limit")
            for task_id in w.task_ids: self.tasks[task_id].owner=replacement; target.task_ids.add(task_id)
        w.state=WorkerState.RETIRED; w.archive={"tasks":sorted(w.task_ids),"lane":w.lane}; w.task_ids.clear()
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
        if not t.review_passed or not t.reviewer or not integration_ok or not architecture_ok: raise InvariantError("completion requires independent review and integration/architecture gates")
        t.state=TaskState.COMPLETE; t.completed_at=now
    def stale(self, actor: Role, task_id: str, reason: str, *, now: int=0, superseded_by: str|None=None, promote: list[str]|None=None) -> None:
        self._role(actor,{Role.MOTHER,Role.ARCHITECT,Role.LEAD}); t=self.tasks[task_id]
        if not reason: raise InvariantError("stale tasks require reason provenance")
        t.state=TaskState.STALE; t.stale_at=now; t.stale_reason=reason; t.superseded_by=superseded_by; t.promoted.extend(promote or [])
    def groom(self, actor: Role, now: int, policy: dict[str,int]) -> list[str]:
        """Mechanical archive only; archive preserves task provenance and knowledge."""
        self._role(actor,{Role.MOTHER}); archived=[]
        delays={ReviewValue.NONE:policy["no_review_archive_delay"],ReviewValue.LOW:policy["low_review_retention"],ReviewValue.HIGH:policy["high_review_retention"]}
        for t in self.tasks.values():
            if t.review_value==ReviewValue.PINNED: continue
            has_active_dependent=any(other.waiting_on==t.id and other.state in {TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW} for other in self.tasks.values())
            if t.state==TaskState.STALE and not has_active_dependent and t.stale_at is not None and now-t.stale_at >= policy["stale_task_archive_delay"]:
                t.state=TaskState.ARCHIVED_STALE; t.archived_at=now; archived.append(t.id)
            elif t.state==TaskState.COMPLETE and t.completed_at is not None and now-t.completed_at >= delays[t.review_value]:
                t.state=TaskState.ARCHIVED; t.archived_at=now; archived.append(t.id)
        reasons={"completed":0,"stale":0}; ages={"fresh":0,"aged":0}
        for task_id in archived:
            t=self.tasks[task_id]; started=t.completed_at if t.completed_at is not None else t.stale_at if t.stale_at is not None else now; reasons["stale" if t.state==TaskState.ARCHIVED_STALE else "completed"]+=1; ages["fresh" if now-started<30 else "aged"]+=1
        self.telemetry.update({"archived":self.telemetry.get("archived",0)+len(archived),"pins":sum(t.review_value==ReviewValue.PINNED for t in self.tasks.values()),"active":sum(t.state in {TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW} for t in self.tasks.values()),"stale":sum(t.state==TaskState.STALE for t in self.tasks.values()),"restores":self.telemetry.get("restores",0),"extensions":sum(t.extensions for t in self.tasks.values()),"completion_to_archive":{task_id:now-(self.tasks[task_id].completed_at if self.tasks[task_id].completed_at is not None else self.tasks[task_id].stale_at if self.tasks[task_id].stale_at is not None else now) for task_id in archived},"archive_reasons":reasons,"age_buckets":ages}); return archived
    def restore(self, actor:Role, task_id:str, reason:str) -> None:
        self._role(actor,{Role.MOTHER,Role.LEAD}); t=self.tasks[task_id]
        if t.state not in {TaskState.ARCHIVED,TaskState.ARCHIVED_STALE} or not reason: raise InvariantError("restore requires archived task and provenance")
        history=t.archive or {}; history.setdefault("archive_history",[]).append({"archived_at":t.archived_at,"reason":reason,"state":t.state.value}); t.archive=history; t.state=TaskState.ACTIVE; t.archived_at=None; t.findings.append(f"restored:{reason}"); self.telemetry["restores"]=self.telemetry.get("restores",0)+1
    def ctrl_event(self, event: str, task_id: str) -> str|None:
        if event in {"HEARTBEAT","PROGRESS"}: return None
        return f"{task_id}: {event.lower().replace('_',' ')}"
    def project_complete(self, actor: Role, integration_ok: bool, architecture_ok: bool) -> bool:
        self._role(actor,{Role.MOTHER})
        return integration_ok and architecture_ok and all(t.state in {TaskState.COMPLETE,TaskState.ARCHIVED,TaskState.BACKLOG} or (t.state==TaskState.ARCHIVED_STALE and t.superseded_by in self.tasks and self.tasks[t.superseded_by].state==TaskState.COMPLETE) for t in self.tasks.values())
