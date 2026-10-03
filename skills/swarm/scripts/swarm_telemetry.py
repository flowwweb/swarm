"""Opt-in, content-free product telemetry for the Flowwweb beacon."""
from __future__ import annotations

import hashlib
import hmac
from contextlib import closing
import json
import os
import platform
from pathlib import Path
import sqlite3
import time
import urllib.request
import uuid

from swarm_config import load, resolve_config_path
from swarm_usage import FIELDS, standard_cost, usage

BEACON = "https://telemetry.flowwweb.com/api/swarm/telemetry"
MODELS = {"gpt-6.1-sol", "gpt-6-sol", "gpt-6-astra", "gpt-6-luna", "gpt-5.6-sol",
          "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.3-codex-spark"}
EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
HOOKS = {"SessionStart": "activation", "UserPromptSubmit": "turn_start", "SubagentStart": "subagent_start",
         "SubagentStop": "subagent_end", "Stop": "turn_end", "PostToolUse": "tool"}
STATE = Path(os.environ.get("PLUGIN_DATA", Path.home() / ".agents/swarm")) / "product-telemetry.sqlite"
VERSION = json.loads((Path(__file__).resolve().parents[3] / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))["version"]


def enabled():
    try:
        return load(resolve_config_path())[0]["telemetry"]["enabled"] is True
    except Exception:
        return False  # Fail closed on unreadable or invalid consent.


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=1)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pending (id TEXT PRIMARY KEY, at INTEGER NOT NULL, payload TEXT NOT NULL);
    """)
    db.execute("INSERT OR IGNORE INTO state VALUES ('installation', ?)", (uuid.uuid4().hex,))
    db.execute("DELETE FROM pending WHERE at < ?", (int(time.time()) - 7 * 86400,))
    db.commit()
    return db


def get(db, key, default=None):
    row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def put(db, key, value):
    db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, json.dumps(value)))


def tool_category(name):
    name = name if isinstance(name, str) else ""
    if name in {"Bash", "exec_command", "write_stdin"}:
        return "shell"
    if name in {"apply_patch", "Edit", "Write"}:
        return "edit"
    if name.endswith(("spawn_agent", "send_message", "followup_task", "create_thread", "send_message_to_thread")):
        return "delegation"
    if name.endswith(("swarm_status", "swarm_projects", "swarm_usage")):
        return "swarm_read"
    return "other"


def base(db, kind, session, model=None, effort=None):
    installation = db.execute("SELECT value FROM state WHERE key='installation'").fetchone()[0]
    return {"event_id": uuid.uuid4().hex, "installation_id": installation,
            "session_id": hmac.new(installation.encode(), str(session).encode(), hashlib.sha256).hexdigest()[:32],
            "at": int(time.time()), "kind": kind, "version": VERSION,
            "os": platform.system() if platform.system() in {"Windows", "Darwin", "Linux"} else "other",
            "model": model if model in MODELS else "unknown" if not model else "other",
            "effort": effort if effort in EFFORTS else "unknown"}


def enqueue(db, event):
    # ponytail: bounded 1,000-event outbox; count dropped events instead of growing disk use offline.
    if db.execute("SELECT count(*) FROM pending").fetchone()[0] >= 1000:
        put(db, "dropped", get(db, "dropped", 0) + 1)
        return
    db.execute("INSERT OR IGNORE INTO pending VALUES (?, ?, ?)",
               (event["event_id"], event["at"], json.dumps(event, separators=(",", ":"))))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never send telemetry to a redirected destination.


def deliver(db, endpoint=BEACON):
    if get(db, "next_attempt", 0) > time.time():
        return
    rows = db.execute("SELECT id,payload FROM pending ORDER BY at,rowid LIMIT 32").fetchall()
    if not rows:
        return
    body = json.dumps({"schema_version": 1, "events": [json.loads(row[1]) for row in rows]}).encode()
    request = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json", "User-Agent": "SWARM/" + VERSION})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=1.5) as response:
            receipt = json.loads(response.read(8192))
        if receipt.get("accepted") != [row[0] for row in rows]:
            raise ValueError("unreconciled receipt")
    except (OSError, ValueError):
        failures = min(8, get(db, "failures", 0) + 1)
        put(db, "failures", failures)
        put(db, "next_attempt", int(time.time()) + min(3600, 15 * 2 ** failures))
        put(db, "delivery", "pending")
    else:
        db.executemany("DELETE FROM pending WHERE id=?", [(row[0],) for row in rows])
        put(db, "failures", 0)
        put(db, "next_attempt", int(time.time()) + 30)
        put(db, "delivery", "acknowledged")
        put(db, "last_ack", int(time.time()))
    db.commit()


def collect_usage(db, event, session):
    """Incrementally read only the hooked session; never serialize transcript content."""
    path = event.get("transcript_path")
    if not isinstance(path, str) or not path:
        return "unavailable"
    state_key = "cursor:" + session
    state = get(db, state_key)
    try:
        with Path(path).open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            if state is None:
                # Consent begins here, not at the beginning of an existing conversation.
                state = {"offset": size, "total": {key: 0 for key in FIELDS} if size <= 262144 else None,
                         "model": event.get("model"), "effort": None}
                start = max(0, size - 262144)
                stream.seek(start)
                raw = stream.read(262144)
                end = raw.rfind(b"\n") + 1
                lines = raw[:end].splitlines()
                if start:
                    lines = lines[1:]  # The bounded tail may start inside a record.
                state["offset"] = start + end
                state["baseline_line"] = end < len(raw)
                baseline = True
            elif state["offset"] > size:
                put(db, state_key, {"offset": size, "total": None, "model": None, "effort": None})
                return "reset"
            else:
                stream.seek(state["offset"])
                raw = stream.read(2 * 1024 * 1024)
                end = raw.rfind(b"\n") + 1
                lines = raw[:end].splitlines()
                state["offset"] += end
                baseline = False
                if state.get("skip_line") and end:
                    lines = lines[1:]
                    state.pop("skip_line", None)
                if not end and len(raw) == 2 * 1024 * 1024:
                    # Skip oversized records without freezing the bounded parser.
                    state["offset"] += len(raw)
                    state["skip_line"] = True
                    state["total"] = None
        coverage = "baseline" if baseline else "partial" if state["offset"] < size else "observed"
        for index, line in enumerate(lines):
            try:
                record = json.loads(line)
                payload = record.get("payload", {})
                if record.get("type") == "turn_context":
                    state.update(model=payload.get("model"), effort=payload.get("effort", payload.get("reasoning_effort")))
                if record.get("type") != "event_msg" or payload.get("type") != "token_count":
                    continue
                info = payload.get("info") or {}
                if not info.get("total_token_usage"):
                    continue
                total = usage(info.get("total_token_usage"))
                previous = state["total"]
                state["total"] = total
                if baseline or (index == 0 and state.get("baseline_line")) or previous is None:
                    continue
                delta = usage({key: total[key] - previous[key] for key in FIELDS})
                if not delta["total_tokens"]:
                    continue
                row = base(db, "usage", session, state["model"], state["effort"])
                row["tokens"] = delta
                row["cost_microusd"] = None
                try:
                    if usage(info.get("last_token_usage")) == delta:
                        row["cost_microusd"] = round(standard_cost(delta, state["model"]) * 1_000_000)
                except ValueError:
                    pass
                enqueue(db, row)
            except (ValueError, TypeError, AttributeError):
                coverage = "partial"
        if not baseline and lines:
            state.pop("baseline_line", None)
        put(db, state_key, state)
        # Bound session cursors. Old sessions establish a new baseline if resumed.
        db.execute("DELETE FROM state WHERE key LIKE 'cursor:%' AND rowid NOT IN (SELECT rowid FROM state WHERE key LIKE 'cursor:%' ORDER BY rowid DESC LIMIT 256)")
        return coverage
    except OSError:
        return "unavailable"


def capture(event, *, path=STATE, endpoint=BEACON, flush=True):
    """Consent is checked before collection, state creation, or any network request."""
    try:
        if not enabled():
            if path.exists():
                with closing(sqlite3.connect(path, timeout=0.2)) as db:
                    db.execute("DELETE FROM pending")
                    db.execute("DELETE FROM state")  # Drop identifiers and cursors on opt-out.
                    db.commit()
            return
        kind = HOOKS.get(event.get("hook_event_name"))
        if kind is None:
            return
        with closing(connect(path)) as db:
            # Background hooks can overlap. Serialize cursors and queued deltas, not HTTP.
            db.execute("BEGIN IMMEDIATE")
            installation = db.execute("SELECT value FROM state WHERE key='installation'").fetchone()[0]
            identity = event.get("agent_id") if kind in {"subagent_start", "subagent_end"} else event.get("session_id", "unknown")
            session = hmac.new(installation.encode(), str(identity).encode(), hashlib.sha256).hexdigest()[:32]
            if kind == "subagent_start" and get(db, "cursor:" + session) is None:
                # A start observed after consent allows this new child's full transcript.
                put(db, "cursor:" + session, {"offset": 0, "total": {key: 0 for key in FIELDS}, "model": event.get("model"), "effort": None})
            usage_event = {**event, "transcript_path": event.get("agent_transcript_path")} if kind == "subagent_end" else event
            coverage = collect_usage(db, usage_event, session) if kind in {"activation", "turn_end", "subagent_end"} else None
            context = get(db, "cursor:" + session, {})
            row = base(db, kind, session, event.get("model", context.get("model")), context.get("effort"))
            if coverage:
                row["coverage"] = coverage
            if kind in {"turn_end", "subagent_end"}:
                started = get(db, "started:" + session)
                row["duration_ms"] = None if started is None else min(86400000, max(0, (row["at"] - started) * 1000))
                db.execute("DELETE FROM state WHERE key=?", ("started:" + session,))
            elif kind in {"turn_start", "subagent_start"}:
                put(db, "started:" + session, row["at"])
            if kind == "tool":
                row["tool"] = tool_category(event.get("tool_name"))
                response = event.get("tool_response")
                row["success"] = None
                if isinstance(response, dict):
                    if type(response.get("exit_code")) is int:
                        row["success"] = response["exit_code"] == 0
                    elif type(response.get("isError")) is bool:
                        row["success"] = not response["isError"]
            db.execute("DELETE FROM state WHERE key LIKE 'started:%' AND rowid NOT IN (SELECT rowid FROM state WHERE key LIKE 'started:%' ORDER BY rowid DESC LIMIT 256)")
            enqueue(db, row)
            db.commit()
            if flush:
                deliver(db, endpoint)
    except Exception:
        return  # Telemetry must never disrupt engineering work.


def status(path=STATE):
    result = {"enabled": enabled(), "beacon": BEACON, "delivery": "not_started", "pending": 0}
    if path.exists():
        try:
            with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=0.2)) as db:
                result.update(delivery=get(db, "delivery", "not_started"), last_ack=get(db, "last_ack"),
                              dropped=get(db, "dropped", 0), pending=db.execute("SELECT count(*) FROM pending").fetchone()[0])
        except sqlite3.Error:
            result["delivery"] = "unreadable"
    return result
