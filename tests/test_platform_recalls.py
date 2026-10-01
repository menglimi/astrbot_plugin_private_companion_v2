"""Platform withdrawals govern admitted and derived materials without undoing ACKs."""

from dataclasses import replace
import json
import unittest

from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.conversation.messages import source_from_document
from companion_v2.conversation.recalls import MessageRecall
from companion_v2.execution.models import digest
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.sources.dependencies import link
from companion_v2.sources.models import SourceRecord
from tests.test_host_application import HostFixture


class PlatformRecallTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def original(self, app, batch, *, position=1):
        row = app.runtime.read_one("SELECT * FROM conversation_inputs WHERE batch_id = ? AND position = ?", (batch, position))
        data = json.loads(row["event_json"])
        context = self.context(app, batch)
        return row, source_from_document(data["source"]), MessageRecall.from_scope(
            context.scope, data["event_id"], data["principal"]["native_account_id"])

    async def test_withdraw_one_merged_input_keeps_only_surviving_text(self):
        host = await self.start()
        app = host.application
        batch = host.receive(self.event("101", text="已经撤回的原话")).unwrap()
        self.assertEqual(host.receive(self.event("102", text="保留的原话")).unwrap(), batch)
        _, _, notice = self.original(app, batch)
        self.assertEqual(app.platform_recall(notice).unwrap()["withdrawn_inputs"], 1)
        self.assertTrue(app.platform_recall(notice).unwrap()["replayed"])
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        materials = self.called[0].original.context.materials
        self.assertFalse(any("已经撤回的原话" in m.payload for m in materials))
        self.assertTrue(any("保留的原话" in m.payload for m in materials))

    async def test_native_withdrawal_revokes_derived_source_and_survives_restart(self):
        host = await self.start()
        app = host.application
        batch = host.receive(self.event("103")).unwrap()
        _, source, notice = self.original(app, batch)
        context = self.context(app, batch)
        child = SourceRef("recall-derived", "role.journal", source.scope, VersionRef("recall-derived", 1), self.clock.now())
        app.messages.sources.publish(SourceRecord(child, context.audience, digest("衍生内容"), "衍生内容"),
                                     observed_at=self.clock.now()).unwrap()
        link(app.runtime, child, (source,), self.clock.now())
        self.assertTrue(app.messages.sources.validate_reference(child, observed_at=self.clock.now()).is_success)
        app.platform_recall(notice).unwrap()
        self.assertIsNotNone(app.messages.sources.validate_reference(child, observed_at=self.clock.now()).failure)
        self.assertEqual(len(self.called), 0)
        await app.close()
        reopened = self.open_runtime()
        second = await self.start(self.host(runtime=reopened), task_generation=1, model_generation=1)
        self.assertTrue(second.application.platform_recall(notice).unwrap()["replayed"])
        self.assertIsNotNone(second.receive(self.event("103")).failure)
        self.assertIsNotNone(second.application.messages.sources.validate_reference(child, observed_at=self.clock.now()).failure)

    async def test_recall_author_and_native_route_do_not_cross_inputs(self):
        host = await self.start()
        app = host.application
        batch = host.receive(self.event("104")).unwrap()
        row, source, notice = self.original(app, batch)
        for wrong in (replace(notice, sender_id="someone-else"), replace(notice, account_id="another-login"),
                      replace(notice, native_scope_id="another-peer"), replace(notice, bot_id="another-bot")):
            self.assertEqual(app.platform_recall(wrong).unwrap()["withdrawn_inputs"], 0)
            self.assertTrue(app.messages.sources.validate_reference(source, observed_at=self.clock.now()).is_success)
        self.assertEqual(app.runtime.read_one("SELECT withdrawn FROM conversation_inputs WHERE event_key = ?", (row["event_key"],))[0], 0)
        self.assertEqual(app.platform_recall(notice).unwrap()["withdrawn_inputs"], 1)

    async def test_recalled_bot_reply_keeps_delivery_proof_but_not_reusable_text(self):
        async def send(envelope):
            return replace(self.receipt(envelope), platform_ref=
                app.messages.recalls.platform_reference(envelope.context.scope, "456"))
        self.send_behavior = send
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0), split=lambda text: (text,)))
        app = host.application
        batch = host.receive(self.event("105")).unwrap()
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        context = self.context(app, batch)
        before = dict(app.runtime.read_one("SELECT * FROM conversation_parts WHERE batch_id = ?", (batch,)))
        notice = MessageRecall.from_scope(context.scope, "456", context.scope.account_id)
        app.platform_recall(notice).unwrap()
        self.assertEqual(dict(app.runtime.read_one("SELECT * FROM conversation_parts WHERE batch_id = ?", (batch,))), before)
        history = app.messages.history(context).unwrap()["items"]
        self.assertEqual(len(history), 1)
        self.assertFalse(history[0]["body_available"])
        self.assertIsNone(history[0]["text"])
        self.assertEqual(len(self.sent), 1)


if __name__ == "__main__":
    unittest.main()
