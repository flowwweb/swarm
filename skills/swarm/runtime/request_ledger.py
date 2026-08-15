"""Atomic private request continuity; schema authority remains in the live runtime."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from .private_state import LockedPrivateState
class RequestStoreError(ValueError): pass
class RequestStore:
    relative_path=Path(".codex")/"swarm"/"requests.json"
    def __init__(self,repo_root:Path|str): self.state=LockedPrivateState(repo_root,self.relative_path)
    @staticmethod
    def canonical(value:dict)->bytes: return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    @staticmethod
    def empty()->dict: return {"version":1,"sequence":0,"order":[],"requests":{},"stages":{}}
    def decode(self,raw:bytes)->dict:
        try: value=json.loads(raw.decode()) if raw else self.empty()
        except (UnicodeDecodeError,json.JSONDecodeError) as error: raise RequestStoreError("request state is corrupt") from error
        if not isinstance(value,dict) or value.get("version")!=1 or not isinstance(value.get("sequence"),int) or value["sequence"]<0 or not isinstance(value.get("order"),list) or not isinstance(value.get("requests"),dict) or not isinstance(value.get("stages"),dict) or len(value["order"])!=len(set(value["order"])) or set(value["order"])!=set(value["requests"]): raise RequestStoreError("request state envelope is invalid")
        return value
    def read(self)->tuple[dict,str]:
        with self.state.locked():
            value=self.decode(self.state.read_bytes_unlocked()); return deepcopy(value),sha256(self.canonical(value)).hexdigest()
    def peek(self)->tuple[dict,str,bool]:
        if not self.state.path.exists(): value=self.empty(); return value,sha256(self.canonical(value)).hexdigest(),False
        before=self.state.path.stat(); raw=self.state.path.read_bytes(); after=self.state.path.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): raise RequestStoreError("request state changed during read-only inspection")
        value=self.decode(raw); return deepcopy(value),sha256(self.canonical(value)).hexdigest(),True
    def _mutate_validated(self,callback,expected:tuple[int,str]|None=None)->tuple[dict,str,object]:
        with self.state.locked():
            value=self.decode(self.state.read_bytes_unlocked()); before=self.canonical(value); digest=sha256(before).hexdigest()
            if expected is not None and expected!=(value["sequence"],digest): raise RequestStoreError("stale request ledger identity")
            candidate=deepcopy(value); result=callback(candidate); candidate["sequence"]+=1; payload=self.canonical(self.decode(self.canonical(candidate))); self.state.replace_bytes_unlocked(payload); return deepcopy(candidate),sha256(payload).hexdigest(),result
    def with_current(self,expected:tuple[int,str]|None,callback):
        with self.state.locked():
            value=self.decode(self.state.read_bytes_unlocked()); digest=sha256(self.canonical(value)).hexdigest()
            if expected is not None and expected!=(value["sequence"],digest): raise RequestStoreError("stale request ledger identity")
            return deepcopy(value),digest,callback(value)
