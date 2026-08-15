"""Locked repo-private atomic byte state shared by runtime ledgers."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
class LockedPrivateState:
    def __init__(self, repo_root:Path|str, relative_path:Path): self.root=Path(repo_root).resolve(); self.path=self.root/relative_path; self.lock_path=self.path.parent/"state.lock"
    def prepare(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try: os.chmod(self.path.parent,0o700)
        except OSError: pass
        git=self.root/".git"
        if git.is_file():
            marker=git.read_text(encoding="utf-8").strip()
            if marker.lower().startswith("gitdir:"): git=(git.parent/marker.split(":",1)[1].strip()).resolve()
        if git.is_dir():
            marker=git/"commondir"; common=(git/marker.read_text(encoding="utf-8").strip()).resolve() if marker.exists() else git; exclude=common/"info"/"exclude"; exclude.parent.mkdir(parents=True,exist_ok=True); old=exclude.read_text(encoding="utf-8") if exclude.exists() else ""
            if "/.codex/swarm/" not in old.splitlines(): exclude.write_text(old+("" if not old or old.endswith("\n") else "\n")+"/.codex/swarm/\n",encoding="utf-8",newline="\n")
    @contextmanager
    def locked(self):
        self.prepare()
        with self.lock_path.open("a+b") as handle:
            handle.seek(0,2)
            if not handle.tell(): handle.write(b"\0"); handle.flush()
            handle.seek(0)
            if os.name=="nt":
                import msvcrt; msvcrt.locking(handle.fileno(),msvcrt.LK_LOCK,1)
                try: yield
                finally: handle.seek(0); msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl; fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
                try: yield
                finally: fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
    def read_bytes_unlocked(self)->bytes: return self.path.read_bytes() if self.path.exists() else b""
    def replace_bytes_unlocked(self,payload:bytes)->None:
        handle=tempfile.NamedTemporaryFile("wb",delete=False,dir=self.path.parent,prefix="state-",suffix=".tmp"); temporary=Path(handle.name)
        try:
            with handle: handle.write(payload); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary,self.path)
            try: os.chmod(self.path,0o600)
            except OSError: pass
        finally:
            if temporary.exists(): temporary.unlink()
