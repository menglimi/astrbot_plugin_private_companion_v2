from __future__ import annotations

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import Mock

from astrbot_host.legacy_api import LegacyMigrationWebAPI
from astrbot_host.native_extensions.reality.settings_methods import RealitySettingsMethods
from companion_v2.execution.models import TaskError
from companion_v2.legacy.migration import ConfigIntent, MigrationPlan
from companion_v2.legacy.reality_migration import (
    reality_settings_state_token,
)


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
