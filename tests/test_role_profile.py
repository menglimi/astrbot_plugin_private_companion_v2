"""Role canon is bounded, isolated by role and sealed into new conversation turns."""

import json
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.foundation.refs import SubjectKind, SubjectRef
from companion_v2.role_profile.configuration import (
    FIELD_LIMITS,
    GROUP,
    RoleProfileConfigurationOwner,
    configuration_fields,
    target_for,
)
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import NOW


class RoleProfileConversationTests(MessageFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.profile_owner = RoleProfileConfigurationOwner(self.runtime)
        self.profile_fields = configuration_fields()

    def save_profile(self, name, value, *, context=None):
        context = context or self.context
        target = target_for(context)
        current = self.profile_owner.read(target, self.profile_fields)
        return self.profile_owner.write(
            target, self.profile_fields, changes={f"{GROUP}.{name}": value}, reset=(),
            expected_revision=current.revision, observed_at=NOW,
        )

    async def test_role_profile_isolated_and_kept_unchanged_after_seal(self):
        self.save_profile("identity", "住在旧城边的电台编辑")
        self.save_profile("name", "沈知夏")
        self.save_profile("species", "人类")
        self.save_profile("birthday", "9 月 18 日")
        self.save_profile("age", "生日在初秋，约二十七岁")
        self.save_profile("personality", "慢热，熟悉之后会用轻松的玩笑表达关心。")
        self.save_profile("first_person", "自称我，不使用本小姐")
        self.save_profile("speech_style", "句子简短，先听完再回答，偶尔用干涩的玩笑缓和气氛。")
        self.save_profile("reaction_patterns", "被夸奖时先嘴硬，再小声道谢。")
        self.save_profile("voice_examples", "示例：你先说完，我在听。")
        self.save_profile("world", "信件总会晚一个雨季才抵达。")
        self.save_profile("rules", "从海上寄出的信至少要经过一整个雨季。")
        self.save_profile("world_adaptation_mode", "fantasy")
        self.save_profile("world_adaptation", "把资料柜说成行囊书匣；描述计划时用旅途安排。")

        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        sealed = json.loads(self.messages.batch(batch)["contributions_json"])["role_profile"]
        self.assertEqual(sealed["role_id"], self.context.role_binding.role.subject_id)
        self.assertEqual(sealed["fields"]["name"], "沈知夏")
        self.assertEqual(sealed["fields"]["birthday"], "9 月 18 日")
        self.assertEqual(sealed["fields"]["world"], "信件总会晚一个雨季才抵达。")

        request = self.messages._request(self.messages.batch(batch), self.context, NOW)
        self.assertIn("【角色稳定档案】", request.instruction)
        self.assertIn("姓名：沈知夏", request.instruction)
        self.assertIn("生日：9 月 18 日", request.instruction)
        self.assertIn("说话方式：句子简短，先听完再回答，偶尔用干涩的玩笑缓和气氛。", request.instruction)
        self.assertIn("自称与代词：自称我，不使用本小姐", request.instruction)
        self.assertIn("典型反应倾向：被夸奖时先嘴硬，再小声道谢。", request.instruction)
        self.assertIn("口吻示例：示例：你先说完，我在听。", request.instruction)
        self.assertIn("只用于体会表达习惯，不照抄台词", request.instruction)
        self.assertIn("身份经历补充：住在旧城边的电台编辑", request.instruction)
        self.assertIn("特殊规则：从海上寄出的信至少要经过一整个雨季。", request.instruction)
        self.assertIn("世界设定补充：信件总会晚一个雨季才抵达。", request.instruction)
        self.assertIn("世界观适配指引：把资料柜说成行囊书匣；描述计划时用旅途安排。", request.instruction)
        self.assertIn("世界观适配模式：fantasy", request.instruction)
        self.assertIn("幻想世界中的等价说法", request.instruction)
        self.assertIn("不要套用到其他人", request.instruction)

        self.save_profile("world", "每封信都会在第二天清晨送到。")
        replay = self.messages._request(self.messages.batch(batch), self.context, NOW)
        self.assertIn("信件总会晚一个雨季才抵达。", replay.instruction)
        self.assertNotIn("每封信都会在第二天清晨送到。", replay.instruction)

        other_role = SubjectRef(self.context.scope.installation_id, SubjectKind.BOT, "another-role")
        other_target = ConfigTarget(
            self.context.scope.installation_id, ConfigLayer.ROLE, other_role,
            bot_id=self.context.scope.bot_id,
        )
        other = self.profile_owner.read(other_target, self.profile_fields)
        self.assertEqual(other.fields[f"{GROUP}.identity"].value, "")
        self.assertEqual(other.fields[f"{GROUP}.name"].value, "")
        self.assertEqual(other.fields[f"{GROUP}.world"].value, "")

    async def test_blank_profile_does_not_add_a_prompt_block(self):
        self.save_profile("identity", " \n ")
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        saved = json.loads(self.messages.batch(batch)["contributions_json"])
        self.assertNotIn("role_profile", saved)
        request = self.messages._request(self.messages.batch(batch), self.context, NOW)
        self.assertNotIn("角色稳定档案", request.instruction)

    async def test_sealed_profiles_from_before_voice_fields_remain_replayable(self):
        self.save_profile("personality", "慢热，但会认真回应熟悉的人。")
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        sealed = json.loads(self.messages.batch(batch)["contributions_json"])["role_profile"]
        for name in ("birthday", "first_person", "emotional_style", "social_distance",
                     "reaction_patterns", "voice_examples", "signature_phrases"):
            sealed["fields"].pop(name)
        sealed["fields"].pop("world_adaptation_mode")
        sealed["fields"].pop("world_adaptation")
        instruction = self.messages.role_profile_context.instruction(sealed, self.context)
        self.assertIn("性格描述：慢热，但会认真回应熟悉的人。", instruction)
        self.assertNotIn("自称与代词：", instruction)

    async def test_profile_field_and_combined_limits_are_enforced(self):
        target = target_for(self.context)
        initial = self.profile_owner.read(target, self.profile_fields)
        with self.assertRaises(ConfigurationError):
            self.profile_owner.write(
                target, self.profile_fields,
                changes={f"{GROUP}.identity": "x" * (FIELD_LIMITS["identity"] + 1)},
                reset=(), expected_revision=initial.revision, observed_at=NOW,
            )
        with self.assertRaises(ConfigurationError):
            self.profile_owner.write(
                target, self.profile_fields,
                changes={f"{GROUP}.world_adaptation_mode": "space_opera"}, reset=(),
                expected_revision=initial.revision, observed_at=NOW,
            )
        changes = {f"{GROUP}.{name}": "x" * limit for name, limit in FIELD_LIMITS.items()}
        with self.assertRaises(ConfigurationError):
            self.profile_owner.write(
                target, self.profile_fields, changes=changes, reset=(),
                expected_revision=initial.revision, observed_at=NOW,
            )
        unchanged = self.profile_owner.read(target, self.profile_fields)
        self.assertEqual(unchanged.fields[f"{GROUP}.world_adaptation_mode"].value, "auto")
        self.assertTrue(all(not item.value for name, item in unchanged.fields.items()
                            if name != f"{GROUP}.world_adaptation_mode"))


if __name__ == "__main__":
    unittest.main()
