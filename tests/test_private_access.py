"""私聊用户权限的默认值与拒绝文案（配置面）。

产品规则（本轮只落这一层）：
* 新私聊用户默认**可以对话**、默认**不可以被主动联系**；
* 无对话权限时回什么、多久回一次，都由配置决定；
* 未绑定的陌生号默认会被婉拒（一次固定文案，不建身份、不进记忆）；
* 每个人的实际权限仍然是既有 grant（``conversation.reply`` / ``proactive.contact``），
  这个组只负责"没人决定过的人从哪开始"，不复制任何人的权限。

用户已拍板：默认权限**不签发 grant**（读的时候按配置解释）；陌生号**也要回**。
"""

import unittest

from companion_v2.relationships.private_access import (DENIED_REPLY, DIALOGUE_DEFAULT,
                                                       NOTICE_COOLDOWN_SECONDS, PROACTIVE_DEFAULT,
                                                       STRANGER_NOTICE_DAILY_CAP, STRANGER_NOTICE_DEFAULT,
                                                       configuration_fields)
from tests.group_host_support import GroupFixture


class PrivateAccessDefaultsTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    @property
    def app(self):
        return self.controller.session.application

    async def test_group_is_registered_with_the_documented_defaults(self):
        await self.start_host()
        fields = {field.field_id: field for field in self.app.configuration.registry.group("private_access")}

        self.assertEqual(set(fields), {"private_access.dialogue_default", "private_access.proactive_default",
                                       "private_access.denied_reply", "private_access.notice_cooldown_seconds",
                                       "private_access.stranger_notice_enabled",
                                       "private_access.stranger_notice_daily_cap"})
        self.assertIs(fields["private_access.dialogue_default"].default, DIALOGUE_DEFAULT)
        self.assertIs(fields["private_access.proactive_default"].default, PROACTIVE_DEFAULT)
        self.assertEqual(fields["private_access.denied_reply"].default, DENIED_REPLY)
        self.assertEqual(fields["private_access.notice_cooldown_seconds"].default, NOTICE_COOLDOWN_SECONDS)
        self.assertIs(fields["private_access.stranger_notice_enabled"].default, STRANGER_NOTICE_DEFAULT)
        self.assertEqual(fields["private_access.stranger_notice_daily_cap"].default, STRANGER_NOTICE_DAILY_CAP)

    async def test_a_new_private_user_defaults_to_answerable_but_not_contacted_first(self):
        await self.start_host()
        context, _ = await self.accepted(identifier="private-access-1", text="你好")

        values = self.app.private_access_settings.defaults(context)

        self.assertIs(values["dialogue"], DIALOGUE_DEFAULT)
        self.assertIs(values["proactive"], PROACTIVE_DEFAULT)
        self.assertEqual(values["denied_reply"], DENIED_REPLY)
        self.assertEqual(values["notice_cooldown_seconds"], NOTICE_COOLDOWN_SECONDS)
        self.assertIs(values["stranger_notice"], STRANGER_NOTICE_DEFAULT)
        self.assertEqual(values["stranger_daily_cap"], STRANGER_NOTICE_DAILY_CAP)

    async def test_defaults_are_layered_and_bounded(self):
        await self.start_host()
        fields = {field.field_id: field for field in self.app.configuration.registry.group("private_access")}

        for field in fields.values():
            # 默认值属于"整个安装 / 这个角色"：一个新用户在任何窗口都一样。
            self.assertEqual(tuple(layer.value for layer in field.layers), ("installation", "role"))
        cooldown = fields["private_access.notice_cooldown_seconds"]
        self.assertEqual((cooldown.minimum, cooldown.maximum), (0, 604800),
                         "0 表示每次都回；上限一周")
        cap = fields["private_access.stranger_notice_daily_cap"]
        self.assertEqual((cap.minimum, cap.maximum), (0, 100),
                         "0 表示一个陌生号都不回；上限每天 100 条")
        self.assertEqual(len(configuration_fields()), 6)
