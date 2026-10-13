"""Migrated relationship descriptions reach native AstrBot requests with their scope intact."""

import unittest
from unittest.mock import Mock, patch

from astrbot.core.provider.entities import ProviderRequest
from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA, inject_core_reply_prompt
from astrbot_host.core_reply_telemetry import prepare_core_reply_telemetry
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.execution.models import digest
from companion_v2.knowledge.catalog import EntryDocument, KnowledgeCatalog, MemberEntry, SourceBinding
from companion_v2.knowledge.configuration import KnowledgeConfigurationOwner, configuration_fields, target_for
from tests.group_host_support import GroupFixture


MEMBER_BACKGROUND = "偏好安静地聊观星，习惯先听别人说完；以前一起聊过秋天的星空。"
LOCAL_KNOWLEDGE = "本群的观星活动通常在周末，聊天时先征求大家的时间。"


class CoreReplyKnowledgeTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = await self.start_host()
        self.catalog = KnowledgeCatalog(self.app.runtime)
        prepared, _, _ = await self.prepare("knowledge-bootstrap")
        self.context = prepared["context"]
        self.configure({"knowledge.member_recognition_enabled": True})

    def configure(self, changes, *, context=None):
        owner = KnowledgeConfigurationOwner(self.app.runtime)
        target = target_for(context) if context is not None else ConfigTarget(
            self.app.runtime.installation_id, ConfigLayer.INSTALLATION)
        fields = configuration_fields()
        owner.write(target, fields, changes=changes, reset=(),
                    expected_revision=owner.read(target, fields).revision, observed_at=self.clock.now())

    def binding(self):
        scope = self.context.scope
        return SourceBinding(scope.installation_id, role_id=self.context.role_binding.role.subject_id,
                             persona_id=self.context.role_binding.role.subject_id,
                             scope_kind=scope.kind, native_scope_ids=(scope.native_scope_id,),
                             scope_route=(scope.platform, scope.bot_id, scope.account_id))

    def store(self, *, source_id="v1-members", binding=None, members=None, entries=(), code="legacy_v1_imported"):
        binding = binding or self.binding()
        if members is None:
            members = (MemberEntry("member-200", name="阿岚", aliases=("岚岚",),
                                   declared_account_ids=("200",), content=MEMBER_BACKGROUND,
                                   group_ids=(self.context.scope.native_scope_id,)),)
        self.catalog.save(binding, source_id=source_id, locator="synthetic-v1-import", format="worldbook",
                          content_digest=digest([item.document for item in (*entries, *members)]),
                          entries=entries, members=members, issues=(), at=self.clock.now(), code=code)
        return binding

    async def prepare(self, identifier, *, target="group-a", sender="200", text="晚上好", event=None):
        event = event or self.group_event(target, identifier, sender, text=text)
        result = await self.controller.prepare_core_reply(event)
        self.assertTrue(result.is_success, result.failure)
        prepared = result.unwrap()
        await prepared["native_source_future"]
        event.set_extra(CORE_REPLY_CONTEXT_EXTRA, {"prepared": prepared})
        request = ProviderRequest(prompt=text, system_prompt="AstrBot 当前人格",
                                  contexts=[{"role": "assistant", "content": "已有的原生会话历史"}])
        inject_core_reply_prompt(event, request)
        return prepared, request, event

    def assert_core_only(self):
        self.assertEqual(self.app.runtime.read_all("SELECT batch_id FROM conversation_batches", ()), ())
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertTrue(all(not platform.client._api._wsr_api.calls for platform in self.native.platforms.values()))

    def states(self, prepared):
        return {item["purpose"]: item["state"] for item in prepared["context_materials"]}

    async def test_migrated_descriptions_and_local_knowledge_reach_actual_system_prompt(self):
        self.store(entries=(EntryDocument("group-worldbook", LOCAL_KNOWLEDGE),))
        self.configure({"knowledge.source_ids": "kb:keep-native"})
        official_reader = Mock(side_effect=AssertionError("official KB belongs to AstrBot"))
        self.app.messages.knowledge.official_candidate_reader = official_reader

        prepared, request, event = await self.prepare("knowledge-injected")

        self.assertIn(MEMBER_BACKGROUND, request.system_prompt)
        self.assertIn(LOCAL_KNOWLEDGE, request.system_prompt)
        self.assertIn("当前发言者（账号 200 由运行时认证", request.system_prompt)
        self.assertTrue(request.system_prompt.startswith("AstrBot 当前人格\n\n"))
        self.assertEqual(request.prompt, "晚上好")
        self.assertEqual(request.contexts, [{"role": "assistant", "content": "已有的原生会话历史"}])
        inject_core_reply_prompt(event, request)
        self.assertEqual(request.system_prompt.count(MEMBER_BACKGROUND), 1)
        state = prepare_core_reply_telemetry(event, request, application=self.app,
                                            submit=lambda job: None, now=self.clock.now)
        material_states = {item["purpose"]: item["state"] for item in state["record"]["materials"]}
        self.assertEqual(material_states["knowledge_reference"], "ready")
        self.assertEqual(material_states["knowledge_member_clue"], "ready")
        published = self.app.runtime.read_all(
            "SELECT native_scope_id, account_id, scope_kind FROM sources WHERE owner='knowledge.v2'", ())
        self.assertEqual(len(published), 2)
        self.assertTrue(all((row["native_scope_id"], row["account_id"], row["scope_kind"]) ==
                            ("300", "100", "group") for row in published))
        official_reader.assert_not_called()
        self.assert_core_only()

    async def test_member_background_does_not_follow_group_account_or_persona_switch(self):
        self.store(entries=(EntryDocument("group-worldbook", LOCAL_KNOWLEDGE),))
        for target in ("group-b", "group-c"):
            with self.subTest(target=target):
                prepared, request, _ = await self.prepare("knowledge-isolation-" + target, target=target)
                self.assertNotIn(MEMBER_BACKGROUND, request.system_prompt)
                self.assertNotIn(LOCAL_KNOWLEDGE, request.system_prompt)
                self.assertEqual(self.states(prepared)["knowledge_member_clue"], "empty")
        event = self.group_event(identifier="knowledge-other-persona")
        self.native.selections[event.unified_msg_origin] = "second"
        prepared, request, _ = await self.prepare("knowledge-other-persona", event=event)
        self.assertNotIn(MEMBER_BACKGROUND, request.system_prompt)
        self.assertNotIn(LOCAL_KNOWLEDGE, request.system_prompt)
        self.assertEqual(self.states(prepared)["knowledge_member_clue"], "empty")
        self.native.selections[event.unified_msg_origin] = "original"
        private = self.event(identifier="knowledge-private-isolation", text="晚上好")
        _, request, _ = await self.prepare("knowledge-private-isolation", event=private)
        self.assertNotIn(MEMBER_BACKGROUND, request.system_prompt)
        self.assertNotIn(LOCAL_KNOWLEDGE, request.system_prompt)
        self.assert_core_only()

    async def test_v1_learning_profile_and_impression_reach_a_native_reply_without_name_trigger(self):
        from companion_v2.legacy.data_migration import _member_profiles, map_legacy_worldbook
        from types import SimpleNamespace

        profiles, _ = _member_profiles({"worldbook_member_profiles": {"200": {
            "name": "阿岚", "content": "偏爱安静的聊天", "identity_note": "常聊观星",
            "boundary_note": "不喜欢拿昵称开玩笑",
            "important_memories": [{"content": "习惯先听别人讲完", "privacy": "internal"}],
        }}})
        members = map_legacy_worldbook(SimpleNamespace(worldbook_items=(), member_profiles=profiles),
                                      confirm_member_ids=True)[1]
        self.store(binding=SourceBinding(self.context.scope.installation_id,
            role_id=self.context.role_binding.role.subject_id), members=members)
        prepared, request, _ = await self.prepare("learning-social-member", text="今天有点累")
        for material in ("偏爱安静的聊天", "常聊观星", "不喜欢拿昵称开玩笑", "习惯先听别人讲完"):
            self.assertIn(material, request.system_prompt)
        self.assertEqual(self.states(prepared)["knowledge_member_clue"], "ready")
        self.assert_core_only()

    async def test_nickname_does_not_bind_member_but_unique_text_mention_keeps_attribution(self):
        self.store()
        event = self.group_event(identifier="knowledge-name-only", sender="201", text="晚上好")
        event.message_obj.sender.nickname = "阿岚"
        prepared, request, _ = await self.prepare("knowledge-name-only", event=event)
        self.assertNotIn(MEMBER_BACKGROUND, request.system_prompt)
        self.assertEqual(self.states(prepared)["knowledge_member_clue"], "empty")
        _, request, _ = await self.prepare("knowledge-mentioned", sender="201", text="岚岚会来吗")
        self.assertIn(MEMBER_BACKGROUND, request.system_prompt)
        self.assertIn("按本轮提及选出，未归属于当前发言者", request.system_prompt)
        self.assertNotIn("当前发言者（账号 200 由运行时认证", request.system_prompt)
        self.assert_core_only()

    async def test_ambiguous_alias_and_duplicated_declared_account_never_pick_a_person(self):
        self.store(members=(
            MemberEntry("alan", name="阿岚", aliases=("岚岚",), declared_account_ids=("200",),
                        content=MEMBER_BACKGROUND),
            MemberEntry("other", name="小岚", aliases=("岚岚",), declared_account_ids=("202",),
                        content="另一个成员喜欢热闹的活动。"),
        ))
        _, request, _ = await self.prepare("knowledge-ambiguous", sender="201", text="岚岚今天在吗")
        self.assertIn("称呼无法唯一确定", request.system_prompt)
        self.assertNotIn(MEMBER_BACKGROUND, request.system_prompt)
        self.assertNotIn("另一个成员喜欢热闹的活动", request.system_prompt)
        self.store(members=(
            MemberEntry("alan", name="阿岚", declared_account_ids=("200",), content=MEMBER_BACKGROUND),
            MemberEntry("other", name="小岚", declared_account_ids=("200",), content="另一个候选项。"),
        ))
        prepared, request, _ = await self.prepare("knowledge-duplicated-account")
        self.assertNotIn(MEMBER_BACKGROUND, request.system_prompt)
        self.assertNotIn("另一个候选项", request.system_prompt)
        self.assertEqual(self.states(prepared)["knowledge_member_clue"], "empty")
        self.assert_core_only()

    async def test_window_disable_and_source_retraction_remove_material_on_next_turn(self):
        binding = self.store(entries=(EntryDocument("group-worldbook", LOCAL_KNOWLEDGE),))
        _, enabled, _ = await self.prepare("knowledge-before-disable")
        self.assertIn(MEMBER_BACKGROUND, enabled.system_prompt)
        self.configure({"knowledge.member_recognition_enabled": False, "knowledge.inject_enabled": False},
                       context=self.context)
        prepared, disabled, _ = await self.prepare("knowledge-disabled")
        self.assertNotIn(MEMBER_BACKGROUND, disabled.system_prompt)
        self.assertNotIn(LOCAL_KNOWLEDGE, disabled.system_prompt)
        self.assertEqual(self.states(prepared)["knowledge_member_clue"], "empty")
        self.assertEqual(self.states(prepared)["knowledge_reference"], "empty")
        self.configure({"knowledge.member_recognition_enabled": True, "knowledge.inject_enabled": True},
                       context=self.context)
        self.catalog.retire(binding, "v1-members", at=self.clock.now())
        _, retired, _ = await self.prepare("knowledge-retired")
        self.assertNotIn(MEMBER_BACKGROUND, retired.system_prompt)
        self.assertNotIn(LOCAL_KNOWLEDGE, retired.system_prompt)
        self.assert_core_only()

    async def test_knowledge_and_member_failures_are_independent_optional_sections(self):
        self.store(entries=(EntryDocument("group-worldbook", LOCAL_KNOWLEDGE),))
        owner = self.app.messages.knowledge
        with patch.object(owner, "background_contributions", side_effect=OSError("knowledge unavailable")):
            prepared, request, _ = await self.prepare("knowledge-background-failed")
        self.assertIn(MEMBER_BACKGROUND, request.system_prompt)
        self.assertEqual(self.states(prepared)["knowledge_reference"], "unavailable")
        self.assertEqual(self.states(prepared)["knowledge_member_clue"], "ready")
        with patch.object(owner, "member_contribution", side_effect=OSError("members unavailable")):
            prepared, request, _ = await self.prepare("knowledge-members-failed")
        self.assertIn(LOCAL_KNOWLEDGE, request.system_prompt)
        self.assertNotIn(MEMBER_BACKGROUND, request.system_prompt)
        self.assertEqual(self.states(prepared)["knowledge_reference"], "ready")
        self.assertEqual(self.states(prepared)["knowledge_member_clue"], "unavailable")
        self.assert_core_only()

    async def test_private_turn_uses_role_background_but_ignores_group_only_member_entries(self):
        self.store(binding=SourceBinding(self.app.runtime.installation_id,
                                        role_id=self.context.role_binding.role.subject_id),
                   members=(MemberEntry("private-member", name="阿岚", declared_account_ids=("200",),
                                        content="喜欢在私聊里慢慢分享读书感想。"),
                            MemberEntry("group-only", name="群内称呼", declared_account_ids=("200",),
                                        content=MEMBER_BACKGROUND, group_ids=("300",))),
                   entries=(EntryDocument("role-worldbook", "角色喜欢用轻松的语气聊书。"),), code="")
        private = self.event(identifier="knowledge-private-role", text="晚上好")
        prepared, request, _ = await self.prepare("knowledge-private-role", event=private)
        self.assertIn("喜欢在私聊里慢慢分享读书感想", request.system_prompt)
        self.assertIn("角色喜欢用轻松的语气聊书", request.system_prompt)
        self.assertNotIn(MEMBER_BACKGROUND, request.system_prompt)
        self.assertEqual(self.states(prepared)["knowledge_member_clue"], "ready")
        self.assert_core_only()


if __name__ == "__main__":
    unittest.main()
