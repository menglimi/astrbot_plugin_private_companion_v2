import sys
import types
import unittest
from unittest.mock import patch

from astrbot_host.token_sources import _bucket, read_token_sources


class TokenSourceTests(unittest.TestCase):
    def test_bucket_keeps_reported_and_estimated_counts(self):
        bucket = _bucket({"calls": 2, "total_tokens": 115, "reported_tokens": 70, "estimated_tokens": 45})
        self.assertEqual((bucket["tokens"], bucket["reported_tokens"], bucket["estimated_tokens"]),
                         (115, 70, 45))

    def test_bucket_without_cache_fields_keeps_cache_rate_unknown(self):
        bucket = _bucket({"calls": 3, "total_tokens": 120, "prompt_tokens": 80,
                          "completion_tokens": 40})
        self.assertEqual(bucket["cache_reported_calls"], 0)
        self.assertEqual(bucket["cache_telemetry_calls"], 0)
        self.assertEqual(bucket["cache_input_tokens"], 0)
        self.assertEqual(bucket["cached_input_tokens"], 0)
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
        self.assertEqual(bucket["cache_input_tokens"], 100)
        self.assertEqual(bucket["cache_reported_calls"], 0)
        self.assertEqual(bucket["cache_telemetry_calls"], 1)

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
