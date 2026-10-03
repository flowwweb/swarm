"""Offline transport and shared-cap contracts; fake provider responses only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.swarm.runtime.jev_policy import MODEL, Rejected, encode
from skills.swarm.runtime.jev_transport import JevBudget, JevCliTransport, RESERVE_NANOUSD


class JevTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.budget = JevBudget(self.root, "test_scope", RESERVE_NANOUSD)
        self.digest = "a" * 64

    def test_reservation_restart_replay_and_unknown_cost(self):
        self.budget.reserve("one", self.digest)
        again = JevBudget(self.root, "test_scope", RESERVE_NANOUSD)
        for identity, digest, reason in (("one", self.digest, "already_reserved"),
                ("one", "b" * 64, "decision_conflict"), ("two", self.digest, "budget_exhausted")):
            with self.assertRaisesRegex(Rejected, reason):
                again.reserve(identity, digest)
        with self.assertRaisesRegex(Rejected, "budget_scope_mismatch"):
            JevBudget(self.root, "new_scope", RESERVE_NANOUSD).reserve("three", self.digest)
        with self.assertRaises(Rejected):
            JevBudget(self.root, "scope", True)

    def test_settle_requires_exact_verified_usage_and_never_releases_unknown(self):
        self.budget.reserve("one", self.digest)
        for tokens in (True, -1, 65537, None):
            with self.assertRaises(Rejected):
                self.budget.settle("one", self.digest, tokens)
        self.budget.settle("one", self.digest, 100)
        with self.assertRaises(Rejected):
            self.budget.settle("one", self.digest, 0)
        state = json.loads(self.budget.store.path.read_text())
        self.assertEqual(state["reservations"]["one"]["actual_nanousd"], 4200)

    def test_concurrent_processes_cannot_overspend(self):
        code = """import os,socket,sys
sys.path.insert(0,os.getcwd())
def blocked(*a,**k): raise AssertionError('No network')
socket.socket.connect=blocked
from skills.swarm.runtime.jev_transport import JevBudget,RESERVE_NANOUSD
from skills.swarm.runtime.jev_policy import Rejected
try:
 JevBudget(sys.argv[1],'test_scope',RESERVE_NANOUSD).reserve(sys.argv[2],'a'*64)
 print('reserved')
