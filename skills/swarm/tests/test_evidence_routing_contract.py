from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import AcceptanceContract, CtrlFeedEventKind, CtrlFeedMessage, CtrlFeedPart, CtrlSurfaceKind, EvidenceDisposition, InvariantError, LaneKind, ReviewEvidence, ReviewScope, ReviewStrategy, Role, Swarm, Task, TaskState, WithholdBasis, WorkerState, audit_ctrl_feed


class EvidenceRoutingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        cls.skill = "\n".join((root / name).read_text(encoding="utf-8") for name in ("SKILL.md", "references/hierarchy.md", "references/monitoring.md", "references/review-contract.md"))

    def setUp(self):
        self.swarm = Swarm()
        self.swarm.start_atomic(Role.CTRL, Task("covers", "artist", "CTRL", 1, {}, subagent_receipt="host:thread:artist",lane_kind=LaneKind.NON_CODE,acceptance_contract=AcceptanceContract.empty()))

    def accept(self):
        self.acceptance_review_only()
        self.swarm.complete(Role.CTRL, "covers", True, True, 1,actor_id="CTRL")

    def acceptance_review_only(self):
        evidence=ReviewEvidence(ReviewStrategy.LIGHT,"independent",True,None,receipt=(("acceptance","review:covers"),),scope=ReviewScope.ACCEPTANCE)
        self.swarm.review(Role.REVIEW, "covers", evidence, True)

    def feed_event(self, receipt, proof_receipts, task_id="covers", kind=CtrlFeedEventKind.RESULT):
        return self.swarm.register_ctrl_feed_event(Role.CTRL,task_id,receipt,kind,proof_receipts)

    def surface_candidates(self, count):
        candidate_ids=tuple(f"cover-{index}" for index in range(count))
        for index,evidence_id in enumerate(candidate_ids):
            self.swarm.register_ctrl_evidence(Role.DOER, "covers", evidence_id, "ImageGen", f"cover-{index}.png")
            self.swarm.surface_ctrl_evidence(Role.CTRL, evidence_id, surface_kind=CtrlSurfaceKind.INLINE_IMAGE, caption=f"Generated cover option {index + 1}.", claim_limit="Concept art only; user selection remains open.", surface_receipt=f"commentary:image:{index}")
        return candidate_ids

    def test_worker_produces_ten_images_but_ctrl_only_links_folder_is_rejected(self):
        for index in range(10):
            self.swarm.register_ctrl_evidence(Role.DOER, "covers", f"cover-{index}", "ImageGen", f"cover-{index}.png")
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "cover-folder", "inventory", "covers/", material=False)
        with self.assertRaisesRegex(InvariantError, "inline proof surface kind"):
            self.swarm.surface_ctrl_evidence(Role.CTRL, "cover-folder", surface_kind="path", caption="Folder inventory for ten generated covers.", claim_limit="This link does not display or approve any cover.", surface_receipt="chat:folder")
        self.acceptance_review_only()
        with self.assertRaisesRegex(InvariantError, "open CTRL evidence acceptance failure"):
            self.swarm.complete(Role.CTRL, "covers", True, True, 1,actor_id="CTRL")
        with self.assertRaisesRegex(InvariantError, "before phase advance"):
            self.swarm.advance_ctrl_phase(Role.CTRL, "implementation")
        self.assertEqual(len(self.swarm.ctrl_feed_due(Role.CTRL)), 10)
        self.swarm.tasks["covers"].state = TaskState.COMPLETE
        self.swarm.tasks["covers"].completed_at = 1
        self.swarm.workers["artist"].state = WorkerState.RETIRED
        self.swarm.workers["artist"].task_ids.clear()
        self.assertFalse(self.swarm.archive_eligible(self.swarm.tasks["covers"]))

    def test_ctrl_embeds_each_material_candidate_once_as_generated_is_accepted(self):
        for index in range(10):
            evidence_id = f"cover-{index}"
            self.swarm.register_ctrl_evidence(Role.DOER, "covers", evidence_id, "ImageGen", f"cover-{index}.png")
            self.swarm.surface_ctrl_evidence(Role.CTRL, evidence_id, surface_kind=CtrlSurfaceKind.INLINE_IMAGE, caption=f"Generated cover option {index + 1}.", claim_limit="Concept art only; user selection and production admission remain open.", surface_receipt=f"chat:image:{index}")
        self.assertEqual(self.swarm.ctrl_feed_due(Role.CTRL), ())
        self.acceptance_review_only()
        with self.assertRaisesRegex(InvariantError,"require one surfaced final gallery"):
            self.swarm.complete(Role.CTRL, "covers", True, True, 1,actor_id="CTRL")
        candidate_ids=tuple(f"cover-{index}" for index in range(10))
        self.swarm.register_ctrl_decision_set(Role.CTRL,"covers","cover-choice",candidate_ids,user_requested_all=True)
        self.swarm.surface_ctrl_decision_gallery(Role.CTRL,"cover-choice",embedded_ids=candidate_ids,labels_defects={candidate:f"Option {index + 1}: no known objective defect." for index,candidate in enumerate(candidate_ids)},complete_inventory=candidate_ids,surface_receipt="final:gallery:covers")
        self.swarm.advance_ctrl_phase(Role.CTRL, "implementation")
        self.accept()
        self.assertEqual(self.swarm.tasks["covers"].state, TaskState.COMPLETE)
        self.assertTrue(all(item.disposition == EvidenceDisposition.SURFACED and item.receipt.startswith("chat:image:") for item in self.swarm.ctrl_evidence_ledger.values()))

    def test_objective_defect_with_explicit_withholding_reason_is_accepted(self):
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "broken-cover", "mockup", "broken-cover.png")
        receipt = self.swarm.withhold_ctrl_evidence(Role.CTRL, "broken-cover", basis=WithholdBasis.OBJECTIVE_DEFECT, reason="The output contains six heroes instead of the required four.")
        self.assertEqual(receipt, "withheld:objective-defect:broken-cover")
        self.accept()
        self.assertEqual(self.swarm.tasks["covers"].state, TaskState.COMPLETE)

    def test_duplicate_reembedding_is_rejected(self):
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "cover-1", "preview", "cover-1.png")
        self.swarm.surface_ctrl_evidence(Role.CTRL, "cover-1", surface_kind=CtrlSurfaceKind.INLINE_IMAGE, caption="Generated cover option 1.", claim_limit="Unapproved preview.", surface_receipt="chat:image:1")
        with self.assertRaisesRegex(InvariantError, "surfaced exactly once"):
            self.swarm.surface_ctrl_evidence(Role.CTRL, "cover-1", surface_kind=CtrlSurfaceKind.INLINE_IMAGE, caption="Generated cover option 1 again.", claim_limit="Unapproved preview.", surface_receipt="chat:image:1-again")

    def test_seven_commentary_surfaces_then_final_links_only_is_rejected(self):
        candidates=self.surface_candidates(7)
        self.swarm.register_ctrl_decision_set(Role.CTRL,"covers","cover-choice",candidates)
        self.assertEqual(self.swarm.ctrl_feed_due(Role.CTRL),())
        self.acceptance_review_only()
        with self.assertRaisesRegex(InvariantError,"open CTRL decision gallery acceptance failure"):
            self.swarm.complete(Role.CTRL,"covers",True,True,1,actor_id="CTRL")
        with self.assertRaisesRegex(InvariantError,"before phase advance"):
            self.swarm.advance_ctrl_phase(Role.CTRL,"production")

    def test_final_consolidated_gallery_embeds_all_seven_once_and_is_accepted(self):
        candidates=self.surface_candidates(7)
        self.swarm.register_ctrl_decision_set(Role.CTRL,"covers","cover-choice",candidates)
        labels={candidate:f"Option {index + 1}; defect: concept art only." for index,candidate in enumerate(candidates)}
        receipt=self.swarm.surface_ctrl_decision_gallery(Role.CTRL,"cover-choice",embedded_ids=candidates,labels_defects=labels,complete_inventory=candidates,surface_receipt="final:gallery:cover-choice")
        self.assertEqual(receipt,"final:gallery:cover-choice")
        self.assertEqual(self.swarm.ctrl_decision_sets["cover-choice"].embedded_ids,candidates)
        self.accept()

    def test_large_set_allows_representative_gallery_only_with_inventory_and_exact_omissions(self):
        candidates=self.surface_candidates(13)
        shown=candidates[:4]; omitted=candidates[4:]
        self.swarm.register_ctrl_decision_set(Role.CTRL,"covers","large-choice",candidates)
        receipt=self.swarm.surface_ctrl_decision_gallery(Role.CTRL,"large-choice",embedded_ids=shown,labels_defects={candidate:f"Representative {candidate}; defect disclosed." for candidate in shown},complete_inventory=candidates,omissions={candidate:"Omitted from inline gallery due to representative large-set limit; present in complete inventory." for candidate in omitted},surface_receipt="final:gallery:large-choice")
        self.assertEqual(receipt,"final:gallery:large-choice")
        self.accept()

    def test_representative_gallery_is_rejected_when_user_requested_every_candidate(self):
        candidates=self.surface_candidates(13)
        self.swarm.register_ctrl_decision_set(Role.CTRL,"covers","all-requested",candidates,user_requested_all=True)
        with self.assertRaisesRegex(InvariantError,"embed every material candidate"):
            self.swarm.surface_ctrl_decision_gallery(Role.CTRL,"all-requested",embedded_ids=candidates[:4],labels_defects={candidate:f"Option {candidate}; defect disclosed." for candidate in candidates[:4]},complete_inventory=candidates,omissions={candidate:"Not shown." for candidate in candidates[4:]},surface_receipt="final:gallery:all-requested")

    def test_surface_requires_external_receipt_and_accepts_compact_nonvisual_proof(self):
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "metrics", "proof", "metrics.json")
        with self.assertRaisesRegex(InvariantError, "external surface receipt"):
            self.swarm.surface_ctrl_evidence(Role.CTRL, "metrics", surface_kind=CtrlSurfaceKind.INLINE_TABLE, caption="Routing improved.", claim_limit="Local run only.", surface_receipt="")
        receipt=self.swarm.surface_ctrl_evidence(Role.CTRL, "metrics", surface_kind=CtrlSurfaceKind.INLINE_TABLE, caption="12 routes: 12 passed, p95 81 ms.", claim_limit="Local API proof only.", surface_receipt="chat:table:metrics")
        self.assertEqual(receipt,"chat:table:metrics")

    def test_visual_evidence_cannot_be_mislabeled_as_a_receipt(self):
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "browser-shot", "browser", "route.png")
        with self.assertRaisesRegex(InvariantError, "visual CTRL evidence"):
            self.swarm.surface_ctrl_evidence(Role.CTRL, "browser-shot", surface_kind=CtrlSurfaceKind.INLINE_RECEIPT, caption="Route map.", claim_limit="Local browser only.", surface_receipt="chat:receipt:not-image")

    def test_one_candidate_in_each_unrelated_task_does_not_create_a_false_gallery(self):
        other=Task("other","other-owner","CTRL",1,{},subagent_receipt="host:thread:other",lane_kind=LaneKind.NON_CODE,acceptance_contract=AcceptanceContract.empty())
        self.swarm.start_atomic(Role.CTRL,other)
        for task_id,evidence_id in (("covers","cover-only"),("other","other-only")):
            self.swarm.register_ctrl_evidence(Role.DOER,task_id,evidence_id,"ImageGen",f"{evidence_id}.png")
            self.swarm.surface_ctrl_evidence(Role.CTRL,evidence_id,surface_kind=CtrlSurfaceKind.INLINE_IMAGE,caption=f"{evidence_id} candidate.",claim_limit="Concept only.",surface_receipt=f"chat:image:{evidence_id}")
        self.assertEqual(self.swarm._uncovered_ctrl_decision_candidates(),())
        self.swarm.advance_ctrl_phase(Role.CTRL,"implementation")

    def test_live_feed_doctrine_requires_prompt_surface_and_receipts(self):
        self.assertRegex(self.skill, r"(?is)human review feed.*next safe boundary.*surfaced once.*blocks acceptance")
        self.assertRegex(self.skill, r"(?is)decision gallery.*every candidate.*complete inventory.*Links.*cannot accept")

    def test_visual_self_review_binds_to_exact_final_deliverable(self):
        self.assertRegex(self.skill, r"(?is)exact delivered artifact.*not previews or transformation receipts")
        self.assertRegex(self.skill, r"(?is)Paths, worker finals, manifests, and folders are provenance.*not delivery")

    def test_contract_preserves_compact_ctrl_stream(self):
        self.assertRegex(self.skill, r"(?is)Emit only a material result.*Never lead with task activity")

    def test_ctrl_feed_is_human_readable_and_proof_first(self):
        self.assertRegex(self.skill, r"(?is)Lead with the user outcome.*smallest decisive inline proof.*remaining risk")
        self.assertRegex(self.skill, r"(?is)fresh representative capture.*compact excerpt, table, or before/after proof")

    def test_progress_reply_cannot_degrade_into_orchestration_narration(self):
        self.assertRegex(self.skill, r"(?is)Never lead with task activity, role inventory, commands, paths, or a tool run")

    def test_heartbeat_accepts_outcome_proof_risk_checkpoint_hierarchy(self):
        self.swarm.register_ctrl_evidence(Role.DOER,"covers","replay-proof","test","replay comparison")
        receipt=self.swarm.surface_ctrl_evidence(Role.CTRL,"replay-proof",surface_kind=CtrlSurfaceKind.INLINE_COMPARISON,caption="Twelve replay cases preserve reconnect state.",claim_limit="Device resume remains unverified.",surface_receipt="chat:replay:12")
        message=CtrlFeedMessage("release-proof",(
            (CtrlFeedPart.OUTCOME,"The release candidate now preserves reconnect state."),
            (CtrlFeedPart.PROOF,"Inline replay comparison: 12 of 12 cases match."),
            (CtrlFeedPart.RISK,"Device resume remains unverified."),
            (CtrlFeedPart.CHECKPOINT,"Next review surface is the device-resume capture."),
        ),(receipt,),"covers","chat:feed:release-proof",self.feed_event("event:release-proof",(receipt,)))
        self.assertTrue(audit_ctrl_feed((message,)).compliant)
        self.assertIsNone(self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=True,recent_ctrl_feed=(message,)))

    def test_compact_feed_can_omit_empty_risk_and_checkpoint(self):
        message=CtrlFeedMessage("accepted",(
            (CtrlFeedPart.OUTCOME,"Reconnect behavior is accepted."),
            (CtrlFeedPart.PROOF,"The inline replay receipt covers every declared case."),
        ),("chat:accepted",),"covers","chat:feed:accepted","event:accepted")
        self.assertTrue(audit_ctrl_feed((message,)).compliant)

    def test_feed_rejects_unbound_proof_without_policing_words(self):
        unbound=CtrlFeedMessage("unbound",((CtrlFeedPart.OUTCOME,"Reconnect is fixed."),(CtrlFeedPart.PROOF,"Twelve cases pass.")))
        self.assertIn("unbound:proof-unbound",audit_ctrl_feed((unbound,)).violations)
        domain_terms=CtrlFeedMessage("domain-terms",(
            (CtrlFeedPart.OUTCOME,"The task command and heartbeat diagnostics now explain the blocker."),
            (CtrlFeedPart.PROOF,"The tool trace and worktree evidence establish the failure boundary."),
        ),("chat:proof",),event_receipt="event:domain-terms")
        self.assertTrue(audit_ctrl_feed((domain_terms,)).compliant)

    def test_long_complex_proof_is_not_rejected_by_arbitrary_caps(self):
        message=CtrlFeedMessage("complex-proof",(
            (CtrlFeedPart.OUTCOME,"The complex migration decision is now reviewable. " + "Necessary outcome context. "*80),
            (CtrlFeedPart.PROOF,"The evidence covers every authority boundary. " + "Necessary proof context. "*80),
            (CtrlFeedPart.RISK,"The remaining safety limits require detailed explanation. " + "Necessary risk context. "*40),
        ),tuple(f"chat:proof:{index}" for index in range(8)),event_receipt="event:complex-proof")
        self.assertTrue(audit_ctrl_feed((message,)).compliant)

    def test_heartbeat_rejects_internal_narration_until_corrected(self):
        self.swarm.register_ctrl_evidence(Role.DOER,"covers","trace-proof","trace","restored session trace")
        receipt=self.swarm.surface_ctrl_evidence(Role.CTRL,"trace-proof",surface_kind=CtrlSurfaceKind.INLINE_EXCERPT,caption="The restored session resumes at turn 8.",claim_limit="Production transport remains unverified.",surface_receipt="chat:trace:turn-8")
        chatter=CtrlFeedMessage("routing-chatter",(
            (CtrlFeedPart.ORCHESTRATION,"CTRL routed REVIEW to the integration SHA."),
            (CtrlFeedPart.TASK_CHATTER,"Lease acquired; command running."),
            (CtrlFeedPart.ACTIVITY,"Three agents are still working."),
            (CtrlFeedPart.ORCHESTRATION,"An advisory manager specialist commented on lane topology."),
        ),(),"covers","chat:feed:routing-chatter")
        with self.assertRaisesRegex(InvariantError,"requires one compliant correction"):
            self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=False,recent_ctrl_feed=(chatter,))
        correction=CtrlFeedMessage("routing-correction",(
            (CtrlFeedPart.OUTCOME,"The reconnect decision is ready for review."),
            (CtrlFeedPart.PROOF,"Inline trace: the restored session resumes at turn 8."),
            (CtrlFeedPart.RISK,"Production transport remains unverified."),
        ),(receipt,),"covers","chat:feed:routing-correction",self.feed_event("event:routing-correction",(receipt,)))
        self.assertEqual(self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=False,recent_ctrl_feed=(chatter,),feed_correction=correction),"covers:feed-reoriented:1:routing-correction")
        audit=self.swarm.telemetry_events[-1]
        self.assertEqual(audit["kind"],"ctrl_feed_audit")
        self.assertEqual(audit["correction"],"routing-correction")
        self.assertEqual(audit["reorientation"],"purpose-reset")
        self.assertEqual(self.swarm.tasks["covers"].superseded_ctrl_feed_ids,["routing-chatter"])
        self.assertEqual(self.swarm.tasks["covers"].last_ctrl_feed_correction_id,"routing-correction")

    def test_heartbeat_rejects_fabricated_inline_proof_receipt(self):
        message=CtrlFeedMessage("fabricated",(
            (CtrlFeedPart.OUTCOME,"Reconnect behavior changed."),
            (CtrlFeedPart.PROOF,"The inline comparison passes."),
        ),("chat:not-surfaced",),"covers","chat:feed:fabricated")
        correction=CtrlFeedMessage("also-fabricated",(
            (CtrlFeedPart.OUTCOME,"Reconnect behavior changed."),
            (CtrlFeedPart.PROOF,"The inline comparison passes."),
        ),("chat:also-not-surfaced",),"covers","chat:feed:also-fabricated")
        with self.assertRaisesRegex(InvariantError,"unknown-proof-receipt"):
            self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=False,recent_ctrl_feed=(message,),feed_correction=correction)

    def test_empty_heartbeat_cannot_hide_unaudited_visible_drift(self):
        drift=CtrlFeedMessage("stored-drift",(
            (CtrlFeedPart.ORCHESTRATION,"CTRL routed three tasks."),
        ),(),"covers","chat:feed:stored-drift")
        self.swarm.publish_ctrl_feed(Role.CTRL,drift)
        with self.assertRaisesRegex(InvariantError,"requires one compliant correction"):
            self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=False,recent_ctrl_feed=())

    def test_feed_reorientation_does_not_create_an_unbound_watchdog(self):
        self.swarm.register_ctrl_evidence(Role.DOER,"covers","watchdog-proof","test","watchdog proof")
        receipt=self.swarm.surface_ctrl_evidence(Role.CTRL,"watchdog-proof",surface_kind=CtrlSurfaceKind.INLINE_EXCERPT,caption="Reconnect proof is ready.",claim_limit="Production remains unverified.",surface_receipt="chat:watchdog-proof")
        self.swarm.propose_milestone(Role.CTRL,"covers",goal_id="feed-goal",milestone="accepted feed",proof_kind="review",horizon_minutes=15,now=10)
        self.assertNotIn("covers",self.swarm.scheduled_wakeups)
        drift=CtrlFeedMessage("drift-with-lost-clock",((CtrlFeedPart.ACTIVITY,"Still running."),),(),"covers","chat:feed:drift-clock")
        correction=CtrlFeedMessage("corrected-clock",(
            (CtrlFeedPart.OUTCOME,"Reconnect proof is ready for review."),
            (CtrlFeedPart.PROOF,"The inline excerpt shows the restored turn."),
            (CtrlFeedPart.RISK,"Production transport remains unverified."),
        ),(receipt,),"covers","chat:feed:corrected-clock",self.feed_event("event:corrected-clock",(receipt,),kind=CtrlFeedEventKind.BLOCKER))
        result=self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=False,recent_ctrl_feed=(drift,),feed_correction=correction)
        self.assertIn("feed-reoriented",result)
        self.assertNotIn("watchdog",result)
        self.assertNotIn("covers",self.swarm.scheduled_wakeups)

    def test_portfolio_feed_binds_each_message_to_its_own_task_proof(self):
        self.swarm.start_atomic(Role.CTRL,Task("second","writer","CTRL",1,{},subagent_receipt="host:thread:writer",lane_kind=LaneKind.NON_CODE,acceptance_contract=AcceptanceContract.empty()))
        messages=[]
        for task_id in ("covers","second"):
            evidence_id=f"{task_id}-proof"; surface=f"chat:{task_id}:proof"
            self.swarm.register_ctrl_evidence(Role.DOER,task_id,evidence_id,"test",f"{task_id} proof")
            self.swarm.surface_ctrl_evidence(Role.CTRL,evidence_id,surface_kind=CtrlSurfaceKind.INLINE_EXCERPT,caption=f"{task_id} result.",claim_limit="Local proof only.",surface_receipt=surface)
            event=self.feed_event(f"event:{task_id}",(surface,),task_id)
            messages.append(CtrlFeedMessage(f"{task_id}-message",((CtrlFeedPart.OUTCOME,f"{task_id} changed."),(CtrlFeedPart.PROOF,"The inline proof passed.")),(surface,),task_id,f"chat:feed:{task_id}",event))
        self.assertIsNone(self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=True,recent_ctrl_feed=tuple(messages)))

    def test_audited_feed_cursor_is_idempotent(self):
        self.swarm.register_ctrl_evidence(Role.DOER,"covers","cursor-proof","test","cursor proof")
        receipt=self.swarm.surface_ctrl_evidence(Role.CTRL,"cursor-proof",surface_kind=CtrlSurfaceKind.INLINE_EXCERPT,caption="Cursor proof passed.",claim_limit="Local only.",surface_receipt="chat:cursor-proof")
        message=CtrlFeedMessage("cursor-message",((CtrlFeedPart.OUTCOME,"The cursor result changed."),(CtrlFeedPart.PROOF,"The inline proof passed.")),(receipt,),"covers","chat:feed:cursor",self.feed_event("event:cursor",(receipt,)))
        self.assertIsNone(self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=True,recent_ctrl_feed=(message,)))
        self.assertIsNone(self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=False,recent_ctrl_feed=()))

    def test_later_material_decision_may_reuse_relevant_audited_proof(self):
        self.swarm.register_ctrl_evidence(Role.DOER,"covers","repeat-proof","test","repeat proof")
        receipt=self.swarm.surface_ctrl_evidence(Role.CTRL,"repeat-proof",surface_kind=CtrlSurfaceKind.INLINE_EXCERPT,caption="Repeat proof passed.",claim_limit="Local only.",surface_receipt="chat:repeat-proof")
        first=CtrlFeedMessage("first-proof-use",((CtrlFeedPart.OUTCOME,"The first result changed."),(CtrlFeedPart.PROOF,"The inline proof passed.")),(receipt,),"covers","chat:feed:first-proof",self.feed_event("event:first",(receipt,)))
        self.assertIsNone(self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=True,recent_ctrl_feed=(first,)))
        repeated=CtrlFeedMessage("second-proof-use",((CtrlFeedPart.OUTCOME,"The same evidence now supports the acceptance decision."),(CtrlFeedPart.PROOF,"The previously surfaced inline proof remains the decision basis.")),(receipt,),"covers","chat:feed:second-proof",self.feed_event("event:acceptance-decision",(receipt,),kind=CtrlFeedEventKind.DECISION))
        self.assertIsNone(self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=True,recent_ctrl_feed=(repeated,)))

    def test_feed_window_has_no_arbitrary_message_or_receipt_count_cap(self):
        messages=tuple(CtrlFeedMessage(f"m-{index}",((CtrlFeedPart.OUTCOME,f"Result {index} changed."),(CtrlFeedPart.PROOF,"The inline proof passed.")),("chat:shared-proof",),"covers",f"chat:feed:{index}",f"event:{index}") for index in range(4))
        self.assertTrue(audit_ctrl_feed(messages).compliant)

    def test_same_batch_cannot_publish_one_material_event_twice(self):
        self.swarm.register_ctrl_evidence(Role.DOER,"covers","batch-proof","test","batch proof")
        receipt=self.swarm.surface_ctrl_evidence(Role.CTRL,"batch-proof",surface_kind=CtrlSurfaceKind.INLINE_EXCERPT,caption="Batch proof passed.",claim_limit="Local only.",surface_receipt="chat:batch")
        event=self.feed_event("event:batch",(receipt,))
        messages=tuple(CtrlFeedMessage(f"batch-{index}",((CtrlFeedPart.OUTCOME,f"Result {index} changed."),(CtrlFeedPart.PROOF,"The inline proof passed.")),(receipt,),"covers",f"chat:feed:batch:{index}",event) for index in range(2))
        with self.assertRaisesRegex(InvariantError,"repeated-material-event"):
            self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=True,recent_ctrl_feed=messages)

    def test_same_batch_allows_distinct_material_events(self):
        self.swarm.register_ctrl_evidence(Role.DOER,"covers","distinct-proof","test","distinct proof")
        receipt=self.swarm.surface_ctrl_evidence(Role.CTRL,"distinct-proof",surface_kind=CtrlSurfaceKind.INLINE_EXCERPT,caption="Distinct proof passed.",claim_limit="Local only.",surface_receipt="chat:distinct")
        events=tuple(self.feed_event(f"event:distinct:{index}",(receipt,)) for index in range(2))
        messages=tuple(CtrlFeedMessage(f"distinct-{index}",((CtrlFeedPart.OUTCOME,f"Result {index} changed."),(CtrlFeedPart.PROOF,"The inline proof passed.")),(receipt,),"covers",f"chat:feed:distinct:{index}",events[index]) for index in range(2))
        self.assertIsNone(self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=True,recent_ctrl_feed=messages))

    def test_heartbeat_rejects_stale_proof_without_a_new_material_event(self):
        self.swarm.register_ctrl_evidence(Role.DOER,"covers","old-proof","test","old proof")
        receipt=self.swarm.surface_ctrl_evidence(Role.CTRL,"old-proof",surface_kind=CtrlSurfaceKind.INLINE_EXCERPT,caption="Old proof passed.",claim_limit="Local only.",surface_receipt="chat:old")
        stale=CtrlFeedMessage("stale-status",((CtrlFeedPart.OUTCOME,"No registered result changed."),(CtrlFeedPart.PROOF,"The old proof is unchanged.")),(receipt,),"covers","chat:feed:stale","event:not-registered")
        with self.assertRaisesRegex(InvariantError,"unknown-material-event"):
            self.swarm.heartbeat(Role.CTRL,"covers",meaningful_progress=False,recent_ctrl_feed=(stale,))

    def test_routing_distinguishes_visible_lanes_from_bounded_subagents(self):
        self.assertRegex(self.skill, r"(?is)Materialize a visible task lane.*durable ownership.*interruption-safe resumption")
        self.assertRegex(self.skill, r"(?is)Use a subagent only as short bounded capacity inside an existing lane")
        self.assertIn("never substitutes for a qualifying durable task", self.skill)
        self.assertRegex(self.skill, r"(?is)CTRL_DIRECT.*low-risk atomic outcome.*otherwise use.*CTRL_DELEGATED")
        self.assertNotIn("each delegated or non-CTRL task delegates", self.skill)
        self.assertNotIn("Default to CTRL working directly or one atomic owner", self.skill)


if __name__ == "__main__":
    unittest.main()
