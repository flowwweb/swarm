from __future__ import annotations

import sys
import unittest
from pathlib import Path


CONSOLE_ROOT = Path(__file__).resolve().parents[3] / "console"
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))

from skills_catalog import resolve  # noqa: E402


class SkillInheritanceContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
