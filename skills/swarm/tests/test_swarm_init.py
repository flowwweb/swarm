import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/swarm/scripts/swarm_init.py"
spec = importlib.util.spec_from_file_location("swarm_init", SCRIPT)
init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init)


class ProjectInitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def brief(self):
        return init.parse_project_brief_markdown((self.root / "SWARM.md").read_text(encoding="utf-8"))

    def write_brief(self, brief):
        (self.root / "SWARM.md").write_text(init._markdown("Edited brief", "<!-- swarm-project-brief:schema=1 -->", brief), encoding="utf-8")

    def snapshot(self):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir() if p.is_file()}

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
