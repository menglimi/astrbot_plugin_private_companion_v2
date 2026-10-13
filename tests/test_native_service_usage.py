"""Reality and Together count real model receipts on their own V2 ledgers."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_astrbot_staging_host as _host_import_root
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot_host.native_extensions.reality.activity_methods import RealityActivityMethods
from astrbot_host.native_extensions.reality.model_methods import RealityModelMethods
from astrbot_host.native_extensions.reality.reality_touch_camera import RealityTouchCameraMixin
from astrbot_host.native_extensions.together.token_usage import TokenUsageTracker as TogetherUsage
from astrbot_host.native_extensions.usage import TokenUsageTracker
from astrbot_host.token_sources import _summary, read_token_sources


class LocalReality(RealityActivityMethods, RealityModelMethods, RealityTouchCameraMixin):
    def __init__(self, root, response):
        self.token_usage = TokenUsageTracker(root / "reality.json", source="reality", display_name="现实观察")
        self._background_tasks = set()
        self.provider = NS(text_chat=AsyncMock(return_value=response))
        self.context = NS(get_provider_by_id=lambda _provider: self.provider)
        self.plugin_vision_provider_id = "vision-a"


class NativeServiceUsageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-native-usage-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def record(self, tracker, response=None, **changes):
        arguments = dict(provider_id="vision-a", task="reality_touch_camera", prompt="真实提示不应保存正文",
                         completion="真实回复不应保存正文", elapsed_ms=80, success=True, response=response, persist=False)
        arguments.update(changes)
        tracker.record(**arguments)
        return tracker.summary()

    async def test_missing_receipt_and_sdk_default_zero_remain_unknown_without_text_estimates(self):
        for response in (None, LLMResponse(role="assistant", completion_text="很长的回复", usage=TokenUsage())):
            with self.subTest(response=response):
                tracker = TokenUsageTracker(self.root / "usage.json")
                summary = self.record(tracker, response)
                latest = summary["recent"][-1]
                self.assertIsNone(latest["total_tokens"])
                self.assertIsNone(latest["reported_tokens"])
                self.assertIsNone(latest["cached_tokens"])
                self.assertIsNone(latest["cache_write_tokens"])
                self.assertEqual(latest["estimated_tokens"], 0)
                self.assertEqual(summary["totals"]["unconfirmed_calls"], 1)

    async def test_openai_explicit_zero_cache_hit_is_reported_but_missing_write_is_unknown(self):
        response = LLMResponse(role="assistant", usage=TokenUsage(100, 0, 20), raw_completion=NS(usage={
            "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 0}}))
        summary = self.record(TokenUsageTracker(self.root / "usage.json"), response)
        latest = summary["recent"][-1]
        self.assertEqual((latest["prompt_tokens"], latest["completion_tokens"], latest["total_tokens"]), (100, 20, 120))
        self.assertEqual(latest["cache_read_tokens"], 0)
        self.assertTrue(latest["cache_hit_reported"])
        self.assertIsNone(latest["cache_write_tokens"])
        self.assertEqual(summary["totals"]["cache_reported_calls"], 1)

    async def test_sdk_reported_usage_keeps_default_cache_zero_unknown(self):
        summary = self.record(TokenUsageTracker(self.root / "usage.json"), NS(usage=TokenUsage(100, 0, 20)))
        latest = summary["recent"][-1]
        self.assertEqual(latest["total_tokens"], 120)
        self.assertIsNone(latest["cache_read_tokens"])
        self.assertIsNone(latest["cache_write_tokens"])
        self.assertFalse(latest["cache_hit_reported"])
        self.assertEqual(summary["totals"]["cache_telemetry_calls"], 0)

    async def test_anthropic_separate_cached_input_is_counted_once(self):
        response = NS(raw_completion=NS(usage={"input_tokens": 60, "output_tokens": 20,
            "cache_read_input_tokens": 40, "cache_creation_input_tokens": 10}), usage=TokenUsage(70, 40, 20))
        summary = self.record(TokenUsageTracker(self.root / "usage.json"), response)
        latest = summary["recent"][-1]
        self.assertEqual((latest["prompt_tokens"], latest["total_tokens"], latest["cache_read_tokens"], latest["cache_write_tokens"]),
                         (110, 130, 40, 10))

    async def test_total_only_receipt_does_not_invent_input_or_output_split(self):
        summary = self.record(TokenUsageTracker(self.root / "usage.json"), NS(usage={"total_tokens": 67}))
        latest = summary["recent"][-1]
        self.assertEqual(latest["reported_tokens"], 67)
        self.assertIsNone(latest["prompt_tokens"])
        self.assertIsNone(latest["completion_tokens"])
        self.assertEqual(latest["estimated_tokens"], 0)

    async def test_provider_explicit_zero_usage_differs_from_the_sdk_default(self):
        summary = self.record(TokenUsageTracker(self.root / "usage.json"), NS(usage={
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}))
        self.assertEqual(summary["recent"][-1]["total_tokens"], 0)
        self.assertTrue(summary["recent"][-1]["usage_available"])
        self.assertEqual(summary["totals"]["unconfirmed_calls"], 0)

    async def test_persistence_preserves_old_estimates_separately_and_new_calls_are_not_estimated(self):
        path = self.root / "together.json"
        old = {"totals": {"calls": 1, "total_tokens": 30, "estimated_tokens": 30,
                           "cached_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0},
               "recent": [{"total_tokens": 30, "estimated": True, "cached_tokens": 0}]}
        path.write_text(json.dumps(old), encoding="utf-8")
        tracker = TogetherUsage(path)
        summary = self.record(tracker, NS(usage=TokenUsage(100, 0, 20)), task="together.realtime")
        self.assertEqual(summary["totals"]["estimated_tokens"], 30)
        self.assertEqual(summary["totals"]["reported_tokens"], 120)
        self.assertFalse(summary["recent"][-1]["estimated"])
        self.assertIsNone(summary["totals"]["cached_tokens"])
        self.assertIsNone(summary["totals"]["cache_write_tokens"])
        projected = _summary(summary, "together", installed=True)
        self.assertEqual(projected["totals"]["cache_reported_calls"], 0)
        self.assertEqual(projected["recent"][-1]["reported_tokens"], 0)
        tracker.save(force=True)
        written = path.read_bytes()
        self.assertNotIn(b"\r\n", written)
        self.assertTrue(written.endswith(b"\n"))
        self.assertNotIn("真实提示不应保存正文", written.decode("utf-8"))
        self.assertNotIn("真实回复不应保存正文", written.decode("utf-8"))

    async def test_camera_analysis_records_the_actual_response_without_together_running(self):
        response = LLMResponse(role="assistant", completion_text=json.dumps({
            "scene_description": "桌上有苹果", "purpose_answer": "苹果", "answer_status": "answered",
            "visible_evidence": ["桌上圆形红色苹果"], "confidence": 0.9}, ensure_ascii=False),
            usage=TokenUsage(100, 0, 20))
        runtime = LocalReality(self.root, response)
        observed = await runtime._analyze_reality_touch_camera_frame(
            {"jpeg_bytes": b"fixture-jpeg", "brightness": "normal", "width": 100, "height": 100}, "桌上有什么")
        self.assertEqual(observed["purpose_answer"], "苹果")
        runtime.provider.text_chat.assert_awaited_once()
        host = NS(native_extensions=NS(service=lambda name: runtime if name == "reality" else None))
        sources = read_token_sources(host)
        self.assertFalse(sources["together"]["available"])
        self.assertEqual(sources["reality"]["totals"]["reported_tokens"], 120)
        self.assertIsNone(sources["reality"]["totals"]["cached_input_tokens"])
        self.assertEqual(sources["reality"]["by_task"][0]["key"], "reality_touch_camera")
        self.assertEqual(sources["reality"]["totals"]["calls"], 1)
        await asyncio.gather(*tuple(runtime._background_tasks))
        self.assertTrue((self.root / "reality.json").is_file())

    async def test_background_disk_save_does_not_hold_new_model_receipts(self):
        tracker = TokenUsageTracker(self.root / "usage.json")
        self.record(tracker)
        entered, release = threading.Event(), threading.Event()
        original_write = Path.write_text

        def delayed_write(path, *args, **kwargs):
            entered.set()
            release.wait(2)
            return original_write(path, *args, **kwargs)

        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(Path, "write_text", delayed_write):
            saving = pool.submit(tracker.save, force=True)
            try:
                self.assertTrue(entered.wait(1))
                recording = pool.submit(self.record, tracker, NS(usage=TokenUsage(100, 0, 20)))
                self.assertEqual(recording.result(timeout=1)["totals"]["calls"], 2)
            finally:
                release.set()
                saving.result(timeout=2)
        tracker.save(force=True)
        written = json.loads(tracker.path.read_text(encoding="utf-8"))
        self.assertEqual(written["totals"]["calls"], 2)
        self.assertEqual(written["totals"]["reported_tokens"], 120)
        self.assertEqual(written["totals"]["unconfirmed_calls"], 1)

    async def test_camera_failure_records_unknown_usage_once_without_replaying(self):
        runtime = LocalReality(self.root, None)
        runtime.provider.text_chat.side_effect = TimeoutError("fixture provider unavailable")
        observed = await runtime._analyze_reality_touch_camera_frame(
            {"jpeg_bytes": b"fixture-jpeg", "brightness": "normal"}, "桌上有什么")
        self.assertFalse(observed["analyzed"])
        runtime.provider.text_chat.assert_awaited_once()
        summary = runtime.token_usage.summary()
        self.assertEqual(summary["totals"]["calls"], 1)
        self.assertEqual(summary["totals"]["unconfirmed_calls"], 1)
        self.assertIsNone(summary["totals"]["total_tokens"])
        await asyncio.gather(*tuple(runtime._background_tasks))


if __name__ == "__main__":
    unittest.main()
