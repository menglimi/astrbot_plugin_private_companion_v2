"""Host prompt integration: one role sees its own private/group windows."""

import json
import unittest

from companion_v2.execution.models import TaskContext
from tests.group_host_support import GroupFixture
from tests.staging_bootstrap_support import wait_for_batch


class RoleAwarenessHostTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await self.start_host()

    @property
    def app(self):
        return self.controller.session.application

    async def prepare(self, event):
        prepared = (await self.controller.prepare_core_reply(event)).unwrap()
        future = prepared.get("native_source_future")
        if future is not None:
            await future
        return prepared

    async def accepted_group(self, identifier, text):
        result = await self.controller.receive_claimed(
            self.group_event(identifier=identifier, sender="200", text=text))
        batch = result.unwrap()
        await wait_for_batch(self.controller.session, batch)
        context = TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))
        return context, batch

    def materials(self, context, batch):
        request = self.app.messages._request(self.app.messages.batch(batch), context, self.clock.now())
        return request.context.materials

    async def test_private_prompt_sees_same_persons_group_activity(self):
        group = await self.prepare(self.group_event(identifier="aware-group", sender="200", text="明天谁有空"))
        self.assertIn("当前是群聊", group["prompt_instruction"])
        private = await self.prepare(self.event(target="first", identifier="aware-private", text="我刚在群里问了"))
        self.assertIn("【跨窗口在场】", private["prompt_instruction"])
        self.assertIn("明天谁有空", private["prompt_instruction"])

    async def test_group_prompt_only_gets_the_private_contact_boolean(self):
        await self.prepare(self.event(target="first", identifier="aware-private-seed", text="私聊里的秘密"))
        group = await self.prepare(self.group_event(identifier="aware-group-after", sender="200", text="在群里说话"))
        self.assertIn("【跨窗口在场】", group["prompt_instruction"])
        self.assertIn("private_contact", group["prompt_instruction"])
        self.assertNotIn("私聊里的秘密", group["prompt_instruction"])

    async def test_private_prompt_sees_a_bounded_peer_count(self):
        await self.prepare(self.group_event(identifier="aware-peer-first", sender="201", text="我先说一句"))
        await self.prepare(self.group_event(identifier="aware-peer-second", sender="200", text="我也来"))
        private = await self.prepare(self.event(target="first", identifier="aware-peer-private",
                                                text="我刚在群里接话"))
        self.assertIn("【跨窗口在场】", private["prompt_instruction"])
        self.assertIn('"peers":1', private["prompt_instruction"])

    async def test_v2_batches_seal_the_same_audience_filtered_view(self):
        group_context, group_batch = await self.accepted_group("aware-v2-group", "明天谁有空")
        private_context, private_batch = await self.accepted("first", "aware-v2-private", "私聊里的秘密")
        private_material = next(item for item in self.materials(private_context, private_batch)
                                if item.purpose == "cross_window_awareness")
        payload = json.loads(private_material.payload)
        self.assertEqual(payload["recent_group_activity"][0]["topic"], "明天谁有空")

        group_context, group_batch = await self.accepted_group("aware-v2-group-after", "在群里说话")
        group_material = next(item for item in self.materials(group_context, group_batch)
                              if item.purpose == "cross_window_awareness")
        self.assertEqual(json.loads(group_material.payload), {"private_contact": True})
        self.assertNotIn("私聊里的秘密", group_material.payload)
