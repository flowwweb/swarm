import base64
import concurrent.futures
import hashlib
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

from test_project_model_views import views, server, project_fixture, markdown_fixture


class TicketDiscussionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "SWARM.md"
        self.path.write_text(markdown_fixture(project_fixture("sample", tasks=[{"id": "task-1"}])), encoding="utf-8")
        self.args = {"project_ids": {"sample"}, "record_id": "task-1"}

    def read(self):
        return views.ticket_discussion(self.path, operation="read_discussion", **self.args)

    def write(self, operation, item, digest):
        return views.ticket_discussion(self.path, operation=operation, item=item, expected_digest=digest,
                                       updated_at="2026-10-29T00:00:00Z", **self.args)

    def test_reload_replay_reply_conflict_and_custody(self):
        original = self.read()["source_digest"]
        comment = {"id": "comment-1", "body": "First", "reply_to": None}
        first = self.write("add_comment", comment, original)
        self.assertEqual(first["item"]["author_provenance"], "LOCAL_UNVERIFIED")
        self.assertTrue(self.write("add_comment", comment, original)["replayed"])
        with self.assertRaisesRegex(views.ProjectModelError, "digest conflict"):
            self.write("add_comment", {"id": "comment-2", "body": "Reply", "reply_to": "comment-1"}, original)
        reply = self.write("add_comment", {"id": "comment-2", "body": "Reply", "reply_to": "comment-1"}, first["source_digest"])
        raw = b"A retained file\n"
        attachment = {"id": "file-1", "name": "proof.txt", "type": "text/plain", "data": base64.b64encode(raw).decode()}
        self.write("add_attachment", attachment, reply["source_digest"])
        loaded = self.read()
        self.assertEqual([x["id"] for x in loaded["comments"]], ["comment-1", "comment-2"])
        saved = loaded["attachments"][0]
        self.assertEqual(base64.b64decode(saved["data"]), raw)
        self.assertEqual(saved["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(saved["size"], len(raw))
        self.assertTrue(self.write("add_attachment", attachment, original)["replayed"])
        with self.assertRaisesRegex(views.ProjectModelError, "already exists"):
            self.write("add_attachment", {**attachment, "data": base64.b64encode(b"changed").decode()}, original)
        self.assertIn("Retained prose.", self.path.read_text(encoding="utf-8"))

    def test_invalid_scope_paths_types_and_size(self):
        digest = self.read()["source_digest"]
        base = {"id": "f", "name": "safe.txt", "type": "text/plain", "data": "eA=="}
        for patch in ({"name": "../escape"}, {"name": "x\\escape"}, {"type": "text/html"},
                      {"data": base64.b64encode(b"x" * 65537).decode()}):
            with self.subTest(patch=patch), self.assertRaises(views.ProjectModelError):
                self.write("add_attachment", {**base, **patch}, digest)
        with self.assertRaises(views.ProjectModelError):
            views.ticket_discussion(self.path, project_ids={"other"}, record_id="task-1", operation="read_discussion")
        with self.assertRaises(views.ProjectModelError):
            self.write("add_comment", {"id": "c", "body": "reply", "reply_to": "missing"}, digest)

    def test_concurrent_writes_do_not_lose_updates(self):
        digest = self.read()["source_digest"]
        def attempt(n):
            try:
                return self.write("add_comment", {"id": f"c-{n}", "body": str(n), "reply_to": None}, digest)
            except views.ProjectModelError as exc:
                return str(exc)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum("digest conflict" in result for result in results if isinstance(result, str)), 1)
        self.assertEqual(len(self.read()["comments"]), 1)

    def test_server_binds_root_and_derives_local_author(self):
        binding = lambda project_id: {"project_id": project_id, "root": self.path.parent,
                                     "identities": frozenset({project_id}), "identity_error": None, "native_id": None}
        app = SimpleNamespace(_saved_project_binding=binding)
        base = {"project_id": "sample", "record_id": "task-1"}
        result = server.App.project_ticket_command(app, {**base, "operation": "add_comment", "acknowledge": True,
            "expected_digest": self.read()["source_digest"], "changes": {"id": "c", "body": "hello", "reply_to": None}})
        self.assertEqual(result["item"]["author_provenance"], "LOCAL_UNVERIFIED")
        self.assertNotIn("author", result["item"])
        loaded = server.App.project_ticket_command(app, {**base, "operation": "read_discussion"})
        self.assertEqual(loaded["comments"][0]["body"], "hello")
        with self.assertRaises(server.ConsoleError):
            server.App.project_ticket_command(app, {**base, "operation": "read_discussion", "author": "spoofed"})

    def test_corrupted_attachment_is_not_returned(self):
        item = {"id": "f", "name": "safe.txt", "type": "text/plain", "data": "eA=="}
        self.write("add_attachment", item, self.read()["source_digest"])
        content = self.path.read_text(encoding="utf-8").replace('"data": "eA=="', '"data": "eQ=="')
        self.path.write_text(content, encoding="utf-8")
        with self.assertRaisesRegex(views.ProjectModelError, "integrity mismatch"):
            self.read()

    def test_discussion_reserves_capacity_for_planning(self):
        digest = self.read()["source_digest"]
        item = {"id":"large", "name":"large.txt", "type":"text/plain", "data":base64.b64encode(b"x" * 65536).decode()}
        with mock.patch.object(views, "_MAX_BRIEF_BYTES", 100000):
            with self.assertRaisesRegex(views.ProjectModelError, "DISCUSSION_CAPACITY"):
                self.write("add_attachment", item, digest)
        self.assertEqual(self.read()["source_digest"], digest)

    def test_symlinked_brief_is_rejected(self):
        linked_root = self.path.parent / "linked"
        linked_root.mkdir()
        link = linked_root / "SWARM.md"
        try:
            link.symlink_to(self.path)
        except OSError as exc:
            self.skipTest(f"Creating a test symlink is unavailable: {exc}")
        with self.assertRaises(views.ProjectModelError):
            views.ticket_discussion(link, operation="read_discussion", **self.args)


if __name__ == "__main__":
    unittest.main()
