"""参考图（photo.reference）与衣柜（wardrobe）两组配置的编辑器与校验器。

两组此前都有 owner、有注册契约、有真实消费端（``ReferenceAssetService._admit``
的总闸、``daily_outfit_options`` 的每日穿搭闸、``wardrobe_material`` 的提示词材料），
只是没有任何页面读写路径：前端 ``config-editor.js`` 早已写好两个分区的声明，
但 ``app.js`` 没有挂载点、``companion_v2.configuration.management`` 没有编辑器、
``astrbot_host.configuration_api.SECTIONS`` 也不含这两个键——页面即使渲染出来，
保存也会以 ``configuration_request_invalid``（unknown configuration section）被拒。
本文件锁四件事：

1. 两个编辑器的 group/owner/layers/error_prefix 声明；
2. 两组都是**角色级**：链里不能出现窗口层，否则单个会话就能改整个角色的参考素材与穿衣；
3. 注册表写下的边界与校验器一致（页面渲染的范围＝后端接受的范围）；
4. 两种注册表表达不了的规则由分组校验器兜住：800 字文本「拒绝而不是截断」，
   以及轮换天数 1–365。
"""

import unittest

from companion_v2.configuration.management import ReferenceManagement, WardrobeManagement
from companion_v2.configuration.models import ConfigLayer, ConfigurationError
from companion_v2.references.configuration import DEFAULTS as REFERENCE_DEFAULTS
from companion_v2.references.configuration import GROUP as REFERENCE_GROUP
from companion_v2.references.configuration import LIMITS as REFERENCE_LIMITS
from companion_v2.references.configuration import OWNER as REFERENCE_OWNER
from companion_v2.references.configuration import configuration_fields as reference_fields
from companion_v2.references.configuration import validate as reference_validate
from companion_v2.references.wardrobe import DEFAULTS as WARDROBE_DEFAULTS
from companion_v2.references.wardrobe import GROUP as WARDROBE_GROUP
from companion_v2.references.wardrobe import LIMITS as WARDROBE_LIMITS
from companion_v2.references.wardrobe import (MAX_IMAGE_PROMPT, MAX_TENDENCY,
                                              OWNER as WARDROBE_OWNER)
from companion_v2.references.wardrobe import configuration_fields as wardrobe_fields
from companion_v2.references.wardrobe import validate as wardrobe_validate


class MaterialEditorDeclarationTests(unittest.TestCase):
    def test_each_editor_binds_its_own_group_owner_and_layers(self):
        expected = {
            WardrobeManagement: (WARDROBE_GROUP, WARDROBE_OWNER, (ConfigLayer.ROLE,), "wardrobe"),
            ReferenceManagement: (REFERENCE_GROUP, REFERENCE_OWNER, (ConfigLayer.ROLE,), "reference"),
        }
        for editor, (group, owner, layers, prefix) in expected.items():
            with self.subTest(editor=editor.__name__):
                self.assertEqual(editor.group, group)
                self.assertEqual(editor.owner, owner)
                self.assertEqual(tuple(editor.layers), layers)
                self.assertEqual(editor.error_prefix, prefix)

    def test_a_role_group_never_claims_a_window_layer(self):
        """反过来的那条规则：``_authorize`` 只在链里有窗口层时才做私聊参与者
        复核。穿衣倾向与参考素材按角色生效，多一个窗口层就等于让某一段关系
        改掉整个角色的设置。"""
        for editor in (WardrobeManagement, ReferenceManagement):
            with self.subTest(editor=editor.__name__):
                self.assertNotIn(ConfigLayer.WINDOW, editor.layers)
                self.assertIn(ConfigLayer.ROLE, editor.layers)

    def test_the_scope_and_configuration_codes_are_prefixed_for_the_page(self):
        """页面按这些字符串取文案；改名会让界面重新漏出裸机器码。"""
        cases = ((WardrobeManagement, "wardrobe_scope_invalid", "wardrobe_configuration_invalid"),
                 (ReferenceManagement, "reference_scope_invalid", "reference_configuration_invalid"))
        for editor, scope_code, configuration_code in cases:
            with self.subTest(editor=editor.__name__):
                instance = editor.__new__(editor)
                self.assertEqual(editor._code(instance, "scope_invalid"), scope_code)
                self.assertEqual(editor._code(instance, "configuration_invalid"), configuration_code)

    def test_the_reference_validator_keeps_its_own_distinct_code(self):
        """参考图的取值校验码来自分组验证器（``photo_reference_*``），与编辑器的
        ``reference_*`` 前缀不同名。两者都要能被页面翻到——内核表里各有一条。"""
        self.assertEqual(REFERENCE_GROUP, "photo.reference")
        with self.assertRaises(ConfigurationError) as caught:
            reference_validate({**REFERENCE_DEFAULTS, "daily_outfit_rotation_days": 0})
        self.assertEqual(caught.exception.code, "photo_reference_configuration_invalid")


