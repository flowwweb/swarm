from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import sys

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from runtime import (  # noqa: E402
    GraphProfile,
    InvariantError,
    Swarm,
    TaskIntake,
    prepare_task_intake,
    select_graph,
)

CONFIG_SCRIPT = SKILL_ROOT / "scripts" / "swarm_config.py"
SPEC = importlib.util.spec_from_file_location("swarm_config_intake_tested", CONFIG_SCRIPT)
assert SPEC and SPEC.loader
config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config)


class IntakeGraphTests(unittest.TestCase):
    def test_work_unit_holders_coordinate_and_cannot_be_producer_assignments(self):
        from runtime import AcceptanceContract, ArtifactIdentity, DelegationContract, LaneKind, OperationClass, ProofClass, Role, RoleGateDecision, Task, WorkRoutingFacts, WorkSize, role_gate
        for kind in ("LAB","FACTORY"):
            from runtime.progress_events import Ledger
            temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
            value=Swarm(request_lifecycle_ledger=Ledger(Path(temporary.name))); value.attach_request_store(Path(temporary.name)); value.add_lead(Role.CTRL,"unit-lead")
            unit={"kind":kind,"goal_id":"goal-unit","parent_goal_id":"goal-project","parent_unit_task_id":None}
            artifact=ArtifactIdentity("unit","v1","non-artifact"); path="receipts/unit.txt"
            holder=Task("unit","unit-lead","CTRL",1,{},goal_id="goal-unit",subagent_receipt="host:thread:unit",owning_lead_id="unit-lead",work_unit=unit,lane_kind=LaneKind.NON_CODE,acceptance_contract=AcceptanceContract.empty(),delegation_contract=DelegationContract("unit","Relay accepted bounded block results.","unit-lead",(path,),artifact,(path,),(ProofClass.SOURCE,),60),routing_facts=WorkRoutingFacts(WorkSize.LARGE,False,True,1))
            staged=value.stage_request_task(Role.CTRL,holder)
            self.assertEqual(staged.owner,"unit-lead")
            self.assertEqual(role_gate(Role.LEAD,holder,OperationClass.MUTATE,actor_id="unit-lead",lease_version=1),RoleGateDecision.DELEGATE)
            self.assertEqual(role_gate(Role.LEAD,holder,OperationClass.COORDINATE,actor_id="unit-lead",lease_version=1),RoleGateDecision.ALLOW)
            with self.assertRaisesRegex(InvariantError,"holders coordinate"):
                value.reuse_warm(Role.LEAD,holder,architecture={},affinity=0)

    def test_large_general_goal_stays_with_coordinators_until_bounded_blocks_exist(self):
        from runtime import WorkSize
        plan=prepare_task_intake(goal="Build the software engineering factory",efficiency_strategy="Split into independently accepted blocks.",domain="factory",work_size=WorkSize.LARGE)
        self.assertTrue(plan.durable_goal)
        self.assertEqual(plan.graph.profile,GraphProfile.GENERAL)
        self.assertEqual(tuple(node.agent_type for node in plan.graph.nodes),("CTRL","LEAD"))
        self.assertIn("bounded artifact blocks",plan.graph.nodes[1].purpose)
        self.assertEqual(plan.graph.nodes[1].depends_on,("ctrl",))

    def test_default_goal_and_bounded_scope_gate_every_producer_admission(self):
        from runtime import AcceptanceContract, ArtifactIdentity, DelegationContract, LaneKind, ProofClass, Role, Task, Worker, WorkerState, WorkRoutingFacts, WorkSize
        def task(identity, *, goal_id="parent-factory-goal", bounded=True, size=WorkSize.SMALL):
            artifact=ArtifactIdentity(identity,"v1","block"); path=f"blocks/{identity}.receipt"
            contract=DelegationContract(identity,f"Return exactly the {identity} block.","block-worker",(path,),artifact,(path,),(ProofClass.SOURCE,),60)
            return Task(identity,"block-worker","CTRL",1,{},goal_id=goal_id,subagent_receipt=f"host:thread:{identity}",lane_kind=LaneKind.NON_CODE,acceptance_contract=AcceptanceContract.empty(),delegation_contract=contract,routing_facts=WorkRoutingFacts(size, bounded, True, 1))
        for route in ("assign","atomic","warm"):
            for missing_goal,bounded,size,pattern in ((True,True,WorkSize.SMALL,"bound goal ID"),(False,False,WorkSize.SMALL,"unbounded parent goals"),(False,True,WorkSize.LARGE,"large or unbounded parent goals")):
                value=Swarm(); value.add_lead(Role.CTRL,"lead")
                if route!="atomic": value.add_worker(Role.LEAD,Worker("block-worker","lead",1,state=WorkerState.WARM if route=="warm" else WorkerState.ACTIVE))
                candidate=task(f"{route}-block",goal_id="" if missing_goal else "parent-factory-goal",bounded=bounded,size=size)
                before=(set(value.tasks),set(value.workers))
                with self.assertRaisesRegex(InvariantError,pattern):
                    if route=="assign": value.assign(Role.LEAD,candidate)
                    elif route=="atomic": value.start_atomic(Role.CTRL,candidate)
                    else: value.reuse_warm(Role.LEAD,candidate,architecture={},affinity=0)
                self.assertEqual((set(value.tasks),set(value.workers)),before)
        value=Swarm(); block=task("bounded-block")
        value.start_atomic(Role.CTRL,block)
        self.assertEqual(value.tasks[block.id].goal_id,"parent-factory-goal")
        opted_out=Swarm(use_goals=False); opted_out.start_atomic(Role.CTRL,task("opt-out",goal_id=""))
        self.assertIn("opt-out",opted_out.tasks)

    def test_intake_requires_both_answers_and_the_two_questions(self) -> None:
        with self.assertRaisesRegex(InvariantError, "goal and an efficiency"):
            TaskIntake("", "strategy")
        with self.assertRaisesRegex(InvariantError, "goal and efficiency questions"):
            TaskIntake("goal", "strategy", questions_asked=("goal",))

    def test_general_selection_stays_shallow(self) -> None:
        plan = prepare_task_intake(
            goal="Correct one documentation typo",
            efficiency_strategy="Keep it atomic because one low-risk surface is faster than a task handoff.",
        )
        self.assertTrue(plan.durable_goal)
        self.assertEqual(plan.goal_action, "create_or_continue")
        self.assertEqual(plan.graph.profile, GraphProfile.GENERAL)
        self.assertEqual(tuple(node.id for node in plan.graph.nodes), ("ctrl", "doer"))

    def test_game_selection_has_parallel_production_and_downstream_gates(self) -> None:
        plan = prepare_task_intake(
            goal="Build a complete game prototype with deterministic gameplay and a shippable build",
            efficiency_strategy="Use the proven game-production flow and parallelize independent disciplines before integrated playtest.",
            domain="game project",
        )
        self.assertEqual(plan.graph.profile, GraphProfile.GAME_STUDIO)
        ids = {node.id for node in plan.graph.nodes}
        self.assertEqual(ids, {"ctrl", "studio_lead", "game_design", "game_engineering", "game_art", "game_audio", "playtest_qa", "release"})
        production = {node.id: node for node in plan.graph.nodes if node.id.startswith("game_")}
        self.assertTrue(all(node.depends_on == ("studio_lead",) for node in production.values()))
        self.assertEqual({node.agent_type for node in plan.graph.nodes}, {"CTRL", "LEAD", "DOER"})
        self.assertEqual([node.title for node in plan.graph.nodes if node.agent_type == "LEAD"], ["Manager LEAD"])
        self.assertEqual(
            {node_id: node.title for node_id, node in production.items()},
            {
                "game_design": "Designer DOER",
                "game_engineering": "Dev DOER",
                "game_art": "Artist DOER",
                "game_audio": "Producer DOER",
            },
        )
        qa = next(node for node in plan.graph.nodes if node.id == "playtest_qa")
        self.assertEqual(qa.title, "Tester DOER")
        self.assertEqual(set(qa.depends_on), set(production))
        release = next(node for node in plan.graph.nodes if node.id == "release")
        self.assertEqual(release.title, "Operator DOER")
        self.assertEqual(release.depends_on, ("playtest_qa",))
        self.assertEqual(set(plan.graph.parallel_lanes), set(production))
        self.assertEqual(len(plan.graph.digest()), 64)

    def test_goal_setting_false_keeps_intake_and_graph_but_disables_root_persistence(self) -> None:
        plan = prepare_task_intake(
            goal="Inspect a small repository",
            efficiency_strategy="Use one bounded read-only lane.",
            use_goals=False,
        )
        self.assertFalse(plan.durable_goal)
        self.assertEqual(plan.goal_action, "disabled")
        self.assertEqual(plan.graph.profile, GraphProfile.GENERAL)

    def test_swarm_from_config_applies_goal_policy(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertTrue(effective["goals"]["use_goals"])
        self.assertTrue(Swarm.from_config(effective).use_goals)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text("[goals]\nuse_goals = false\n", encoding="utf-8")
            disabled, _ = config.load(path)
        self.assertFalse(disabled["goals"]["use_goals"])
        swarm = Swarm.from_config(disabled)
        self.assertFalse(swarm.use_goals)
        self.assertFalse(swarm.plan_task_intake(goal="Inspect", efficiency_strategy="Keep it atomic.").durable_goal)

    def test_explicit_profile_is_typed_and_invalid_graphs_are_rejected(self) -> None:
        intake = TaskIntake("Build a game", "Use the game graph.")
        self.assertEqual(select_graph(intake, profile=GraphProfile.GAME_STUDIO).profile, GraphProfile.GAME_STUDIO)
        with self.assertRaisesRegex(InvariantError, "dependency cycles"):
            from runtime import GraphNodeSpec, GraphSelection

            GraphSelection(
                GraphProfile.GENERAL,
                "goal",
                "strategy",
                (
                    GraphNodeSpec("ctrl", "CTRL", "CTRL", "root"),
                    GraphNodeSpec("a", "DEV", "DOER", "a", ("b",)),
                    GraphNodeSpec("b", "TESTER", "DOER", "b", ("a",)),
                ),
                "bad",
            )
        with self.assertRaisesRegex(InvariantError, "built-in profession"):
            from runtime import GraphNodeSpec

            GraphNodeSpec("lead", "LEAD", "LEAD", "ambiguous bare lane", ("ctrl",))
        with self.assertRaisesRegex(InvariantError, "explicit dependency"):
            from runtime import GraphSelection

            GraphSelection(
                GraphProfile.GENERAL,
                "goal",
                "strategy",
                (
                    GraphNodeSpec("ctrl", "CTRL", "CTRL", "root"),
                    GraphNodeSpec("orphan", "DEV", "DOER", "orphan"),
                ),
                "bad",
            )


if __name__ == "__main__":
    unittest.main()
