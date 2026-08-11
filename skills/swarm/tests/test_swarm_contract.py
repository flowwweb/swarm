from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "swarm_contract.py"
SPEC = importlib.util.spec_from_file_location("swarm_contract_tested", SCRIPT)
assert SPEC and SPEC.loader
contract = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = contract
SPEC.loader.exec_module(contract)


class SwarmContractTests(unittest.TestCase):
    def test_mandatory_roles_are_independent_of_boost(self) -> None:
        self.assertEqual(
            contract.MANDATORY_DURABLE_GOAL_ROLES,
            {"mother", "lead", "specialist", "architect"},
        )

    def test_forward_goal_cases(self) -> None:
        cases = contract.forward_cases()
        self.assertEqual(cases["mother_startup_no_goal"]["action"], "create")
        self.assertEqual(cases["mother_uppercase_no_goal"]["action"], "create")
        self.assertEqual(cases["lead_resume_matching_goal"]["action"], "continue")
        self.assertEqual(cases["lead_mixed_case_matching_goal"]["action"], "continue")
        self.assertEqual(cases["architect_startup"]["action"], "create")
        self.assertEqual(cases["missing_goal_tool"]["action"], "blocked")
        self.assertEqual(
            cases["architect_uppercase_missing_goal_tool"]["action"], "blocked"
        )

    def test_public_role_boundary_normalizes_case(self) -> None:
        matching = contract.Goal(
            role="aRcHiTeCt",
            objective_key="system",
            objective="map system",
            stopping_condition="decision receipt",
            authority_boundary="architecture only",
            required_proof="dependency proof",
        )
        self.assertEqual(
            contract.goal_decision("ARCHITECT", matching, "system").action,
            "continue",
        )
        self.assertEqual(
            contract.goal_decision(
                "mOtHeR", None, "portfolio", goal_controls_available=False
            ).action,
            "blocked",
        )

    def test_forward_heartbeat_cases(self) -> None:
        cases = contract.forward_cases()
        self.assertEqual(cases["heartbeat_healthy"]["action"], "observe")
        self.assertEqual(cases["heartbeat_stalled"]["action"], "recover")
        self.assertEqual(cases["heartbeat_second_unchanged"]["action"], "release")

    def test_silence_does_not_trigger_recovery(self) -> None:
        decision = contract.heartbeat_decision(
            contract.LaneObservation("BUILD", False, False, 9, 0)
        )
        self.assertEqual(decision.action, "observe")

    def test_finite_roles_do_not_create_goals(self) -> None:
        decision = contract.goal_decision("assist", None, "temporary")
        self.assertEqual(decision.action, "not_required")


if __name__ == "__main__":
    unittest.main()
