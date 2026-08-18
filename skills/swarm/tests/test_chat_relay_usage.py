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
    ChatRelayResponse,
    ChatRelayTransportReceipt,
    build_chat_relay_context,
    consult_chat_relay,
)
from skills.swarm.runtime.chat_relay_usage import ChatRelayUsageLedger, read_chat_relay_usage


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
            transport=ChatRelayTransportReceipt(
                client_thread_id="client-thread",
                thread_id="thread-1",
                request_id="request-1",
                response_id="response-1",
                asset_ids=("asset-1",),
                model="gpt-5.6-luna",
                input_tokens=10,
                output_tokens=4,
                total_tokens=14,
                usage_status="reported",
                usage_reason="",
            ),
        )


class ChatRelayUsageTests(unittest.TestCase):
    def test_successful_visible_consult_records_provider_fields_without_savings_claim(self) -> None:
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
            self.assertEqual(usage["reported_total_tokens"], 14)
            self.assertEqual(usage["savings_status"], "unavailable")
            self.assertNotIn("estimated_tokens_saved", usage)
            self.assertEqual(usage["events"][0]["response_id"], "response-1")
            self.assertEqual(usage["events"][0]["asset_ids"], ["asset-1"])
            self.assertEqual(usage["events"][0]["task_id"], "ctrl/task-1")
            self.assertNotIn("bounded advice", ledger.path.read_text(encoding="utf-8"))

    def test_missing_provider_usage_is_explicitly_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "chat-relay-usage.json"
            ledger = ChatRelayUsageLedger(path)
            ledger.record(
                task_id="task",
                purpose="plan",
                response=ChatRelayResponse(
                    text="advice",
                    host_receipt="response",
                    observed_model="GPT-5.6 Luna",
                    observed_effort="Extra High",
                ),
            )
            usage = read_chat_relay_usage(path)
            self.assertEqual(usage["unavailable_usage_consultations"], 1)
            self.assertEqual(usage["events"][0]["usage_status"], "unavailable")
            self.assertIn("did not expose", usage["events"][0]["usage_reason"])

    def test_clear_removes_the_local_log(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "chat-relay-usage.json"
            ledger = ChatRelayUsageLedger(path)
            ledger.record(
                task_id="task",
                purpose="plan",
                response=ChatRelayResponse(
                    text="advice",
                    host_receipt="response",
                    observed_model="Pro",
                    observed_effort="Pro",
                ),
            )
            self.assertEqual(read_chat_relay_usage(path)["consultations"], 1)
            ledger.clear()
            self.assertEqual(read_chat_relay_usage(path)["consultations"], 0)


if __name__ == "__main__":
    unittest.main()
