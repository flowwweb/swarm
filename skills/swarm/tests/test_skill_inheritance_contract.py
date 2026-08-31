from __future__ import annotations

import sys
import unittest
from pathlib import Path


CONSOLE_ROOT = Path(__file__).resolve().parents[3] / "console"
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))

from skills_catalog import resolve  # noqa: E402


class SkillInheritanceContractTests(unittest.TestCase):
    @staticmethod
    def _skill(
        skill_id: str,
        *,
        role: str = "LEAD",
        task_kind: str = "CODE",
        installed: bool = True,
        review_status: str = "approved",
        **extra: object,
    ) -> dict[str, object]:
        return {
            "skill_id": skill_id,
            "source_repo": "trusted/repo",
            "source_path": f"skills/{skill_id}",
            "source_ref": "v1",
            "source_version": "v1",
            "review_status": review_status,
            "installed": installed,
            "builtin": False,
            "allowed_roles": [role],
            "allowed_task_kinds": [task_kind],
            **extra,
        }

    def test_only_approved_relevant_installed_skill_is_inherited(self) -> None:
        catalog = [
            {"skill_id": "systematic-debugging", "source_repo": "trusted/repo", "source_path": "skills/systematic-debugging", "source_ref": "v1", "source_version": "v1", "review_status": "approved", "installed": True, "builtin": False, "allowed_roles": ["LEAD"], "allowed_task_kinds": ["CODE"]},
            {"skill_id": "unreviewed", "source_repo": "unknown/repo", "source_path": "skills/unreviewed", "source_ref": "main", "source_version": "main", "review_status": "candidate", "installed": True, "builtin": False, "allowed_roles": ["LEAD"], "allowed_task_kinds": ["CODE"]},
            {"skill_id": "irrelevant", "source_repo": "trusted/repo", "source_path": "skills/irrelevant", "source_ref": "v1", "source_version": "v1", "review_status": "approved", "installed": True, "builtin": False, "allowed_roles": ["DESIGNER"], "allowed_task_kinds": ["DESIGN"]},
            {"skill_id": "unpreferred", "source_repo": "trusted/repo", "source_path": "skills/unpreferred", "source_ref": "v1", "source_version": "v1", "review_status": "approved", "installed": True, "builtin": False, "allowed_roles": ["LEAD"], "allowed_task_kinds": ["CODE"]},
        ]
        result = resolve(catalog, None, None, None, role="LEAD", task_kind="CODE", global_preferred=["systematic-debugging"])
        statuses = {item["skill_id"]: item["status"] for item in result["skills"]}
        self.assertEqual(statuses, {"systematic-debugging": "inherited", "unreviewed": "blocked_unreviewed", "irrelevant": "not_relevant", "unpreferred": "not_selected"})

    def test_profile_constrains_the_effective_preferred_shortlist(self) -> None:
        catalog = [
            {"skill_id": "systematic-debugging", "source_repo": "trusted/repo", "source_path": "skills/debug", "source_ref": "v1", "source_version": "v1", "review_status": "approved", "installed": True, "builtin": False, "allowed_roles": ["LEAD"], "allowed_task_kinds": ["DEBUG"]},
            {"skill_id": "test-driven-development", "source_repo": "trusted/repo", "source_path": "skills/test", "source_ref": "v1", "source_version": "v1", "review_status": "approved", "installed": True, "builtin": False, "allowed_roles": ["LEAD"], "allowed_task_kinds": ["DEBUG"]},
        ]
        result = resolve(catalog, None, None, None, role="LEAD", task_kind="DEBUG", global_profile="debug", global_preferred=["systematic-debugging", "test-driven-development"])
        statuses = {item["skill_id"]: item["status"] for item in result["skills"]}
        self.assertEqual(statuses["systematic-debugging"], "inherited")
        self.assertEqual(statuses["test-driven-development"], "not_selected")

    def test_authority_expanding_metadata_is_rejected_even_when_approved(self) -> None:
        result = resolve([{
            "skill_id": "unsafe", "source_repo": "trusted/repo", "source_path": "skills/unsafe", "source_ref": "v1", "source_version": "v1",
            "review_status": "approved", "installed": True, "builtin": False,
            "allowed_roles": ["LEAD"], "allowed_task_kinds": ["CODE"], "permissions": ["browser_control"],
        }], None, None, None, role="LEAD", task_kind="CODE")
        self.assertEqual(result["skills"][0]["status"], "blocked_authority")
        self.assertFalse(result["skills"][0]["authority_safe"])

    def test_global_preferred_skill_is_all_agent_base_and_lower_scopes_cannot_remove_it(self) -> None:
        catalog = [self._skill("systematic-debugging", role="LEAD", task_kind="CODE")]
        global_scope = {
            "inheritance_enabled": True,
            "profile": "default",
            "preferred_ids": ["systematic-debugging"],
        }
        project_scope = {
            "inheritance_enabled": False,
            "profile": "design",
            "preferred_ids": [],
        }
        ctrl_scope = {
            "inheritance_enabled": False,
            "preferred_ids": ["systematic-debugging"],
        }

        result = resolve(
            catalog,
            global_scope,
            project_scope,
            ctrl_scope,
            role="DESIGNER",
            task_kind="DESIGN",
        )
        skill = result["skills"][0]
        self.assertEqual(skill["status"], "inherited")
        self.assertFalse(skill["relevant"])
        self.assertTrue(skill["global"])
        self.assertEqual(skill["source_scope"], "global")

    def test_only_global_scope_can_disable_global_inheritance(self) -> None:
        catalog = [self._skill("systematic-debugging")]
        result = resolve(
            catalog,
            {"inheritance_enabled": False, "preferred_ids": ["systematic-debugging"]},
            {"inheritance_enabled": True, "preferred_ids": ["systematic-debugging"]},
            {"inheritance_enabled": True, "preferred_ids": ["systematic-debugging"]},
            role="LEAD",
            task_kind="CODE",
        )
        self.assertEqual(result["skills"][0]["status"], "inheritance_disabled")
        self.assertTrue(result["skills"][0]["global"])

    def test_global_entries_fail_closed_before_role_or_task_relevance(self) -> None:
        catalog = [
            self._skill("systematic-debugging", role="DESIGNER", task_kind="DESIGN", installed=False),
            self._skill("test-driven-development", role="DESIGNER", task_kind="DESIGN", review_status="candidate"),
            self._skill(
                "verification-before-completion",
                role="DESIGNER",
                task_kind="DESIGN",
                permissions=["browser_control"],
            ),
        ]
        result = resolve(
            catalog,
            {
                "inheritance_enabled": True,
                "preferred_ids": [
                    "systematic-debugging",
                    "test-driven-development",
                    "verification-before-completion",
                ],
            },
            None,
            None,
            role="LEAD",
            task_kind="CODE",
        )
        statuses = {item["skill_id"]: item["status"] for item in result["skills"]}
        self.assertEqual(statuses, {
            "systematic-debugging": "available_to_install",
            "test-driven-development": "blocked_unreviewed",
            "verification-before-completion": "blocked_authority",
        })

    def test_project_and_ctrl_additions_are_additive_but_remain_profile_and_relevance_bound(self) -> None:
        catalog = [
            self._skill("systematic-debugging", task_kind="DEBUG"),
            self._skill("verification-before-completion", task_kind="DEBUG"),
            self._skill("test-driven-development", role="DESIGNER", task_kind="DESIGN"),
        ]
        result = resolve(
            catalog,
            None,
            {
                "inheritance_enabled": True,
                "profile": "debug",
                "preferred_ids": ["systematic-debugging", "test-driven-development"],
            },
            {
                "inheritance_enabled": True,
                "preferred_ids": ["verification-before-completion"],
            },
            role="LEAD",
            task_kind="DEBUG",
        )
        by_id = {item["skill_id"]: item for item in result["skills"]}
        self.assertEqual(by_id["systematic-debugging"]["status"], "inherited")
        self.assertEqual(by_id["systematic-debugging"]["source_scope"], "project")
        self.assertEqual(by_id["verification-before-completion"]["status"], "inherited")
        self.assertEqual(by_id["verification-before-completion"]["source_scope"], "ctrl")
        self.assertEqual(by_id["test-driven-development"]["status"], "not_relevant")

    def test_resolution_order_and_replay_are_stable(self) -> None:
        catalog = [
            self._skill("verification-before-completion", task_kind="DEBUG"),
            self._skill("systematic-debugging", task_kind="DEBUG"),
        ]
        scopes = (
            {"inheritance_enabled": True, "preferred_ids": ["verification-before-completion"]},
            {"inheritance_enabled": True, "profile": "debug", "preferred_ids": ["systematic-debugging"]},
            {"inheritance_enabled": True, "preferred_ids": ["systematic-debugging"]},
        )
        first = resolve(catalog, *scopes, role="LEAD", task_kind="DEBUG")
        replay = resolve(list(reversed(catalog)), *scopes, role="LEAD", task_kind="DEBUG")
        self.assertEqual(first, replay)
        self.assertEqual(
            [item["skill_id"] for item in first["skills"]],
            ["systematic-debugging", "verification-before-completion"],
        )
        self.assertEqual(
            first["settings"]["preferred_ids"],
            ["verification-before-completion", "systematic-debugging"],
        )


if __name__ == "__main__":
    unittest.main()
