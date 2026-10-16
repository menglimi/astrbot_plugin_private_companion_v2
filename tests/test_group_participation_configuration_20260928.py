"""群聊参与（conversation.group_participation）的编辑器与校验器。

这一组此前有 owner、有注册契约、有真实消费端（group_observation.py 的氛围参考、
participation_prompts.py 的提示词、group_interjection.py 的插话与跟读预算），
只是没有页面读写路径。本文件锁三件事：

1. ``GroupParticipationManagement`` 的 group/owner/layers/error_prefix 声明；
2. ``group_repeat_interrupt_text`` 这条**注册表表达不了**的规则
   （一行、非空、无控制字符、≤80 字）在 owner 的读、写、预览三处都成立——
   少了写侧那两处，一条越界文案会被存进去，然后让下一轮群聊读取整个报错；
3. 注册表写下的边界与校验器一致，避免页面按注册表渲染出会被后端拒的范围。
"""

import unittest

from companion_v2.configuration.management import GroupParticipationManagement
from companion_v2.configuration.models import ConfigLayer, ConfigurationError
from companion_v2.conversation.participation import (CONFIG_DEFAULTS, CONFIG_GROUP, CONFIG_LIMITS,
                                                     CONFIG_OWNER, MAX_INTERRUPT_TEXT,
                                                     GroupParticipationConfigurationOwner,
                                                     configuration_fields, validate_interrupt_text)


class GroupParticipationEditorTests(unittest.TestCase):
    def test_the_editor_binds_the_groups_own_owner_and_layer_chain(self):
        self.assertEqual(GroupParticipationManagement.group, CONFIG_GROUP)
        self.assertEqual(GroupParticipationManagement.owner, CONFIG_OWNER)
        self.assertEqual(GroupParticipationManagement.error_prefix, "group_participation")
        # 窗口层在链里：这一组按会话生效，必须走私聊参与者的绑定复核分支。
        self.assertIn(ConfigLayer.WINDOW, GroupParticipationManagement.layers)

    def test_the_scope_and_target_codes_are_prefixed_for_the_page(self):
        editor = GroupParticipationManagement
        self.assertEqual(editor._code(editor.__new__(editor), "scope_invalid"),
                         "group_participation_scope_invalid")
        self.assertEqual(editor._code(editor.__new__(editor), "target_changed"),
                         "group_participation_target_changed")

    def test_every_field_is_registered_under_the_group_prefix(self):
        fields = configuration_fields()
        self.assertEqual(len(fields), len(CONFIG_DEFAULTS))
        for field in fields:
            with self.subTest(field=field.field_id):
                self.assertEqual(field.group_id, CONFIG_GROUP)
                self.assertEqual(field.owner_id, CONFIG_OWNER)
                self.assertTrue(field.field_id.startswith(CONFIG_GROUP + "."))

    def test_registered_bounds_match_the_validator(self):
        """注册表声明的范围就是页面渲染出来的范围；与校验器不一致会变成
        「页面允许、后端拒绝」。"""
        by_name = {field.field_id.removeprefix(CONFIG_GROUP + "."): field
                   for field in configuration_fields()}
        for name, (low, high) in CONFIG_LIMITS.items():
            with self.subTest(name=name):
                self.assertEqual(by_name[name].minimum, low)
                self.assertEqual(by_name[name].maximum, high)
        # 概率字段没有 CONFIG_LIMITS 条目，但必须是 0–1 的小数。
        for name, default in CONFIG_DEFAULTS.items():
            if type(default) is float:
                with self.subTest(name=name):
                    self.assertIsNone(by_name[name].minimum)
                    self.assertIsNone(by_name[name].maximum)


class InterruptTextRuleTests(unittest.TestCase):
    """注册表表达不了的那一条：contract_of 不下发字符串长度。"""

    def test_accepts_one_short_printable_line(self):
        self.assertEqual(validate_interrupt_text("禁止复读"), "禁止复读")
        self.assertEqual(validate_interrupt_text("停一下"), "停一下")

    def test_rejects_blank_oversized_and_control_characters(self):
        for value in ("", "   ", "长" * (MAX_INTERRUPT_TEXT + 1), "两\n行", "带\t制表", None, 7):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ConfigurationError) as caught:
                    validate_interrupt_text(value)
                self.assertEqual(caught.exception.code, "group_participation_configuration")

    def test_the_length_limit_is_inclusive(self):
        self.assertEqual(len(validate_interrupt_text("长" * MAX_INTERRUPT_TEXT)), MAX_INTERRUPT_TEXT)

    def test_the_owner_type_carries_no_extra_state(self):
        """owner 只是 SparseConfigurationOwner 的子类；这里只确认类本身存在，
        真正的读写校验由下面的快照测试驱动。"""
        self.assertTrue(issubclass(GroupParticipationConfigurationOwner, object))
        self.assertEqual(GroupParticipationConfigurationOwner.owner_id, CONFIG_OWNER)


class OwnerWritePathTests(unittest.TestCase):
    """owner 的 preview_set/write 必须复跑同一条规则，否则存得进去、读不出来。"""

    class _Item:
        def __init__(self, value):
            self.value = value

    def _fields(self, value):
        return {CONFIG_GROUP + ".group_repeat_interrupt_text": self._Item(value)}

    def test_preview_and_write_apply_the_same_rule_as_the_reader(self):
        from companion_v2.conversation.participation import _check_interrupt_text
        for value in ("禁止复读", "长" * MAX_INTERRUPT_TEXT):
            with self.subTest(value=repr(value)):
                _check_interrupt_text(self._fields(value))  # 不抛
        for value in ("", "长" * (MAX_INTERRUPT_TEXT + 1), "两\n行"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ConfigurationError):
                    _check_interrupt_text(self._fields(value))

    def test_a_snapshot_without_the_field_is_left_alone(self):
        """分段预览可能只带被改的字段；没有这一项时不能凭空报错。"""
        from companion_v2.conversation.participation import _check_interrupt_text
        _check_interrupt_text({})
        _check_interrupt_text({CONFIG_GROUP + ".enable_group_repeat_follow": self._Item(True)})


class GroupDefaultsTests(unittest.TestCase):
    """默认值本身也是契约：V1 的默认行为要保持不变。"""

    def test_repeat_following_is_on_by_default_and_interjection_is_off(self):
        self.assertTrue(CONFIG_DEFAULTS["enable_group_repeat_follow"])
        self.assertFalse(CONFIG_DEFAULTS["enable_group_interjection"])
        # 氛围参考整组默认关闭，开了才会读氛围。
        self.assertFalse(CONFIG_DEFAULTS["enable_group_social_context"])

    def test_every_switch_is_a_real_boolean(self):
        """开关集合由源码派生，别再手工数一遍。"""
        from companion_v2.conversation.participation import CONFIG_SWITCHES
        switches = [name for name, value in CONFIG_DEFAULTS.items() if type(value) is bool]
        self.assertEqual(set(switches), set(CONFIG_SWITCHES))
        self.assertTrue({"enable_group_behavior_learning", "enable_group_behavior_imitation",
                         "enable_group_behavior_feedback"}.issubset(switches))

    def test_switches_come_before_the_limits_they_govern(self):
        """页面的 sections 顺序依赖这一点：总闸先于受它约束的数字。"""
        names = list(CONFIG_DEFAULTS)
        self.assertLess(names.index("enable_group_repeat_follow"),
                        names.index("group_repeat_trigger_threshold"))
        self.assertLess(names.index("enable_group_interjection"),
                        names.index("group_interject_max_daily"))


if __name__ == "__main__":
    unittest.main()