except Rejected as e: print(str(e))
"""
        env = {k:v for k,v in os.environ.items() if k.upper() in {"SYSTEMROOT","WINDIR","TEMP","TMP"}}
        children = [subprocess.Popen([sys.executable,"-B","-E","-s","-S","-c",code,str(self.root),name],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,
                    creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)) for name in ("one","two")]
        results = []
        for child in children:
            try:
                out, err = child.communicate(timeout=60)
            finally:
                if child.poll() is None:
                    child.kill(); child.communicate()
            self.assertEqual(child.returncode,0,err.decode())
            results.append(out.decode().strip())
        self.assertCountEqual(results,["reserved","budget_exhausted"])

    def transport(self, mock=False):
        node = self.root / "node.exe"; node.write_bytes(b"test placeholder")
        entry = self.root / "dist/swarm-jev.cjs"; entry.parent.mkdir(exist_ok=True); entry.write_bytes(b"test placeholder")
        digest = hashlib.sha256(b"test placeholder").hexdigest()
        return JevCliTransport(node=node,entrypoint=entry,bundle_sha256=digest,budget=self.budget,mock=mock)

    def test_unavailable_does_not_create_budget_and_bundle_change_blocks(self):
        transport = self.transport()
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(transport.availability(),"credential_unavailable")
        self.assertFalse(self.budget.store.path.exists())
        transport.entrypoint.write_bytes(b"changed")
        self.assertEqual(transport.availability(),"bundle_mismatch")

    def test_live_boundary_scrubs_environment_and_settles_only_valid_response(self):
        transport = self.transport()
        request = {"model":MODEL,"state":"synthetic","questions":{"stall.v1":{"type":"noul"}}}
        response = {"model":MODEL,"answers":{"stall.v1":{"type":"noul","noul":.96}},
                    "usage":{"input_tokens":100,"output_tokens":0},"truncated":False,"coverage":{}}
        result = subprocess.CompletedProcess([],0,encode(response))
        with patch.dict(os.environ,{"TYPESAFE_API_KEY":"synthetic-test-key","NODE_OPTIONS":"hostile", "HTTPS_PROXY":"hostile"}), patch("subprocess.run",return_value=result) as run:
            transport.evaluate(request,decision_id="one",material_digest=self.digest)
            kwargs = run.call_args.kwargs
            self.assertNotIn("NODE_OPTIONS",kwargs["env"])
            self.assertNotIn("HTTPS_PROXY",kwargs["env"])
            self.assertEqual(kwargs["env"]["TYPESAFE_BASE_URL"],"https://api.typesafe.ai")
            self.assertEqual(kwargs["env"]["JEV_MCP_TIMEOUT_MS"],"10000")
            self.assertIs(kwargs["stderr"],subprocess.DEVNULL)
            self.assertEqual(kwargs["timeout"],12.0)
            self.assertEqual(run.call_count,1)
        self.assertEqual(json.loads(self.budget.store.path.read_text())["reservations"]["one"]["status"],"settled")

    def test_invalid_provider_outcomes_retain_full_reservation(self):
        transport = self.transport()
        request = {"model":MODEL,"state":"synthetic","questions":{"stall.v1":{"type":"noul"}}}
        good = {"model":MODEL,"answers":{"stall.v1":{"type":"noul","noul":.96}},
                "usage":{"input_tokens":100,"output_tokens":0},"truncated":False,"coverage":{}}
        cases = [subprocess.CompletedProcess([],1,b""), subprocess.CompletedProcess([],0,b"not json"),
                 subprocess.CompletedProcess([],0,encode({**good,"truncated":True})),
                 subprocess.CompletedProcess([],0,encode({**good,"usage":{"input_tokens":65537,"output_tokens":0}}))]
        self.budget = JevBudget(self.root,"test_scope",RESERVE_NANOUSD * len(cases))
        transport.budget = self.budget
        for index,result in enumerate(cases):
            with patch.dict(os.environ,{"TYPESAFE_API_KEY":"synthetic-test-key"}), patch("subprocess.run",return_value=result):
                with self.assertRaises(ValueError):
                    transport.evaluate(request,decision_id=f"case_{index}",material_digest=self.digest)
        rows=json.loads(self.budget.store.path.read_text())["reservations"].values()
        self.assertTrue(all(row["status"] == "reserved" and row["actual_nanousd"] is None for row in rows))

    def test_explicit_config_does_not_require_user_home(self):
        from skills.swarm.scripts.swarm_jev import configured_adapter
        transport=self.transport(mock=True)
        config={"mode":"mock","node":str(transport.node),"entrypoint":str(transport.entrypoint),
                "bundle_sha256":transport.bundle_sha256,"budget_root":str(self.root),
                "budget_scope":"test_scope","cap_nanousd":0}
        path=self.root/"config.json";path.write_text(json.dumps(config))
        with patch.dict(os.environ,{"SWARM_JEV_CONFIG":str(path)},clear=True):
            self.assertEqual(configured_adapter().transport.availability(),"available")
        self.assertFalse(self.budget.store.path.exists())

    def test_timeout_retains_reservation_and_does_not_retry(self):
        transport = self.transport()
        with patch.dict(os.environ,{"TYPESAFE_API_KEY":"synthetic-test-key"}), patch("subprocess.run",side_effect=subprocess.TimeoutExpired("node",2)) as run:
            with self.assertRaises(TimeoutError):
                transport.evaluate({},decision_id="one",material_digest=self.digest)
            self.assertEqual(run.call_count,1)
        row = json.loads(self.budget.store.path.read_text())["reservations"]["one"]
        self.assertEqual(row["status"],"reserved")
        self.assertIsNone(row["actual_nanousd"])


if __name__ == "__main__":
    unittest.main()
