"""V1 learning relationship nodes retain their material and remain attributable."""

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from companion_v2.foundation.refs import ScopeKind
from companion_v2.knowledge.catalog import KnowledgeCatalog, MemberEntry, SourceBinding
from companion_v2.knowledge.members import select_member_clues
from companion_v2.legacy.data_migration import build_data_plan, map_legacy_worldbook
from companion_v2.storage.runtime import StorageRuntime


class LegacySocialProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="v1-learning-social-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def plan(self, payload):
        (self.root / "companions.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return build_data_plan(self.root)

    def test_profile_replaces_original_entries_and_retains_notes_memories_and_aliases(self):
        plan = self.plan({"worldbook_entries": [
            {"__template_key": "user", "scope": ["200"], "name": "旧称呼", "content": "旧资料"}],
            "worldbook_member_profiles": {"200": {
                "name": "阿岚", "aliases": ["岚岚"], "observed_names": ["旧名片"],
                "content": "偏爱安静的聊天", "identity_note": "经常讨论观星",
                "boundary_note": "不喜欢拿昵称开玩笑",
                "important_memories": [{"title": "相处印象", "content": "习惯先听别人讲完",
                                        "privacy": "internal", "weight": 80}],
                "pending_observations": [{"content": "尚未确认的猜测"}],
            }}})
        entries, members, _, _ = map_legacy_worldbook(plan, confirm_member_ids=True)
        self.assertEqual(len(members), 1)
        member = members[0]
        self.assertEqual(member.content, "偏爱安静的聊天")
        self.assertEqual(member.identity_note, "经常讨论观星")
        self.assertEqual(member.boundary_note, "不喜欢拿昵称开玩笑")
        self.assertEqual(member.aliases, ("岚岚", "旧名片"))
        self.assertEqual(member.important_memories[0].content, "习惯先听别人讲完")
        self.assertEqual(MemberEntry.restore(member.document), member)
        prompt = select_member_clues(members, text="晚上好", native_account_id="200").prompt(char_limit=1200)
        for text in ("偏爱安静的聊天", "经常讨论观星", "不喜欢拿昵称开玩笑", "习惯先听别人讲完"):
            self.assertIn(text, prompt)
        for text in ("旧资料", "尚未确认的猜测"):
            self.assertNotIn(text, prompt)
        preview = plan.document()["worldbook"]
        self.assertEqual((preview["member_count"], preview["member_profile_count"], preview["available_count"]), (1, 1, 1))
        self.assertTrue(preview["requires_id_confirmation"])
        self.assertNotIn("习惯先听别人讲完", json.dumps(preview, ensure_ascii=False))

    def test_disabled_deleted_and_merged_profiles_are_not_resurrected_from_source_entries(self):
        plan = self.plan({"worldbook_entries": [
            {"__template_key": "user", "scope": [account], "name": "旧成员", "content": "旧正文"}
            for account in ("200", "201", "202")],
            "worldbook_member_profiles": {"200": {"content": "禁用资料", "enabled": False},
                                          "202": {"content": "合并资料", "merged_into_user_id": "203"}},
            "worldbook_deleted_member_ids": ["201"]})
        self.assertEqual(map_legacy_worldbook(plan, confirm_member_ids=True)[1], ())

    def test_multiple_source_entries_for_one_account_are_one_usable_node(self):
        plan = self.plan({"worldbook_entries": [
            {"__template_key": "user", "scope": ["200"], "name": "阿岚", "content": "喜欢观星", "priority": 120},
            {"__template_key": "user", "scope": ["200"], "name": "岚岚", "content": "习惯早起", "priority": 100}]})
        members = map_legacy_worldbook(plan, confirm_member_ids=True)[1]
        self.assertEqual(len(members), 1)
        self.assertEqual(plan.document()["worldbook"]["member_count"], 1)
        selection = select_member_clues(members, text="早上好", native_account_id="200")
        self.assertEqual(len(selection.clues), 1)
        self.assertIn("喜欢观星", selection.prompt(char_limit=1200))
        self.assertIn("习惯早起", selection.prompt(char_limit=1200))

    def test_memory_visibility_depends_on_its_owner_and_current_window(self):
        member = MemberEntry("member", name="阿岚", declared_account_ids=("200",),
            important_memories=[{"content": "内部印象", "privacy": "internal"},
                                {"content": "公开经历", "privacy": "public"},
                                {"content": "私人经历", "privacy": "private"},
                                {"content": "已停用记忆", "enabled": False},
                                {"content": "未识别隐私", "privacy": "unknown"}])
        self_selection = select_member_clues((member,), text="你好", native_account_id="200")
        mentioned = select_member_clues((member,), text="阿岚最近如何", native_account_id="201")
        group_prompt = self_selection.prompt(char_limit=1200)
        self.assertIn("内部印象（不当作已确认事实）", group_prompt)
        self.assertIn("公开经历", group_prompt)
        self.assertNotIn("私人经历", group_prompt)
        self.assertIn("私人经历", self_selection.prompt(char_limit=1200, private_chat=True))
        self.assertNotIn("私人经历", mentioned.prompt(char_limit=1200, private_chat=True))
        self.assertNotIn("已停用记忆", group_prompt)
        self.assertNotIn("未识别隐私", group_prompt)

    def test_group_mapping_keeps_the_full_social_material_in_the_mapped_group(self):
        from astrbot_host.legacy_group_data_api import LegacyGroupDataWebAPI

        plan = self.plan({"worldbook_member_profiles": {"200": {
            "name": "阿岚", "content": "群内相处资料", "identity_note": "身份备注",
            "boundary_note": "相处边界", "important_memories": [{"content": "群内印象"}],
            "projection_kind": "group_observation", "group_observation_scope_ids": ["789"],
        }}})
        members = map_legacy_worldbook(plan, source_group_id="789", confirm_member_ids=True,
                                      include_group=True)[3]
        mapped = LegacyGroupDataWebAPI._remap_group_members(members, "789", "790")
        self.assertEqual(mapped[0].group_ids, ("790",))
        self.assertEqual(mapped[0].identity_note, "身份备注")
        self.assertEqual(mapped[0].boundary_note, "相处边界")
        self.assertEqual(mapped[0].important_memories[0].content, "群内印象")

    def test_long_current_speaker_material_is_bounded_without_dropping_the_member(self):
        member = MemberEntry("member", name="阿岚", declared_account_ids=("200",), content="很长的相处记录" * 100,
                             identity_note="身份备注" * 100, boundary_note="相处边界" * 100)
        prompt = select_member_clues((member,), text="你好", native_account_id="200").prompt(char_limit=200)
        self.assertIn("当前发言者", prompt)
        self.assertIn("阿岚", prompt)
        self.assertLessEqual(len(prompt), 200)

    def test_reimport_updates_impressions_and_remains_idempotent(self):
        from astrbot_host.legacy_api import LegacyMigrationWebAPI

        runtime = StorageRuntime.open(data_root=self.root / "v2", installation_id="install")
        self.addCleanup(runtime.close)
        api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
        api.controller = SimpleNamespace(runtime=runtime, now=lambda: datetime.now(timezone.utc))
        context = SimpleNamespace(scope=SimpleNamespace(installation_id="install", kind=ScopeKind.PRIVATE,
            native_scope_id="200"), role_binding=SimpleNamespace(role=SimpleNamespace(subject_id="role-a")))
        payload = {"worldbook_member_profiles": {"200": {"name": "阿岚", "content": "喜欢观星",
            "important_memories": [{"content": "旧印象"}]}}}
        first = api._import_legacy_worldbook(self.plan(payload), context, "", confirm_member_ids=True)
        second = api._import_legacy_worldbook(self.plan(payload), context, "", confirm_member_ids=True)
        payload["worldbook_member_profiles"]["200"]["important_memories"][0]["content"] = "更正后的印象"
        third = api._import_legacy_worldbook(self.plan(payload), context, "", confirm_member_ids=True)
        self.assertEqual((first["members_state"], second["members_state"], third["members_state"]),
                         ("imported", "unchanged", "imported"))
        version = KnowledgeCatalog(runtime).get(SourceBinding("install", role_id="role-a", persona_id="role-a"),
            api._worldbook_source_id("", category="members"))
        self.assertEqual(version.revision, 2)
        self.assertEqual(version.members[0].important_memories[0].content, "更正后的印象")
