import json
import tempfile
import unittest
import runpy
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from swarm_usage import FIELDS, build_report, read_session, standard_cost, verify_candidate


def counts(input=100, cached=80, output=20, reasoning=5, writes=0):
    return dict(zip(FIELDS, (input, cached, writes, output, reasoning, input + output)))


class TrackingTests(unittest.TestCase):
    def session(self, events):
        records = [{"type": "session_meta", "payload": {"id": "one"}},
                   {"type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": "xhigh"}}]
        records.extend(events)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "session.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        return path

    def event(self, total=None, last=None, hour=1):
        return {"type": "event_msg", "timestamp": f"2026-10-01T{hour:02}:00:00Z",
                "payload": {"type": "token_count", "info": {
                    "total_token_usage": total or counts(), "last_token_usage": last or counts()}}}

    def test_native_fork_header_preserves_child_identity_and_cannot_double_count(self):
        path = self.session([self.event()])
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records[0]["payload"].update(source={"subagent":{"thread_spawn":{"parent_thread_id":"parent"}}})
        records.insert(1, {"type":"session_meta", "payload":{"id":"parent"}})
        path.write_text("\n".join(json.dumps(record) for record in records)+"\n",encoding="utf-8")
        result = read_session(path)
        self.assertEqual(result["thread_id"], "one")
        self.assertEqual(result["accounting_status"], "SNAPSHOT")
        self.assertEqual(result["tokens"]["total_tokens"], 120)
        records.append({"type":"session_meta", "payload":{"id":"unrelated"}})
        path.write_text("\n".join(json.dumps(record) for record in records)+"\n",encoding="utf-8")
        self.assertEqual(read_session(path)["accounting_status"], "UNVERIFIED")

    def test_fork_metadata_does_not_hide_conflicts_after_out_of_window_usage(self):
        path=self.session([self.event(), {"type":"session_meta","payload":{"id":"parent"}}])
        records=[json.loads(line) for line in path.read_text().splitlines()]
        records[0]["payload"]["source"]={"subagent":{"thread_spawn":{"parent_thread_id":"parent"}}}
        path.write_text("\n".join(json.dumps(record) for record in records)+"\n",encoding="utf-8")
        self.assertIn("conflicting session identities",read_session(path,after="2026-10-01T02:00:00Z")["issues"])
        records[0]["payload"]["source"]={"subagent":None}
        path.write_text("\n".join(json.dumps(record) for record in records[:3])+"\n",encoding="utf-8")
        self.assertEqual(read_session(path)["thread_id"],"one")

    def test_unknown_missing_identity_cannot_be_mistaken_for_fork_parent(self):
        result=read_session(self.session([{"type":"session_meta","payload":{"id":None}},self.event()]))
        self.assertEqual(result["thread_id"],"one")
        self.assertIn("conflicting session identities",result["issues"])

    def test_cache_and_reasoning_price(self):
        self.assertEqual(standard_cost(counts(), "gpt-6.1-sol"), Decimal("0.000248"))

    def test_long_context_is_per_request(self):
        self.assertEqual(standard_cost(counts(300_000, 200_000, 100), "gpt-6.1-sol"), Decimal("0.4415"))
        self.assertEqual(standard_cost(counts(272_000, 200_000, 100), "gpt-6.1-sol"), Decimal("0.165"))

    def test_duplicate_cumulative_event_is_counted_once(self):
        report = read_session(self.session([self.event(), self.event()]))
        self.assertEqual(report["tokens"]["total_tokens"], 120)
        self.assertEqual(report["usage_events"], 1)

    def test_start_boundary_subtracts_old_usage(self):
        report = read_session(self.session([self.event(), self.event(counts(200,160,40,10), hour=2)]), after="2026-10-01T01:30:00Z")
        self.assertEqual(report["tokens"]["total_tokens"], 120)
        self.assertEqual(report["by_model"][0]["standard_api_equivalent_usd"], "0.000248")

    def test_low_effort_is_rejected(self):
        change = {"type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": "low"}}
        report = build_report([read_session(self.session([change, self.event()]))])
        self.assertEqual(report["model_lock_status"], "FAIL")

    def test_unknown_model_is_unpriced(self):
        change = {"type": "turn_context", "payload": {"model": "unknown", "effort": "xhigh"}}
        report = build_report([read_session(self.session([change, self.event()]))])
        self.assertIsNone(report["standard_api_equivalent_usd"])

    def test_cache_writes_are_not_guessed(self):
        report = read_session(self.session([self.event(counts(writes=10), counts(writes=10))]))
        self.assertIsNone(report["by_model"][0]["standard_api_equivalent_usd"])

    def test_reset_and_missing_categories_invalidate_coverage(self):
        report = read_session(self.session([self.event(), self.event(counts(50,40,10,2), hour=2)]))
        self.assertEqual(report["accounting_status"], "UNVERIFIED")
        bad = counts(); del bad["cached_input_tokens"]
        report = read_session(self.session([self.event(bad)]))
        self.assertEqual(report["accounting_status"], "UNVERIFIED")

    def test_duplicate_identity_cannot_double_charge(self):
        report = read_session(self.session([self.event()]))
        with self.assertRaises(ValueError):
            build_report([report, report])

    def test_bad_request_reconciliation_hides_total_price(self):
        report = build_report([read_session(self.session([self.event(counts(200,160,40,10))]))])
        self.assertIsNone(report["standard_api_equivalent_usd"])

    def test_invalid_window_and_timezone(self):
        path = self.session([self.event()])
        with self.assertRaises(ValueError):
            read_session(path, after="2026-10-01T02:00:00Z", before="2026-10-01T01:00:00Z")
        with self.assertRaises(ValueError):
            read_session(path, after="2026-10-01T01:00:00")

    def test_candidate_detects_unexpected_file(self):
        path = self.session([])
        root = path.parent / "candidate"; root.mkdir()
        (root / "unexpected").write_text("new")
        manifest = path.parent / "manifest.json"
        manifest.write_text(json.dumps({"candidate_root": str(root), "files": []}))
        self.assertEqual(verify_candidate(manifest)["status"], "FAIL")

    def test_rate_limit_only_event_does_not_invalidate(self):
        event = self.event(); event["payload"]["info"] = None
        report = read_session(self.session([event, self.event()]))
        self.assertEqual(report["accounting_status"], "SNAPSHOT")

    def test_impossible_cached_delta_is_rejected(self):
        report = read_session(self.session([self.event(counts(100,10)),
                                             self.event(counts(110,100), counts(10,90), hour=2)]))
        self.assertEqual(report["accounting_status"], "UNVERIFIED")


class SourceConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = runpy.run_path(str(SKILL_ROOT / "scripts/swarm_config.py"))
        cls.effective, _ = cls.config["load"](SKILL_ROOT / "assets/swarm-benchmark.toml")

    def test_model_capability_gap_reproduced_without_override(self):
        original = deepcopy(self.effective)
        del original["model_capabilities"]["gpt-6.1-sol"]
        with self.assertRaisesRegex(self.config["ConfigError"], "no declared capabilities"):
            self.config["resolve_role_assignment"](original, "doer", explicit_model="gpt-6.1-sol", explicit_reasoning="xhigh")

    def test_all_roles_profiles_and_route_tiers_keep_xhigh(self):
        roles = self.config["STRUCTURAL_CONFIG_ROLES"] | self.config["BUILT_IN_PROFESSIONS"].keys()
        for profile in ("high", "medium", "low"):
            effective = deepcopy(self.effective)
            effective["execution"]["usage_profile"] = profile
            for role in roles:
                for tier in (1, 2, 3):
                    with self.subTest(profile=profile, role=role, tier=tier):
                        assignment = self.config["resolve_role_assignment"](effective, role, route_tier=tier)
                        self.assertEqual(assignment, {"model": "gpt-6.1-sol", "reasoning": "xhigh"})

    def test_assignments_disable_routes_and_preserve_explicit_selection(self):
        self.assertFalse(self.effective["execution"]["usage_saver"])
        self.assertFalse(self.effective["execution"]["jev_model_selection"])
        self.assertFalse(self.effective["boost"]["spark_enabled"])
        self.assertFalse(self.effective["chat_relay"]["enabled"])
        for surface in ("codex_task", "subagent"):
            for role in self.config["STRUCTURAL_CONFIG_ROLES"]:
                assignment = self.config["resolve_model_assignment"](
                    self.effective, role, surface=surface,
                    explicit_model="gpt-6.1-sol", explicit_reasoning="xhigh")
                self.assertEqual((assignment["model"], assignment["reasoning_effort"]), ("gpt-6.1-sol", "xhigh"))
                self.assertEqual(assignment["selection_source"], "explicit_user")
                self.assertEqual(assignment["actual_model_verification"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
