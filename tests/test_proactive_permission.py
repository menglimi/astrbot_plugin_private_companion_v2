"""主动权限被收回后，规划这一步不再往下走。

与对话权限对称：收回 ``proactive.contact`` 之后，调度器**不应该**再为这个人准备
主动联系，而且**不能写任何状态**——`proactive_contacts` 里出现这个 task 会被
``service.py`` 判成"已退休、不可重新生成"，等于永久封死该对象。要收回的是权限，
不是这个人。

注意：夹具默认把主用户当**核心用户**（core），核心用户的能力检查不看 grant，
所以这里先把层级降到 STANDARD——那才是宿主给普通私聊用户的实际层级。
"""

import unittest

from companion_v2.adapters.astrbot.staging_config import REQUIRED_CAPABILITIES
from companion_v2.execution.models import TaskError
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.proactive.configuration import GROUP
from tests.contact_schedule_support import ContactScheduleFixture


class RevokedProactivePermissionTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.issued = 0

    def as_standard(self, app, context):
        """把这个人降成普通用户：能力从此按 grant 判定。"""
        policy = app.tasks.policy
        policy.set_tier(context.actor.subject, AuthorizationTier.STANDARD,
                        expected_revision=policy.revision, observed_at=self.clock.now())

    def issue(self, app, context, capability):
        self.issued += 1
        identity = app.tasks.identity
        return identity.issue_grant(grant_id=f"grant-{capability}-{self.issued}",
                                    subject=context.actor.subject, scope=context.scope,
                                    capability=capability, tier=AuthorizationTier.STANDARD,
                                    valid_from=self.clock.now(), expected_revision=identity.revision)

    def grant_standard_set(self, app, context):
        """普通私聊用户实际拿到的那一套能力（宿主签发的是 REQUIRED_CAPABILITIES）。

        夹具默认把主用户当核心用户，所以这些 grant 平时根本不需要；一旦降到 STANDARD，
        少了 `configuration.read` 这类能力，规划会因为**别的原因**报 authorization_denied，
        测试就测不到"主动权限"这一件事了。
        """
        for capability in sorted(REQUIRED_CAPABILITIES):
            self.issue(app, context, capability)

    def grant_proactive(self, app, context):
        return self.issue(app, context, GROUP)

    def revoke_proactive(self, app):
        identity = app.tasks.identity
        active = [grant for grant in identity.snapshot().grants
                  if grant.capability == GROUP and grant.state.value == "active"]
        self.assertTrue(active, "这一步应当有一张生效中的 proactive.contact")
        for grant in active:
            identity.revoke_grant(grant.grant_id, revoked_at=self.clock.now(),
                                  expected_revision=identity.revision)

    def contacts(self, app):
        return app.runtime.read_all("SELECT * FROM proactive_contacts", ())

    async def test_revoked_proactive_permission_never_plans_and_never_records(self):
        host, _batch = await self.scheduled()
        app = host.application
        context = self.contact_context()
        self.as_standard(app, context)
        self.grant_standard_set(app, context)
        self.assertTrue(app.proactive.proactive_denied(context, at=self.clock.now()),
                        "普通用户没有 proactive.contact grant 时就是'没有主动权限'")

        self.grant_proactive(app, context)  # 先给权限，确认这条链路本来通
        self.assertFalse(app.proactive.proactive_denied(context, at=self.clock.now()))
        self.revoke_proactive(app)
        self.assertTrue(app.proactive.proactive_denied(context, at=self.clock.now()))

        self.advance(app, 60)               # 越过 idle 门槛：正常情况下这里就该发起主动联系
        app.contact_schedule.advance()

        self.assertEqual(self.contacts(app), (), "收回主动权限后不该产生任何主动联系记录")
        self.assertEqual(app.contact_schedule._workers, {}, "更不该真的发起一次主动联系")

    async def test_revoked_permission_is_not_a_permanent_block(self):
        """收回权限只是"这一轮不联系"：把权限还回来，规划立刻恢复。"""
        host, _batch = await self.scheduled()
        app = host.application
        context = self.contact_context()
        self.as_standard(app, context)
        self.grant_standard_set(app, context)
        self.grant_proactive(app, context)
        self.revoke_proactive(app)

        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(self.contacts(app), (), "没有权限时不该产生联系")

        self.grant_proactive(app, context)           # 还回权限
        self.assertFalse(app.proactive.proactive_denied(context, at=self.clock.now()),
                         "权限还回来之后判定要立刻回到'允许'")

        # 规划这一步不再被权限挡住：要么给出计划，要么因为别的原因（时段、预算…）不做，
        # 但**不能**再是"没有权限"。这条断言让"收回权限没有封死这个人"可验证。
        row = app.runtime.read_one("""SELECT f.sequence, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id
            ORDER BY f.sequence DESC LIMIT 1""", ())
        try:
            app.contact_schedule._plan(row, self.clock.now())
        except TaskError as error:
            self.assertNotIn(error.code, ("authorization_denied", "authorization_revoked",
                                          "scope_not_granted"),
                             "权限还回来之后不该再因为权限而失败")
        self.assertEqual(self.contacts(app), (), "拒绝本身不该留下任何记录")
