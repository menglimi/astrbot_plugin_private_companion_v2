"""Intervention decisions stay bounded and leave no persisted copy of chat text."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from astrbot_host.laya_client import LayaDecisionClient
from companion_v2.decision.prompt import intervention_question, render_intervention_state
from companion_v2.decision.service import LayaDecisionService
from companion_v2.decision.store import LayaSettingsStore
from companion_v2.storage.runtime import StorageRuntime


class InterventionLayaTests(unittest.TestCase):
    def test_client_sends_one_choice_limited_to_currently_allowed_domains(self):
        captured = {}
        client = LayaDecisionClient(mode="remote", endpoint="https://laya.example.test")

        async def post(state, questions):
            captured["state"] = state
            captured["questions"] = questions
            return json.dumps({"answers": {"intervention_need": {"type": "choice", "choice": "state"}}})

        client._post = post
        choice = asyncio.run(client.classify_intervention({
            "scope_kind": "private", "user_text": "你最近太累了，早点休息吧。",
            "conversation": [
                {"speaker": "user", "text": "你最近太累了，早点休息吧。", "at": "2026-10-18T10:00:00+08:00"},
                {"speaker": "assistant", "text": "那我去躺一会儿。", "at": "2026-10-18T10:00:02+08:00"},
            ],
            "allowed_domains": ["state"], "resting": False, "rest_wake_allowed": False,
        }))

        self.assertEqual(choice, "state")
        self.assertEqual(set(captured["questions"]), {"intervention_need"})
        self.assertEqual(set(captured["questions"]["intervention_need"]["criteria"]), {"none", "state"})
        self.assertIn("你最近太累了", captured["state"])
        self.assertIn("那我去躺一会儿", captured["state"])
        instructions = captured["questions"]["intervention_need"]["instructions"]
        self.assertIn("后台复核路由", instructions)
        self.assertIn("不要求出现特定词句", instructions)
        self.assertIn("下游维护者", instructions)
        self.assertNotIn("建议、邀请和假设", instructions)

    def test_classifier_routes_for_review_instead_of_declaring_a_change(self):
        question = intervention_question({"allowed_domains": ["state", "calendar"]})["intervention_need"]

        self.assertIn("both", question["criteria"])
        self.assertIn("值得复核", question["criteria"]["both"])
        self.assertIn("不代表两者最终都会发生变化", question["criteria"]["both"])
        self.assertIn("没有新的、尚未反映", question["criteria"]["none"])

    def test_intervention_state_marks_missing_role_reply_without_inventing_one(self):
        state = json.loads(render_intervention_state({
            "scope_kind": "private", "user_text": "你早点休息吧。",
            "conversation": [{"speaker": "user", "text": "你早点休息吧。"}],
            "allowed_domains": ["state"],
        }))
        facts = state["facts"]
        self.assertFalse(facts["assistant_reply_returned"])
        self.assertEqual(facts["conversation"], [{"speaker": "user", "at": "", "text": "你早点休息吧。"}])

    def test_intervention_diagnostics_do_not_store_message_or_model_response_bodies(self):
        with TemporaryDirectory(prefix="companion-v2-intervention-laya-") as directory:
            root = Path(directory)
            store = LayaSettingsStore(root / "settings", "target", "role")
            store.update(store.read()["revision"], {"enabled": True})
            runtime = StorageRuntime.open(data_root=root / "runtime", installation_id="laya-intervention-test")
            try:
                class RecordedClient:
                    last_trace = {
                        "request": {"model": "multilingual", "sent": True,
                                    "state": '{"facts":{"user_text":"private intervention text"}}'},
                        "response": {"format": "json", "body": "private intervention text", "value": {}},
                        "processing": {"stages": [{"name": "inference", "status": "ok"}]},
                    }

                    async def classify_intervention(self, _facts):
                        return "state"

                service = LayaDecisionService(store, runtime=runtime, origin_key="role-key")
                service._client = lambda _values: RecordedClient()
                service.set_trace(event_ref="role-intervention-test", source="role_intervention")
                result = asyncio.run(service.classify_intervention({
                    "scope_kind": "private", "user_text": "private intervention text",
                    "allowed_domains": ["state"],
                }))

                event = service.recent()["events"][0]
                self.assertEqual(result["intervention_need"], "state")
                self.assertNotIn("private intervention text", json.dumps(event, ensure_ascii=False))
                self.assertEqual(event["request"], {"model": "multilingual", "sent": True})
                self.assertEqual(event["response"], {"format": "json"})
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
