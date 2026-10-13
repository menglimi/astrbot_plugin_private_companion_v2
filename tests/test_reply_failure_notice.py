import unittest

from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.conversation.generation import MODEL_FAILURE_NOTICE
from companion_v2.execution.models import TaskError
from tests.test_host_application import HostFixture


class ReplyFailureNoticeTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_private_model_failure_sends_one_notice_without_replaying_call(self):
        async def unknown_result(_envelope):
            raise TaskError("model_usage_unknown", "provider result is unknown")

        self.model_behavior = unknown_result
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        batch = host.receive(self.event("provider-failure")).unwrap()

        self.advance(app, 0)
        self.assertEqual((await self.done(app, batch))["state"], "complete")

        self.assertEqual(len(self.called), 1)
        self.assertEqual([message.text for message in self.sent], [MODEL_FAILURE_NOTICE])
        saved = app.messages.batch(batch)
        self.assertIsNone(saved["call_id"])
        self.assertEqual(saved["part_count"], 1)
        calls = app.runtime.read_all("SELECT state FROM model_calls WHERE task_id = ?",
                                     (saved["generation_task_id"],))
        self.assertEqual([row["state"] for row in calls], ["unknown"])


if __name__ == "__main__":
    unittest.main()
