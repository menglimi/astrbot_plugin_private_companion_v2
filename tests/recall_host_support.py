"""SDK-shaped recall notices and assertions over temporary host stores."""

from copy import copy
import json
from uuid import uuid4

# This fixture redirects AstrBot's import-time data root before importing the SDK.
from tests import test_astrbot_staging_host as sdk_environment
from aiocqhttp import Event
from companion_v2.execution.models import TaskContext
from companion_v2.memory import codec
from tests.staging_bootstrap_support import wait_for_batch


def recall_notice(original, *, message_id=None, operator_id=None):
    """Match 4.27.2 notice conversion, including its unrelated generated UUID."""
    event = copy(original)
    event.message_obj = message = copy(original.message_obj)
    message.sender = copy(original.message_obj.sender)
    event.session = copy(original.session)
    event.platform_meta = copy(original.platform_meta)
    group = getattr(message, "group_id", "")
    sender = message.sender.user_id
    message.session_id = group or sender
    message.message_id = uuid4().hex
    message.message = []
    message.message_str = event.message_str = ""
    message.raw_message = Event(
        post_type="notice", notice_type="group_recall" if group else "friend_recall",
        self_id=int(message.self_id), user_id=int(sender), time=int(event.created_at),
        message_id=int(original.message_obj.message_id if message_id is None else message_id),
    )
    if group:
        message.raw_message.update(group_id=int(group), operator_id=int(operator_id or sender))
    return event


class RecallAssertions:
    async def admit(self, event):
        result = await self.controller.receive_claimed(event)
        self.assertTrue(result.is_success, result.failure)
        batch = result.unwrap()
        await wait_for_batch(self.controller.session, batch)
        return batch

    async def recall(self, event):
        self.assertFalse(self.controller.claims(event))
        result = await self.controller.receive_notice(event)
        self.assertIsNotNone(result)
        self.assertTrue(result.is_success, result.failure)
        value = result.unwrap()
        self.assertTrue({"replayed", "withdrawn_inputs", "revoked_quotes", "recalled_replies"}.issubset(value))
        return value

    def input_row(self, app, batch):
        return app.runtime.read_one("SELECT * FROM conversation_inputs WHERE batch_id = ?", (batch,))

    def original_context(self, app, batch):
        return TaskContext.restore(json.loads(app.messages.batch(batch)["context_json"]))

    def assert_withdrawn(self, app, batch, expected=True):
        row = self.input_row(app, batch)
        self.assertEqual(bool(row["withdrawn"]), expected)
        source = codec.source(json.loads(row["event_json"])["source"])
        result = app.messages.sources.validate_reference(source, observed_at=self.clock.now())
        self.assertEqual(result.is_success, not expected)

    def notice_count(self, app):
        return app.runtime.read_one(
            "SELECT COUNT(*) FROM inbox WHERE consumer = ?", ("conversation.platform_recall.v1",)
        )[0]
