"""Intervention decisions stay bounded and leave no persisted copy of chat text."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from astrbot_host.laya_client import LayaDecisionClient
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
            "allowed_domains": ["state"], "resting": False, "rest_wake_allowed": False,
        }))

        self.assertEqual(choice, "state")
        self.assertEqual(set(captured["questions"]), {"intervention_need"})
        self.assertEqual(set(captured["questions"]["intervention_need"]["criteria"]), {"none", "state"})
        self.assertIn("你最近太累了", captured["state"])

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
