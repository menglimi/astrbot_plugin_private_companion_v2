"""Role-wide automatic sleep settings keep private routine settings window-scoped."""

import unittest
from dataclasses import replace
from datetime import timedelta
import json

from companion_v2.configuration.models import ConfigLayer
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.execution.models import digest, stamp
from companion_v2.role_work.life.configuration import GROUP as LIFE_GROUP, OWNER as LIFE_OWNER, target_for
from astrbot_host.management_identity import dashboard_operator
from tests.multi_host_support import multi_config
from tests.multi_life_support import MultiLifeFixture


class RoleSleepConfigurationTests(MultiLifeFixture, unittest.IsolatedAsyncioTestCase):
    def shared_role_config(self):
        config = multi_config()
        # Two native accounts/windows use the same logical Bot and role.
        config["multi_host"]["targets"][1]["bot_id"] = "bot-a"
        config["multi_host"]["personas"] = [mapping for mapping in config["multi_host"]["personas"]
                                               if mapping["bot_id"] == "bot-a"]
        return config

    async def test_automatic_sleep_settings_share_one_execution_plan_but_diary_stays_private(self):
        app = await self.initialize(self.shared_role_config())
        first_enable = await self.enable("first", "role-a", timezone="Europe/London")
        second_enable = await self.enable("second", "role-a", timezone="America/New_York")
        self.assertNotEqual(first_enable["operation_id"], second_enable["operation_id"])

        await self.command("configure", "first", "role-a", key="set-shared-sleep", changes={
            "sleep_enabled": True, "sleep_time": "00:01", "sleep_timezone": "UTC", "sleep_minutes": 45,
            "diary_time": "21:15",
        })
        first = await self.status("first", "role-a")
        second = await self.status("second", "role-a")
        self.assertEqual((first["config"]["sleep_enabled"], first["config"]["sleep_time"],
                          first["config"]["sleep_timezone"], first["config"]["sleep_minutes"]),
                         (True, "00:01", "UTC", 45))
        self.assertEqual((second["config"]["sleep_enabled"], second["config"]["sleep_time"],
                          second["config"]["sleep_timezone"], second["config"]["sleep_minutes"]),
                         (True, "00:01", "UTC", 45))
        self.assertEqual((first["config"]["diary_time"], first["config"]["timezone"]),
                         ("21:15", "Europe/London"))
        self.assertEqual((second["config"]["diary_time"], second["config"]["timezone"]),
                         ("23:50", "America/New_York"))
        self.assertEqual((first["sleep_schedule"]["owner"]["bot_id"],
                          first["sleep_schedule"]["owner"]["role_id"]), ("bot-a", "role-a"))
        self.assertTrue(first["sleep_schedule"]["owner"]["installation_id"].endswith("shared-test"))
        self.assertEqual(first["sleep_schedule"]["next_sleep_at"], second["sleep_schedule"]["next_sleep_at"])
        self.assertEqual(first["sleep_schedule"]["next_wake_at"], second["sleep_schedule"]["next_wake_at"])

        stale = await self.body("configure", "second", "role-a", key="stale-shared-settings",
            changes={"diary_time": "10:10"})
        await self.command("configure", "first", "role-a", key="new-shared-settings",
            changes={"sleep_minutes": 60})
        rejected = await self.request("second", "role-a", data=stale)
        self.assertEqual(rejected["data"]["code"], "configuration_revision_conflict")

    async def test_first_role_write_adopts_this_windows_legacy_sleep_plan_once(self):
        app = await self.initialize(self.shared_role_config())
        owner = app.configuration._owners[LIFE_OWNER]
        fields = tuple(replace(field, layers=(ConfigLayer.WINDOW,))
                       for field in app.configuration.registry.group(LIFE_GROUP))
        for target_id, timezone, sleep_time, minutes in (
            ("first", "Europe/London", "22:10", 510),
            ("second", "America/New_York", "23:20", 420),
        ):
            context = self.context(target_id, "role-a")
            target = target_for(context)
            legacy = SparseConfigurationOwner.read(owner, target, fields)
            SparseConfigurationOwner.write(owner, target, fields,
                changes={LIFE_GROUP + ".timezone": timezone, LIFE_GROUP + ".sleep_enabled": True,
                         LIFE_GROUP + ".sleep_time": sleep_time, LIFE_GROUP + ".sleep_minutes": minutes},
                reset=(), expected_revision=legacy.revision, observed_at=self.clock.now())

        first = await self.status("first", "role-a")
        second = await self.status("second", "role-a")
        self.assertEqual(first["config"]["sleep_timezone"], "Europe/London")
        self.assertEqual(second["config"]["sleep_timezone"], "America/New_York")
        await self.command("configure", "first", "role-a", changes={"diary_enabled": False})
        adopted_first = await self.status("first", "role-a")
        adopted_second = await self.status("second", "role-a")
        self.assertEqual((adopted_first["config"]["sleep_time"], adopted_first["config"]["sleep_timezone"],
                          adopted_first["config"]["sleep_minutes"]), ("22:10", "Europe/London", 510))
        # The second window set its own sleep plan into the window layer, and a window
        # value is only a fallback for the role value when the window has none, so its
        # own plan stands. Its sleep timezone has no window value of its own, so the
        # role's shared one applies — the fallback to this window's timezone only fires
        # when no layer supplies a sleep timezone at all.
        self.assertEqual((adopted_second["config"]["sleep_time"], adopted_second["config"]["sleep_timezone"],
                          adopted_second["config"]["sleep_minutes"]), ("23:20", "Europe/London", 420))
        self.assertEqual(adopted_second["config"]["timezone"], "America/New_York")

    async def test_only_selected_valid_window_starts_shared_automatic_sleep(self):
        app = await self.initialize(self.shared_role_config())
        await self.enable("first", "role-a", sleep_enabled=True, sleep_time="00:01",
                          sleep_timezone="UTC", sleep_minutes=45)
        await self.enable("second", "role-a")
        await self.start()

        first = await self.status("first", "role-a")
        second = await self.status("second", "role-a")
        self.assertNotEqual(first["sleep_schedule"]["executor_is_current"],
                            second["sleep_schedule"]["executor_is_current"])
        self.assertEqual(first["sleep_schedule"]["next_sleep_at"], second["sleep_schedule"]["next_sleep_at"])
        selected = app.life_runtime.sleep_executor(self.routine())
        self.assertIsNotNone(selected)
        selected_target = "first" if selected.context.key == self.context().key else "second"
        selected_status = await self.status(selected_target, "role-a")
        executor = selected_status["sleep_schedule"]["executor_window"]
        self.assertIsNotNone(executor)
        self.assertEqual(executor["account_id"], selected.context.scope.account_id)
        self.assertEqual(executor["native_scope_id"], selected.context.scope.native_scope_id)
        self.assertIn(selected.context.scope.platform, executor["label"])

        app.life_runtime.advance()
        self.clock.advance(timedelta(minutes=2))
        app.life_runtime.advance()
        active = app.role_state.body_clock.active(self.context(), "sleep")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].work.context_key, selected.context.key)
        selected_status = await self.status(selected_target, "role-a")
        self.assertEqual(selected_status["sleep_schedule"]["active_wake_at"], stamp(active[0].work.due_at))

    async def test_legacy_configuration_owner_receipt_replays_after_owner_partition(self):
        app = await self.initialize(self.shared_role_config())
        key = "legacy-life-settings"
        changes = {"diary_enabled": False}
        original_body = await self.body("configure", "first", "role-a", key=key, changes=changes)
        first = self.ok(await self.request("first", "role-a", data=original_body))
        current_id = first["operation_id"]
        operator = dashboard_operator(app.runtime, "admin", at=self.clock.now())
        legacy_id = "life-config-" + digest([operator.subject, key])
        self.assertNotEqual(legacy_id, current_id)

        # Recreate the durable shape written by the pre-partition owner.  The
        # result is copied verbatim, so the compatibility check exercises the
        # real configuration receipt path rather than a special test branch.
        change = app.runtime.read_one("SELECT * FROM configuration_changes WHERE operation_id = ?", (current_id,))
        result = json.loads(change["result_json"])
        result["operation_id"] = legacy_id
        with app.runtime.transaction() as connection:
            connection.execute(
                """INSERT INTO operations(
                    operation_id, owner, installation_id, platform, scope_kind, native_scope_id,
                    bot_id, account_id, conversation_id, session_id, lineage_id, operation_revision,
                    idempotency_key, parameter_hash, state, commit_state, created_at, updated_at)
                   SELECT ?, 'configuration', installation_id, platform, scope_kind, native_scope_id,
                    bot_id, account_id, conversation_id, session_id, ?, operation_revision,
                    ?, parameter_hash, state, commit_state, created_at, updated_at
                   FROM operations WHERE operation_id = ?""",
                (legacy_id, legacy_id, legacy_id, current_id),
            )
            connection.execute(
                """INSERT INTO configuration_changes(
                    operation_id, target_key, group_id, changed, result_json, created_at)
                   SELECT ?, target_key, group_id, changed, ?, created_at
                   FROM configuration_changes WHERE operation_id = ?""",
                (legacy_id, json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")), current_id),
            )

        replay = self.ok(await self.request("first", "role-a", data=original_body))
        self.assertEqual(replay["operation_id"], legacy_id)
        self.assertTrue(replay["replayed"])

    async def test_shared_sleep_plan_reloads_and_recalculates_after_a_role_change(self):
        app = await self.initialize(self.shared_role_config())
        await self.enable("first", "role-a", sleep_enabled=True, sleep_time="00:01",
                          sleep_timezone="UTC", sleep_minutes=45)
        await self.enable("second", "role-a")
        await self.start()
        before = await self.status("first", "role-a")
        original_next = before["sleep_schedule"]["next_sleep_at"]
        original_executor = before["sleep_schedule"]["executor_window"]
        self.assertIsNotNone(original_executor)

        await self.controller.terminate()
        self.controller = self.make_controller(self.shared_role_config())
        self.register()
        loaded = await self.controller.load_existing()
        self.assertTrue(loaded.is_success, loaded.failure)
        app = await self.start()
        restored = await self.status("second", "role-a")
        self.assertEqual(restored["sleep_schedule"]["next_sleep_at"], original_next)
        self.assertEqual(restored["sleep_schedule"]["executor_window"], original_executor)

        changed = await self.command("configure", "second", "role-a", key="move-shared-sleep",
                                    changes={"sleep_time": "00:03", "sleep_minutes": 60})
        self.assertFalse(changed["replayed"])
        first_after = await self.status("first", "role-a")
        second_after = await self.status("second", "role-a")
        self.assertNotEqual(first_after["sleep_schedule"]["next_sleep_at"], original_next)
        self.assertEqual(first_after["sleep_schedule"]["next_sleep_at"], second_after["sleep_schedule"]["next_sleep_at"])
        self.assertEqual(first_after["sleep_schedule"]["duration_minutes"], 60)


if __name__ == "__main__":
    unittest.main()