class MaterialFieldContractTests(unittest.TestCase):
    def test_every_field_is_registered_under_its_group_prefix(self):
        for group, owner, fields, defaults in (
                (WARDROBE_GROUP, WARDROBE_OWNER, wardrobe_fields(), WARDROBE_DEFAULTS),
                (REFERENCE_GROUP, REFERENCE_OWNER, reference_fields(), REFERENCE_DEFAULTS)):
            with self.subTest(group=group):
                self.assertEqual(len(fields), len(defaults))
                for field in fields:
                    with self.subTest(field=field.field_id):
                        self.assertEqual(field.group_id, group)
                        self.assertEqual(field.owner_id, owner)
                        self.assertTrue(field.field_id.startswith(group + "."))
                        self.assertEqual(tuple(field.layers), (ConfigLayer.ROLE,))

    def test_registered_bounds_match_the_validator(self):
        """页面渲染的范围就是注册表声明的范围；两者不一致会变成「页面允许、
        后端拒绝」。衣柜的两处文字还额外声明了 800 字上限。"""
        wardrobe = {field.field_id.removeprefix(WARDROBE_GROUP + "."): field
                    for field in wardrobe_fields()}
        for name, (low, high) in WARDROBE_LIMITS.items():
            with self.subTest(name=name):
                self.assertEqual(wardrobe[name].minimum, low)
                self.assertEqual(wardrobe[name].maximum, high)
        self.assertEqual(wardrobe["tendency"].maximum, MAX_TENDENCY)
        self.assertEqual(wardrobe["image_prompt"].maximum, MAX_IMAGE_PROMPT)

        reference = {field.field_id.removeprefix(REFERENCE_GROUP + "."): field
                     for field in reference_fields()}
        for name, (low, high) in REFERENCE_LIMITS.items():
            with self.subTest(name=name):
                self.assertEqual(reference[name].minimum, low)
                self.assertEqual(reference[name].maximum, high)
        for name in ("enabled", "group_enabled", "daily_outfit_enabled"):
            with self.subTest(name=name):
                self.assertIsNone(reference[name].minimum)
                self.assertIsNone(reference[name].maximum)


class WardrobeValidatorTests(unittest.TestCase):
    def test_accepts_the_declared_defaults(self):
        self.assertEqual(wardrobe_validate(dict(WARDROBE_DEFAULTS)), WARDROBE_DEFAULTS)

    def test_refuses_an_over_long_note_instead_of_truncating_it(self):
        for name, maximum in (("tendency", MAX_TENDENCY), ("image_prompt", MAX_IMAGE_PROMPT)):
            with self.subTest(name=name):
                self.assertEqual(wardrobe_validate({**WARDROBE_DEFAULTS, name: "好" * maximum})[name],
                                 "好" * maximum)
                with self.assertRaises(ConfigurationError) as caught:
                    wardrobe_validate({**WARDROBE_DEFAULTS, name: "好" * (maximum + 1)})
                self.assertEqual(caught.exception.code, "wardrobe_configuration_invalid")

    def test_refuses_out_of_range_counts_and_wrong_types(self):
        for values in ({"prompt_max_items": 0}, {"prompt_max_items": 25},
                       {"image_max_count": 9}, {"enabled": "yes"}, {"tendency": 12}):
            with self.subTest(values=values):
                with self.assertRaises(ConfigurationError) as caught:
                    wardrobe_validate({**WARDROBE_DEFAULTS, **values})
                self.assertEqual(caught.exception.code, "wardrobe_configuration_invalid")

    def test_refuses_a_partial_payload(self):
        with self.assertRaises(ConfigurationError):
            wardrobe_validate({"enabled": True})


class ReferenceValidatorTests(unittest.TestCase):
    def test_accepts_the_declared_defaults(self):
        self.assertEqual(reference_validate(dict(REFERENCE_DEFAULTS)), REFERENCE_DEFAULTS)

    def test_refuses_a_rotation_outside_one_to_three_hundred_sixty_five_days(self):
        for days in (0, 366, True, "14"):
            with self.subTest(days=days):
                with self.assertRaises(ConfigurationError) as caught:
                    reference_validate({**REFERENCE_DEFAULTS, "daily_outfit_rotation_days": days})
                self.assertEqual(caught.exception.code, "photo_reference_configuration_invalid")
        self.assertEqual(
            reference_validate({**REFERENCE_DEFAULTS, "daily_outfit_rotation_days": 365})[
                "daily_outfit_rotation_days"], 365)

    def test_refuses_non_boolean_switches_and_a_partial_payload(self):
        with self.assertRaises(ConfigurationError):
            reference_validate({**REFERENCE_DEFAULTS, "enabled": 1})
        with self.assertRaises(ConfigurationError):
            reference_validate({"enabled": True})


if __name__ == "__main__":
    unittest.main()
