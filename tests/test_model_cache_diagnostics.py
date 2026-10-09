import json
from datetime import date, timedelta
import unittest

from companion_v2.model_gateway.cache_diagnostics import (
    checked_signature, event_severity, signature_changes, signature_for_payload, signature_snapshot,
)
from companion_v2.model_gateway.management import _cache_diagnostic_summary
from companion_v2.execution.models import digest, encode


class ModelCacheDiagnosticsTests(unittest.TestCase):
    def scope_json(self, *, session="session-a", conversation="conversation-a"):
        return json.dumps({"installation_id": "install-a", "platform": "test-platform",
            "kind": "private", "native_scope_id": "participant-a", "bot_id": "bot-a",
            "account_id": "account-a", "conversation_id": conversation, "session_id": session})

    def payload(self, *, model="model-a", system=("role prompt", "stable contract"), request="private request",
                materials=None, tools=(), deferred=(), unavailable=()):
        if materials is None:
            materials = [{"owner": "user", "purpose": "current_source", "content_class": "current_user_request",
                          "text": request},
                         {"owner": "memory", "purpose": "reference", "content_class": "reference_data",
                          "text": "private fact"}]
        messages = [{"role": "system", "content": text} for text in system]
        messages.append({"role": "user", "content": json.dumps({"materials": materials,
            "deferred": list(deferred), "unavailable": list(unavailable)}, ensure_ascii=False)})
        return signature_for_payload(model, messages, tools)

    def test_signatures_exclude_current_request_text_and_retain_only_hashes(self):
        first = self.payload(request="first secret")
        second = self.payload(request="second secret")
        self.assertEqual(signature_changes(second, first), ())
        self.assertNotIn("secret", json.dumps(first.to_record()))
        self.assertNotIn("private fact", json.dumps(first.to_record()))
        self.assertEqual(first.context_material_count, 1)
        self.assertEqual(first.context_chars, len("private fact"))
        self.assertEqual(first.context_bytes, len("private fact".encode("utf-8")))
        self.assertEqual(first.context_est_tokens, 3)
        self.assertGreater(first.system_est_tokens, 0)
        self.assertEqual(first.estimates_observed, True)
        self.assertEqual(first.message_count, 3)
        self.assertEqual(first.system_message_count, 2)
        self.assertGreater(first.message_est_tokens, 0)
        self.assertEqual(first.request_est_tokens, first.context_est_tokens + first.message_est_tokens
                         + first.system_est_tokens + first.tool_est_tokens)
        self.assertEqual(first.message_chars, len(json.dumps({"materials": [
            {"owner": "user", "purpose": "current_source", "content_class": "current_user_request", "text": "first secret"},
            {"owner": "memory", "purpose": "reference", "content_class": "reference_data", "text": "private fact"}],
            "deferred": [], "unavailable": []}, ensure_ascii=False)))
        self.assertTrue(first.request_estimate_observed)
        self.assertNotIn("first secret", json.dumps(first.to_record()))

    def test_context_token_estimate_matches_cjk_heuristic_from_cost_control(self):
        signature = self.payload(materials=[
            {"owner": "memory", "purpose": "reference", "content_class": "reference_data",
             "text": "你好世界测试"},
        ])
        self.assertEqual(signature.context_est_tokens, 3)

    def test_request_context_estimate_covers_messages_system_and_tools(self):
        tool = {"name": "lookup", "description": "查找资料", "parameters": {"type": "object"}}
        signature = self.payload(request="你好", tools=(tool,))
        self.assertEqual(signature.request_est_tokens,
            signature.context_est_tokens + signature.message_est_tokens
            + signature.system_est_tokens + signature.tool_est_tokens)
        self.assertGreater(signature.message_chars, 0)
        self.assertGreater(signature.message_bytes, signature.message_chars)
        self.assertGreater(signature.tool_est_tokens, 0)

    def test_request_estimate_includes_assistant_tool_call_payloads(self):
        messages = [
            {"role": "system", "content": "stable system"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "call-1", "function": {"name": "lookup", "arguments": '{"q":"天气"}'}}]},
            {"role": "tool", "content": "晴天"},
        ]
        signature = signature_for_payload("model-a", messages, ())
        self.assertGreater(signature.message_est_tokens, 0)
        self.assertGreater(signature.message_chars, len("晴天"))
        self.assertEqual(signature.request_est_tokens, signature.system_est_tokens + signature.message_est_tokens)

    def test_context_availability_changes_are_recorded_without_retaining_material_text(self):
        baseline = self.payload(deferred=[{"owner": "weather", "purpose": "current_weather"}])
        restored = self.payload(unavailable=[{"owner": "weather", "purpose": "current_weather"}])
        self.assertIn("context_availability_change", signature_changes(restored, baseline))
        snapshot = signature_snapshot(restored)
        self.assertEqual(snapshot["deferred_materials"], 0)
        self.assertEqual(snapshot["unavailable_materials"], 1)
        self.assertNotIn("current_weather", json.dumps(restored.to_record()))

    def test_maximum_signature_fits_the_bounded_storage_record(self):
        materials = [{"owner": "memory", "purpose": str(index), "content_class": "reference_data",
                      "text": "fact " + str(index)} for index in range(256)]
        system = tuple("system " + str(index) for index in range(32))
        tools = tuple({"name": "tool-" + str(index), "description": "bounded tool",
                       "parameters": {"type": "object"}} for index in range(64))
        signature = self.payload(system=system, materials=materials, tools=tools)
        self.assertLessEqual(len(encode(signature.to_record())), 32768)

    def test_provider_switch_is_reported_without_cross_provider_hit_comparison(self):
        today = date(2026, 10, 9).isoformat()
        signature_json = json.dumps(self.payload().to_record())
        rows = [
            {"position": 0, "input_tokens": 1000, "cached_input_tokens": 400,
             "finished_at": today + "T12:00:00+00:00", "started_at": None, "created_at": None,
             "kind": "conversation.reply", "origin_key": "private-chat",
             "provider_json": '{"provider":"provider-a"}', "signature_json": signature_json,
             "audience_scope_json": self.scope_json()},
            {"position": 0, "input_tokens": 1000, "cached_input_tokens": 0,
             "finished_at": today + "T12:01:00+00:00", "started_at": None, "created_at": None,
             "kind": "conversation.reply", "origin_key": "private-chat",
             "provider_json": '{"provider":"provider-b"}', "signature_json": signature_json,
             "audience_scope_json": self.scope_json()},
        ]

        class Runtime:
            def read_all(self, query, account_keys):
                return rows

        reports = _cache_diagnostic_summary(Runtime(), {today: "account"}, {today}, "test-role")
        daily = reports["all"]["daily"][0]
        event = reports["all"]["recent_events"][0]
        self.assertEqual(daily["provider_changes"], 1)
        self.assertEqual(daily["cache_hit_comparable_changes"], 0)
        self.assertEqual(event["previous_provider"], "provider-a")
        self.assertEqual(event["provider"], "provider-b")
        self.assertIn("provider_change", event["changes"])
        self.assertEqual(event["severity"], "high")
        scope = json.loads(self.scope_json())
        self.assertEqual(event["session_ref"], digest(["cache-diagnostics-session", digest(scope)])[:8])
        self.assertIsNone(event["cache_hit_delta"])
        self.assertEqual(daily["route_stable_calls"], 0)
        self.assertEqual(daily["system_stable_calls"], 1)
        self.assertEqual(daily["system_cache_calls"], 0)
        self.assertEqual(daily["system_cache_input_tokens_total"], 0)
        self.assertEqual(daily["system_cached_input_tokens_total"], 0)

    def test_event_severity_uses_strongest_change_and_session_is_opaque(self):
        today = date(2026, 10, 9).isoformat()
        first = self.payload()
        changed = self.payload(system=("changed system",))
        rows = [
            {"position": 0, "input_tokens": 1000, "cached_input_tokens": 500,
             "finished_at": today + "T12:00:00+00:00", "started_at": None, "created_at": None,
             "kind": "conversation.reply", "origin_key": "private-chat",
             "provider_json": '{"provider":"provider-a"}', "signature_json": json.dumps(first.to_record()),
             "audience_scope_json": self.scope_json(session="native-session-secret"),
             "session_id": "native-session-secret"},
            {"position": 0, "input_tokens": 1000, "cached_input_tokens": 400,
             "finished_at": today + "T12:01:00+00:00", "started_at": None, "created_at": None,
             "kind": "conversation.reply", "origin_key": "private-chat",
             "provider_json": '{"provider":"provider-a"}', "signature_json": json.dumps(changed.to_record()),
             "audience_scope_json": self.scope_json(session="native-session-secret"),
             "session_id": "native-session-secret"},
        ]

        class Runtime:
            def read_all(self, query, account_keys):
                return rows

        report = _cache_diagnostic_summary(Runtime(), {today: "account"}, {today}, "test-role")["all"]
        event = report["recent_events"][0]
        self.assertEqual(event["severity"], "high")
        self.assertEqual(report["daily"][0]["high_severity_events"], 1)
        self.assertEqual(report["daily"][0]["medium_severity_events"], 0)
        self.assertEqual(report["daily"][0]["low_severity_events"], 0)
        scope = json.loads(self.scope_json(session="native-session-secret"))
        self.assertEqual(event["session_ref"], digest(["cache-diagnostics-session", digest(scope)])[:8])
        self.assertNotIn("native-session-secret", json.dumps(event))
        self.assertNotEqual(event["before"]["system_fingerprint"], event["after"]["system_fingerprint"])
        self.assertEqual(event_severity(("context_availability_change",)), "low")
        self.assertEqual(event_severity(("tool_order_drift", "model_change")), "high")

    def test_session_routes_are_isolated_and_missing_routes_do_not_compare(self):
        today = date(2026, 10, 9).isoformat()
        first = self.payload()
        changed = self.payload(system=("changed system",))
        rows = [
            {"call_id": "call-a1", "position": 0, "input_tokens": 1000, "cached_input_tokens": 500,
             "finished_at": today + "T12:00:00+00:00", "started_at": None, "created_at": None,
             "kind": "conversation.reply", "origin_key": "private-chat",
             "provider_json": '{"provider":"provider-a"}', "signature_json": json.dumps(first.to_record()),
             "audience_scope_json": self.scope_json(session="session-a")},
            {"call_id": "call-b1", "position": 0, "input_tokens": 1000, "cached_input_tokens": 400,
             "finished_at": today + "T12:01:00+00:00", "started_at": None, "created_at": None,
             "kind": "conversation.reply", "origin_key": "private-chat",
             "provider_json": '{"provider":"provider-a"}', "signature_json": json.dumps(changed.to_record()),
             "audience_scope_json": self.scope_json(session="session-b", conversation="conversation-b")},
            {"call_id": "call-a2", "position": 0, "input_tokens": 1000, "cached_input_tokens": 450,
             "finished_at": today + "T12:02:00+00:00", "started_at": None, "created_at": None,
             "kind": "conversation.reply", "origin_key": "private-chat",
             "provider_json": '{"provider":"provider-a"}', "signature_json": json.dumps(changed.to_record()),
             "audience_scope_json": self.scope_json(session="session-a")},
            {"call_id": "call-unknown", "position": 0, "input_tokens": 1000, "cached_input_tokens": 450,
             "finished_at": today + "T12:03:00+00:00", "started_at": None, "created_at": None,
             "kind": "conversation.reply", "origin_key": "private-chat",
             "provider_json": '{"provider":"provider-a"}', "signature_json": json.dumps(changed.to_record()),
             "audience_scope_json": None},
        ]

        class Runtime:
            def read_all(self, query, account_keys):
                return rows

        report = _cache_diagnostic_summary(Runtime(), {today: "account"}, {today}, "test-role")["all"]
        daily = report["daily"][0]
        self.assertEqual((daily["baseline_calls"], daily["compared_calls"], daily["changed_calls"]), (3, 1, 1))
        self.assertEqual(len(report["recent_events"]), 1)
        self.assertEqual(report["recent_events"][0]["session_ref"],
            digest(["cache-diagnostics-session", digest(json.loads(self.scope_json(session="session-a")))])[:8])

    def test_model_change_and_short_context_prefix_change_are_reported(self):
        previous = self.payload(materials=[
            {"owner": "memory", "purpose": "a", "content_class": "reference_data", "text": "old A"},
            {"owner": "memory", "purpose": "b", "content_class": "reference_data", "text": "old B"},
            {"owner": "memory", "purpose": "c", "content_class": "reference_data", "text": "old C"},
        ])
        changed_model = self.payload(model="model-b", materials=[
            {"owner": "memory", "purpose": "a", "content_class": "reference_data", "text": "old A"},
            {"owner": "memory", "purpose": "b", "content_class": "reference_data", "text": "old B"},
            {"owner": "memory", "purpose": "c", "content_class": "reference_data", "text": "old C"},
        ])
        self.assertIn("model_change", signature_changes(changed_model, previous))

        shortened = self.payload(materials=[
            {"owner": "memory", "purpose": "x", "content_class": "reference_data", "text": "new start"},
        ])
        self.assertIn("context_prefix_change", signature_changes(shortened, previous))

    def test_tail_trim_and_append_are_distinguished_from_prefix_breaks(self):
        first_material = {"owner": "memory", "purpose": "a", "content_class": "reference_data", "text": "A"}
        second_material = {"owner": "memory", "purpose": "b", "content_class": "reference_data", "text": "B"}
        third_material = {"owner": "memory", "purpose": "c", "content_class": "reference_data", "text": "C"}
        first = self.payload(materials=[first_material, second_material])
        appended = self.payload(materials=[first_material, second_material, third_material])
        trimmed = self.payload(materials=[first_material])
        self.assertEqual(signature_changes(appended, first), ())
        self.assertEqual(signature_changes(trimmed, first), ("context_tail_trim",))

    def test_final_payload_statistics_count_multimodal_parts_without_storing_bodies(self):
        messages = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,private"}},
            {"type": "input_audio", "input_audio": {"data": "private"}},
            {"type": "video_data", "video_data": {"data": "private"}},
        ]}]
        signature = signature_for_payload("model-a", messages, ())
        self.assertEqual((signature.image_count, signature.audio_count, signature.video_count), (1, 1, 1))
        self.assertEqual(signature.message_count, 1)
        self.assertEqual(signature.message_est_tokens, 0)
        self.assertNotIn("private", json.dumps(signature.to_record()))

    def test_version_one_signatures_remain_readable(self):
        legacy = {"version": 1, "model_hash": "a" * 64, "system_hash": "b" * 64,
            "system_parts": ["b" * 64], "tools_hash": "c" * 64, "tool_parts": [],
            "context_hashes": [], "context_bytes": 0, "context_observed": True}
        restored = checked_signature(json.dumps(legacy))
        self.assertIsNotNone(restored)
        self.assertFalse(restored.request_stats_observed)
        self.assertFalse(restored.estimates_observed)
        self.assertEqual(signature_changes(restored, restored), ())

    def test_version_two_signatures_remain_readable_without_fake_estimates(self):
        current = self.payload()
        legacy = current.to_record()
        legacy["version"] = 2
        for key in ("estimates_observed", "context_est_tokens", "system_est_tokens", "tool_est_tokens"):
            legacy.pop(key, None)
        restored = checked_signature(json.dumps(legacy))
        self.assertTrue(restored.request_stats_observed)
        self.assertFalse(restored.estimates_observed)
        self.assertIsNone(signature_snapshot(restored)["system_est_tokens"])

    def test_version_three_signatures_do_not_claim_new_request_estimates(self):
        legacy = self.payload().to_record()
        legacy["version"] = 3
        for key in ("message_estimates_observed", "message_est_tokens", "message_chars", "message_bytes",
                    "request_estimate_observed", "request_est_tokens", "context_availability_observed",
                    "context_availability_hash", "deferred_material_count", "unavailable_material_count"):
            legacy.pop(key, None)
        restored = checked_signature(json.dumps(legacy))
        snapshot = signature_snapshot(restored)
        self.assertIsNone(snapshot["message_est_tokens"])
        self.assertIsNone(snapshot["request_est_tokens"])
        self.assertIsNone(snapshot["deferred_materials"])

    def test_version_four_message_estimate_is_split_without_changing_request_total(self):
        legacy = self.payload().to_record()
        legacy["version"] = 4
        legacy["message_est_tokens"] += legacy["context_est_tokens"]
        restored = checked_signature(json.dumps(legacy))
        self.assertEqual(restored.message_est_tokens, self.payload().message_est_tokens)
        self.assertEqual(restored.request_est_tokens, legacy["request_est_tokens"])

    def test_version_one_baseline_does_not_create_upgrade_change_events(self):
        current = self.payload()
        legacy = current.to_record()
        legacy["version"] = 1
        for key in ("context_sequence_hash", "context_multiset_hash", "context_material_count",
                    "context_chars", "request_stats_observed", "estimates_observed", "context_est_tokens",
                    "system_est_tokens", "tool_est_tokens", "message_count", "system_message_count",
                    "system_chars", "system_bytes", "tool_count", "tool_bytes", "image_count",
                    "audio_count", "video_count"):
            legacy.pop(key, None)
        previous = checked_signature(json.dumps(legacy))
        self.assertEqual(signature_changes(current, previous), ())

    def test_system_tool_and_context_changes_are_classified(self):
        first = self.payload()
        system_changed = self.payload(system=("new role prompt", "stable contract"))
        self.assertEqual(signature_changes(system_changed, first), ("system_prompt_change",))

        first_tools = self.payload(tools=({"name": "lookup", "parameters": {}},))
        reordered_tools = self.payload(tools=({"name": "other", "parameters": {}},
                                              {"name": "lookup", "parameters": {}}))
        self.assertIn("tool_definition_change", signature_changes(reordered_tools, first_tools))

        many = [{"owner": "memory", "purpose": str(index), "content_class": "reference_data",
                 "text": "x" * 1200} for index in range(4)]
        with_context = self.payload(materials=many)
        without_context = self.payload(materials=[])
        self.assertIn("context_reset", signature_changes(without_context, with_context))

    def test_stable_context_order_change_is_detected(self):
        left = [{"owner": "memory", "purpose": "a", "content_class": "reference_data", "text": "A"},
                {"owner": "memory", "purpose": "b", "content_class": "reference_data", "text": "B"}]
        right = list(reversed(left))
        self.assertIn("context_order_drift", signature_changes(self.payload(materials=right),
                                                                  self.payload(materials=left)))

    def test_history_scan_keeps_cross_batch_baseline_and_bounds_query_rows(self):
        start = date(2026, 1, 1)
        days = [(start + timedelta(days=index)).isoformat() for index in range(31)]
        role_accounts = {day: "account-" + day for day in days}

        def signature(system):
            part = ("b" if system == "b" else "c") * 64
            return json.dumps({"version": 5, "model_hash": "a" * 64, "system_hash": part,
                "system_parts": [part], "tools_hash": "d" * 64, "tool_parts": [],
                "context_sequence_hash": "7" * 64, "context_multiset_hash": "8" * 64,
                "context_hashes": ["e" * 64, "f" * 64], "context_material_count": 2,
                "context_chars": 100, "context_bytes": 120, "context_observed": True,
                "estimates_observed": True, "context_est_tokens": 70, "system_est_tokens": 10,
                "tool_est_tokens": 15, "message_estimates_observed": True,
                "message_est_tokens": 40, "message_chars": 80, "message_bytes": 100,
                "request_estimate_observed": True, "request_est_tokens": 135,
                "context_availability_observed": True, "context_availability_hash": "9" * 64,
                "deferred_material_count": 1, "unavailable_material_count": 2,
                "request_stats_observed": True, "message_count": 4, "system_message_count": 2,
                "system_chars": 20, "system_bytes": 25, "tool_count": 1, "tool_bytes": 30,
                "image_count": 2, "audio_count": 0, "video_count": 0})

        rows = []
        for index, day in enumerate(days):
            rows.append({"account_key": role_accounts[day], "call_id": "call-" + day, "position": 0,
                "input_tokens": 1200, "cached_input_tokens": 300 if index < 30 else 0,
                "finished_at": day + "T12:00:00+00:00", "started_at": None,
                "created_at": None, "kind": "conversation.reply", "origin_key": "private-chat",
                "audience_scope_json": self.scope_json(),
                "provider_json": '{"provider":"primary"}',
                "signature_json": signature("b" if index < 30 else "c")})

        class Runtime:
            def __init__(self):
                self.batch_sizes = []

            def read_all(self, query, account_keys):
                day_accounts = account_keys[:-2]
                self.batch_sizes.append(len(day_accounts))
                selected = set(day_accounts)
                return [row for row in rows if row["account_key"] in selected]

        runtime = Runtime()
        reports = _cache_diagnostic_summary(runtime, role_accounts, set(days), "test-role")
        result = reports["all"]
        last = result["daily"][-1]
        self.assertEqual(runtime.batch_sizes, [30, 1])
        self.assertEqual((last["signature_calls"], last["compared_calls"], last["changed_calls"]), (1, 1, 1))
        self.assertEqual((last["context_stats_calls"], last["context_text_stats_calls"],
                          last["request_stats_calls"], last["context_estimate_calls"],
                          last["system_estimate_calls"], last["tool_estimate_calls"],
                          last["message_estimate_calls"], last["request_estimate_calls"],
                          last["context_est_tokens_total"], last["system_est_tokens_total"],
                          last["tool_est_tokens_total"], last["message_est_tokens_total"],
                          last["request_est_tokens_total"], last["context_availability_calls"],
                          last["deferred_materials_total"], last["unavailable_materials_total"],
                          last["context_materials_total"],
                          last["context_chars_total"], last["context_bytes_total"],
                          last["messages_total"], last["images_total"]),
                         (1, 1, 1, 1, 1, 1, 1, 1, 70, 10, 15, 40, 135, 1, 1, 2, 2, 100, 120, 4, 2))
        self.assertEqual((last["request_profile_calls"], last["profile_context_est_tokens_total"],
                          last["profile_message_est_tokens_total"], last["profile_system_est_tokens_total"],
                          last["profile_tool_est_tokens_total"], last["profile_request_est_tokens_total"]),
                         (1, 70, 40, 10, 15, 135))
        self.assertEqual(result["recent_events"][0]["day"], days[-1])
        event = result["recent_events"][0]
        self.assertEqual(event["before"]["context_materials"], 2)
        self.assertEqual(event["after"]["context_materials"], 2)
        self.assertEqual(event["after"]["messages"], 4)
        self.assertEqual(event["after"]["context_est_tokens"], 70)
        self.assertEqual(event["after"]["message_est_tokens"], 40)
        self.assertEqual(event["after"]["request_est_tokens"], 135)
        self.assertEqual(event["after"]["unavailable_materials"], 2)
        self.assertEqual(event["cache_hit_delta"], -25.0)
        self.assertEqual(last["cache_hit_comparable_changes"], 1)
        self.assertEqual(last["cache_hit_drop_after_change_calls"], 1)
        self.assertEqual(event["after"]["system_est_tokens"], 10)
        self.assertEqual(reports["conversation"], result)
        self.assertEqual(reports["plugin"]["daily"], [])
        self.assertEqual(reports["plugin"]["recent_events"], [])
