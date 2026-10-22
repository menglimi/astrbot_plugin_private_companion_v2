from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import Mock

from astrbot_host.legacy_api import LegacyMigrationWebAPI
from astrbot_host.native_extensions.reality.settings_methods import RealitySettingsMethods
from companion_v2.execution.models import TaskError
from companion_v2.legacy.migration import ConfigIntent, MigrationPlan
from companion_v2.legacy.reality_migration import (
    convert_reality_configuration,
    reality_settings_state_token,
)
from companion_v2.legacy.native_extension_configuration import _leaves


def base_config():
    return {
        "camera": {
            "enabled": False,
            "min_interval_seconds": 60,
            "capture_timeout_seconds": 5,
            "analysis_timeout_seconds": 25,
        },
        "audio": {"default_playback_volume": 35},
        "timezone": "Asia/Shanghai",
    }


class SavingConfig(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.save_count = 0

    def save_config(self):
        self.save_count += 1
        return True


class RealityService(RealitySettingsMethods):
    def __init__(self, config=None):
        self.config = SavingConfig(config or base_config())
        self._sync_runtime_config()


class RealitySettingsApplyTests(TestCase):
    def test_portable_timeouts_are_consumed_without_starting_private_services(self):
        runtime = RealityService()
        changes = {"home.request_timeout_seconds": 12, "health.ttl_seconds": 7200,
                   "mobile.location_ttl_seconds": 1800, "camera.proactive_max_daily": 2,
                   "vision_provider_id": "existing-vision"}
        result = runtime._apply_legacy_migrated_settings(
            changes, reality_settings_state_token(runtime.config, changes), tuple(changes))
        self.assertTrue(result["saved"])
        self.assertEqual(runtime.home_request_timeout_seconds, 12)
        self.assertEqual(runtime.health_ttl_seconds, 7200)
        self.assertEqual(runtime._cfg_int("mobile.location_ttl_seconds", 900), 1800)
        self.assertEqual(runtime.reality_touch_camera_proactive_max_daily, 2)
        self.assertEqual(runtime.plugin_vision_provider_id, "existing-vision")
        self.assertFalse(runtime.home_enabled)
        self.assertFalse(runtime.enable_reality_touch_camera_proactive_curiosity)
        self.assertNotIn("enabled", runtime.config["mobile"])

    def test_flat_and_nested_values_stay_in_sync_and_failed_saves_restore_both(self):
        config = base_config()
        config["camera.min_interval_seconds"] = 60
        runtime = RealityService(config)
        changes = {"camera.min_interval_seconds": 45}
        runtime._apply_legacy_migrated_settings(
            changes, reality_settings_state_token(runtime.config, changes), tuple(changes))
        self.assertEqual(runtime.config["camera.min_interval_seconds"], 45)
        self.assertEqual(runtime.config["camera"]["min_interval_seconds"], 45)
        self.assertEqual(runtime.reality_touch_camera_min_interval_seconds, 45)
        before = deepcopy(dict(runtime.config))
        runtime.config.save_config = Mock(return_value=False)
        with self.assertRaises(RuntimeError):
            changes = {"camera.min_interval_seconds": 50, "mobile.location_ttl_seconds": 1800}
            runtime._apply_legacy_migrated_settings(
                changes, reality_settings_state_token(runtime.config, changes), tuple(changes))
        self.assertEqual(dict(runtime.config), before)
        self.assertEqual(runtime.reality_touch_camera_min_interval_seconds, 45)

    def test_service_persists_only_whitelisted_settings(self):
        runtime = RealityService()
        changes = {"camera.enabled": True, "audio.default_playback_volume": 50}
        token = reality_settings_state_token(runtime.config, changes)

        result = runtime._apply_legacy_migrated_settings(changes, token, tuple(changes))

        self.assertTrue(result["saved"])
        self.assertEqual(runtime.config["camera"]["enabled"], True)
        self.assertEqual(runtime.config["audio"]["default_playback_volume"], 50)
        self.assertEqual(runtime.config.save_count, 1)

    def test_service_rejects_stale_state_and_nonportable_fields(self):
        runtime = RealityService()
        changes = {"camera.enabled": True}
        token = reality_settings_state_token(runtime.config, changes)
        runtime.config["camera"]["enabled"] = True

        stale = runtime._apply_legacy_migrated_settings(changes, token, tuple(changes))
        forbidden = runtime._apply_legacy_migrated_settings(
            {"camera.index": 700}, token, ("camera.index",),
        )

        self.assertEqual(stale["reason"], "reality_config_changed")
        self.assertEqual(forbidden["reason"], "reality_migration_field_not_allowed")
        self.assertEqual(runtime.config.save_count, 0)


class LegacyRealityIntentTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = SimpleNamespace(config=base_config())
        self.runtime._apply_legacy_migrated_settings = Mock(return_value={"saved": True})
        registry = SimpleNamespace(service=Mock(return_value=self.runtime))
        self.api = LegacyMigrationWebAPI(SimpleNamespace(native_extensions=registry))

    def test_reality_scope_filters_unrelated_intents(self):
        reality = ConfigIntent("reality.settings", "reality", {"camera.enabled": True},
                               "reality.configuration", target_kind="reality_config")
        private = ConfigIntent("role.state", "role.state", {"field": True},
                               "private.host_configuration")
        plan = MigrationPlan("v1", intents=(reality, private))

        scoped = self.api._configuration_scoped_plan(plan, "reality")

        self.assertEqual([item.source_id for item in scoped.intents], ["reality.configuration"])

    async def test_host_intent_preserves_same_values_and_checks_preview_token(self):
        intent = ConfigIntent(
            "reality.settings",
            "reality",
            {"camera.enabled": True, "camera.min_interval_seconds": 60,
             "audio.default_playback_volume": 35},
            "reality.configuration",
            target_kind="reality_config",
        )
        differences, status, tokens = [], [], {}

        prepared = self.api._prepare_reality_config_intent(intent, differences, status, tokens)

        self.assertEqual(prepared.changes, {"camera.enabled": True})
        self.assertEqual(status[0]["available"], True)
        self.assertEqual(tokens["reality_config_fields"], sorted(intent.changes))
        written = await self.api._apply_reality_config_intent(
            prepared, tokens["reality_config_state"], tokens["reality_config_fields"],
        )
        self.assertEqual(written, ["reality.camera.enabled"])
        self.runtime._apply_legacy_migrated_settings.assert_called_once_with(
            {"camera.enabled": True}, tokens["reality_config_state"],
            tuple(tokens["reality_config_fields"]),
        )

    async def test_host_rejects_settings_changed_after_preview(self):
        intent = ConfigIntent("reality.settings", "reality", {"camera.enabled": True},
                              "reality.configuration", target_kind="reality_config")
        tokens = {}
        prepared = self.api._prepare_reality_config_intent(intent, [], [], tokens)
        self.runtime.config["camera"]["enabled"] = True

        with self.assertRaises(TaskError):
            await self.api._apply_reality_config_intent(
                prepared, tokens["reality_config_state"], tokens["reality_config_fields"],
            )
        self.runtime._apply_legacy_migrated_settings.assert_not_called()

    async def test_only_compatible_vision_providers_are_reused(self):
        intent = ConfigIntent("reality.settings", "reality",
            {"vision_provider_id": "old-vision", "home.request_timeout_seconds": 12},
            "reality.configuration", target_kind="reality_config")
        provider = SimpleNamespace(text_chat=Mock(), provider_config={"modalities": ["image", "text"]})
        self.api.controller.context = SimpleNamespace(get_provider_by_id=lambda _: provider)
        tokens = {}
        prepared = self.api._prepare_reality_config_intent(intent, [], [], tokens)
        self.assertEqual(prepared.changes, intent.changes)
        await self.api._apply_reality_config_intent(
            prepared, tokens["reality_config_state"], tokens["reality_config_fields"])
        provider.text_chat.assert_not_called()
        self.runtime._apply_legacy_migrated_settings.reset_mock()
        provider.provider_config = {"modalities": ["text"]}
        with self.assertRaises(TaskError):
            await self.api._apply_reality_config_intent(
                prepared, tokens["reality_config_state"], tokens["reality_config_fields"])
        self.runtime._apply_legacy_migrated_settings.assert_not_called()
        differences = []
        remaining = self.api._prepare_reality_config_intent(intent, differences, [], {})
        self.assertEqual(remaining.changes, {"home.request_timeout_seconds": 12})
        self.assertEqual(differences[0]["kind"], "provider_reselection_required")


class RealityConfigurationCoverageTests(TestCase):
    def test_every_nonportable_source_is_accounted_for_without_private_values(self):
        source = {"mobile": {"enabled": True, "pairing_token": "secret-mobile-token",
                             "location_ttl_seconds": 1800, "allowed_user_id": "private-user"},
                  "home": {"access_token": "secret-home-token", "request_timeout_seconds": 10},
                  "mihome": {"enabled": True, "control_tool": {"admin_only": True}},
                  "camera": {"index": 700, "proactive_curiosity_enabled": True,
                             "proactive_max_daily": 2}}
        result = convert_reality_configuration(source)
        noted = {item["field"].removeprefix("reality.") for item in result.differences}
        self.assertEqual(set(result.changes) | noted, {path for path, _ in _leaves(source)})
        self.assertFalse(set(result.changes) & {"mobile.enabled", "mihome.enabled", "camera.index"})
        for value in ("secret-mobile-token", "secret-home-token", "private-user"):
            self.assertNotIn(value, json.dumps(result.differences))

    def test_invalid_values_are_reported_without_silent_clamping(self):
        result = convert_reality_configuration({"camera": {"enabled": [], "proactive_max_daily": 999},
            "mobile": {"session_ttl_hours": True}, "timezone": 123, "vision_provider_id": 4})
        self.assertFalse(result.changes)
        self.assertEqual(len(result.differences), 5)
        self.assertEqual({item["kind"] for item in result.differences}, {"invalid_value"})
