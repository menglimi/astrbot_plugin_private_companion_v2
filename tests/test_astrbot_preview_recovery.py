"""Persisted previews are readable after load, without starting a worker lease."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest

from tests import test_astrbot_staging_host as support
from tests.image_delivery_support import attach_originals
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.staging_bootstrap_support import database_contents, wait_for_batch
from tests.test_conversation_images import image_bytes
from tests.test_management_access import NOW
from astrbot.core.message.components import Image, Plain
from astrbot_host.controller import AstrBotStagingController
from astrbot_host.media import load_native_image
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.conversation.messages import event_from_document
from companion_v2.execution.service import TaskSupervisor


class PreviewRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="v2-preview-recovery-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.native = support.WebContext()
        self.types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi)
        self.controller = self.make_controller()

    def make_controller(self):
        controller = AstrBotStagingController(self.native, support.host_config(), self.root,
                                              native_types=self.types, now=lambda: NOW)
        # This suite exercises the internal rehearsal reader, not live chat.
        load_session = controller._load_session
        controller._load_session = lambda **_: load_session(review_only=True)
        self.addAsyncCleanup(controller.terminate)
        return controller

    async def prepare(self, *, images=False):
        if images:
            self.types = replace(self.types, image=Image, image_loader=load_native_image)
            self.controller = self.make_controller()
            self.native.provider.client.state.behavior = attach_originals
        (await self.controller.initialize_profile()).unwrap()
        (await self.controller.start(review_only=True)).unwrap()
        event = FakeEvent(self.native)
        if images:
            event.message_obj.message = [Plain("看看这张图片"), Image.fromBytes(image_bytes())]
        self.batch = (await self.controller.receive_claimed(event)).unwrap()
        await wait_for_batch(self.controller.session, self.batch)
        self.target = self.controller.session.profile.target
        row = self.controller.runtime.read_one("SELECT event_json FROM conversation_inputs WHERE batch_id = ?", (self.batch,))
        self.original = event_from_document(json.loads(row[0]), self.target)
        await self.controller.terminate()
        self.controller = self.make_controller()
        self.assertTrue((await self.controller.load_existing()).unwrap()["loaded"])
        self.app = self.controller.session.application

    async def test_saved_preview_without_start_is_read_only_and_leaves_execution_fenced(self):
        await self.prepare()
        before = database_contents(self.controller.runtime)
        # Call the underlying reader as well so failures retain their owner stack.
        self.controller.session._readable_draft(self.batch)
        preview = (await self.controller.preview(self.batch)).unwrap()
        self.assertEqual([part["text"] for part in preview["parts"]], ["我在这里。"])
        self.assertFalse(preview["sent"])
        self.assertEqual(database_contents(self.controller.runtime), before)
        self.assertIsNone(self.app.tasks.generation)
        self.assertEqual(self.app.tasks.authorize_context(self.target, action="conversation.reply",
            observed_at=NOW).failure.code, "supervisor_fenced")
        self.assertFalse(self.controller.status()["accepting"])
        self.assertEqual(len(self.native.provider.client.state.calls), 1)
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_source_revoked_after_reload_hides_saved_preview(self):
        await self.prepare()
        self.app.messages.sources.revoke(self.original.source, expected_governance_revision=1, observed_at=NOW).unwrap()
        before = database_contents(self.controller.runtime)
        result = await self.controller.preview(self.batch)
        self.assertEqual(result.failure.code, "source_revoked")
        self.assertEqual(database_contents(self.controller.runtime), before)

    async def test_saved_image_preview_recovers_without_writes_or_worker_lease(self):
        await self.prepare(images=True)
        before = database_contents(self.controller.runtime)
        preview = (await self.controller.preview(self.batch)).unwrap()
        image = preview["parts"][-1]["images"][0]
        self.assertEqual((image["mime_type"], image["width"], image["height"]), ("image/png", 3, 2))
        self.assertFalse(preview["sent"])
        self.assertNotIn("base64", str(preview))
        self.assertEqual(database_contents(self.controller.runtime), before)
        self.assertIsNone(self.app.tasks.generation)

    async def test_grant_revoked_after_reload_hides_saved_preview(self):
        await self.prepare()
        identity = self.controller.bootstrap.identity
        identity.revoke_grant(self.controller.bootstrap.grant_id("text"), revoked_at=NOW,
                              expected_revision=identity.revision)
        before = database_contents(self.controller.runtime)
        result = await self.controller.preview(self.batch)
        self.assertEqual(result.failure.code, "authorization_revoked")
        self.assertEqual(database_contents(self.controller.runtime), before)

    async def test_saved_preview_cannot_read_another_batch_owner(self):
        await self.prepare()
        with self.controller.runtime.transaction() as connection:
            connection.execute("UPDATE conversation_batches SET origin_key = ? WHERE batch_id = ?", ("another-owner", self.batch))
        before = database_contents(self.controller.runtime)
        result = await self.controller.preview(self.batch)
        self.assertEqual(result.failure.code, "message_batch_unavailable")
        self.assertEqual(database_contents(self.controller.runtime), before)

    async def test_replaced_running_generation_remains_fenced(self):
        await self.prepare()
        (await self.controller.start(review_only=True)).unwrap()
        self.app = self.controller.session.application
        replacement = TaskSupervisor(self.app.runtime, tuple(self.app.tasks.registrations.values()),
                                     limits=self.app.tasks.limits, now=lambda: NOW)
        replacement.start(expected_generation=self.app.tasks.generation).unwrap()
        before = database_contents(self.controller.runtime)
        self.assertEqual((await self.controller.preview(self.batch)).failure.code, "supervisor_fenced")
        self.assertEqual(database_contents(self.controller.runtime), before)
