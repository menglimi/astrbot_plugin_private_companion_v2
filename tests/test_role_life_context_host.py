"""Full host intake consumes real life-worker results with local model/sender ports."""

import asyncio
import json
import unittest

from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.role_work.journal.models import JournalDraft
from companion_v2.identity_policy.models import AuthorizationTier
from tests.test_management_access import SCOPE
from tests.test_role_life_runtime import LifeFixture
from tests.test_role_tool_loop import answered


def payloads(request):
    return [json.loads(m.payload) for m in request.context.materials
            if m.owner == "role.life" and m.purpose != "role_life_context"]


class LifeContextHostTests(LifeFixture, unittest.IsolatedAsyncioTestCase):
    async def chat(self, identifier, *, host=None):
        host = host or self.host_instance
        before = len(self.called)
        batch = host.receive(self.event(identifier)).unwrap()
        self.advance(host.application)
        result = await self.done(host.application, batch)
        self.assertEqual(result["state"], "complete", dict(result))
        replies = [e.original for e in self.called[before:] if e.original.output_format == "conversation"]
        self.assertEqual(len(replies), 1)
        return replies[0]

    async def model_with_chat(self, envelope):
        if envelope.original.output_format == "conversation":
            return answered("我刚才想到了一个问题。")
        return await self.model(envelope)

    async def test_read_sleep_wake_then_chat_uses_saved_experiences_and_current_edits(self):
        await self.setup_life()
        self.model_behavior = self.model_with_chat
        book = (await self.add_text())[0]
        (await self.command("read", book)).unwrap()
        await self.settle()
        (await self.command("diary")).unwrap()
        (await self.command("sleep", minutes=1)).unwrap()
        first = await self.chat("during-sleep")
        by_kind = {p["kind"]: p for p in payloads(first)}
        self.assertEqual(by_kind["sleep"]["state"], "active")
        self.assertEqual(by_kind["reading"]["reading"]["reflection"], "这篇资料让我想到一个还未想明白的问题。")
        self.assertEqual(by_kind["diary"]["content_form"], "derived")
        self.assertEqual(first.role_instruction, "原角色人格提示")
        self.advance(self.app, 61)
        await self.until(lambda: any(j["kind"] == "dream" for j in self.status()["journals"]))
        await self.settle()
        second = await self.chat("after-wake")
        by_kind = {p["kind"]: p for p in payloads(second)}
        self.assertEqual(by_kind["sleep"]["state"], "completed")
        self.assertEqual(by_kind["dream"]["basis"], "subjective_dream")
        journals = {j["kind"]: j for j in self.status()["journals"]}
        (await self.command("edit", journals["diary"], body="人工更正后保留的生活记述。")).unwrap()
        (await self.command("delete", journals["dream"])).unwrap()
        before = len(self.called)
        third = await self.chat("after-edit")
        by_kind = {p["kind"]: p for p in payloads(third)}
        self.assertEqual(by_kind["diary"]["body"], "人工更正后保留的生活记述。")
        self.assertNotIn("dream", by_kind)
        self.assertEqual(len(self.called), before + 1)
        self.assertEqual(len(self.sent), 3)

    async def test_foreground_reply_does_not_wait_for_inflight_reading(self):
        await self.setup_life()
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow_reader(envelope):
            if envelope.original.output_format == "role_reading":
                entered.set()
                await release.wait()
            return await self.model_with_chat(envelope)
        self.model_behavior = slow_reader
        book = (await self.add_text())[0]
        (await self.command("read", book)).unwrap()
        try:
            await asyncio.wait_for(entered.wait(), 3)
            reply = await self.chat("while-reading")
            activity = next(p for p in payloads(reply) if p["kind"] == "reading")
            self.assertEqual(activity["state"], "active")
            self.assertNotIn("reading", activity)
            self.assertIn("planned_reading_span", activity)
            self.assertFalse(release.is_set())
            self.assertEqual(len(self.sent), 1)
        finally:
            release.set()
            await self.settle()

    async def test_life_setting_manages_standard_participants_read_grant(self):
        await self.setup_life()
        self.model_behavior = self.model_with_chat
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
                             expected_revision=self.policy.revision, observed_at=self.clock.now())
        for action in ("configuration.read", "conversation.reply"):
            self.grant(self.important, SCOPE, action)
        await self.add_text()
        self.assertTrue(self.app.tasks.identity.authorize(self.important, scope=SCOPE,
            capability="role.life.read", observed_at=self.clock.now()).is_success)
        reply = await self.chat("with-permission")
        self.assertEqual(payloads(reply)[0]["state"], "planned")
        await self.configure(enabled=False)
        self.assertFalse(self.app.tasks.identity.authorize(self.important, scope=SCOPE,
            capability="role.life.read", observed_at=self.clock.now()).is_success)
        reply = await self.chat("without-permission")
        self.assertEqual(payloads(reply), [])

    async def test_restart_before_next_part_rechecks_corrected_journal_without_replaying(self):
        self.host_instance = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 3)))
        self.app = self.host_instance.application
        from companion_v2.role_work.journal.models import JournalContext, JournalKey, JournalKind
        from companion_v2.foundation.refs import RoleOwnerRef
        batch = self.host_instance.receive(self.event("seed")).unwrap()
        context = self.context(self.app, batch)
        key = JournalKey(RoleOwnerRef(SCOPE.installation_id, SCOPE.bot_id, context.role_binding.role.subject_id),
                         JournalKind.DIARY, self.clock.now().date().isoformat())
        target = JournalContext(key, SCOPE, "UTC")
        self.app.role_journal.save(JournalDraft(target, body="修改前的私人日记。"), expected_revision=0, operation_id="write")
        await self.until(lambda: self.app.flow.row(batch)["reason"] == "part_spacing")
        self.assertEqual(len(self.sent), 1)
        await self.app.close()
        self.app.role_journal.save(JournalDraft(target, body="重启前已经更正。"), expected_revision=1, operation_id="edit")
        new = await self.start(self.host(runtime=self.open_runtime()), 1, 1)
        self.advance(new.application, 4)
        result = await self.done(new.application, batch)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(len(self.called), 1)
        self.assertEqual(len(self.sent), 1)
        history = new.application.messages.history(context).unwrap()["items"]
        self.assertEqual(len(history), 1)
        self.assertFalse(history[0]["body_available"])


if __name__ == "__main__":
    unittest.main()
