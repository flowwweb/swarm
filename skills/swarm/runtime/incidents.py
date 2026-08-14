"""Private repo-local escaped-defect ledger with serialized daily folds."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
import json
import os
from pathlib import Path
import re
import tempfile


class IncidentError(ValueError): pass


class IncidentDisposition(StrEnum):
    LOCAL_ONLY="local-only"; CANDIDATE="candidate"; FOLDED="folded"; REJECTED="rejected"


class EvidenceKind(StrEnum):
    TEST_RECEIPT="test-receipt"; FILE_DIGEST="file-digest"; LOG_REFERENCE="log-reference"; REVIEW_RECEIPT="review-receipt"; URL_REFERENCE="url-reference"


_CREDENTIALS=(
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\/-]{12,}"),
    re.compile(r"(?i)(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?):\/\/[^\s:\/@]+:[^\s@\/]+@"),
    re.compile(r"(?i)\b(?:api[_-]?key|password|passwd|client[_-]?secret|access[_-]?token)\s*[:=]\s*['\"]?[^\s,'\"]{8,}"),
)
_REPO_COMMAND=re.compile(r"(?i)(?:\bnpm\s+run\b|\bpnpm\b|\byarn\b|\bpytest\b|\bgradlew\b|(?:^|\s)[a-z]:\\|(?:^|\s)\./)")


def _reject_credentials(value:str) -> None:
    if any(pattern.search(value) for pattern in _CREDENTIALS): raise IncidentError("incident records must not contain credential material")


@dataclass(frozen=True)
class EvidenceReference:
    kind:EvidenceKind; locator:str; digest:str=""
    def __post_init__(self):
        if not isinstance(self.kind,EvidenceKind) or not self.locator.strip(): raise IncidentError("evidence requires a typed kind and safe locator")
        _reject_credentials(f"{self.locator}\n{self.digest}")


@dataclass(frozen=True)
class IncidentRecord:
    incidentId:str; occurredAt:str; artifact:str; scope:str; introducedAt:str; ownerSurface:str
    detectedAt:str; gate:str; earliestCheapDetector:str; missedGateReason:str; propagationPath:tuple[str,...]
    localCorrection:str; generalizedCandidate:str; disposition:IncidentDisposition; evidence:tuple[EvidenceReference,...]
    cost:float|None=None; timeLost:float|None=None; dispositionReason:str=""

    def __post_init__(self):
        required=(self.incidentId,self.occurredAt,self.artifact,self.scope,self.introducedAt,self.ownerSurface,self.detectedAt,self.gate,self.earliestCheapDetector,self.missedGateReason,self.localCorrection)
        if any(not isinstance(value,str) or not value.strip() for value in required): raise IncidentError("incident record requires stable identity, scope, causal trace, detector, missed gate, and correction")
        if not self.propagationPath or any(not item.strip() for item in self.propagationPath) or not self.evidence or any(not isinstance(item,EvidenceReference) for item in self.evidence): raise IncidentError("material incident requires propagation path and structured evidence references")
        if not isinstance(self.disposition,IncidentDisposition): raise IncidentError("incident disposition must be typed")
        if (self.cost is not None and self.cost<0) or (self.timeLost is not None and self.timeLost<0): raise IncidentError("incident cost and time lost must be nonnegative")
        _reject_credentials(json.dumps(asdict(self),default=str,ensure_ascii=False))

    @property
    def failure_class(self) -> tuple[str,str,str]:
        candidate=self.generalizedCandidate.strip().casefold()
        return (self.scope.strip().casefold(),candidate or self.earliestCheapDetector.strip().casefold(),self.missedGateReason.strip().casefold())


@dataclass(frozen=True)
class FoldCandidate:
    control:str; incident_ids:tuple[str,...]; contrasting_regression_proof:str
    demonstrably_generalizable:bool=False; repository_specific:bool=False; person_specific:bool=False
    def __post_init__(self):
        if not self.control.strip() or not self.incident_ids: raise IncidentError("daily fold requires a control and incident identities")
        if len(set(self.incident_ids))!=len(self.incident_ids): raise IncidentError("daily fold incident identities must be distinct")


@dataclass(frozen=True)
class FoldResult:
    promoted:bool; disposition:IncidentDisposition; reason:str; incident_ids:tuple[str,...]


class IncidentLedger:
    """Locked JSONL store rooted at private, Git-ignored ``.codex/swarm`` state."""
    relative_path=Path(".codex")/"swarm"/"incidents.jsonl"
    ignore_rule="/.codex/swarm/"

    def __init__(self, repo_root:Path|str):
        self.repo_root=Path(repo_root).resolve(); self.path=self.repo_root/self.relative_path; self.lock_path=self.path.with_suffix(".lock")
        self._ensure_private_ignored_state()

    def _ensure_private_ignored_state(self) -> None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try: os.chmod(self.path.parent,0o700)
        except OSError: pass
        git=self.repo_root/".git"; git_dir=git
        if git.is_file():
            marker=git.read_text(encoding="utf-8").strip()
            if marker.lower().startswith("gitdir:"): git_dir=(git.parent/marker.split(":",1)[1].strip()).resolve()
        if git_dir.is_dir():
            common_marker=git_dir/"commondir"; common_dir=(git_dir/common_marker.read_text(encoding="utf-8").strip()).resolve() if common_marker.exists() else git_dir
            exclude=common_dir/"info"/"exclude"; exclude.parent.mkdir(parents=True,exist_ok=True); existing=exclude.read_text(encoding="utf-8") if exclude.exists() else ""
            if self.ignore_rule not in existing.splitlines():
                with exclude.open("a",encoding="utf-8",newline="\n") as handle: handle.write(("" if not existing or existing.endswith("\n") else "\n")+self.ignore_rule+"\n")

    @contextmanager
    def _lock(self):
        self.lock_path.parent.mkdir(parents=True,exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            handle.seek(0,os.SEEK_END)
            if handle.tell()==0: handle.write(b"\0"); handle.flush()
            handle.seek(0)
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_LOCK,1)
                try: yield
                finally:
                    handle.seek(0); msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
                try: yield
                finally: fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

    def _decode(self, raw:dict) -> IncidentRecord:
        raw["disposition"]=IncidentDisposition(raw["disposition"]); raw["propagationPath"]=tuple(raw["propagationPath"])
        raw["evidence"]=tuple(EvidenceReference(EvidenceKind(item["kind"]),item["locator"],item.get("digest","")) for item in raw["evidence"])
        return IncidentRecord(**raw)

    def _read_unlocked(self) -> tuple[IncidentRecord,...]:
        if not self.path.exists(): return ()
        return tuple(self._decode(json.loads(line)) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip())

    def read(self) -> tuple[IncidentRecord,...]:
        with self._lock(): return self._read_unlocked()

    def append(self, record:IncidentRecord) -> None:
        with self._lock():
            if any(existing.incidentId==record.incidentId for existing in self._read_unlocked()): raise IncidentError("incident identity already exists")
            payload=(json.dumps(asdict(record),default=str,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8")
            descriptor=os.open(self.path,os.O_APPEND|os.O_CREAT|os.O_WRONLY,0o600)
            try: os.write(descriptor,payload); os.fsync(descriptor)
            finally: os.close(descriptor)
            try: os.chmod(self.path,0o600)
            except OSError: pass

    def unresolved(self, *, artifact:str, scope:str) -> tuple[IncidentRecord,...]:
        return tuple(item for item in self.read() if item.artifact==artifact and item.scope==scope and item.disposition in {IncidentDisposition.LOCAL_ONLY,IncidentDisposition.CANDIDATE})

    def daily_fold(self, candidate:FoldCandidate) -> FoldResult:
        with self._lock():
            records={item.incidentId:item for item in self._read_unlocked()}; selected=tuple(records[item] for item in candidate.incident_ids if item in records)
            valid=len(selected)==len(candidate.incident_ids); repeated=len(selected)>=2 and len({item.failure_class for item in selected})==1
            portable=not candidate.repository_specific and not candidate.person_specific and not _REPO_COMMAND.search(candidate.control)
            eligible=valid and portable and bool(candidate.contrasting_regression_proof.strip()) and (repeated or candidate.demonstrably_generalizable)
            reason="repeated/generalizable control with contrasting regression proof" if eligible else "candidate remains pending until portable repetition/generalization and contrasting proof exist"
            if eligible: self._rewrite_unlocked({item.incidentId:(IncidentDisposition.FOLDED,reason) for item in selected})
            return FoldResult(eligible,IncidentDisposition.FOLDED if eligible else IncidentDisposition.CANDIDATE,reason,tuple(item.incidentId for item in selected))

    def reject(self, incident_ids:tuple[str,...], *, reason:str) -> None:
        if not incident_ids or len(set(incident_ids))!=len(incident_ids) or not reason.strip(): raise IncidentError("explicit rejection requires distinct incident identities and reason")
        with self._lock():
            records={item.incidentId:item for item in self._read_unlocked()}
            if any(identity not in records for identity in incident_ids): raise IncidentError("cannot reject unknown incident")
            self._rewrite_unlocked({identity:(IncidentDisposition.REJECTED,reason.strip()) for identity in incident_ids})

    def _rewrite_unlocked(self, dispositions:dict[str,tuple[IncidentDisposition,str]]) -> None:
        records=tuple(replace(item,disposition=dispositions[item.incidentId][0],dispositionReason=dispositions[item.incidentId][1]) if item.incidentId in dispositions else item for item in self._read_unlocked())
        handle=tempfile.NamedTemporaryFile("w",encoding="utf-8",delete=False,dir=self.path.parent,prefix="incidents-",suffix=".tmp",newline="\n"); temporary=Path(handle.name)
        try:
            with handle:
                for record in records: handle.write(json.dumps(asdict(record),default=str,ensure_ascii=False,separators=(",",":"))+"\n")
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary,self.path)
            try: os.chmod(self.path,0o600)
            except OSError: pass
        finally:
            if temporary.exists(): temporary.unlink()


def utc_timestamp() -> str: return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
