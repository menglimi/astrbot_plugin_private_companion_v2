from datetime import timedelta
import unittest

from companion_v2.role_work import RoleActivity, RoleActivityState as State
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, ROLE, SCOPE


class RoleLifeHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_application_restart_resumes_original_life_without_background_fabrication(self):
        host = await self.start()
        ledger = host.application.role_life
        activity = ledger.add_activity(RoleActivity("reading", ROLE.subject_id, SCOPE, NOW, State.ACTIVE,
                                                   description="阅读", checkpoint="第三章"))
        paused = ledger.transition_activity(activity.activity_id, owner=activity.owner, expected_revision=1,
            state=State.PAUSED, operation_id="pause-before-restart", checkpoint="第三章的一半")
        await host.application.close()
        self.runtime.close()
        self.clock.advance(timedelta(days=2))
        restored = await self.start(self.host(runtime=self.open_runtime()), task_generation=1, model_generation=1)
        current = restored.application.role_life.activity(activity.activity_id, owner=activity.owner)
        self.assertEqual(current, paused)
        self.assertEqual((self.called, self.sent), ([], []))
        resumed = restored.application.role_life.transition_activity(activity.activity_id, owner=activity.owner,
            expected_revision=2, state=State.ACTIVE, operation_id="resume-after-restart")
        self.assertEqual((resumed.checkpoint, resumed.revision), (paused.checkpoint, 3))
        self.assertEqual(resumed.updated_at, self.clock.now())
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_role_life_and_conversation_use_the_same_assembled_runtime(self):
        host = await self.start()
        ledger = host.application.role_life
        self.assertIs(ledger.runtime, host.application.runtime)
        activity = ledger.add_activity(RoleActivity("walk", ROLE.subject_id, SCOPE, NOW, State.PLANNED,
                                                   description="稍后散步"))
        batch = host.receive(self.event()).unwrap()
        self.advance(host.application, 1)
        self.assertEqual((await self.done(host.application, batch))["state"], "complete")
        self.assertEqual(ledger.activity("walk", owner=activity.owner), activity)
        self.assertEqual(len(self.called), 1)
        self.assertEqual([part.text for part in self.sent], ["第一段", "第二段"])


if __name__ == "__main__":
    unittest.main()
