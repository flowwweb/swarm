from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skills.swarm.runtime.chat_relay import (
    ChatRelayCapability,
    ChatRelayPolicy,
    ChatRelayPurpose,
    ChatRelayRequest,
    build_chat_relay_context,
    consult_chat_relay,
)
from skills.swarm.runtime.chat_relay_usage import ChatRelayUsageLedger, estimate_tokens, read_chat_relay_usage


class Adapter:
    def capability(self) -> ChatRelayCapability:
        return ChatRelayCapability(True, True, True, "capability", "GPT-5.6 Luna", "Extra High")

    def send_consult(self, prompt: str, *, model: str, effort: str):
        from skills.swarm.runtime.chat_relay import ChatRelayResponse

        return ChatRelayResponse(
            text="bounded advice",
            host_receipt="response",
            observed_model="GPT-5.6 Luna",
            observed_effort="Extra High",
        )


class ChatRelayUsageTests(unittest.TestCase):
    def test_successful_visible_consult_records_bounded_estimate_and_task(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plan.md").write_text("bounded plan", encoding="utf-8")
            context = build_chat_relay_context(repo_root=root, objective="review", relative_paths=("plan.md",))
            request = ChatRelayRequest(
                purpose=ChatRelayPurpose.PLAN,
                consequence_tier="T0",
                prompt_digest=hashlib.sha256(b"usage").hexdigest(),
                task_id="ctrl/task-1",
            )
            ledger = ChatRelayUsageLedger(root / "chat-relay-usage.json")
            result = consult_chat_relay(
                policy=ChatRelayPolicy(enabled=True),
                request=request,
                context=context,
                adapter=Adapter(),
                ledger=ledger,
            )

            self.assertEqual(result.decision.route.value, "visible_chat")
            usage = read_chat_relay_usage(ledger.path)
            self.assertEqual((usage["consultations"], usage["routed_tasks"]), (1, 1))
            self.assertGreater(usage["estimated_tokens_saved"], estimate_tokens("bounded advice"))
            self.assertEqual(usage["events"][0]["task_id"], "ctrl/task-1")
            self.assertNotIn("bounded advice", ledger.path.read_text(encoding="utf-8"))

    def test_clear_removes_the_local_log(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "chat-relay-usage.json"
            ledger = ChatRelayUsageLedger(path)
            ledger.record(task_id="task", purpose="plan", model="pro", effort="pro", prompt="p", response="r")
            self.assertEqual(read_chat_relay_usage(path)["consultations"], 1)
            ledger.clear()
            self.assertEqual(read_chat_relay_usage(path)["consultations"], 0)


if __name__ == "__main__":
    unittest.main()
