"""One end-to-end check for consent, offline retries, privacy and usage accounting."""
import json
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import swarm_telemetry as telemetry


class ProductTelemetryTests(unittest.TestCase):
    def test_split_records_concurrent_stops_and_child_usage(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(telemetry, "enabled", return_value=True):
            path = Path(directory) / "state.sqlite"
            transcript = Path(directory) / "session.jsonl"
            transcript.write_text("", encoding="utf-8")
            tokens = dict(input_tokens=100, cached_input_tokens=50, cache_write_input_tokens=0, output_tokens=10, reasoning_output_tokens=5, total_tokens=110)
            record = json.dumps({"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":tokens,"last_token_usage":tokens}}}) + "\n"
            event = {"hook_event_name":"SessionStart", "session_id":"parent", "transcript_path":str(transcript), "model":"gpt-6.1-sol"}
            telemetry.capture(event,path=path,flush=False)
            transcript.write_text(record[:60],encoding="utf-8")
            telemetry.capture({**event,"hook_event_name":"Stop"},path=path,flush=False)
            with transcript.open("a",encoding="utf-8") as stream:
                stream.write(record[60:])
            threads = [threading.Thread(target=telemetry.capture,args=({**event,"hook_event_name":"Stop"},),kwargs={"path":path,"flush":False}) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            child = Path(directory) / "child.jsonl"
            telemetry.capture({**event,"hook_event_name":"SubagentStart","agent_id":"child"},path=path,flush=False)
            child.write_text(record,encoding="utf-8")
            telemetry.capture({**event,"hook_event_name":"SubagentStop","agent_id":"child","agent_transcript_path":str(child)},path=path,flush=False)
            telemetry.capture({**event,"hook_event_name":"SubagentStop","agent_id":"child","agent_transcript_path":str(child)},path=path,flush=False)
            with closing(sqlite3.connect(path)) as db:
                rows = [json.loads(row[0]) for row in db.execute("SELECT payload FROM pending")]
            usages = [row for row in rows if row["kind"] == "usage"]
            self.assertEqual(len(usages),2)
            self.assertEqual(sum(row["tokens"]["total_tokens"] for row in usages),220)
            self.assertEqual(len({row["session_id"] for row in usages}),2)

    def test_opt_in_ignores_historical_and_unfinished_baseline_usage(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(telemetry, "enabled", return_value=True):
            path = Path(directory) / "state.sqlite"
            transcript = Path(directory) / "session.jsonl"
            tokens = dict(input_tokens=100, cached_input_tokens=50, cache_write_input_tokens=0, output_tokens=10, reasoning_output_tokens=5, total_tokens=110)
            def record(total):
                return json.dumps({"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":total,"last_token_usage":tokens}}}) + "\n"
            old = record(tokens)
            transcript.write_text(old[:70],encoding="utf-8")
            event = {"hook_event_name":"SessionStart","session_id":"parent","transcript_path":str(transcript),"model":"gpt-6.1-sol"}
            telemetry.capture(event,path=path,flush=False)
            with transcript.open("a",encoding="utf-8") as stream:
                stream.write(old[70:])
            telemetry.capture({**event,"hook_event_name":"Stop"},path=path,flush=False)
            with transcript.open("a",encoding="utf-8") as stream:
                stream.write(record({key:value*2 for key,value in tokens.items()}))
            telemetry.capture({**event,"hook_event_name":"Stop"},path=path,flush=False)
            with closing(sqlite3.connect(path)) as db:
                rows = [json.loads(row[0]) for row in db.execute("SELECT payload FROM pending")]
            usages = [row for row in rows if row["kind"] == "usage"]
            self.assertEqual(len(usages),1)
            self.assertEqual(usages[0]["tokens"],tokens)

    def test_consent_usage_offline_retry_and_opt_out(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite"
            transcript = Path(directory) / "session.jsonl"
            transcript.write_text(json.dumps({"type":"session_meta", "payload":{"id":"PRIVATE"}})+"\n", encoding="utf-8")
            event = {"hook_event_name":"SessionStart", "session_id":"PRIVATE", "model":"gpt-6.1-sol", "transcript_path":str(transcript), "cwd":"PRIVATE", "prompt":"SECRET"}
            with patch.object(telemetry, "enabled", return_value=False), patch.object(telemetry.urllib.request, "build_opener") as network:
                telemetry.capture(event, path=path)
                network.assert_not_called()
                self.assertFalse(path.exists())
            with patch.object(telemetry, "enabled", return_value=True):
                telemetry.capture(event, path=path, endpoint="http://127.0.0.1:1")
                self.assertEqual(telemetry.status(path)["pending"], 1)
                tokens = dict(input_tokens=100, cached_input_tokens=50, cache_write_input_tokens=0, output_tokens=10, reasoning_output_tokens=5, total_tokens=110)
                with transcript.open("a",encoding="utf-8") as stream:
                    for record in [{"type":"turn_context","payload":{"model":"gpt-6.1-sol","effort":"xhigh"}}, {"type":"response_item","payload":{"content":"SECRET"}}, {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":tokens,"last_token_usage":tokens}}}]:
                        stream.write(json.dumps(record)+"\n")
                telemetry.capture({**event,"hook_event_name":"Stop"}, path=path, flush=False)
                telemetry.capture({**event,"hook_event_name":"Stop"}, path=path, flush=False)
                with closing(sqlite3.connect(path)) as db:
                    rows = [json.loads(row[0]) for row in db.execute("SELECT payload FROM pending")]
                    usage = [row for row in rows if row["kind"] == "usage"]
                    self.assertEqual(len(usage),1)
                    self.assertEqual(usage[0]["tokens"],tokens)
                    self.assertEqual(usage[0]["effort"],"xhigh")
                    self.assertEqual(usage[0]["cost_microusd"],205)
                    wire = json.dumps(rows)
                    for private in ["SECRET","PRIVATE",str(transcript),"prompt","cwd","content"]:
                        self.assertNotIn(private,wire)
                    telemetry.put(db,"next_attempt",0)
                    db.commit()
                received = []
                class Receiver(BaseHTTPRequestHandler):
                    def do_POST(self):
                        batch = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                        received.extend(batch["events"])
                        self.send_response(200); self.end_headers()
                        self.wfile.write(json.dumps({"accepted":[row["event_id"] for row in batch["events"]]}).encode())
                    def log_message(self,*_): pass
                server = HTTPServer(("127.0.0.1",0),Receiver)
                thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
                try:
                    telemetry.capture({**event,"hook_event_name":"SubagentStart"}, path=path, endpoint=f"http://127.0.0.1:{server.server_port}")
                finally:
                    server.shutdown(); server.server_close(); thread.join()
                self.assertEqual(telemetry.status(path)["pending"],0)
                self.assertEqual(telemetry.status(path)["delivery"],"acknowledged")
                self.assertEqual(len(received),5)
                telemetry.capture(event,path=path,flush=False)
            with patch.object(telemetry,"enabled",return_value=False), patch.object(telemetry.urllib.request,"build_opener") as network:
                telemetry.capture(event,path=path)
                network.assert_not_called()
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM pending").fetchone()[0],0)
                    self.assertEqual(db.execute("SELECT count(*) FROM state").fetchone()[0],0)


if __name__ == "__main__":
    unittest.main()
