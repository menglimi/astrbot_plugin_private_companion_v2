"""Model page management uses the registered V2 router and scoped configuration."""

import unittest
import json
from dataclasses import asdict
from datetime import timedelta

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.execution.models import digest
from companion_v2.model_gateway.management import ModelManagement
from tests.test_host_application import HostFixture


class ModelManagementTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.host_instance = await self.start()
        self.app = self.host_instance.application
        batch = self.host_instance.receive(self.event("model-settings-context")).unwrap()
        self.advance(self.app)
        await self.done(self.app, batch)
        self.role_context = self.context(self.app, batch)
        self.manager = ModelManagement(self.app, self.role_context)

    def request(self, status, *, changes=None, reset=None, key="model-settings"):
        task = status["tasks"][0]
        return {"kind": task["kind"], "operation_key": key, "edit_token": task["edit_token"],
                "changes": changes or {}, "reset": reset or []}

    async def test_status_projects_the_provider_model_name(self):
        """管理面列出 Provider 时必须带上模型名。

        只列 id 的话，同一个 AstrBot 上挂两个同类型 Provider（一个便宜一个强）
        在页面上是两行一样的字，选错只能靠试——V1 面板一直在显示 `id · model`，
        这个字段就是那次对齐补的。

        夹具里的本地 provider 没有模型概念，所以这里验的是**默认降级为空串**
        而不是编一个名字出来（空串合法，非空时才做不透明性校验）。
        """
        before = self.manager.status(self.core).unwrap()
        self.assertEqual(before["providers"][0]["model"], "")

    async def test_storage_check_reports_integrity_without_mutating_runtime(self):
        page_count = self.app.runtime.read_one("PRAGMA page_count", ())[0]
        result = self.manager.check_storage(self.core).unwrap()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["integrity"], ["ok"])
        self.assertEqual(result["foreign_key_issues"], 0)
        self.assertEqual(self.app.runtime.read_one("PRAGMA page_count", ())[0], page_count)

    async def test_maintenance_aggregates_cache_receipts_and_handles_non_object_provider_json(self):
        call = self.app.runtime.read_one("SELECT call_id FROM model_calls LIMIT 1", ())
        self.assertIsNotNone(call)
        with self.app.runtime.transaction() as connection:
            connection.execute("""UPDATE model_calls SET actual_tokens = 120, input_tokens = 100,
                cached_input_tokens = 40, cache_creation_tokens = 10, output_tokens = 20, provider_json = ?
                WHERE call_id = ?""", ("[]", call["call_id"]))

        first = self.manager.maintenance(self.core).unwrap()
        self.assertEqual(first["ledger_scope"], "current_role")
        self.assertEqual(first["runtime"]["identity_scope"], {
            "dashboard_operator": "verified", "role_access": "verified", "token_ledger": "current_role"})
        trace = first["runtime"]["debounce_trace"]
        self.assertTrue(trace)
        self.assertGreaterEqual(trace[0]["input_count"], 1)
        self.assertIsInstance(trace[0]["quiet_window_ms"], int)
        self.assertFalse({"batch_id", "route_key", "merge_key", "context"} & set(trace[0]))
        self.assertEqual(first["summary"]["tokens"], 120)
        self.assertEqual(first["summary"]["cache_input_tokens"], 100)
        self.assertEqual(first["summary"]["cache_hit_rate"], 40)
        self.assertEqual(first["summary"]["cache_coverage_pct"], 100)
        self.assertEqual(first["recent"][0]["provider"], "")
        self.assertEqual(first["recent"][0]["cache_hit_rate"], 40)
        self.assertEqual(first["totals"]["tokens"], 120)
        self.assertEqual(first["totals"]["calls"], 1)
        self.assertEqual(first["windows"]["7d"]["totals"]["tokens"], 120)
        self.assertEqual(first["windows"]["30d"]["totals"]["calls"], 1)
        self.assertEqual(first["by_provider"][0]["key"], "未知 Provider")
        self.assertEqual(first["windows"]["7d"]["providers"][0]["key"], "未知 Provider")
        self.assertEqual(first["history"][-1]["tokens"], 120)
        self.assertEqual(first["history"][-1]["providers"][0]["key"], "未知 Provider")
        self.assertEqual(sum(row["tokens"] for row in first["hourly"]), 120)

        with self.app.runtime.transaction() as connection:
            connection.execute("UPDATE model_calls SET provider_json = ? WHERE call_id = ?",
                               (json.dumps({"provider": "primary"}), call["call_id"]))
        ranked = self.manager.maintenance(self.core).unwrap()
        self.assertEqual(ranked["by_provider"][0]["key"], "primary")
        self.assertEqual(ranked["by_task"][0]["key"], "conversation.reply")
        self.assertEqual(ranked["history"][-1]["tasks"][0]["key"], "conversation.reply")

        with self.app.runtime.transaction() as connection:
            connection.execute("UPDATE model_calls SET input_tokens = NULL WHERE call_id = ?", (call["call_id"],))
        incomplete = self.manager.maintenance(self.core).unwrap()
        self.assertIsNone(incomplete["summary"]["cache_hit_rate"])
        self.assertEqual(incomplete["summary"]["cache_creation_tokens"], 10)
        self.assertIsNone(incomplete["recent"][0]["cache_hit_rate"])

    async def test_maintenance_windows_keep_old_role_calls_in_30d_but_not_7d(self):
        call = self.app.runtime.read_one("SELECT call_id FROM model_calls LIMIT 1", ())
        self.assertIsNotNone(call)
        today = self.app.now().date()
        old_day = today - timedelta(days=10)
        scope = self.role_context.scope
        role_address = [scope.installation_id, scope.bot_id, asdict(self.role_context.role_binding.role)]
        current_key = digest(["role", role_address, today.isoformat()])
        old_key = digest(["role", role_address, old_day.isoformat()])
        with self.app.runtime.transaction() as connection:
            account = connection.execute("SELECT * FROM model_budget_accounts WHERE account_key = ?",
                                         (current_key,)).fetchone()
            self.assertIsNotNone(account)
            connection.execute("INSERT INTO model_budget_accounts VALUES (?, ?, ?, ?, 0, 0, ?, ?)",
                (old_key, account["policy_hash"], account["token_limit"], account["cost_limit"],
                 account["spent_tokens"], account["spent_cost"]))
            connection.execute("UPDATE model_calls SET started_at = ?, finished_at = ? WHERE call_id = ?",
                (old_day.isoformat() + "T12:00:00+00:00", old_day.isoformat() + "T12:00:01+00:00", call["call_id"]))
            connection.execute("UPDATE model_call_accounts SET account_key = ? WHERE call_id = ? AND account_key = ?",
                (old_key, call["call_id"], current_key))

        data = self.manager.maintenance(self.core).unwrap()
        self.assertEqual(data["totals"]["calls"], 1)
        self.assertEqual(data["windows"]["7d"]["totals"]["calls"], 0)
        self.assertEqual(data["windows"]["30d"]["totals"]["calls"], 1)
        self.assertEqual(data["history"][0]["key"], old_day.isoformat())

    async def test_save_replay_inherit_and_upstream_source(self):
        before = self.manager.status(self.core).unwrap()
        task = before["tasks"][0]
        self.assertEqual(task["fields"]["prompt"]["inherited_source"], "default")
        self.assertEqual([provider["id"] for provider in before["providers"]], ["primary"])

        role = ConfigTarget(self.role_context.scope.installation_id, ConfigLayer.ROLE,
                            self.role_context.role_binding.role, bot_id=self.role_context.scope.bot_id)
        parent = self.app.configuration.read(self.core, target=role, group_id="model.conversation.reply",
                                             observed_at=self.app.now()).unwrap()
        self.app.configuration.patch(self.core, target=role, group_id=parent.group_id,
            operation=self.operation(role.authorization_scope), expected_edit_token=parent.edit_token,
            changes={"model.conversation.reply.prompt": "角色级任务补充"}, observed_at=self.app.now()).unwrap()
        inherited = self.manager.status(self.core).unwrap()
        field = inherited["tasks"][0]["fields"]["prompt"]
        self.assertEqual((field["value"], field["source"], field["inherited_source"]),
                         ("角色级任务补充", "role", "role"))

        payload = self.request(inherited, changes={"prompt": ""}, key="clear-prompt")
        saved = self.manager.configure(self.core, payload).unwrap()
        self.assertFalse(saved["replayed"])
        self.assertEqual(saved["task"]["fields"]["prompt"]["value"], "")
        self.assertEqual(saved["task"]["fields"]["prompt"]["inherited_source"], "role")
        replay = self.manager.configure(self.core, payload).unwrap()
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["operation_id"], saved["operation_id"])

        current = self.manager.status(self.core).unwrap()
        restored = self.manager.configure(self.core,
            self.request(current, reset=["prompt"], key="inherit-prompt")).unwrap()["task"]["fields"]["prompt"]
        self.assertEqual((restored["value"], restored["source"], restored["explicit"]),
                         ("角色级任务补充", "role", False))

    async def test_invalid_patch_stale_version_and_non_core_access(self):
        status = self.manager.status(self.core).unwrap()
        for invalid in (None, {}, {"kind": "conversation.reply"},
                        self.request(status, changes={"provider": "primary"}, reset=["provider"]),
                        self.request(status, changes={"provider": "unregistered"})):
            result = self.manager.configure(self.core, invalid)
            self.assertIsNotNone(result.failure)
        self.assertEqual(self.manager.status(self.important).failure.code, "core_access_required")
        self.assertEqual(self.manager.configure(self.important,
            self.request(status, changes={"prompt": "private"})).failure.code, "core_access_required")
        saved = self.manager.configure(self.core, self.request(status, changes={"prompt": "new"})).unwrap()
        self.assertFalse(saved["replayed"])
        stale = self.manager.configure(self.core,
            self.request(status, changes={"prompt": "stale"}, key="stale-model-settings"))
        self.assertEqual(stale.failure.code, "configuration_revision_conflict")

    async def test_replacement_rules_save_inherit_and_reject_unsupported_targets(self):
        before = self.manager.status(self.core).unwrap()
        self.assertFalse(before["providers"][0]["supports_model_override"])
        rules = json.dumps([{"id": "ordinary", "provider_id": "primary", "keywords": ["private"]}])
        saved = self.manager.configure(self.core, self.request(before,
            changes={"replacement_rules": rules}, key="save-routes")).unwrap()
        field = saved["task"]["fields"]["replacement_rules"]
        self.assertEqual((field["value"], field["source"], field["explicit"]), (rules, "window", True))
        for value in (
            '[{"provider_id":"missing","keywords":["private"]}]',
            '[{"provider_id":"primary","model":"creative","keywords":["private"]}]',
            '[{"provider_id":"primary","keywords":7,"time_window":{"timezone":"Asia/Shanghai","start":"07:00","end":"09:00"}}]',
        ):
            with self.subTest(value=value):
                current = self.manager.status(self.core).unwrap()
                result = self.manager.configure(self.core, self.request(current,
                    changes={"replacement_rules": value}, key="invalid-" + str(len(value))))
                self.assertEqual(result.failure.code, "model_route_invalid")
        current = self.manager.status(self.core).unwrap()
        inherited = self.manager.configure(self.core, self.request(current,
            reset=["replacement_rules"], key="inherit-routes")).unwrap()
        field = inherited["task"]["fields"]["replacement_rules"]
        self.assertEqual((field["value"], field["source"], field["explicit"]), ("[]", "default", False))
