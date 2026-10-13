"""Internal image rehearsals and live SDK delivery receipts on a local platform."""

import asyncio
from datetime import timedelta
from pathlib import Path
import unittest

from tests import test_astrbot_image_host as image_host
from astrbot_host.controller import AstrBotStagingController
from companion_v2.conversation.media.reply import OWNER
from tests.image_delivery_support import attach_originals
from tests.staging_bootstrap_support import wait_for_batch
from tests.test_management_access import NOW


class AstrBotImageDeliveryHostTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        image_host.AstrBotImageHostTests.setUp(self)
        self.observed_at = NOW
        self.controller.now = lambda: self.observed_at
        self.native.provider.client.state.behavior = attach_originals

    def event(self):
        return image_host.AstrBotImageHostTests.event(self)

    async def start_host(self, *, delivery=False):
        if delivery:
            config = image_host.sdk_environment.host_config(staging={
                "profile_id": "image-sender", "delivery_mode": "onebot_private"})
            self.controller = AstrBotStagingController(self.native, config, Path(self.temp.name),
                native_types=self.types, now=lambda: self.observed_at)
            self.addAsyncCleanup(self.controller.terminate)
        (await self.controller.initialize_profile()).unwrap()
        (await self.controller.start(review_only=not delivery)).unwrap()

    async def test_image_preview_has_original_metadata_without_delivery_or_history(self):
        await self.start_host()
        batch = (await self.controller.receive_claimed(self.event())).unwrap()
        session = self.controller.session
        await wait_for_batch(session, batch)
        preview = (await self.controller.preview(batch)).unwrap()
        self.assertFalse(preview["sent"])
        image = preview["parts"][-1]["images"][0]
        self.assertEqual((image["mime_type"], image["width"], image["height"]), ("image/png", 3, 2))
        self.assertNotIn("base64", str(preview))
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        self.assertEqual(session.application.messages.history(session.profile.target).unwrap()["items"], [])
        source = session.application.messages.reply_images.reference(session.application.messages.batch(batch), session.profile.target)
        session.application.messages.sources.revoke(source, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertEqual((await self.controller.preview(batch)).failure.code, "source_revoked")

    async def test_image_delivery_records_combined_ack_without_global_grant(self):
        await self.start_host(delivery=True)
        grant = self.controller.status()["delivery_authorization"]
        self.assertTrue(grant["authorized"])
        self.assertFalse(grant["required"])
        self.assertIsNone(grant["expires_at"])
        batch = (await self.controller.receive_claimed(self.event())).unwrap()
        session = self.controller.session
        await wait_for_batch(session, batch)
        self.assertTrue((await self.controller.inspect(batch)).unwrap()["confirmed_delivery"])
        action, params = self.native.platform.client._api._wsr_api.calls[0]
        self.assertEqual((action, params["self_id"], params["user_id"]), ("send_private_msg", "100", 200))
        self.assertEqual([p["type"] for p in params["message"]], ["text", "image"])
        history = session.application.messages.history(session.profile.target).unwrap()["items"]
        self.assertEqual(len(history), 1)
        self.assertEqual(len(history[0]["images"]), 1)

    async def test_stop_while_sender_prepares_images_prevents_late_dispatch(self):
        await self.start_host(delivery=True)
        session = self.controller.session
        entered = asyncio.Event()
        async def held(_):
            if session.runtime.read_one("SELECT 1 FROM sources WHERE owner = ?", (OWNER,)):
                entered.set()
                await asyncio.Event().wait()
        self.native.before_resolve = held
        batch = (await self.controller.receive_claimed(self.event())).unwrap()
        await asyncio.wait_for(entered.wait(), 3)
        (await self.controller.stop()).unwrap()
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        self.native.before_resolve = None
        self.observed_at += timedelta(seconds=1)
        (await self.controller.start()).unwrap()
        session = self.controller.session
        await wait_for_batch(session, batch)
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        self.assertEqual(session.application.messages.history(session.profile.target).unwrap()["items"], [])
