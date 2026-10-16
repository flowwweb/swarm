import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills/swarm"))
SCRIPT = ROOT / "skills/swarm/scripts/swarm_init.py"
spec = importlib.util.spec_from_file_location("swarm_init", SCRIPT)
init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init)


class ProjectInitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, {"SWARM_CONFIG_PATH": str(self.root / "missing-config.toml")})
        environment.start()
        self.addCleanup(environment.stop)

    def brief(self):
        return init.parse_project_brief_markdown((self.root / "SWARM.md").read_text(encoding="utf-8"))

    def write_brief(self, brief):
        (self.root / "SWARM.md").write_text(init._markdown("Edited brief", "<!-- swarm-project-brief:schema=1 -->", brief), encoding="utf-8")

    def snapshot(self):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir() if p.is_file()}

    def test_plan_retains_named_links_and_unknown_history_without_conversion(self):
        import hashlib
        brief = init._new_brief(self.root)
        brief["links"] = {f"source_{i}": f"evidence/source-{i}.md" for i in range(10)}
        brief["planning"] = {"history": [{"owner_id": "owner-1", "artifact": {"id": "proof-1"}}]}
        self.write_brief(brief)
        before = self.snapshot()
        parsed, digest = self.brief()
        self.assertEqual(parsed, brief)
        self.assertEqual(digest, "sha256:" + hashlib.sha256(json.dumps(
            brief, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
        for _ in range(2):
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root),
                                     "--plan", "--no-questions"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertEqual(plan["status"], "LEGACY_LAYOUT")
            self.assertFalse(plan["approval_verified"])
            self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.brief(), (brief, digest))
        with self.assertRaisesRegex(ValueError, "named links must be explicitly migrated"):
            init.archive_brief_section(self.root, "planning", expected_sha256=hashlib.sha256(before["SWARM.md"][0]).hexdigest())
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / "history").exists())

    def test_named_links_reject_invalid_mapping_without_writes(self):
        for links in ({"": "source.md"}, {"source": ""}, {"source": None},
                      {"source": ["source.md"]}, {"source": {"ref": "source.md"}},
                      {"source\n": "source.md"}, {"source": "source\x00.md"}, 1, "source.md"):
            with self.subTest(links=links):
                brief = init._new_brief(self.root)
                brief["links"] = links
                self.write_brief(brief)
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, "field links is invalid"):
                    init.plan_alignment(self.root, questions_enabled=False)
                self.assertEqual(self.snapshot(), before)

    def test_alignment_missing_cli_is_read_only_even_with_questions_off(self):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root),
                                 "--plan", "--no-questions"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["status"], "MISSING")
        self.assertEqual(plan["missing"], ["project.md", "roadmap.md", "swarm.md", "design.md"])
        self.assertFalse(plan["questions_enabled"])
        self.assertFalse(plan["approval_verified"])
        self.assertTrue(plan["requires_explicit_approval"])
        self.assertEqual(plan["next_action"], "EXPLICIT_BASELINE_REVIEW")
        self.assertEqual(list(self.root.iterdir()), [])
        invalid = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root),
                                  "--no-questions"], capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("--no-questions requires --plan", invalid.stderr)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_alignment_human_cohort_is_content_bound_not_text_approved(self):
        import hashlib
        for name in ("project.md", "roadmap.md", "swarm.md", "design.md"):
            (self.root / name).write_bytes(("# Approved " + name + "\r\n").encode())
        before = self.snapshot()
        first = init.plan_alignment(self.root)
        self.assertEqual(first["status"], "PROVISIONAL")
        self.assertEqual(init.plan_alignment(self.root), first)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(first["next_action"], "GUIDED_ALIGNMENT")
        self.assertFalse(first["approval_verified"])
        for row in first["documents"]:
            self.assertEqual(row["kind"], "HUMAN_MARKDOWN")
            self.assertEqual(row["sha256"], hashlib.sha256(before[row["name"]][0]).hexdigest())
        (self.root / "design.md").write_text("# Revised", encoding="utf-8")
        self.assertNotEqual(init.plan_alignment(self.root)["cohort_digest"], first["cohort_digest"])

    def test_alignment_partial_human_document_never_creates_legacy_index(self):
        (self.root / "project.md").write_text("# User-owned project", encoding="utf-8")
        before = self.snapshot()
        plan = init.plan_alignment(self.root)
        self.assertEqual(plan["status"], "PARTIAL")
        self.assertEqual(plan["missing"], ["roadmap.md", "swarm.md", "design.md"])
        self.assertEqual(self.snapshot(), before)

    def test_alignment_uses_real_config_and_questions_never_approve(self):
        settings = self.root / "settings.toml"
        settings.write_text("[init]\nguided_interview = false\n", encoding="utf-8")
        before = self.snapshot()
        off = init.plan_alignment(self.root, config_path=settings)
        self.assertFalse(off["questions_enabled"])
        self.assertEqual(off["questions"], [])
        self.assertEqual(off["question_source"], "CONFIG")
        self.assertFalse(off["approval_verified"])
        explicit = init.plan_alignment(self.root, config_path=settings, questions_enabled=True)
        self.assertEqual([q["id"] for q in explicit["questions"]], ["outcome", "boundaries"])
        self.assertEqual(explicit["question_source"], "USER_OVERRIDE")
        self.assertFalse(explicit["approval_verified"])
        self.assertEqual(self.snapshot(), before)
        settings.write_text("[init]\nguided_interview = true\n", encoding="utf-8")
        cli = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "--plan",
                              "--config", str(settings), "--no-questions"], capture_output=True, text=True)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertEqual(json.loads(cli.stdout)["questions"], [])
        settings.write_text('[init]\nguided_interview = "false"\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            init.plan_alignment(self.root, config_path=settings)
        invalid = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "--plan",
                                  "--config", str(settings)], capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 1)
        self.assertEqual(json.loads(invalid.stderr)["status"], "BLOCKED")

    def test_alignment_legacy_layout_preserves_upper_lower_case_alias(self):
        init.initialize(self.root)
        before = self.snapshot()
        plan = init.plan_alignment(self.root, questions_enabled=False)
        self.assertEqual(plan["status"], "LEGACY_LAYOUT")
        self.assertEqual(plan["legacy"], ["project.md", "swarm.md"])
        self.assertEqual(plan["documents"][2]["path"], "SWARM.md")
        self.assertEqual(plan["documents"][2]["kind"], "LEGACY_BRIEF")
        self.assertEqual(plan["next_action"], "REVIEW_LEGACY_MIGRATION")
        self.assertEqual(self.snapshot(), before)
        manifest = init._parse_manifest((self.root / "project.md").read_text(encoding="utf-8"))
        manifest["project"]["id"] = "conflicting"
        (self.root / "project.md").write_text(init._markdown("Snapshot", init.MANIFEST_MARKER, manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "identities conflict"):
            init.plan_alignment(self.root)

    def test_alignment_invalid_or_oversize_source_is_not_empty_success(self):
        for text in ("<!-- swarm-project-brief:schema=1 -->\ninvalid",
                     "<!-- swarm-project-brief:schema=2 -->\nunsupported", "x" * (init.MAX_BYTES + 1)):
            (self.root / "swarm.md").write_text(text, encoding="utf-8")
            before = self.snapshot()
            with self.assertRaises(ValueError):
                init.plan_alignment(self.root)
            self.assertEqual(self.snapshot(), before)
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "--plan"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["status"], "BLOCKED")
        self.assertEqual(self.snapshot(), before)
        with self.assertRaisesRegex(ValueError, "boolean"):
            init.plan_alignment(self.root, questions_enabled="false")

    def test_alignment_rejects_collisions_and_changes_without_writes(self):
        original = Path.iterdir
        with patch.object(Path, "iterdir", lambda p: iter([p / "project.md", p / "PROJECT.md"])
                          if p == self.root else original(p)):
            with self.assertRaisesRegex(ValueError, "collision"):
                init.plan_alignment(self.root)
        (self.root / "design.md").write_text("# First", encoding="utf-8")
        read = init._read
        reads = 0
        def changed(path):
            nonlocal reads
            reads += 1
            return read(path) if reads == 1 else "# Concurrent edit"
        before = self.snapshot()
        with patch.object(init, "_read", changed):
            with self.assertRaisesRegex(ValueError, "changed during alignment"):
                init.plan_alignment(self.root)
        self.assertEqual(self.snapshot(), before)

    def human_cohort(self):
        init.initialize(self.root)
        directory = self.root / "alignment"
        directory.mkdir()
        for name in ("project.md", "roadmap.md", "swarm.md", "design.md"):
            (directory / name).write_bytes(("# Draft " + name + "\r\n").encode())
        return directory

    def test_alignment_explicit_cohort_preserves_canonical_brief_and_legacy_index(self):
        directory = self.human_cohort()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        plan = init.plan_alignment(self.root, cohort_dir=Path("alignment"))
        self.assertEqual(plan["status"], "PROVISIONAL")
        self.assertEqual(plan["legacy"], [])
        self.assertEqual(Path(plan["documents_root"]), directory)
        self.assertEqual(plan["source_binding"]["canonical_brief_digest"], self.brief()[1])
        self.assertFalse(plan["approval_verified"])
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root),
                                 "--plan", "--cohort-dir", "alignment"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), plan)
        self.assertEqual({p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}, before)

    def test_alignment_staged_answers_are_exact_bound_review_input_never_approval(self):
        self.human_cohort()
        plan = init.plan_alignment(self.root, cohort_dir=Path("alignment"))
        staged = {"binding_digest": plan["binding_digest"],
                  "answers": {"outcome": "Synthetic fixture only", "boundaries": "Preserve user files"}}
        result = init.plan_alignment(self.root, cohort_dir=Path("alignment"), staged_answers=staged)
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["answered_question_ids"], ["outcome", "boundaries"])
        self.assertTrue(result["ready_for_explicit_review"])
        self.assertFalse(result["approval_verified"])
        self.assertTrue(result["requires_explicit_approval"])
        self.assertNotIn("Synthetic fixture only", json.dumps(result))
        self.assertEqual(init.plan_alignment(self.root, cohort_dir=Path("alignment"), staged_answers=staged), result)
        revised = {**staged, "answers": {**staged["answers"], "outcome": "Different fixture"}}
        self.assertNotEqual(init.plan_alignment(self.root, cohort_dir=Path("alignment"), staged_answers=revised)["review_digest"], result["review_digest"])
        partial = init.plan_alignment(self.root, cohort_dir=Path("alignment"),
                                      staged_answers={**staged, "answers": {"outcome": "One answer"}})
        self.assertEqual([q["id"] for q in partial["questions"]], ["boundaries"])
        self.assertFalse(partial["ready_for_explicit_review"])
        answers = self.root / "answers.json"
        answers.write_text(json.dumps(staged), encoding="utf-8")
        cli = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "--plan",
                              "--cohort-dir", "alignment", "--answers", str(answers)], capture_output=True, text=True)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertEqual(json.loads(cli.stdout), result)
        self.assertNotIn("Synthetic fixture only", cli.stdout)

    def test_alignment_stale_root_cohort_and_cross_project_answers_fail_closed(self):
        directory = self.human_cohort()
        plan = init.plan_alignment(self.root, cohort_dir=Path("alignment"))
        staged = {"binding_digest": plan["binding_digest"], "answers": {"outcome": "Fixture"}}
        source = directory / "design.md"
        original = source.read_bytes()
        source.write_bytes(original + b"changed")
        with self.assertRaisesRegex(ValueError, "exact current"):
            init.plan_alignment(self.root, cohort_dir=Path("alignment"), staged_answers=staged)
        source.write_bytes(original)
        root_brief = self.root / "SWARM.md"
        original_brief = root_brief.read_bytes()
        root_brief.write_bytes(original_brief + b"\n")
        self.assertEqual(self.brief()[1], plan["source_binding"]["canonical_brief_digest"])
        with self.assertRaisesRegex(ValueError, "exact current"):
            init.plan_alignment(self.root, cohort_dir=Path("alignment"), staged_answers=staged)
        root_brief.write_bytes(original_brief)
        other = self.root / "another-project"
        other.mkdir()
        init.initialize(other)
        other_cohort = other / "alignment"
        other_cohort.mkdir()
        for path in directory.iterdir():
            (other_cohort / path.name).write_bytes(path.read_bytes())
        with self.assertRaisesRegex(ValueError, "exact current"):
            init.plan_alignment(other, cohort_dir=Path("alignment"), staged_answers=staged)
        foreign, _ = init.parse_project_brief_markdown((other / "SWARM.md").read_text(encoding="utf-8"))
        (directory / "swarm.md").write_text(init._markdown("Foreign", "<!-- swarm-project-brief:schema=1 -->", foreign), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "another project"):
            init.plan_alignment(self.root, cohort_dir=Path("alignment"))
        (directory / "swarm.md").write_text("# Human guide", encoding="utf-8")
        (directory / "project.md").write_bytes((other / "project.md").read_bytes())
        with self.assertRaisesRegex(ValueError, "another project"):
            init.plan_alignment(self.root, cohort_dir=Path("alignment"))

    def test_alignment_cohort_and_answer_input_rejects_unsafe_or_approval_fields(self):
        directory = self.human_cohort()
        plan = init.plan_alignment(self.root, cohort_dir=Path("alignment"))
        staged = {"binding_digest": plan["binding_digest"], "answers": {"outcome": "Fixture"}}
        for invalid in (None, [], {**staged, "approval_verified": True},
                        {**staged, "answers": {"approved": "yes"}},
                        {**staged, "answers": {"outcome": " "}},
                        {**staged, "answers": {"outcome": True}},
                        {**staged, "answers": {"outcome": "é" * 1001}}):
            if invalid is None:
                continue
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                init.plan_alignment(self.root, cohort_dir=Path("alignment"), staged_answers=invalid)
        for invalid in (Path("../outside"), directory):
            with self.subTest(path=invalid), self.assertRaisesRegex(ValueError, "relative directory"):
                init.plan_alignment(self.root, cohort_dir=invalid)
        regular = init._regular
        def reparse(path, **kwargs):
            if path == directory:
                raise ValueError("link/reparse path is not admissible")
            return regular(path, **kwargs)
        with patch.object(init, "_regular", reparse), self.assertRaisesRegex(ValueError, "reparse"):
            init.plan_alignment(self.root, cohort_dir=Path("alignment"))
        before = self.snapshot()
        for args in (["--cohort-dir", "alignment"], ["--answers", "missing.json"]):
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root), *args],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("require --plan", result.stderr)
        answers = self.root / "answers.json"
        answers.write_text("x" * 8193, encoding="utf-8")
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "--plan",
                                 "--cohort-dir", "alignment", "--answers", str(answers)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("exceeds 8192", result.stderr)
        answers.unlink()
        self.assertEqual(self.snapshot(), before)

    def inventory_brief(self):
        brief = init._new_brief(self.root)
        brief["tasks"] = [{"id": "task-accepted", "state": "accepted"}, {"id": "task-complete", "state": "completed"}]
        brief["hq_screen_acceptance"] = {"screen_states": [
            {"id": f"screen-{i}", "state": "accepted" if i % 2 else "unknown",
             "history": [{"revision": 1, "gate": "pending"}]} for i in range(249)]}
        text = init._markdown("Retained brief", "<!-- swarm-project-brief:schema=1 -->", brief)
        text = text.replace('"hq_screen_acceptance": {', '"hq_screen_acceptance": ' + " " * init.MAX_BYTES + "{")
        (self.root / "SWARM.md").write_bytes(text.encode("utf-8"))
        return brief, text.encode("utf-8")

    def review_fixture(self):
        from dataclasses import replace
        from runtime import AcceptanceContract, Role
        from skills.swarm.tests import test_request_ledger as requests

        self.human_cohort()
        binding = init.plan_alignment(self.root, cohort_dir=Path("alignment"))["binding_digest"]
        options = {"cohort_dir": Path("alignment"), "staged_answers": {
            "binding_digest": binding, "answers": {"outcome": "Synthetic outcome", "boundaries": "Synthetic constraints"}}}
        artifact = init.alignment_review_artifact(self.root, **options)
        live = requests.swarm(self.root)
        task = requests.task()
        task.acceptance_contract = AcceptanceContract(artifact, observation_root=str(self.root))
        task.delegation_contract = replace(task.delegation_contract, artifact=artifact)
        stage = live.stage_request_task(Role.CTRL, task)
        return requests, live, task, stage, options, artifact

    def test_alignment_registers_exact_live_review_and_retains_existing_request(self):
        from runtime import CtrlFeedEventKind, RequestDue, RequestState
        requests, live, task, stage, options, artifact = self.review_fixture()
        decision, _ = requests.event(live, task.id, (stage.request_id,), "alignment", CtrlFeedEventKind.DECISION, "usr")
        accepted = init.register_alignment_review(self.root, live, stage.id, decision,
                                                  accepted_at=1, due=RequestDue("alignment-review", 2), **options)
        self.assertEqual(accepted.record.state, RequestState.OPEN)
        self.assertEqual(accepted.record.task_id, task.id)
        self.assertEqual(accepted.record.outcome_identity, live._request_outcome_identity(task, stage.request_id))
        self.assertEqual(task.acceptance_contract.artifact, artifact)
        before = live.request_store.peek()
        retained = {p: p.read_bytes() for p in (self.root / ".codex").rglob("*") if p.is_file()}
        replay = init.register_alignment_review(self.root, live, stage.id, decision,
                                                accepted_at=1, due=RequestDue("alignment-review", 2), **options)
        self.assertEqual(replay.record, accepted.record)
        self.assertEqual(live.request_store.peek(), before)
        self.assertEqual({p: p.read_bytes() for p in retained}, retained)
        restarted = requests.swarm(self.root)
        restarted.tasks[task.id] = task
        self.assertEqual(restarted.request_audit(2).records, (accepted.record,))
        self.assertEqual(restarted.request_audit(2).orphaned_ids, ())
        self.assertFalse(init.plan_alignment(self.root, **options)["approval_verified"])

    def test_alignment_review_rejects_changed_source_answers_and_foreign_stage(self):
        from runtime import CtrlFeedEventKind, RequestDue
        requests, live, task, stage, options, artifact = self.review_fixture()
        decision, _ = requests.event(live, task.id, (stage.request_id,), "stalealignment", CtrlFeedEventKind.DECISION, "usr")
        before = live.request_store.peek()
        retained = {p: p.read_bytes() for p in (self.root / ".codex").rglob("*") if p.is_file()}
        changed = {**options, "staged_answers": {**options["staged_answers"], "answers": {
            **options["staged_answers"]["answers"], "outcome": "Changed synthetic outcome"}}}
        with self.assertRaisesRegex(ValueError, "does not bind"):
            init.register_alignment_review(self.root, live, stage.id, decision,
                                           accepted_at=1, due=RequestDue("review", 2), **changed)
        with self.assertRaisesRegex(ValueError, "does not bind"):
            init.register_alignment_review(self.root, live, "stg-missing", decision,
                                           accepted_at=1, due=RequestDue("review", 2), **options)
        source = self.root / "alignment/design.md"
        source.write_bytes(source.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "exact current"):
            init.register_alignment_review(self.root, live, stage.id, decision,
                                           accepted_at=1, due=RequestDue("review", 2), **options)
        self.assertEqual(live.request_store.peek(), before)
        self.assertEqual({p: p.read_bytes() for p in retained}, retained)

    def test_alignment_review_requires_live_root_and_explicit_existing_user_decision(self):
        from runtime import CtrlFeedEventKind, RequestDue
        requests, live, task, stage, options, artifact = self.review_fixture()
        decision, _ = requests.event(live, task.id, (stage.request_id,), "notuser", CtrlFeedEventKind.DECISION)
        before = live.request_store.peek()
        with self.assertRaisesRegex(Exception, "user decision"):
            init.register_alignment_review(self.root, live, stage.id, decision,
                                           accepted_at=1, due=RequestDue("review", 2), **options)
        for authority, root in ((object(), self.root), (live, self.root / "foreign")):
            with self.assertRaisesRegex(ValueError, "live Swarm"):
                init.register_alignment_review(root, authority, stage.id, decision,
                                               accepted_at=1, due=RequestDue("review", 2), **options)
        self.assertEqual(live.request_store.peek(), before)
        self.assertFalse(init.plan_alignment(self.root, **options)["approval_verified"])

    def test_alignment_review_rejects_unanswered_questions_cohort_collision_and_race(self):
        directory = self.human_cohort()
        with self.assertRaisesRegex(ValueError, "resolved questions"):
            init.alignment_review_artifact(self.root, cohort_dir=Path("alignment"))
        original = Path.iterdir
        with patch.object(Path, "iterdir", lambda p: iter([p / "project.md", p / "PROJECT.md"])
                          if p == directory else original(p)):
            with self.assertRaisesRegex(ValueError, "collision"):
                init.alignment_review_artifact(self.root, cohort_dir=Path("alignment"), questions_enabled=False)
        from runtime import ArtifactIdentity
        reobserve = ArtifactIdentity.reobserve
        def changed(artifact, root):
            (directory / "design.md").write_text("# Concurrent edit", encoding="utf-8")
            return reobserve(artifact, root)
        with patch.object(ArtifactIdentity, "reobserve", changed):
            with self.assertRaisesRegex(ValueError, "source changed"):
                init.alignment_review_artifact(self.root, cohort_dir=Path("alignment"), questions_enabled=False)

    def test_space_snapshot_cli_retains_all_states_and_is_deterministic_without_writes(self):
        import hashlib
        self.human_cohort()
        (self.root / "alignment/design.md").write_text("# Direction → 🐙", encoding="utf-8")
        brief, _ = self.brief()
        brief["milestones"] = [{"id": "m", "state": "accepted", "task_ids": ["done", "accepted", "open"]}]
        brief["tasks"] = [{"id": "done", "state": "completed", "history": ["PRIVATE fixture"],
                           "raw_answers": "PRIVATE fixture"},
                          {"id": "accepted", "state": "accepted"}, {"id": "open", "state": "unknown"}]
        self.write_brief(brief)
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        first = init.space_snapshot(self.root, cohort_dir=Path("alignment"))
        second = init.space_snapshot(self.root, cohort_dir=Path("alignment"))
        self.assertEqual(first["snapshot"], second["snapshot"])
        self.assertEqual(first["snapshot_digest"], second["snapshot_digest"])
        records = first["snapshot"]["records"]
        self.assertEqual([r["value"]["state"] for r in records["tasks"]], ["completed", "accepted", "unknown"])
        self.assertEqual(records["milestones"][0]["source_pointer"], "/milestones/0")
        self.assertEqual(records["tasks"][0]["source_record_digest"], "sha256:" + hashlib.sha256(json.dumps(
            brief["tasks"][0], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
        self.assertNotIn("PRIVATE fixture", json.dumps(first))
        self.assertIsNone(first["snapshot"]["cursor"])
        self.assertIsNone(first["destination"])
        self.assertFalse(first["approval_verified"])
        self.assertEqual(first["snapshot"]["canonical_digest"], self.brief()[1])
        self.assertEqual(len(first["snapshot"]["documents"]), 4)
        cli = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root),
                              "--space-snapshot", "--cohort-dir", "alignment"], capture_output=True, text=True,
                             env={**os.environ, "PYTHONIOENCODING": "cp1252"})
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertEqual(json.loads(cli.stdout)["snapshot_digest"], first["snapshot_digest"])
        self.assertEqual({p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}, before)

    def test_space_snapshot_unknown_missing_invalid_and_duplicate_records_fail_honestly(self):
        self.human_cohort()
        unknown = init.space_snapshot(self.root, cohort_dir=Path("alignment"))
        self.assertIsNone(unknown["snapshot"]["records"]["tasks"])
        self.assertEqual(unknown["snapshot"]["records"]["milestones"], [])
        brief, _ = self.brief()
        for invalid in ({"copied": "not a task list"}, [{"id": "duplicate"}, {"id": "duplicate"}],
                        [{"id": "nested", "title": {"history": "PRIVATE"}}]):
            brief["tasks"] = invalid
            self.write_brief(brief)
            with self.assertRaises(ValueError):
                init.space_snapshot(self.root, cohort_dir=Path("alignment"))
        (self.root / "alignment/design.md").unlink()
        with self.assertRaisesRegex(ValueError, "complete separate"):
            init.space_snapshot(self.root, cohort_dir=Path("alignment"))
        cli = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "--space-snapshot"],
                             capture_output=True, text=True)
        self.assertEqual(cli.returncode, 1)
        self.assertIn("explicit --cohort-dir", cli.stderr)

    def test_space_refresh_changed_source_is_rejected_without_replacing_prior_payload(self):
        self.human_cohort()
        previous = init.space_snapshot(self.root, cohort_dir=Path("alignment"))
        frozen = json.dumps(previous, sort_keys=True)
        original = init.plan_alignment
        calls = 0
        def changed(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.root / "alignment/design.md").write_text("# New design", encoding="utf-8")
            return original(*args, **kwargs)
        with patch.object(init, "plan_alignment", changed):
            with self.assertRaisesRegex(ValueError, "source changed during Space refresh"):
                init.space_snapshot(self.root, cohort_dir=Path("alignment"))
        self.assertEqual(json.dumps(previous, sort_keys=True), frozen)
        current = init.space_snapshot(self.root, cohort_dir=Path("alignment"))
        self.assertNotEqual(current["snapshot_digest"], previous["snapshot_digest"])

    def test_interview_cli_asks_real_stdin_and_returns_only_unwritten_version_bound_drafts(self):
        self.human_cohort()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        command = [sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "--interview", "--cohort-dir", "alignment"]
        result = subprocess.run(command, input="Synthetic fixture objective\nPreserve fixture files\n",
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        proposal = json.loads(result.stdout)
        self.assertIn("What should this project achieve", result.stderr)
        self.assertIn("What must remain out of scope", result.stderr)
        self.assertEqual(proposal["plan"]["questions"], [])
        self.assertEqual(proposal["plan"]["answered_question_ids"], ["outcome", "boundaries"])
        self.assertEqual(set(proposal["draft_documents"]), {"project.md", "roadmap.md", "design.md", "swarm.md"})
        self.assertIn("Synthetic fixture objective", proposal["draft_documents"]["project.md"])
        self.assertIn("Preserve fixture files", proposal["draft_documents"]["project.md"])
        self.assertNotIn("answers", proposal)
        self.assertFalse(proposal["approval_verified"])
        repeated = subprocess.run(command, input="Synthetic fixture objective\nPreserve fixture files\n",
                                  capture_output=True, text=True)
        self.assertEqual(json.loads(repeated.stdout)["draft_digest"], proposal["draft_digest"])
        changed = subprocess.run(command, input="Changed fixture objective\nPreserve fixture files\n",
                                 capture_output=True, text=True)
        self.assertNotEqual(json.loads(changed.stdout)["draft_digest"], proposal["draft_digest"])
        self.assertEqual({p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}, before)

    def test_interview_questions_off_eof_and_invalid_answers_never_create_or_approve(self):
        self.human_cohort()
        config = self.root / "settings.toml"
        config.write_text("[init]\nguided_interview = false\n", encoding="utf-8")
        ask = unittest.mock.Mock(side_effect=AssertionError("must not ask"))
        off = init.interview_alignment(self.root, cohort_dir=Path("alignment"), config_path=config, ask=ask)
        ask.assert_not_called()
        self.assertIsNone(off["draft_documents"])
        self.assertFalse(off["plan"]["approval_verified"])
        before = self.snapshot()
        for answer in ("", "\n", "x" * 2001 + "\n"):
            cli = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root),
                                  "--interview", "--cohort-dir", "alignment"], input=answer,
                                 capture_output=True, text=True)
            self.assertEqual(cli.returncode, 1)
            self.assertEqual(json.loads(cli.stderr.splitlines()[-1])["status"], "BLOCKED")
            self.assertEqual(cli.stdout, "")
        self.assertEqual(self.snapshot(), before)

    def test_interview_detects_source_change_during_human_answer(self):
        directory = self.human_cohort()
        def edit_while_answering(question):
            (directory / "design.md").write_text("# Concurrent design", encoding="utf-8")
            return "Synthetic fixture"
        with self.assertRaisesRegex(ValueError, "exact current"):
            init.interview_alignment(self.root, cohort_dir=Path("alignment"), ask=edit_while_answering)

    def test_history_extraction_roundtrip_restart_and_exact_replay(self):
        import hashlib
        brief, original = self.inventory_brief()
        self.assertGreater(len(original), init.MAX_BYTES)
        expected = hashlib.sha256(original).hexdigest()
        result = init.archive_brief_section(self.root, "hq_screen_acceptance", expected_sha256=expected)
        self.assertEqual(result["status"], "ARCHIVED")
        reference = result["archive"]
        self.assertEqual((self.root / reference["path"]).read_bytes(), original)

        current_before = (self.root / "SWARM.md").read_bytes()
        self.assertEqual(init.initialize(self.root)["created"], ["project.md"])
        self.assertEqual(init.initialize(self.root)["created"], [])
        self.assertEqual((self.root / "SWARM.md").read_bytes(), current_before)
        self.assertEqual((self.root / reference["path"]).read_bytes(), original)
        current, _ = self.brief()
        for key, value in brief.items():
            if key not in {"hq_screen_acceptance", "links", "updated_at"}:
                self.assertEqual(current[key], value)
        self.assertEqual(current["links"], [*brief["links"], reference])
        retained = init.read_brief_history(self.root, reference)
        self.assertEqual(retained, brief["hq_screen_acceptance"])
        self.assertEqual(len(retained["screen_states"]), 249)
        self.assertLess((self.root / "SWARM.md").stat().st_size, init.MAX_BYTES)
        before = self.snapshot()
        replay = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root),
                                 "--archive-section", "hq_screen_acceptance", "--expected-sha256", expected],
                                capture_output=True, text=True)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        self.assertEqual(json.loads(replay.stdout)["status"], "REPLAY")
        plan = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "--plan"],
                              capture_output=True, text=True)
        self.assertEqual(plan.returncode, 0, plan.stderr)
        self.assertEqual(json.loads(plan.stdout)["status"], "LEGACY_LAYOUT")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((self.root / reference["path"]).read_bytes(), original)

    def test_history_stale_core_and_tampered_references_fail_closed(self):
        import hashlib
        _, original = self.inventory_brief()
        expected = hashlib.sha256(original).hexdigest()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "changed"):
            init.archive_brief_section(self.root, "hq_screen_acceptance", expected_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "current canonical state"):
            init.archive_brief_section(self.root, "tasks", expected_sha256=expected)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / "history").exists())
        result = init.archive_brief_section(self.root, "hq_screen_acceptance", expected_sha256=expected)
        ref = result["archive"]
        with self.assertRaisesRegex(ValueError, "invalid brief history"):
            init.read_brief_history(self.root, {**ref, "path": "../outside.md"})
        with self.assertRaisesRegex(ValueError, "canonical binding"):
            init.read_brief_history(self.root, {**ref, "canonical_digest": "sha256:" + "0" * 64})
        archive = self.root / ref["path"]
        archive.write_bytes(original + b"\nchanged")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "bytes/digest"):
            init.plan_alignment(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_history_interruption_preserves_backup_and_racing_owner(self):
        import hashlib
        _, original = self.inventory_brief()
        expected = hashlib.sha256(original).hexdigest()
        create = init._create
        def racing_create(path, text):
            create(path, text)
            if path.parent.name == "history":
                (self.root / "SWARM.md").write_bytes(original + b"\nother owner edit")
        with patch.object(init, "_create", racing_create):
            with self.assertRaisesRegex(ValueError, "changed before"):
                init.archive_brief_section(self.root, "hq_screen_acceptance", expected_sha256=expected)
        self.assertEqual((self.root / "SWARM.md").read_bytes(), original + b"\nother owner edit")
        self.assertEqual((self.root / f"history/swarm-brief-{expected}.md").read_bytes(), original)
        self.assertEqual(list(self.root.glob(".swarm-brief-*.tmp")), [])

    def test_clean_cli_creates_both_and_parser_bound_manifest(self):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["created"], ["SWARM.md", "project.md"])
        brief, digest = self.brief()
        manifest = init._parse_manifest((self.root / "project.md").read_text(encoding="utf-8"))
        self.assertEqual(manifest["project"]["id"], brief["project"]["id"])
        self.assertEqual(manifest["provenance"]["canonical_digest"], digest)
        self.assertEqual(receipt["canonical_brief_digest"], digest)
        self.assertEqual(set(p.name for p in self.root.iterdir()), {"SWARM.md", "project.md"})

    def test_repeat_preserves_edits_identity_and_mtimes_reports_stale(self):
        first = init.initialize(self.root)
        brief, _ = self.brief()
        brief["project"]["purpose"] = "User edited purpose"
        self.write_brief(brief)
        with (self.root / "project.md").open("a", encoding="utf-8") as stream:
            stream.write("\nMy handwritten notes.\n")
        before = self.snapshot()
        result = init.initialize(self.root)
        self.assertEqual(result["status"], "ADOPTED")
        self.assertEqual(result["project_id"], first["project_id"])
        self.assertTrue(any("stale" in item for item in result["warnings"]))
        self.assertEqual(self.snapshot(), before)

    def test_partial_uppercase_adopts_exact_historical_brief_and_milestone_refs(self):
        brief, _ = init.parse_project_brief_markdown((ROOT / "SWARM.md").read_text(encoding="utf-8"))
        self.write_brief(brief)
        before = self.snapshot()["SWARM.md"]
        result = init.initialize(self.root)
        self.assertEqual(result["created"], ["project.md"])
        self.assertEqual(result["project_id"], "swarm")
        self.assertEqual(self.snapshot()["SWARM.md"], before)
        self.assertIn("existing brief has no project.md link; preserved", result["warnings"])
        manifest = init._parse_manifest((self.root / "project.md").read_text(encoding="utf-8"))
        self.assertEqual(manifest["roadmap"]["ids"], [m["id"] for m in brief["milestones"]])
        self.assertNotIn("state", manifest["roadmap"])

    def test_case_insensitive_adoption(self):
        init.initialize(self.root)
        (self.root / "SWARM.md").rename(self.root / "swarm.md")
        (self.root / "project.md").rename(self.root / "PROJECT.md")
        before = self.snapshot()
        self.assertEqual(init.initialize(self.root)["created"], [])
        self.assertEqual(self.snapshot(), before)

    def test_case_collision_rejected_before_any_write_even_on_windows(self):
        real_iterdir = Path.iterdir
        def entries(path):
            return iter([path / "SWARM.md", path / "swarm.md"]) if path == self.root else real_iterdir(path)
        with patch.object(Path, "iterdir", entries):
            with self.assertRaisesRegex(ValueError, "collision"):
                init.initialize(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unknown_metadata_no_invented_owner_goal_or_binding(self):
        init.initialize(self.root)
        brief, _ = self.brief()
        self.assertTrue(brief["project"]["purpose"].startswith("UNKNOWN"))
        self.assertEqual(brief["repo"]["app"]["status"], "UNKNOWN")
        self.assertEqual(brief["repo"]["remote"]["status"], "UNKNOWN")
        self.assertEqual(brief["ownership"]["ctrl"]["status"], "UNKNOWN")
        self.assertEqual(brief["milestones"], [])
        self.assertNotIn("goals", brief)
        self.assertNotIn("claims", brief)

    def test_local_git_observation_does_not_verify_remote_or_app(self):
        replies = [subprocess.CompletedProcess([], 0, str(self.root)), subprocess.CompletedProcess([], 0, "a" * 40)]
        with patch.object(init.subprocess, "run", side_effect=replies) as run:
            init.initialize(self.root)
        brief, _ = self.brief()
        self.assertEqual(brief["repo"]["local_git"]["status"], "OBSERVED_LOCAL")
        self.assertEqual(brief["repo"]["app"]["status"], "UNKNOWN")
        self.assertEqual(brief["repo"]["remote"]["status"], "UNKNOWN")
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("remote", str(run.call_args_list))

    def test_adopted_sparse_brief_snapshot_labels_unknowns(self):
        brief = init._new_brief(self.root)
        brief["repo"] = {}
        brief["ownership"] = {}
        brief["proof_acceptance"] = {}
        self.write_brief(brief)
        init.initialize(self.root)
        manifest = init._parse_manifest((self.root / "project.md").read_text(encoding="utf-8"))
        self.assertEqual(manifest["bindings"]["app"]["status"], "UNKNOWN")
        self.assertEqual(manifest["owners"]["ctrl"]["status"], "UNKNOWN")
        self.assertEqual(manifest["acceptance_evidence"]["required"]["status"], "UNKNOWN")

    def test_adoption_missing_scope_never_relabels_current_objective(self):
        brief, _ = init.parse_project_brief_markdown((ROOT / "SWARM.md").read_text(encoding="utf-8"))
        self.assertNotIn("scope", brief["objective"])
        self.assertTrue(brief["objective"]["current"])
        self.write_brief(brief)
        before = self.snapshot()["SWARM.md"]
        init.initialize(self.root)
        manifest = init._parse_manifest((self.root / "project.md").read_text(encoding="utf-8"))
        self.assertEqual(manifest["scope"], {"status": "UNKNOWN", "reason": "brief has no scope"})
        self.assertIn("/objective", manifest["provenance"]["pointers"])
        self.assertEqual(self.snapshot()["SWARM.md"], before)

    def test_adoption_roadmap_requires_usable_ids_not_nonempty_collection(self):
        for milestones, expected in ((["Roadmap not supplied"], []),
                                     ([{}, {"id": None}, {"id": 1}, {"id": " "}], []),
                                     (["Roadmap not supplied", {"id": "foundation", "state": "open"}], ["foundation"])):
            with self.subTest(milestones=milestones):
                root = self.root / str(len(list(self.root.iterdir())))
                root.mkdir()
                brief = init._new_brief(root)
                brief["milestones"] = milestones
                path = root / "SWARM.md"
                path.write_text(init._markdown("Adopted", "<!-- swarm-project-brief:schema=1 -->", brief), encoding="utf-8")
                before = (path.read_bytes(), path.stat().st_mtime_ns)
                init.initialize(root)
                manifest = init._parse_manifest((root / "project.md").read_text(encoding="utf-8"))
                self.assertEqual(manifest["roadmap"]["ids"], expected)
                self.assertEqual(manifest["roadmap"]["status"], "REFERENCED" if expected else "UNKNOWN")
                if not expected:
                    self.assertEqual(manifest["roadmap"]["reason"], "No usable milestone IDs supplied.")
                self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_changed_brief_during_manifest_creation_fails_without_manifest(self):
        create = init._create
        def change_after_create(path, text):
            create(path, text)
            if path.name == "SWARM.md":
                path.write_text(text + "\nUser edit\n", encoding="utf-8")
        with patch.object(init, "_create", change_after_create):
            with self.assertRaisesRegex(ValueError, "changed during"):
                init.initialize(self.root)
        self.assertFalse((self.root / "project.md").exists())
        self.assertIn("User edit", (self.root / "SWARM.md").read_text(encoding="utf-8"))

    def test_invalid_or_ambiguous_brief_preserved_no_manifest(self):
        for text in ("user notes, not a brief", (ROOT / "SWARM.md").read_text(encoding="utf-8") * 2):
            with self.subTest(text=text[:20]):
                (self.root / "SWARM.md").write_text(text, encoding="utf-8")
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    init.initialize(self.root)
                self.assertEqual(self.snapshot(), before)

    def test_conflicting_identity_rejected_without_repair(self):
        init.initialize(self.root)
        manifest = init._parse_manifest((self.root / "project.md").read_text(encoding="utf-8"))
        manifest["project"]["id"] = "other-project"
        (self.root / "project.md").write_text(init._markdown("Edited", init.MANIFEST_MARKER, manifest), encoding="utf-8")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "identities conflict"):
            init.initialize(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_existing_unrecognized_manifest_prevents_brief_creation(self):
        (self.root / "project.md").write_text("User-owned project document", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            init.initialize(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_manifest_alone_never_reconstructs_authoritative_brief(self):
        init.initialize(self.root)
        (self.root / "SWARM.md").unlink()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "not authority"):
            init.initialize(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_nonregular_target_preflight(self):
        (self.root / "project.md").mkdir()
        with self.assertRaisesRegex(ValueError, "non-regular"):
            init.initialize(self.root)
        self.assertFalse((self.root / "SWARM.md").exists())

    def test_reparse_attribute_preflight(self):
        original = Path.lstat
        def observed(path):
            if path == self.root:
                from types import SimpleNamespace
                return SimpleNamespace(st_mode=init.stat.S_IFDIR, st_file_attributes=init.stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return original(path)
        with patch.object(Path, "lstat", observed):
            with self.assertRaisesRegex(ValueError, "reparse"):
                init.initialize(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_symlink_target_preflight(self):
        original = Path.lstat
        (self.root / "SWARM.md").write_text("untouched", encoding="utf-8")
        def observed(path):
            if path == self.root / "SWARM.md":
                from types import SimpleNamespace
                return SimpleNamespace(st_mode=init.stat.S_IFLNK, st_file_attributes=0)
            return original(path)
        with patch.object(Path, "lstat", observed):
            with self.assertRaisesRegex(ValueError, "link/reparse"):
                init.initialize(self.root)
        self.assertFalse((self.root / "project.md").exists())

    def test_interruption_after_brief_recovers_same_id(self):
        create = init._create
        def interrupted(path, text):
            if path.name == "project.md":
                raise OSError("simulated interruption")
            create(path, text)
        with patch.object(init, "_create", interrupted):
            with self.assertRaisesRegex(OSError, "interruption"):
                init.initialize(self.root)
        brief, _ = self.brief()
        before = self.snapshot()["SWARM.md"]
        result = init.initialize(self.root)
        self.assertEqual(result["created"], ["project.md"])
        self.assertEqual(result["project_id"], brief["project"]["id"])
        self.assertEqual(self.snapshot()["SWARM.md"], before)

    def test_exclusive_creation_never_overwrites_racing_writer(self):
        create = init._create
        def race(path, text):
            path.write_text("other writer", encoding="utf-8")
            create(path, text)
        with patch.object(init, "_create", race):
            with self.assertRaises(FileExistsError):
                init.initialize(self.root)
        self.assertEqual((self.root / "SWARM.md").read_text(), "other writer")
        self.assertFalse((self.root / "project.md").exists())


if __name__ == "__main__":
    unittest.main()
