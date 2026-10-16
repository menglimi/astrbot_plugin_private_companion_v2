from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from companion_v2.legacy.data_migration import (
    build_data_plan,
    load_reference_image,
    load_reaction_asset,
    map_legacy_worldbook,
    next_reaction_batch,
    next_journal_batch,
)
from companion_v2.foundation.refs import ScopeKind
from companion_v2.knowledge.catalog import KnowledgeCatalog, SourceBinding
from companion_v2.storage.runtime import StorageRuntime


ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0N8AAAAASUVORK5CYII="
)
SECOND_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXmEAAAAASUVORK5CYII="
)


class LegacyDataMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-legacy-data-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write_reaction_catalog(self, files):
        library = self.root / "reaction_expression_library"
        images = library / "images"
        images.mkdir(parents=True, exist_ok=True)
        items = []
        for filename, content, metadata in files:
            (images / filename).write_bytes(content)
            items.append({"filename": filename, "stored_name": filename,
                          "sha256": hashlib.sha256(content).hexdigest(), **metadata})
        (library / "catalog.json").write_text(
            json.dumps({"version": 2, "items": items}, ensure_ascii=False), encoding="utf-8")

    def write_profile(self, payload):
        (self.root / "companions.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_preview_maps_reaction_metadata_and_only_group_aggregates(self):
        self.write_reaction_catalog([("laugh.png", ONE_PIXEL_PNG, {
            "name": "笑哭", "description": "轻松回应", "visible_text": "哈哈",
            "tags": ["接梗"], "emotions": ["开心"], "intents": ["回应"],
        })])
        (self.root / "companions.json").write_text(json.dumps({"groups": {
            "123": {
                "members": {"200": {"name": "小禾", "count": 5,
                                     "recent_phrases": ["私密旧文本不应进入新提示"]},
                            "201": {"name": "阿青", "count": 3}},
                "relationship_edges": {"200|201": {"a": "200", "b": "201", "count": 2,
                    "tone": {"玩笑": 2}, "last_ts": 1790000000}},
            },
        }}, ensure_ascii=False), encoding="utf-8")

        plan = build_data_plan(self.root)
        document = plan.document(source_group_id="123")

        self.assertEqual(len(plan.reaction_assets), 1)
        self.assertEqual(plan.reaction_assets[0].metadata["intents"], ["回应"])
        self.assertEqual(document["reaction_assets"]["ready"], 1)
        self.assertEqual(document["selected_group"]["edge_count"], 1)
        self.assertNotIn("私密旧文本", json.dumps(document, ensure_ascii=False))
        self.assertNotIn("recent_phrases", json.dumps(document, ensure_ascii=False))
        self.assertEqual(plan.group_networks[0]["edges"][0]["tone"], "banter")
        self.assertEqual(plan.group_networks[0]["members"]["200"]["evidence_basis"],
                         "v1_group_aggregate")

    def test_duplicate_assets_are_hash_deduplicated_and_batch_continues(self):
        self.write_reaction_catalog([
            ("one.png", ONE_PIXEL_PNG, {"name": "一"}),
            ("same.png", ONE_PIXEL_PNG, {"name": "重复"}),
        ])
        plan = build_data_plan(self.root)

        self.assertEqual(len(plan.reaction_assets), 1)
        self.assertEqual(next_reaction_batch(plan)[0].sha256, hashlib.sha256(ONE_PIXEL_PNG).hexdigest())
        self.assertEqual(plan.document(existing_reaction_ids={plan.reaction_assets[0].sha256})[
            "reaction_assets"]["ready"], 0)

    def test_unsafe_paths_missing_files_and_catalog_hash_mismatch_are_reported(self):
        library = self.root / "reaction_expression_library"
        images = library / "images"
        images.mkdir(parents=True)
        (images / "valid.png").write_bytes(ONE_PIXEL_PNG)
        (library / "catalog.json").write_text(json.dumps({"version": 2, "items": [
            {"stored_name": "../escape.png", "filename": "escape.png"},
            {"stored_name": "missing.png", "filename": "missing.png"},
            {"stored_name": "valid.png", "filename": "valid.png", "sha256": "0" * 64},
        ]}), encoding="utf-8")

        plan = build_data_plan(self.root)

        self.assertEqual(plan.reaction_assets, ())
        self.assertEqual({item["reason"] for item in plan.reaction_rejected},
                         {"invalid_filename", "image_missing", "catalog_hash_mismatch"})

    def test_asset_is_rechecked_after_preview(self):
        self.write_reaction_catalog([("one.png", ONE_PIXEL_PNG, {})])
        plan = build_data_plan(self.root)
        item = plan.reaction_assets[0]
        (self.root / item.relative_path).write_bytes(ONE_PIXEL_PNG + b"changed")

        with self.assertRaisesRegex(ValueError, "image_changed_after_preview"):
            load_reaction_asset(self.root, item)

    def test_reference_gallery_and_wardrobe_preview_preserve_text_and_enforce_role_acl(self):
        reference_directory = self.root / "photo_reference_images"
        asset_directory = self.root / "photo_reference_assets"
        reference_directory.mkdir()
        asset_directory.mkdir()
        (reference_directory / "portrait.png").write_bytes(ONE_PIXEL_PNG)
        (asset_directory / "shared.png").write_bytes(ONE_PIXEL_PNG)
        (asset_directory / "private.png").write_bytes(SECOND_PIXEL_PNG)
        (asset_directory / "route-restricted.png").write_bytes(SECOND_PIXEL_PNG)
        (asset_directory / "generation-disabled.png").write_bytes(SECOND_PIXEL_PNG)
        (asset_directory / "malformed-acl.png").write_bytes(SECOND_PIXEL_PNG)
        self.write_profile({
            "photo_reference_assets": [
                {"id": "role-wide", "scope": "relation_role", "path": "photo_reference_assets/shared.png",
                 "image_access": {"subject_ref": None, "allow_generation": True,
                     "readers": ["*"], "audiences": ["*"], "routes": ["*"]}},
                {"id": "restricted", "scope": "relation_role", "path": "photo_reference_assets/shared.png",
                 "image_access": {"subject_ref": None, "allow_generation": True,
                     "readers": ["owner"], "audiences": ["*"], "routes": ["*"]}},
                {"id": "private-user", "scope": "relation_user", "path": "photo_reference_assets/private.png",
                 "image_access": {"subject_ref": None, "allow_generation": True,
                     "readers": ["person:legacy-user"], "audiences": ["private:legacy-account"],
                     "routes": ["*"]}},
                {"id": "private-route-restricted", "scope": "relation_user",
                 "path": "photo_reference_assets/route-restricted.png",
                 "image_access": {"subject_ref": None, "allow_generation": True,
                     "readers": ["person:legacy-user"], "audiences": ["private:legacy-account"],
                     "routes": ["private:legacy-account"]}},
                {"id": "private-generation-disabled", "scope": "relation_user",
                 "path": "photo_reference_assets/generation-disabled.png",
                 "image_access": {"subject_ref": None, "allow_generation": False,
                     "readers": ["person:legacy-user"], "audiences": ["private:legacy-account"],
                     "routes": ["*"]}},
                {"id": "private-malformed-acl", "scope": "relation_user",
                 "path": "photo_reference_assets/malformed-acl.png",
                 "image_access": {"subject_ref": None, "allow_generation": True,
                     "readers": "person:legacy-user", "audiences": ["private:legacy-account"],
                     "routes": ["*"]}},
            ],
        })
        configuration = {
            "photo_reference_catalog": [
                {"id": "portrait", "source": "photo_reference_images/portrait.png",
                 "note": "主视觉", "reference_roles": ["identity"]},
                {"id": "remote", "source": "https://example.invalid/image.png"},
            ],
            "wardrobe_items": [
                {"id": "scarf", "name": "红围巾", "description": "羊毛材质", "tags": ["冬季"],
                 "source": "photo_reference_images/portrait.png"},
                {"id": "dress", "name": "白裙", "description": "仅保留文字描述",
                 "url": "https://example.invalid/dress.png"},
                {"id": "gloves", "name": "手套", "description": "没有旧图片"},
            ],
        }

        plan = build_data_plan(self.root, v1_configuration=configuration)
        preview = plan.document(reference_slots_available=24, wardrobe_slots_available=24)

        self.assertEqual(len(plan.reference_images), 2)
        self.assertEqual(preview["reference_images"]["batch_count"], 2)
        self.assertEqual({item.source_key for item in plan.reference_images},
                         {"catalog:portrait", "asset:private-user"})
        self.assertEqual(preview["wardrobe_items"]["batch_count"], 3)
        self.assertEqual(preview["wardrobe_items"]["image_count"], 1)
        self.assertEqual(preview["wardrobe_items"]["image_skipped_count"], 1)
        self.assertIn("remote_url_not_downloaded",
                      {item["reason"] for item in preview["reference_images"]["rejected"]})
        self.assertIn("image_access_not_role_wide",
                      {item["reason"] for item in preview["reference_images"]["rejected"]})
        self.assertGreaterEqual(sum(item["reason"] == "image_access_not_role_wide"
                                    for item in preview["reference_images"]["rejected"]), 4)
        self.assertNotIn("asset:role-wide",
                         {item.get("source_id") for item in preview["reference_images"]["rejected"]})
        self.assertEqual({item.name for item in plan.wardrobe_items}, {"红围巾", "白裙", "手套"})
        self.assertEqual(next(item for item in plan.wardrobe_items if item.name == "白裙").image_reason,
                         "remote_url_not_downloaded")

    def test_cleared_reference_catalog_does_not_restore_legacy_paths_and_rechecks_hash(self):
        directory = self.root / "photo_reference_images"
        directory.mkdir()
        source = directory / "portrait.png"
        source.write_bytes(ONE_PIXEL_PNG)
        self.write_profile({})
        configuration = {
            "photo_reference_catalog": [],
            "photo_reference_catalog_user_cleared": True,
            "photo_persona_reference_image_path": "photo_reference_images/portrait.png",
            "photo_reference_library": ["photo_reference_images/portrait.png"],
        }

        cleared = build_data_plan(self.root, v1_configuration=configuration)
        self.assertEqual(cleared.reference_images, ())

        catalogued = build_data_plan(self.root, v1_configuration={
            "photo_reference_catalog": [{"id": "portrait", "source": "photo_reference_images/portrait.png"}],
        })
        source.write_bytes(ONE_PIXEL_PNG + b"changed")
        with self.assertRaisesRegex(ValueError, "image_changed_after_preview"):
            load_reference_image(self.root, catalogued.reference_images[0])

    def test_owned_reaction_catalog_is_included_without_enabling_when_disabled(self):
        library = self.root / "owned_reaction_assets"
        library.mkdir()
        (library / "owned.png").write_bytes(ONE_PIXEL_PNG)
        plan = build_data_plan(self.root, v1_configuration={
            "owned_reaction_assets": [{"id": "owned-one", "file": "owned.png",
                "sha256": hashlib.sha256(ONE_PIXEL_PNG).hexdigest(), "tags": ["回应"]}],
            "enable_owned_reaction_asset_workbench": False,
        })

        self.assertEqual(len(plan.reaction_assets), 1)
        self.assertEqual(plan.reaction_assets[0].source_id, "private.owned_reaction_assets")
        self.assertFalse(plan.reaction_assets[0].enabled)

    def test_worldbook_maps_only_supported_scope_and_does_not_preview_content(self):
        self.write_profile({"worldbook_entries": [
            {"id": "setting", "name": "角色设定", "content": "普通世界资料",
             "__template_key": "role", "enabled": True},
            {"id": "member", "name": "阿禾", "content": "成员线索私密正文",
             "__template_key": "user", "scope": ["12345"]},
            {"id": "disabled-member", "name": "旧条目", "content": "禁用线索",
             "__template_key": "user", "scope": ["12345"], "enabled": False},
            {"id": "group", "name": "群设定", "content": "群内资料",
             "__template_key": "group", "scope": ["default:groupmessage:789"]},
            {"id": "opaque-group", "name": "不透明群设定", "content": "不透明群资料",
             "__template_key": "group", "scope": ["opaque room 7"]},
            {"id": "bad-member", "name": "未知账号", "content": "不能绑定",
             "__template_key": "user", "scope": ["friendmessage:12345"]},
            {"id": "bad-group", "name": "未知群", "content": "不能绑定",
             "__template_key": "group", "scope": ["friendmessage:789"]},
        ]})

        plan = build_data_plan(self.root)
        preview = plan.document(source_group_id="789")
        base_entries, members, group_entries, group_members = map_legacy_worldbook(
            plan, source_group_id="789", confirm_member_ids=False, include_group=True)
        confirmed_entries, confirmed_members, confirmed_group_entries, confirmed_group_members = map_legacy_worldbook(
            plan, source_group_id="789", confirm_member_ids=True, include_group=True)

        self.assertEqual((preview["worldbook"]["general_count"],
                          preview["worldbook"]["member_count"],
                          preview["worldbook"]["disabled_member_count"],
                          preview["worldbook"]["group_count"],
                          preview["worldbook"]["available_count"]), (1, 1, 1, 2, 3))
        self.assertEqual((len(base_entries), len(members), len(group_entries), len(group_members)),
                         (1, 0, 0, 0))
        self.assertEqual((len(confirmed_entries), len(confirmed_members),
                          len(confirmed_group_entries), len(confirmed_group_members)), (1, 1, 1, 0))
        self.assertEqual({item["reason"] for item in preview["worldbook"]["rejected"]},
                         {"member_scope_unmapped", "group_scope_invalid"})
        self.assertIn("opaque room 7",
                      {item["source_group_id"] for item in preview["worldbook"]["groups"]})
        self.assertNotIn("普通世界资料", json.dumps(preview, ensure_ascii=False))
        self.assertNotIn("成员线索私密正文", json.dumps(preview, ensure_ascii=False))
        self.assertNotIn("群内资料", json.dumps(preview, ensure_ascii=False))

    def test_group_member_profiles_are_kept_in_their_declared_group(self):
        self.write_profile({
            "worldbook_group_profiles": {
                "789": {"name": "甲群资料", "content": "甲群只读资料"},
                "790": {"name": "乙群资料", "content": "乙群只读资料"},
            },
            "worldbook_member_profiles": {
                "501": {"user_id": "501", "name": "甲群成员", "content": "甲群成员线索",
                    "projection_kind": "group_observation",
                    "group_observation_scope_ids": ["default:groupmessage:789"]},
                "502": {"user_id": "502", "name": "乙群成员", "content": "乙群成员线索",
                    "projection_kind": "group_observation",
                    "group_observation_scope_ids": ["default:groupmessage:790"]},
            },
        })

        plan = build_data_plan(self.root)
        first = map_legacy_worldbook(plan, source_group_id="789", confirm_member_ids=True,
                                     include_group=True)
        second = map_legacy_worldbook(plan, source_group_id="790", confirm_member_ids=True,
                                      include_group=True)
        preview = plan.document(source_group_id="789")

        self.assertEqual((len(first[2]), len(first[3])), (1, 1))
        self.assertEqual((len(second[2]), len(second[3])), (1, 1))
        self.assertEqual(first[3][0].declared_account_ids, ("501",))
        self.assertEqual(first[3][0].group_ids, ("789",))
        self.assertEqual(preview["worldbook"]["selected_group_member_profile_count"], 1)
        self.assertNotIn("甲群成员线索", json.dumps(preview, ensure_ascii=False))

    def test_host_import_writes_knowledge_with_role_and_group_scope_idempotently(self):
        from astrbot_host.legacy_api import LegacyMigrationWebAPI

        self.write_profile({"worldbook_entries": [
            {"id": "setting", "name": "海岛设定", "content": "普通世界资料",
             "__template_key": "role", "enabled": True},
            {"id": "member", "name": "阿禾", "content": "成员线索",
             "__template_key": "user", "scope": ["12345"]},
            {"id": "group", "name": "群设定", "content": "群内资料",
             "__template_key": "group", "scope": ["default:groupmessage:789"]},
        ], "worldbook_group_profiles": {
            "789": {"name": "群角色资料", "content": "额外群资料"},
        }, "worldbook_member_profiles": {
            "555": {"user_id": "555", "name": "群成员", "content": "群范围成员线索",
                "projection_kind": "group_observation",
                "group_observation_scope_ids": ["default:groupmessage:789"]},
        }})
        temporary = TemporaryDirectory(prefix="companion-v2-legacy-worldbook-")
        self.addCleanup(temporary.cleanup)
        runtime = StorageRuntime.open(data_root=Path(temporary.name) / "v2", installation_id="install")
        self.addCleanup(runtime.close)
        api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
        api.controller = SimpleNamespace(runtime=runtime, now=lambda: datetime.now(timezone.utc))
        plan = build_data_plan(self.root)
        context = SimpleNamespace(
            scope=SimpleNamespace(installation_id="install", kind=ScopeKind.GROUP,
                                  native_scope_id="v2-group-789"),
            role_binding=SimpleNamespace(role=SimpleNamespace(subject_id="role-a")))

        first = api._import_legacy_worldbook(plan, context, "789", confirm_member_ids=True)
        repeated = api._import_legacy_worldbook(plan, context, "789", confirm_member_ids=True)
        catalog = KnowledgeCatalog(runtime)
        base_binding = SourceBinding("install", role_id="role-a", persona_id="role-a")
        group_binding = SourceBinding("install", role_id="role-a", persona_id="role-a",
                                      native_scope_ids=("v2-group-789",), scope_kind=ScopeKind.GROUP)
        base = catalog.get(base_binding, api._worldbook_source_id("", category="entries"))
        members = catalog.get(base_binding, api._worldbook_source_id("", category="members"))
        group = catalog.get(group_binding, api._worldbook_source_id("", "789"))

        self.assertEqual((first["entries_imported"], first["members_imported"],
                          first["group_entries_imported"], first["group_members_imported"]),
                         (1, 1, 2, 1))
        self.assertEqual((repeated["entries_state"], repeated["members_state"],
                          repeated["group_state"]), ("unchanged", "unchanged", "unchanged"))
        self.assertEqual(base.entries[0].content, "普通世界资料")
        self.assertEqual(members.members[0].declared_account_ids, ("12345",))
        self.assertEqual(group.binding.native_scope_ids, ("v2-group-789",))
        self.assertEqual({item.content for item in group.entries}, {"群内资料", "额外群资料"})
        self.assertEqual(group.members[0].content, "群范围成员线索")
        other_group_binding = SourceBinding("install", role_id="role-a", persona_id="role-a",
            native_scope_ids=("v2-group-790",), scope_kind=ScopeKind.GROUP)
        self.assertIsNone(catalog.get(other_group_binding, api._worldbook_source_id("", "789")))

    def test_journals_are_previewed_without_body_and_continue_in_bounded_batches(self):
        diaries = [{"date": (date(2025, 1, 1) + timedelta(days=index)).isoformat(),
                    "body": f"合成日记 {index}"} for index in range(102)]
        self.write_profile({"bot_diaries": diaries,
            "daily_dream": {"content": "没有日期的旧梦", "afterglow": "片段"},
            "dream_fragments": ["只供合成测试的旧梦片段"]})

        plan = build_data_plan(self.root)
        batch = next_journal_batch(plan)
        remaining = next_journal_batch(plan, {item.key for item in batch})
        preview = plan.document()

        self.assertEqual(len(plan.journals), 102)
        self.assertEqual((len(batch), len(remaining)), (100, 2))
        self.assertEqual((preview["journals"]["batch_count"],
                          preview["journals"]["remaining_after_batch"]), (100, 2))
        self.assertEqual(preview["profile_data"]["dream_fragments"], 1)
        self.assertIn({"kind": "dream", "reason": "dream_date_invalid"},
                      preview["journals"]["rejected"])
        self.assertNotIn("合成日记", json.dumps(preview, ensure_ascii=False))
        self.assertNotIn("没有日期的旧梦", json.dumps(preview, ensure_ascii=False))
        self.assertNotIn("只供合成测试", json.dumps(preview, ensure_ascii=False))

    def test_each_persona_profile_is_previewed_separately(self):
        self.write_profile({"bot_diaries": [{"date": "2025-01-01", "body": "主角色日记"}]})
        persona_directory = self.root / "persona_profiles"
        persona_directory.mkdir()
        (persona_directory / "persona-a.json").write_text(
            json.dumps({"bot_diaries": [{"date": "2025-01-02", "body": "次人格日记"}]},
                       ensure_ascii=False), encoding="utf-8")

        primary = build_data_plan(self.root)
        secondary = build_data_plan(self.root, source_persona_id="persona-a")
        inventory = secondary.document()

        self.assertEqual([item.local_date for item in primary.journals], ["2025-01-01"])
        self.assertEqual([item.local_date for item in secondary.journals], ["2025-01-02"])
        self.assertEqual(inventory["source_persona_id"], "persona-a")
        self.assertEqual(inventory["selected_persona"]["state"], "ready")

    def test_group_network_preview_reports_members_and_edges_above_v2_limits(self):
        members = {f"member-{index:03d}": {"name": f"成员{index}", "count": index}
                   for index in range(520)}
        edges = {f"member-{index:03d}|member-{index + 1:03d}": {
            "a": f"member-{index:03d}", "b": f"member-{index + 1:03d}", "count": 1}
            for index in range(519)}
        members["invalid"] = None
        self.write_profile({"groups": {"789": {"members": members,
            "relationship_edges": edges}}})

        preview = build_data_plan(self.root).document(source_group_id="789")
        group = preview["selected_group"]

        self.assertEqual(group["member_count"], 512)
        self.assertEqual(group["edge_count"], 511)
        self.assertEqual(group["omitted_member_count"], 8)
        self.assertEqual(group["omitted_edge_count"], 8)
        self.assertEqual(group["rejected_member_count"], 1)
        self.assertNotIn("members", group)
        self.assertNotIn("edges", group)


if __name__ == "__main__":
    unittest.main()
