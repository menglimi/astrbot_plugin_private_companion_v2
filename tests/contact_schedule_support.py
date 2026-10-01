"""Mixed foreground/background fixture for automatic contact integration."""

from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.conversation.foreground import BackgroundPromptTrigger
from companion_v2.execution.models import TERMINAL
from tests.proactive_support import ContactFixture
from tests.test_role_tool_loop import answered


class ContactScheduleFixture(ContactFixture):
    async def generate(self, envelope):
        self.called.append(envelope)
        if self.model_behavior:
            return await self.model_behavior(envelope)
        return answered('{"decision":"send","text":"刚想起上次的话题。"}'
            if isinstance(envelope.original.event, BackgroundPromptTrigger) else "记住了。")

    async def scheduled(self, *, automatic=True, **options):
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0), **options))
        self.settings(host.application, {"enabled": True, "automatic_enabled": automatic,
            "interval_seconds": 60, "idle_seconds": 60}).unwrap()
        batch = host.receive(self.event()).unwrap()
        await self.done(host.application, batch)
        return host, batch

    def contact_calls(self):
        return [item for item in self.called if isinstance(item.original.event, BackgroundPromptTrigger)]

    def contacts(self, app):
        return app.runtime.read_all("SELECT * FROM proactive_contacts ORDER BY created_at, contact_id", ())

    async def automatic_delivery(self, app, *, count=1):
        await self.until(lambda: len(self.contacts(app)) >= count or app.state == "faulted")
        self.assertEqual(app.state, "running", app.failure_code)
        task_id = self.contacts(app)[-1]["task_id"]
        return await self.delivery_state(app, task_id, "delivered")

    async def delivery_state(self, app, task_id, state):
        row = await super().delivery_state(app, task_id, state)
        await self.until(lambda: app.runtime.read_one("SELECT state FROM execution_tasks WHERE task_id = ?",
            (row["task_id"],))[0] in TERMINAL)
        return row
