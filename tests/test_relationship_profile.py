"""Manual relationship details stay with one person and one role."""

from dataclasses import replace
import json
import unittest

from companion_v2.execution.models import TaskContext
from companion_v2.foundation.refs import AudienceRef, ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.relationships.profile import (
    FIELD_LIMITS,
    GROUP,
    ConversationRelationshipProfileContext,
    RelationshipProfileConfigurationOwner,
    configuration_fields,
    target_for,
)
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import NOW


class RelationshipProfileConversationTests(MessageFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.profile_context = ConversationRelationshipProfileContext(self.runtime)
        self.owner = RelationshipProfileConfigurationOwner(self.runtime)
        self.fields = configuration_fields()

    def save(self, name, value, *, context=None):
        target = target_for(context or self.context)
        current = self.owner.read(target, self.fields)
        return self.owner.write(
            target, self.fields, changes={f"{GROUP}.{name}": value}, reset=(),
            expected_revision=current.revision, observed_at=NOW,
        )

    async def test_sealed_private_reply_uses_only_its_persons_manual_relationship_profile(self):
        self.save("default_nickname", "小舟")
        self.save("role_relation", "她是角色确认过的搭档。")
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        saved = json.loads(self.messages.batch(batch)["contributions_json"])
        snapshot = saved["relationship_profile"]

        self.assertEqual(snapshot["role_id"], self.context.role_binding.role.subject_id)
        self.assertEqual(snapshot["subject_id"], self.context.actor.subject.subject_id)
        request = self.messages._request(self.messages.batch(batch), self.context, NOW)
        self.assertIn("【当前私聊关系资料】", request.instruction)
        self.assertIn("对用户的称呼：小舟", request.instruction)
        self.assertIn("用户与角色的关系：她是角色确认过的搭档。", request.instruction)
        self.assertIn("不主动罗列生日、职业等个人信息", request.instruction)

        other_subject = SubjectRef(self.context.scope.installation_id, SubjectKind.HUMAN, "other-person")
        other_actor = replace(self.context.actor, subject=other_subject)
        other_context = TaskContext(
            other_actor, self.context.role_binding, AudienceRef(self.context.scope, (other_subject,)))
        self.assertIsNone(self.profile_context.capture(other_context, NOW))
        with self.assertRaisesRegex(Exception, "does not match this person"):
            self.profile_context.instruction(snapshot, other_context)

    async def test_group_context_cannot_capture_private_relationship_details(self):
        group_scope = ScopeRef(
            self.context.scope.installation_id, self.context.scope.platform, ScopeKind.GROUP,
            "group-profile-test", bot_id=self.context.scope.bot_id,
            account_id=self.context.scope.account_id,
            conversation_id="group-profile-test", session_id=self.context.scope.session_id,
        )
        group_context = TaskContext(
            self.context.actor, replace(self.context.role_binding, scope=group_scope),
            AudienceRef(group_scope, (self.context.actor.subject,)),
        )
        self.save("default_nickname", "小舟")
        self.assertIsNone(self.profile_context.capture(group_context, NOW))

    async def test_relationship_profile_field_limits_are_bounded(self):
        target = target_for(self.context)
        current = self.owner.read(target, self.fields)
        with self.assertRaisesRegex(ValueError, "no longer than"):
            self.owner.write(
                target, self.fields,
                changes={f"{GROUP}.interaction": "x" * (FIELD_LIMITS["interaction"] + 1)},
                reset=(), expected_revision=current.revision, observed_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
