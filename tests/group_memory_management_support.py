"""Seed governed collective statements through real host intake and tool receipts."""

import json
from types import SimpleNamespace as NS

from tests.group_host_support import GroupFixture, group_config
from tests.native_adapter_support import completion, final_text
from tests.staging_bootstrap_support import wait_for_batch
from astrbot_host.management_identity import dashboard_operator
from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.execution.models import TaskContext, encode
from companion_v2.memory.group.management import GroupMemoryManagement, GroupMemoryTarget


class GroupMemoryManagementFixture(GroupFixture):
    def setUp(self):
        super().setUp()
        self.sequence = 0
        self.config = group_config()

    @property
    def app(self):
        return self.controller.session.application

    @property
    def memory(self):
        return self.app.messages.group_memory

    async def conversation(self, wording="周六去公园", *, remember=False, sender="201", **options):
        async def model(payload, _):
            if remember and not any(m["role"] == "tool" for m in payload["messages"]):
                return completion(tools=[NS(id="save", type="function", function=NS(
                    name=tool_alias("group.memory.remember"),
                    arguments=encode({"input_handle": "group-input-1", "statement": wording})))])
            return completion(final_text("收到这条群聊发言。"))
        self.native.provider.client.state.behavior = model
        self.sequence += 1
        event = self.group_event(identifier="group-admin-" + str(self.sequence), text=wording, sender=sender, **options)
        result = await self.controller.receive_claimed(event)
        self.assertTrue(result.is_success, result.failure)
        batch = result.unwrap()
        await wait_for_batch(self.controller.session, batch)
        row = self.app.messages.batch(batch)
        self.assertEqual(row["state"], "ready", dict(self.app.flow.row(batch)))
        context = TaskContext.restore(json.loads(row["context_json"]))
        receipt = None
        if remember:
            result = json.loads(self.app.tools._rows(batch)[0]["result_json"])
            self.assertEqual(result["state"], "succeeded", result)
            receipt = result["payload"]
        return context, batch, receipt

    def target(self, context):
        scope = context.scope
        return GroupMemoryTarget(scope.installation_id, scope.platform, scope.bot_id, scope.account_id,
                                 scope.native_scope_id, scope.session_id, context.role_binding.role.subject_id)

    def manager(self, username="admin"):
        return GroupMemoryManagement(self.memory,
            dashboard_operator(self.app.runtime, username, at=self.clock.now()))

    @staticmethod
    def command(item, key="retract", **extras):
        return {"memory_id": item["memory_id"], "expected_revision": item["revision"],
                "view_token": item["view_token"], "operation_key": key, **extras}

    async def restart(self):
        await self.controller.terminate()
        self.controller = self.make_controller(self.config)
        (await self.controller.load_existing()).unwrap()
        (await self.controller.start()).unwrap()
