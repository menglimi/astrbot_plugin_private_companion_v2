"""Exercise native intake with installed Laya weights and isolated QQ fixtures."""

import argparse
import asyncio
import json
import logging
from time import perf_counter
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests.test_core_reply_decision import CoreReplyDecisionTests


class InstalledLayaSmoke(CoreReplyDecisionTests):
    output = None
    action_only = False
    model_path = ""

    async def test_installed_weights(self):
        self.predict_patch.stop()
        if self.model_path:
            from companion_v2.decision.store import LayaSettingsStore
            store = LayaSettingsStore(self.root / "decision-config")
            store.update(store.raw()["revision"], {"local_model_path": self.model_path})
        if self.action_only:
            self.fields = {name: name == "action" for name in self.fields}
        from astrbot_host.laya_client import _load_local_model
        started = perf_counter()
        device = await asyncio.to_thread(_load_local_model, self.model_path)
        initialization_ms = round((perf_counter() - started) * 1000)
        print(json.dumps({"initialized": True, "device": device, "initialization_ms": initialization_ms}), flush=True)
        from astrbot_host import laya_client
        predict = laya_client._local_predict
        raw_usage = {}

        def observe_predict(state, questions, **options):
            result = predict(state, questions, **options)
            raw_usage.clear()
            raw_usage.update(result.get("usage", {}))
            return result

        observation = patch("astrbot_host.laya_client._local_predict", side_effect=observe_predict)
        observation.start()
        self.addCleanup(observation.stop)
        results = []
        for identifier, body, mention, expected in (
            ("other-member-question", "dsh 有没有什么好玩的插件", False, "silent"),
            ("direct-request", "你有什么好玩的插件推荐吗？", True, "reply"),
            ("wait-for-more", "我还没说完，等我补充后再答", True, "wait"),
            ("explicit-silence", "这条只记一下，不用回复", True, "silent"),
        ):
            event = self.incoming(identifier, body)
            if mention:
                event.message_obj.message.insert(0, NS(type="At", qq="100"))
            prepared = await self.intake(event)
            decision = prepared["laya_decision"]
            result = {"scenario": identifier, "text": body, "mentioned": mention, "expected_action": expected,
                "status": decision["status"], "action": decision.get("applied_decision", {}).get("action"),
                "decision": decision.get("decision"), "elapsed_ms": decision.get("elapsed_ms"),
                "reason": decision.get("reason"), "usage": dict(raw_usage), "core_wake": event.is_at_or_wake_command,
                "default_model_forbidden": getattr(event, "call_llm", False), "send_count": len(event.sent)}
            result["matches_scenario"] = result["action"] == expected
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            self.assertEqual(event.sent, [])
        report = {"backend": "installed_laya_local_weights", "host": "AstrBot native intake with isolated QQ fixtures",
            "initialization_ms": initialization_ms, "device": device, "model_path": self.model_path,
            "external_qq_connected": False, "main_model_called": False, "results": results,
            "laya_events": len(self.app.runtime.read_all("SELECT event_id FROM laya_decision_events", ())) }
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        self.assertTrue(all(item["status"] == "ok" for item in results), "see real inference report")
        self.assertTrue(all(item["matches_scenario"] for item in results), "see real classification report")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--action-only", action="store_true")
    parser.add_argument("--model-path", default="")
    args = parser.parse_args()
    for name in ("httpcore", "httpx", "huggingface_hub"):
        logging.getLogger(name).setLevel(logging.WARNING)
    InstalledLayaSmoke.output = args.output
    InstalledLayaSmoke.action_only = args.action_only
    InstalledLayaSmoke.model_path = args.model_path
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite([InstalledLayaSmoke("test_installed_weights")]))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
