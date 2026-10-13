"""Multi-target receipt views retain their owners, media and fences across reloads."""

from dataclasses import replace
import json
import unittest

# Establish the isolated SDK import root before importing installed components.
from tests.multi_host_support import MultiFixture
from tests.image_delivery_support import attach_originals
from tests.staging_bootstrap_support import database_contents, wait_for_batch
from tests.test_conversation_images import image_bytes
from astrbot.core.message.components import Image, Plain
from astrbot_host.media import load_native_image
from companion_v2.conversation.messages import event_from_document
from companion_v2.execution.models import TaskContext
from companion_v2.execution.service import TaskSupervisor


class MultiPreviewRecoveryTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def prepare(self, *, images=False, withdrawn=False):
        if images:
            self.types = replace(self.types, image=Image, image_loader=load_native_image)
            self.controller = self.make_controller()
            self.native.provider.client.state.behavior = attach_originals
        app = await self.start_host()
        event = self.event()
        if images:
            event.message_obj.message = [Plain("看看这张图片"), Image.fromBytes(image_bytes())]
        self.batch = (await self.controller.receive_claimed(event)).unwrap()
        await wait_for_batch(self.controller.session, self.batch)
        self.target = TaskContext.restore(json.loads(app.messages.batch(self.batch)["context_json"]))
        row = app.runtime.read_one("SELECT event_json FROM conversation_inputs WHERE batch_id = ?", (self.batch,))
        self.original = event_from_document(json.loads(row[0]), self.target)
        if withdrawn:
            app.messages.withdraw(self.target, self.original.scoped_key).unwrap()
        await self.controller.terminate()
        self.controller = self.make_controller()
        self.assertTrue((await self.controller.load_existing()).unwrap()["loaded"])
        self.app = self.controller.session.application

    async def test_reload_preview_keeps_bot_owner_and_does_not_start_execution(self):
        await self.prepare()
        before = database_contents(self.controller.runtime)
        preview = self.controller.preview("first", self.batch).unwrap()
        self.assertEqual([p["text"] for p in preview["parts"]], ["我在这里。"])
        self.assertTrue(preview["sent"])
        self.assertEqual([part["state"] for part in preview["parts"]], ["delivered"])
        self.assertEqual(self.controller.preview("second", self.batch).failure.code, "host_target_mismatch")
        self.assertIsNone(self.app.tasks.generation)
        self.assertFalse(self.controller.status()["accepting"])
        self.assertEqual(self.app.tasks.authorize_context(self.target, action="conversation.reply",
            observed_at=self.clock.now()).failure.code, "supervisor_fenced")
        self.assertEqual(database_contents(self.controller.runtime), before)
        self.assertEqual(len(self.native.provider.client.state.calls), 1)
        self.assertEqual([action for action, _ in self.native.platforms["qq-main"].client._api._wsr_api.calls],
                         ["send_private_msg"])
        self.assertEqual(self.native.platforms["qq-second"].client._api._wsr_api.calls, [])

    async def test_image_preview_reuses_recovered_materials_and_rechecks_revocation(self):
        await self.prepare(images=True)
        before = database_contents(self.controller.runtime)
        preview = self.controller.preview("first", self.batch).unwrap()
        image = preview["parts"][-1]["images"][0]
        self.assertEqual((image["mime_type"], image["width"], image["height"]), ("image/png", 3, 2))
        self.assertNotIn("base64", str(preview))
        self.assertEqual(database_contents(self.controller.runtime), before)
        self.app.messages.sources.revoke(self.original.source, expected_governance_revision=1,
                                         observed_at=self.clock.now()).unwrap()
        before = database_contents(self.controller.runtime)
        self.assertEqual(self.controller.preview("first", self.batch).failure.code, "source_revoked")
        self.assertEqual(database_contents(self.controller.runtime), before)

    async def test_replaced_running_host_cannot_read_a_saved_preview(self):
        await self.prepare()
        (await self.controller.start()).unwrap()
        tasks = self.controller.session.application.tasks
        replacement = TaskSupervisor(tasks.runtime, tuple(tasks.registrations.values()),
                                     limits=tasks.limits, now=self.clock.now)
        replacement.start(expected_generation=tasks.generation).unwrap()
        before = database_contents(self.controller.runtime)
        self.assertEqual(self.controller.preview("first", self.batch).failure.code, "supervisor_fenced")
        self.assertEqual(database_contents(self.controller.runtime), before)

    async def test_withdrawn_draft_cannot_expose_persisted_text_after_reload(self):
        await self.prepare(withdrawn=True)
        before = database_contents(self.controller.runtime)
        self.assertEqual(self.controller.preview("first", self.batch).failure.code, "staging_draft_unavailable")
        self.assertEqual(database_contents(self.controller.runtime), before)

    async def test_mismatched_origin_cannot_reuse_the_serialized_context(self):
        await self.prepare()
        with self.controller.runtime.transaction() as connection:
            connection.execute("UPDATE conversation_batches SET origin_key = ? WHERE batch_id = ?",
                               ("another-owner", self.batch))
        before = database_contents(self.controller.runtime)
        self.assertEqual(self.controller.preview("first", self.batch).failure.code, "message_batch_unavailable")
        self.assertEqual(database_contents(self.controller.runtime), before)
