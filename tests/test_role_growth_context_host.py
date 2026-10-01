"""The composed host consumes managed growth through the original reply lifecycle."""

import unittest

from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.execution.models import TaskContext
from companion_v2.foundation.refs import AudienceRef
from companion_v2.role_work.growth.management import RoleGrowthManagement
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE


class GrowthContextHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def setup_growth(self):
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 3)))
        app = host.application
        seed = host.inbound.ingest(self.event("growth-evidence"), capability="text").unwrap()
        context = TaskContext(self.important, self.identity.resolve_role(SCOPE, observed_at=NOW).unwrap(),
                              AudienceRef(SCOPE, (self.important.subject,)))
        manager = RoleGrowthManagement(app.role_growth)
        token = manager.list(operator=self.core, context=context).unwrap()["create_token"]
        proposal = manager.create(operator=self.core, context=context, view_token=token,
            operation_key="propose", kind="skill", title="练习表达", description="继续写短篇。",
            progress_note="能把一小段经历写清楚。", sources=(seed.source,)).unwrap()["item"]
        active = manager.command(operator=self.core, context=context, growth_id=proposal["growth_id"],
            expected_revision=proposal["revision"], view_token=proposal["view_token"],
            operation_key="confirm", action="confirm").unwrap()["item"]
        return host, manager, context, active

    async def test_host_prompt_contains_managed_growth_and_rechecks_it_after_restart(self):
        host, manager, context, active = await self.setup_growth()
        app = host.application
        self.assertIs(app.messages.role_growth_context.reader.ledger, app.role_growth)
        batch = host.receive(self.event("chat")).unwrap()
        self.advance(app)
        await self.until(lambda: app.flow.row(batch)["reason"] == "part_spacing")
        self.assertEqual(len(self.sent), 1)
        request = self.called[0].original
        self.assertEqual(request.role_instruction, "原角色人格提示")
        self.assertEqual(len([m for m in request.context.materials if m.purpose == "role_growth_skill"]), 1)
        await app.close()
        manager.command(operator=self.core, context=context, growth_id=active["growth_id"],
            expected_revision=active["revision"], view_token=active["view_token"], operation_key="revise",
            action="revise", title="重新整理表达目标", description="", progress_note="").unwrap()
        new = await self.start(self.host(runtime=self.open_runtime()), 1, 1)
        self.advance(new.application, 4)
        result = await self.done(new.application, batch)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(len(self.called), 1)
        self.assertEqual(len(self.sent), 1)
        history = new.application.messages.history(context).unwrap()["items"]
        self.assertEqual(len(history), 1)
        self.assertFalse(history[0]["body_available"])
