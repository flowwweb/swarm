from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
import multiprocessing
import json
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import EvidenceKind, EvidenceReference, FoldCandidate, IncidentDisposition, IncidentError, IncidentLedger, IncidentRecord, InvariantError, Role, Swarm, Task


def incident(identity, *, artifact="route", scope="routing", candidate="Require exact artifact gate receipts", note="auth token validation receipt"):
    return IncidentRecord(identity,"2026-08-12T00:00:00Z",artifact,scope,"handoff","server/types","review","typecheck","bounded compiler check","gate timed out and was treated as approval",("handoff","review","acceptance"),"rerun exact compiler gate",candidate,IncidentDisposition.CANDIDATE,(EvidenceReference(EvidenceKind.TEST_RECEIPT,note,f"sha256:{identity}"),),timeLost=12)


def _append_same(root):
    try: IncidentLedger(root).append(incident("same-id")); return True
    except IncidentError: return False


def _append_unique(root): IncidentLedger(root).append(incident("i-3"))
def _fold_existing(root): IncidentLedger(root).daily_fold(FoldCandidate("Bind acceptance to exact artifact and named PASS gates",("i-1","i-2"),"regression: source-only fails; exact pass succeeds"))


class IncidentLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve(); (self.root/".git"/"info").mkdir(parents=True); self.ledger=IncidentLedger(self.root)
    def tearDown(self): self.temp.cleanup()

    def test_persists_private_ignored_jsonl_and_deduplicates_identity(self):
        self.ledger.append(incident("i-1")); self.assertEqual(self.ledger.path,self.root/".codex"/"swarm"/"incidents.jsonl")
        self.assertEqual(self.ledger.read()[0].incidentId,"i-1"); self.assertIn(IncidentLedger.ignore_rule,(self.root/".git"/"info"/"exclude").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(IncidentError,"already exists"): self.ledger.append(incident("i-1"))

    def test_same_failure_class_is_deterministic(self): self.assertEqual(incident("i-1").failure_class,incident("i-2").failure_class)

    def test_explicit_supersession_is_same_family_and_restart_safe_without_rewriting_history(self):
        first=incident("first",artifact="route@v1:source"); self.ledger.append(first)
        unrelated=incident("unrelated",artifact="other@v1:source"); self.ledger.append(unrelated)
        before=self.ledger.path.read_bytes()
        next_record=replace(incident("next",artifact="route@v2:source"),supersedesIncidentId="first")
        self.ledger.append(next_record)
        after=self.ledger.path.read_bytes(); self.assertTrue(after.startswith(before))
        self.assertEqual(IncidentLedger(self.root).read()[-1].supersedesIncidentId,"first")
        self.assertEqual(self.ledger.path.read_bytes(),after)
        self.assertIs(self.ledger.read()[1].disposition,IncidentDisposition.CANDIDATE)
        for bad in (replace(incident("missing"),supersedesIncidentId="absent"),
                    replace(incident("wrong-family",artifact="other@v2:source"),supersedesIncidentId="first"),
                    replace(incident("wrong-purpose",artifact="route@v2:other"),supersedesIncidentId="first"),
                    replace(incident("fork",artifact="route@v3:source"),supersedesIncidentId="first")):
            with self.subTest(bad=bad.incidentId),self.assertRaises(IncidentError): self.ledger.append(bad)
        self.assertEqual(self.ledger.path.read_bytes(),after)

    def test_content_bound_revisions_keep_same_family_without_copying_old_observations(self):
        from runtime import ArtifactIdentity
        path=self.root/'observed.txt'; path.write_text('v1',encoding='utf-8')
        first_key=ArtifactIdentity.capture('observed','v1','source',root=str(self.root),paths=('observed.txt',)).key()
        self.ledger.append(incident('observed-first',artifact=first_key))
        path.write_text('v2',encoding='utf-8')
        next_key=ArtifactIdentity.capture('observed','v2','source',root=str(self.root),paths=('observed.txt',)).key()
        self.assertNotEqual(first_key,next_key)
        self.ledger.append(replace(incident('observed-next',artifact=next_key),supersedesIncidentId='observed-first'))
        self.assertEqual(IncidentLedger(self.root).read()[-1].supersedesIncidentId,'observed-first')

    def test_historical_incident_omission_remains_unverified_and_byte_preserved(self):
        raw=asdict(incident("historical")); raw.pop("supersedesIncidentId")
        before=(json.dumps(raw,default=str)+"\n").encode(); self.ledger.path.write_bytes(before)
        decoded=IncidentLedger(self.root).read()[0]
        self.assertIsNone(decoded.supersedesIncidentId)
        self.assertEqual(self.ledger.path.read_bytes(),before)

    def test_structured_evidence_allows_auth_language_but_rejects_credentials(self):
        self.ledger.append(incident("ordinary",note="auth token validation receipt"))
        for leaked in ("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456","AKIAABCDEFGHIJKLMNOP","sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456","sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456","Bearer abcdefghijklmnopqrstuvwxyz.123456","postgresql://user:password123@db.example/test"):
            with self.assertRaisesRegex(IncidentError,"credential"): incident("leak",note=leaked)
        self.assertNotIn("person",IncidentRecord.__dataclass_fields__)

    def test_linked_worktree_uses_effective_common_git_exclude(self):
        repo=self.root/"repo"; linked=self.root/"linked"; repo.mkdir()
        subprocess.run(("git","init",str(repo)),check=True,capture_output=True,text=True)
        subprocess.run(("git","-C",str(repo),"-c","user.name=SWARM Test","-c","user.email=swarm@example.invalid","commit","--allow-empty","-m","initial"),check=True,capture_output=True,text=True)
        subprocess.run(("git","-C",str(repo),"worktree","add","--detach",str(linked)),check=True,capture_output=True,text=True)
        IncidentLedger(linked)
        common_text=subprocess.run(("git","-C",str(linked),"rev-parse","--git-common-dir"),check=True,capture_output=True,text=True).stdout.strip(); common=Path(common_text)
        if not common.is_absolute(): common=(linked/common).resolve()
        self.assertIn(IncidentLedger.ignore_rule,(common/"info"/"exclude").read_text(encoding="utf-8"))
        gitdir_marker=(linked/".git").read_text(encoding="utf-8").split(":",1)[1].strip(); worktree_gitdir=Path(gitdir_marker)
        if not worktree_gitdir.is_absolute(): worktree_gitdir=(linked/worktree_gitdir).resolve()
        per_worktree=worktree_gitdir/"info"/"exclude"; self.assertFalse(per_worktree.exists() and IncidentLedger.ignore_rule in per_worktree.read_text(encoding="utf-8"))

    def test_lead_consults_matching_unresolved_incidents_before_gate_work(self):
        self.ledger.append(incident("i-1")); swarm=Swarm(); swarm.tasks["route"]=Task("route","builder","lead",1,{},owning_lead_id="lead")
        matched=swarm.consult_incidents(Role.LEAD,"route",self.ledger,artifact="route",scope="routing",actor_id="lead")
        self.assertEqual(tuple(item.incidentId for item in matched),("i-1",)); self.assertIn("i-1",swarm.tasks["route"].incident_consultation_receipt)

    def test_only_bound_lead_records_material_post_handoff_defects(self):
        swarm=Swarm(); swarm.tasks["route"]=Task("route","builder","lead",1,{},owning_lead_id="lead")
        self.assertFalse(swarm.record_post_handoff_incident(Role.LEAD,"route",self.ledger,incident("minor"),material=False,actor_id="lead")); self.assertEqual(self.ledger.read(),())
        with self.assertRaisesRegex(InvariantError,"bound owning LEAD"): swarm.record_post_handoff_incident(Role.LEAD,"route",self.ledger,incident("wrong"),material=True,actor_id="other")
        self.assertTrue(swarm.record_post_handoff_incident(Role.LEAD,"route",self.ledger,incident("material"),material=True,actor_id="lead")); self.assertEqual(self.ledger.read()[0].incidentId,"material")

    def test_daily_fold_requires_distinct_ids_and_preserves_pending_until_eligible(self):
        self.ledger.append(incident("i-1"))
        with self.assertRaisesRegex(IncidentError,"distinct"): FoldCandidate("portable",("i-1","i-1"),"contrast")
        first=self.ledger.daily_fold(FoldCandidate("Require exact receipts",("i-1",),"")); self.assertFalse(first.promoted); self.assertIs(self.ledger.read()[0].disposition,IncidentDisposition.CANDIDATE)
        self.ledger.append(incident("i-2")); later=self.ledger.daily_fold(FoldCandidate("Require exact receipts",("i-1","i-2"),"source-only fails; exact pass succeeds")); self.assertTrue(later.promoted)

    def test_daily_fold_rejects_only_through_explicit_reasoned_api(self):
        self.ledger.append(incident("i-1")); pending=self.ledger.daily_fold(FoldCandidate("Run npm run server:typecheck",("i-1",),"contrast",demonstrably_generalizable=True))
        self.assertFalse(pending.promoted); self.assertIs(self.ledger.read()[0].disposition,IncidentDisposition.CANDIDATE)
        self.ledger.reject(("i-1",),reason="repo-specific command is not portable"); record=self.ledger.read()[0]
        self.assertIs(record.disposition,IncidentDisposition.REJECTED); self.assertEqual(record.dispositionReason,"repo-specific command is not portable")

    def test_cross_process_same_identity_appends_exactly_once(self):
        with ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context("spawn")) as pool: results=tuple(pool.map(_append_same,(str(self.root),)*64))
        self.assertEqual(sum(results),1); self.assertEqual(tuple(item.incidentId for item in self.ledger.read()),("same-id",))

    def test_append_racing_fold_loses_no_record(self):
        self.ledger.append(incident("i-1")); self.ledger.append(incident("i-2")); context=multiprocessing.get_context("spawn")
        append=context.Process(target=_append_unique,args=(str(self.root),)); fold=context.Process(target=_fold_existing,args=(str(self.root),)); append.start(); fold.start(); append.join(20); fold.join(20)
        self.assertEqual((append.exitcode,fold.exitcode),(0,0)); records=self.ledger.read(); self.assertEqual({item.incidentId for item in records},{"i-1","i-2","i-3"})

    def test_global_doctrine_states_generalization_bar_without_incident_rule(self):
        root=Path(__file__).resolve().parents[1]
        skill="\n".join((root / name).read_text(encoding="utf-8") for name in ("SKILL.md", "references/review-contract.md"))
        self.assertIn("## Escaped-defect propagation", skill)
        self.assertIn("contrasting regression", skill)
        self.assertIn("repo-specific commands", skill)
        self.assertNotIn("corridor_route_lead",skill); self.assertNotIn("repo-specific routing compiler",skill)


if __name__=="__main__": unittest.main()
