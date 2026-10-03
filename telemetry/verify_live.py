"""Synthetic beacon delivery/readback check; removes only its random test installation."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from unittest.mock import patch

import manage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/swarm/scripts"))
import swarm_telemetry as telemetry


def verify():
    headers = {"User-Agent": "SWARM/" + telemetry.VERSION}
    with urllib.request.urlopen(urllib.request.Request(telemetry.BEACON, headers=headers), timeout=25) as response:
        assert response.status == 200 and json.load(response)["service"] == "swarm-telemetry"
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.sqlite"
        transcript = Path(directory) / "synthetic.jsonl"
        transcript.write_text("", encoding="utf-8")
        event = {"hook_event_name": "SessionStart", "session_id": "synthetic-test", "transcript_path": str(transcript), "model": "gpt-6.1-sol"}
        with patch.object(telemetry, "enabled", return_value=True):
            telemetry.capture(event, path=path, flush=False)
            tokens = dict(input_tokens=100, cached_input_tokens=50, cache_write_input_tokens=0, output_tokens=10, reasoning_output_tokens=5, total_tokens=110)
            transcript.write_text("\n".join(json.dumps(row) for row in [
                {"type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": "xhigh"}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": tokens, "last_token_usage": tokens}}}]) + "\n", encoding="utf-8")
            telemetry.capture({**event, "hook_event_name": "Stop"}, path=path, flush=False)
        with closing(sqlite3.connect(path)) as db:
            installation = db.execute("SELECT value FROM state WHERE key='installation'").fetchone()[0]
            rows = [json.loads(row[0]) for row in db.execute("SELECT payload FROM pending ORDER BY at,rowid")]
            body = json.dumps({"schema_version": 1, "events": rows}).encode()
            try:
                telemetry.deliver(db)
                assert db.execute("SELECT count(*) FROM pending").fetchone()[0] == 0, "uploader did not receive durable acknowledgement"
                request = urllib.request.Request(telemetry.BEACON, data=body, headers={**headers, "Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=25) as response:
                    assert json.load(response)["accepted"] == [row["event_id"] for row in rows]
                stored = manage.query("SELECT payload FROM events WHERE installation=? ORDER BY occurred_at,id", [installation])[0]["results"]
                assert len(stored) == 3, "duplicate delivery inflated central rows"
                usage = [json.loads(row["payload"]) for row in stored if json.loads(row["payload"])["kind"] == "usage"]
                assert len(usage) == 1 and usage[0]["tokens"] == tokens and usage[0]["cost_microusd"] == 205
                assert usage[0]["model"] == "gpt-6.1-sol" and usage[0]["effort"] == "xhigh"
                try:
                    urllib.request.urlopen(urllib.request.Request(telemetry.BEACON + "/admin", headers=headers), timeout=25)
                    raise AssertionError("public admin endpoint exists")
                except urllib.error.HTTPError as error:
                    assert error.code == 404
            finally:
                manage.query("DELETE FROM events WHERE installation=?", [installation])
            assert not manage.query("SELECT id FROM events WHERE installation=?", [installation])[0]["results"], "synthetic events remained in fleet"
    return {"beacon": telemetry.BEACON, "health": "PASS", "uploader_delivery": "PASS", "authenticated_readback": "PASS", "duplicate_delivery": "PASS", "model_effort_tokens_price": "PASS", "public_admin_absent": "PASS", "synthetic_events_removed": "PASS"}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
