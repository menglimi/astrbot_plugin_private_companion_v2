"""Regression checks for 6.7.0 settings that share names but not semantics."""

from dataclasses import asdict, replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.private_debounce import quiet_seconds
from companion_v2.conversation.reply_settings import (
    GROUP, ReplyConfigurationOwner, configuration_fields, private_debounce_settings, validate,
    voice_policy, voice_settings,
)
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.storage.runtime import StorageRuntime
from tests.test_management_access import NOW
from companion_v2.conversation.segmentation import SegmentationPolicy
from companion_v2.conversation.voice_reply import VoiceReplyPolicy, eligible
from companion_v2.legacy.configuration_migration import (
    convert_configuration, convert_plugin_configuration, unmapped_configuration_differences,
)
from companion_v2.model_gateway.budget import SOFT_FIELDS


def reply_registry():
    return FieldRegistry(version="legacy-reply-regression", fields=(
        *configuration_fields(SegmentationPolicy(), False, 0), *SOFT_FIELDS))


class LegacyReplyConfigurationTests(unittest.TestCase):
    def test_actual_global_voice_configuration_keeps_independent_settings(self):
        result = convert_plugin_configuration({
            "voice_action_config": {
                "tts_generation_mode": "fast_tag", "tts_conversion_scope": "full",
                "tts_delivery_mode": "voice_and_text", "tts_frequency_control_mode": "global",
                "tts_session_min_interval_seconds": 0.0,
                "tts_private_min_interval_seconds": -1.0, "tts_group_min_interval_seconds": -1.0,
            },
            "auto_voice_config": {"auto_voice_full_conversion_enabled": False,
                                  "auto_voice_cooldown_seconds": 120},
        }, window_kind="private")
        policy = VoiceReplyPolicy(**{key.partition(".")[2]: value for key, value in result.changes.items()})
        self.assertEqual((policy.generation_mode, policy.conversion_scope, policy.delivery_mode),
                         ("model_tag", "full", "voice_and_text"))
        self.assertEqual((policy.cooldown("private"), policy.cooldown("group")), (0, 0))
        self.assertEqual(result.differences, ())

    def test_generation_aliases_and_postprocess_difference(self):
        for alias in ("fast_tag", "direct", "hybrid", "tag", "tags", "fast"):
            with self.subTest(alias=alias):
                result = convert_plugin_configuration({"voice_action_config": {"tts_generation_mode": alias}})
                self.assertEqual(result.changes["voice_reply.generation_mode"], "model_tag")
                self.assertEqual(result.differences, ())
        result = convert_plugin_configuration({"voice_action_config": {"tts_generation_mode": "postprocess"}})
        self.assertEqual(result.changes["voice_reply.generation_mode"], "model_tag")
        self.assertEqual([item.kind for item in result.differences], ["partial_mapping"])

    def test_scope_legacy_alias_does_not_change_delivery(self):
        result = convert_plugin_configuration({
            "voice_action_config": {"tts_conversion_scope": "", "tts_delivery_mode": "voice_only"},
            "auto_voice_config": {"auto_voice_full_conversion_enabled": False},
        })
        self.assertEqual(result.changes["voice_reply.conversion_scope"], "partial")
        self.assertEqual(result.changes["voice_reply.delivery_mode"], "voice_only")
        self.assertEqual(result.differences, ())

    def test_global_cooldown_retains_separate_private_and_group_overrides(self):
        result = convert_plugin_configuration({"voice_action_config": {
            "tts_frequency_control_mode": "global", "tts_session_min_interval_seconds": 90,
            "tts_private_min_interval_seconds": 0, "tts_group_min_interval_seconds": 180,
        }})
        policy = VoiceReplyPolicy(**{key.partition(".")[2]: value for key, value in result.changes.items()})
        self.assertEqual((policy.cooldown("private"), policy.cooldown("group")), (0, 180))
        self.assertEqual(replace(policy, group_cooldown_seconds=-1).cooldown("group"), 90)

    def test_legacy_frequency_uses_only_its_active_cooldown_path(self):
        result = convert_plugin_configuration({
            "voice_action_config": {"tts_frequency_control_mode": "legacy",
                "tts_session_min_interval_seconds": 90, "tts_group_min_interval_seconds": 300},
            "auto_voice_config": {"auto_voice_cooldown_seconds": 120},
        })
        self.assertEqual(result.changes, {"voice_reply.cooldown_seconds": 120})
        self.assertIn("partial_mapping", {item.kind for item in result.differences})

    def test_debounce_model_and_platform_dedup_never_override_reply_settings(self):
        source = {"basic_config": {"LLM_PROVIDER_ID": "primary"},
                  "message_debounce_config": {"SMART_MESSAGE_DEBOUNCE_PROVIDER_ID": "small-model",
                                              "text_message_debounce_seconds": 0},
                  "proactive_reach_config": {"inbound_message_debounce_seconds": 7}}
        plugin = convert_plugin_configuration(source)
        self.assertEqual(plugin.changes, {"model.provider_id": "primary"})
        self.assertEqual(plugin.differences, ())
        audit = {item.source_key: item.kind for item in unmapped_configuration_differences(source)}
        self.assertEqual(audit["message_debounce_config.SMART_MESSAGE_DEBOUNCE_PROVIDER_ID"], "manual_required")
        result = convert_configuration(source, registry=reply_registry(), window_kind="private")
        values = {key.rsplit(".", 1)[-1]: value for key, value in result.changes.items()}
        self.assertFalse(private_debounce_settings(values).enabled)

    def test_fractional_fixed_wait_and_total_deadline_reach_the_core_policy(self):
        result = convert_configuration({"message_debounce_config": {
            "enable_message_debounce": True, "text_message_debounce_seconds": 1.75,
            "text_message_debounce_max_wait_seconds": 12.0,
            "semantic_message_debounce_seconds": 8.0,
        }}, registry=reply_registry(), window_kind="private")
        values = {key.rsplit(".", 1)[-1]: value for key, value in result.changes.items()}
        policy = private_debounce_settings(values)
        self.assertEqual((policy.min_seconds, policy.max_seconds, policy.total_seconds), (1.75, 1.75, 12))
        self.assertEqual(quiet_seconds("短句", policy), 1.75)
        self.assertEqual(quiet_seconds("足够完整的正文。" * 20, policy), 1.75)

    def test_disabled_master_and_legacy_wait_alias_follow_old_precedence(self):
        for source, enabled, wait in (
            ({"enable_message_debounce": False, "enable_semantic_message_debounce": True,
              "text_message_debounce_seconds": 8}, False, None),
            ({"enable_semantic_message_debounce": True, "semantic_message_debounce_seconds": 8}, True, 8),
            ({"enable_message_debounce": True, "text_message_debounce_seconds": 0,
              "semantic_message_debounce_seconds": 8}, False, None),
        ):
            with self.subTest(source=source):
                result = convert_configuration({"message_debounce_config": source},
                    registry=reply_registry(), window_kind="private")
                values = {key.rsplit(".", 1)[-1]: value for key, value in result.changes.items()}
                policy = private_debounce_settings(values)
                self.assertEqual(policy.enabled, enabled)
                if wait is not None:
                    self.assertEqual(policy.min_seconds, wait)

    def test_soft_budget_primary_beats_empty_and_outdated_compatibility_values(self):
        for alias in ("", "640000"):
            result = convert_configuration({
                "basic_config": {"enable_daily_token_soft_limit": False, "daily_token_soft_limit": 2000000},
                "legacy_compat_config": {"enable_maintenance_token_saver": True,
                                         "maintenance_token_soft_limit": alias},
            }, registry=reply_registry())
            self.assertEqual(result.changes, {"model.budget.enable_daily_token_soft_limit": False,
                                              "model.budget.daily_token_soft_limit": 2000000})
            self.assertEqual(result.differences, ())
        fallback = convert_configuration({"legacy_compat_config": {"maintenance_token_soft_limit": "640000"}},
                                         registry=reply_registry())
        self.assertEqual(fallback.changes, {"model.budget.daily_token_soft_limit": 640000})

    def test_group_waiting_is_reported_without_writing_private_settings(self):
        result = convert_configuration({"message_debounce_config": {
            "enable_message_debounce": True, "text_message_debounce_seconds": 8,
        }}, registry=reply_registry(), window_kind="group")
        self.assertFalse(any("private_debounce" in key for key in result.changes))
        self.assertEqual([item.kind for item in result.differences], ["partial_mapping"])
        self.assertIn("群聊", result.differences[0].summary)

    def test_sub_full_voice_probability_can_still_trigger_ordinary_chat(self):
        result = convert_plugin_configuration({"voice_action_config": {"tts_frequency_control_mode": "global",
            "tts_trigger_probability": 25}, "auto_voice_config": {"auto_voice_enabled": False}})
        policy = VoiceReplyPolicy(**{key.partition(".")[2]: value for key, value in result.changes.items()})
        outcomes = {eligible(policy, input_text="普通聊天", kind="private", batch_id=str(i)) for i in range(100)}
        self.assertEqual(outcomes, {True, False})


