import sys
import types
import unittest
from unittest.mock import Mock, call, patch

from astrbot_host.token_sources import _bucket, read_token_sources


class TokenSourceTests(unittest.TestCase):
    def test_together_reads_internal_service_without_importing_a_legacy_star(self):
        raw = {"totals": {"calls": 1, "total_tokens": 87},
               "by_task": {"together.realtime": {"calls": 1, "total_tokens": 87}},
               "counted_in_private_companion_budget": False}
        tracker = types.SimpleNamespace(summary=Mock(return_value=raw), record=Mock())
        service = types.SimpleNamespace(token_usage=tracker)
        registry = types.SimpleNamespace(service=Mock(side_effect=lambda name: service if name == "together" else None))
        controller = types.SimpleNamespace(native_extensions=registry)
        legacy = types.ModuleType("astrbot_plugin_together_companion")
        legacy.PLUGIN_NAME = legacy.__name__
        legacy.get_together_companion_api = Mock(side_effect=AssertionError("legacy Together must not be read"))
        with patch.dict(sys.modules, {legacy.__name__: legacy}):
            together = read_token_sources(controller)["together"]
        self.assertEqual(registry.service.call_args_list,
                         [call("together"), call("reality"), call("live"), call("game")])
        tracker.summary.assert_called_once_with()
        tracker.record.assert_not_called()
        legacy.get_together_companion_api.assert_not_called()
        self.assertTrue(together["available"])
        self.assertEqual(together["totals"]["tokens"], 87)
        self.assertFalse(together["counted_in_private_companion_budget"])
        self.assertEqual(raw["totals"], {"calls": 1, "total_tokens": 87})

    def test_missing_internal_together_does_not_fall_back_to_legacy_stats(self):
        legacy = types.ModuleType("astrbot_plugin_together_companion")
        legacy.PLUGIN_NAME = legacy.__name__
        legacy.get_together_companion_api = Mock()
        controller = types.SimpleNamespace(native_extensions=types.SimpleNamespace(service=lambda _name: None))
        with patch.dict(sys.modules, {legacy.__name__: legacy}):
            together = read_token_sources(controller)["together"]
        self.assertFalse(together["available"])
        self.assertFalse(together["installed"])
        legacy.get_together_companion_api.assert_not_called()

    def test_live_and_game_ledgers_preserve_real_and_unknown_receipts(self):
        live = {"available": True, "totals": {"calls": 2, "total_tokens": 90,
            "reported_tokens": 90, "unconfirmed_calls": 1, "cache_telemetry_calls": 0}}
        game = {"available": True, "totals": {"calls": 1, "total_tokens": None,
            "reported_tokens": None, "unconfirmed_calls": 1, "cache_telemetry_calls": 0}}
        services = {name: types.SimpleNamespace(token_usage=types.SimpleNamespace(
            summary=Mock(return_value=summary))) for name, summary in (("live", live), ("game", game))}
        controller = types.SimpleNamespace(native_extensions=types.SimpleNamespace(service=services.get))
        report = read_token_sources(controller)
        self.assertEqual(report["live"]["totals"]["tokens"], 90)
        self.assertIsNone(report["game"]["totals"]["tokens"])
        for name in services:
            self.assertTrue(report[name]["available"])
            self.assertIsNone(report[name]["totals"]["cached_input_tokens"])
            self.assertEqual(report[name]["totals"]["unconfirmed_calls"], 1)
            self.assertFalse(report[name]["counted_in_private_companion_budget"])
            services[name].token_usage.summary.assert_called_once_with()

    def test_failed_internal_statistics_leave_the_reply_source_available_for_retry(self):
        tracker = types.SimpleNamespace(summary=Mock(side_effect=RuntimeError("statistics unavailable")))
        controller = types.SimpleNamespace(native_extensions=types.SimpleNamespace(
            service=lambda _name: types.SimpleNamespace(token_usage=tracker)))
        together = read_token_sources(controller)["together"]
        self.assertFalse(together["available"])
        self.assertTrue(together["installed"])

    def test_bucket_keeps_reported_and_estimated_counts(self):
        bucket = _bucket({"calls": 2, "total_tokens": 115, "reported_tokens": 70, "estimated_tokens": 45})
        self.assertEqual((bucket["tokens"], bucket["reported_tokens"], bucket["estimated_tokens"]),
                         (115, 70, 45))

    def test_bucket_keeps_missing_usage_and_cache_fields_unknown(self):
        bucket = _bucket({"calls": 1, "total_tokens": None, "prompt_tokens": None,
                          "completion_tokens": None, "reported_tokens": None, "unconfirmed_calls": 1,
                          "cache_hit_reported": False, "cache_telemetry_calls": 0})
        self.assertIsNone(bucket["tokens"])
        self.assertIsNone(bucket["input_tokens"])
        self.assertIsNone(bucket["output_tokens"])
        self.assertIsNone(bucket["reported_tokens"])
        self.assertIsNone(bucket["cached_input_tokens"])
        self.assertIsNone(bucket["cache_creation_tokens"])
        self.assertEqual(bucket["unconfirmed_calls"], 1)

    def test_bucket_without_cache_fields_keeps_cache_rate_unknown(self):
        bucket = _bucket({"calls": 3, "total_tokens": 120, "prompt_tokens": 80,
                          "completion_tokens": 40})
        self.assertEqual(bucket["cache_reported_calls"], 0)
        self.assertEqual(bucket["cache_telemetry_calls"], 0)
        self.assertEqual(bucket["cache_input_tokens"], 0)
        self.assertIsNone(bucket["cached_input_tokens"])
        self.assertFalse(bucket["cache_hit_reported"])

    def test_bucket_explicit_zero_cache_hit_is_reported(self):
        bucket = _bucket({"calls": 1, "total_tokens": 100, "prompt_tokens": 100,
                          "cached_input_tokens": 0, "cache_hit_reported": True})
        self.assertTrue(bucket["cache_hit_reported"])
        self.assertEqual(bucket["cached_input_tokens"], 0)
        self.assertEqual(bucket["cache_input_tokens"], 100)
        self.assertEqual(bucket["cache_reported_calls"], 1)
        self.assertEqual(bucket["cache_telemetry_calls"], 1)

    def test_bucket_explicit_no_hit_field_keeps_rate_uncomputable(self):
        bucket = _bucket({"calls": 1, "total_tokens": 100, "prompt_tokens": 100,
                          "cache_hit_reported": False})
        self.assertFalse(bucket["cache_hit_reported"])
        self.assertEqual(bucket["cache_input_tokens"], 0)
        self.assertEqual(bucket["cache_reported_calls"], 0)
        self.assertEqual(bucket["cache_telemetry_calls"], 0)

    def test_public_bridge_projects_bounded_history_and_drops_prompt_content(self):
        summary = {
            "available": True,
            "display_name": "记忆伴侣",
            "updated_at": "2026-10-01T12:00:00",
            "totals": {"calls": 2, "total_tokens": 115, "reported_tokens": 70, "estimated_tokens": 45},
            "by_day": {"2026-10-01": {"calls": 2, "total_tokens": 115,
                                         "reported_tokens": 70, "estimated_tokens": 45}},
            "by_provider": {"memory-model": {"calls": 2, "total_tokens": 115,
                                                 "reported_tokens": 70, "estimated_tokens": 45}},
            "by_task": {"memory.recall": {"calls": 2, "total_tokens": 115,
                                             "reported_tokens": 70, "estimated_tokens": 45}},
            "recent": [{"task": "memory.recall", "provider": "memory-model", "success": True,
                        "total_tokens": 115, "reported_tokens": 70, "estimated_tokens": 45,
                        "prompt": "must not leave the provider summary"}],
        }
        bridge = types.SimpleNamespace(get_token_usage_summary=lambda: summary)
        module = types.ModuleType("astrbot_plugin_remember_you")
        module.PLUGIN_NAME = "astrbot_plugin_remember_you"
        module.get_memory_companion_bridge = lambda: bridge
        with patch.dict(sys.modules, {module.__name__: module}):
            sources = read_token_sources()

        memory = sources["memory"]
        self.assertTrue(memory["available"])
        self.assertEqual(memory["totals"]["tokens"], 115)
        self.assertEqual((memory["daily"][0]["reported_tokens"], memory["daily"][0]["estimated_tokens"]),
                         (70, 45))
        self.assertEqual((memory["by_provider"][0]["reported_tokens"], memory["by_task"][0]["estimated_tokens"]),
                         (70, 45))
        self.assertNotIn("prompt", memory["recent"][0])
        self.assertEqual(memory["recent"][0]["reported_tokens"], 70)


if __name__ == "__main__":
    unittest.main()
