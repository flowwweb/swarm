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

class Depth(StrEnum):
    ATOMIC="CTRL_DOER"; SIMPLE="CTRL_MOTHER_DOER"; WORKSTREAM="CTRL_MOTHER_LEAD_DOER"; PROJECT="CTRL_MOTHER_ARCHITECT_LEADS_DOERS"

def choose_depth(*, scope: int, architecture_impact: bool=False, independent_tasks: int=1, dependencies: int=0, uncertainty: int=0, blast_radius: int=0, specialisations: int=1, useful_parallelism: int=1, coordination_overhead: int=0) -> Depth:
    """Choose infrastructure only when its reliability benefit exceeds its cost."""
    if scope <= 1 and independent_tasks <= 1 and not architecture_impact and dependencies == uncertainty == blast_radius == 0: return Depth.ATOMIC
    if architecture_impact and (independent_tasks >= 3 or specialisations >= 2): return Depth.PROJECT
    if independent_tasks >= 2 or dependencies >= 2 or specialisations >= 2 or useful_parallelism >= 2:
        return Depth.WORKSTREAM if coordination_overhead < 3 else Depth.SIMPLE
    return Depth.SIMPLE

@dataclass
class Task:
    id: str; owner: str; creator: str; architecture_version: int; contracts: dict[str,int]
    state: TaskState=TaskState.ACTIVE; waiting_on: str|None=None; reviewer: str|None=None; findings: list[str]=field(default_factory=list)
    evidence: list[str]=field(default_factory=list); recovery_dimensions: set[str]=field(default_factory=set); review_value: ReviewValue=ReviewValue.NONE
    completed_at: int|None=None; stale_at: int|None=None; archived_at: int|None=None; stale_reason: str|None=None; superseded_by: str|None=None; promoted: list[str]=field(default_factory=list); extensions: int=0; review_passed: bool=False

@dataclass
class Worker:
    id: str; lead: str; lane: int; state: WorkerState=WorkerState.SPAWNED; task_ids: set[str]=field(default_factory=set); archive: dict[str, object]=field(default_factory=dict)

@dataclass
class Swarm:
    architecture_version: int=1; contract_versions: dict[str,int]=field(default_factory=dict); topology: set[str]=field(default_factory=set)
    workers: dict[str,Worker]=field(default_factory=dict); tasks: dict[str,Task]=field(default_factory=dict); leases: dict[str,str]=field(default_factory=dict); events: list[tuple[str,str]]=field(default_factory=list); telemetry: dict[str,int]=field(default_factory=dict); lane_width:int=3; wip_limit:int=3
    @classmethod
    def from_config(cls, config: dict) -> "Swarm":
        return cls(lane_width=config["coordination"]["preferred_lane_width"], wip_limit=config.get("execution_limits",{}).get("doer_wip_limit",3))

    def _role(self, actor: Role, allowed: set[Role]) -> None:
        if actor not in allowed: raise InvariantError(f"{actor} cannot perform this transition")
    def add_lead(self, actor: Role, lead: str) -> None:
        self._role(actor,{Role.MOTHER}); self.topology.add(lead)
    def add_worker(self, actor: Role, worker: Worker) -> None:
        self._role(actor,{Role.LEAD});
        if worker.lead not in self.topology or not 1 <= worker.lane <= self.lane_width: raise InvariantError("worker requires a known lead and configured lane")
        if sum(w.lead==worker.lead and w.state!=WorkerState.RETIRED for w in self.workers.values()) >= self.lane_width: raise InvariantError("lead capacity reached")
        self.workers[worker.id]=worker
    def assign(self, actor: Role, task: Task) -> None:
        self._role(actor,{Role.LEAD}); w=self.workers.get(task.owner)
        if not w or w.state==WorkerState.RETIRED or len(w.task_ids)>=self.wip_limit: raise InvariantError("owner unavailable or at WIP limit")
        self.tasks[task.id]=task; w.task_ids.add(task.id)
    def change_architecture(self, actor: Role, contracts: dict[str,int]) -> None:
        self._role(actor,{Role.ARCHITECT}); self.architecture_version+=1; self.contract_versions.update(contracts)
        for task in self.tasks.values():
            if task.state not in {TaskState.COMPLETE,TaskState.BACKLOG,TaskState.ARCHIVED,TaskState.ARCHIVED_STALE} and (task.architecture_version != self.architecture_version or any(task.contracts.get(k,0)!=v for k,v in contracts.items())): task.state=TaskState.STALE; task.stale_reason="architecture or contract version changed"; task.stale_at=len(self.events)
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
    def add_artifact(self, actor: Role, task_id: str, artifact: str, risk: str="") -> None:
        self._role(actor,{Role.DOER}); t=self.tasks[task_id]; t.evidence.append(artifact); t.findings.extend([risk] if risk else [])
    def discover(self, artifact: str) -> list[str]:
        return [t.id for t in self.tasks.values() if artifact in t.evidence]
    def review(self, actor: Role, task_id: str, reviewer: str, passed: bool, finding: str="") -> None:
        self._role(actor,{Role.REVIEW}); t=self.tasks[task_id]
        if reviewer in {t.creator,t.owner}: raise InvariantError("creator cannot be sole independent reviewer")
        t.reviewer=reviewer
        if passed: t.review_passed=True; t.state=TaskState.REVIEW
        else: t.state=TaskState.ACTIVE; t.findings.append(finding or "review failed")
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
        self._role(actor,{Role.MOTHER}); active=[t for t in self.tasks.values() if t.state not in {TaskState.COMPLETE,TaskState.BACKLOG}]
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
        self.telemetry.update({"archived":self.telemetry.get("archived",0)+len(archived),"pins":sum(t.review_value==ReviewValue.PINNED for t in self.tasks.values()),"active":sum(t.state in {TaskState.ACTIVE,TaskState.WAITING,TaskState.REVIEW} for t in self.tasks.values()),"stale":sum(t.state==TaskState.STALE for t in self.tasks.values()),"restores":self.telemetry.get("restores",0),"extensions":sum(t.extensions for t in self.tasks.values())}); return archived
    def ctrl_event(self, event: str, task_id: str) -> str|None:
        if event in {"HEARTBEAT","PROGRESS"}: return None
        return f"{task_id}: {event.lower().replace('_',' ')}"
    def project_complete(self, actor: Role, integration_ok: bool, architecture_ok: bool) -> bool:
        self._role(actor,{Role.MOTHER})
        return integration_ok and architecture_ok and all(t.state in {TaskState.COMPLETE,TaskState.ARCHIVED,TaskState.ARCHIVED_STALE,TaskState.BACKLOG} for t in self.tasks.values())