class ReplyUpgradeCompatibilityTests(unittest.TestCase):
    def test_old_voice_snapshot_uses_the_new_scope_default(self):
        values = {**asdict(SegmentationPolicy()), "streaming": False, "part_gap_ms": 0,
                  **voice_settings(VoiceReplyPolicy())}
        values.pop("voice_conversion_scope")
        validate(values)
        self.assertEqual(voice_policy(values).conversion_scope, "full")

    def test_role_and_window_voice_preferences_survive_reopen_and_reset(self):
        policy = VoiceReplyPolicy(cooldown_seconds=90, private_cooldown_seconds=0,
                                  group_cooldown_seconds=180)
        fields = configuration_fields(SegmentationPolicy(), False, 0, policy)
        role = SubjectRef("reply-upgrade", SubjectKind.BOT, "role-a")
        role_target = ConfigTarget("reply-upgrade", ConfigLayer.ROLE, role, bot_id="bot-a")
        windows = [ConfigTarget("reply-upgrade", ConfigLayer.WINDOW, role,
            ScopeRef("reply-upgrade", "qq-main", kind, "200", "bot-a", "100",
                     "conversation-a", "session-a"))
            for kind in (ScopeKind.PRIVATE, ScopeKind.GROUP)]
        cooldown, scope = GROUP + ".voice_cooldown_seconds", GROUP + ".voice_conversion_scope"
        with TemporaryDirectory(prefix="companion-reply-upgrade-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary), installation_id="reply-upgrade")
            try:
                owner = ReplyConfigurationOwner(runtime, policy)
                self.assertEqual([owner.read(target, fields).fields[cooldown].value
                                  for target in windows], [0, 180])
                owner.write(role_target, fields, changes={cooldown: 25, scope: "partial"}, reset=(),
                    expected_revision=0, observed_at=NOW)
                private = owner.read(windows[0], fields)
                owner.write(windows[0], fields, changes={cooldown: 0}, reset=(),
                    expected_revision=private.revision, observed_at=NOW)
                self.assertEqual([owner.read(target, fields).fields[cooldown].value
                                  for target in windows], [0, 25])
            finally:
                runtime.close()
            runtime = StorageRuntime.open(data_root=Path(temporary), installation_id="reply-upgrade")
            try:
                owner = ReplyConfigurationOwner(runtime, policy)
                for target in windows:
                    self.assertEqual(owner.read(target, fields).fields[scope].value, "partial")
                private = owner.read(windows[0], fields)
                self.assertEqual(private.fields[cooldown].value, 0)
                owner.write(windows[0], fields, changes={}, reset=(cooldown,),
                    expected_revision=private.revision, observed_at=NOW)
                self.assertEqual(owner.read(windows[0], fields).fields[cooldown].value, 25)
                self.assertEqual(owner.read(windows[1], fields).fields[cooldown].value, 25)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
