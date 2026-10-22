"""Exercise the legacy importer against the persistent host services."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from astrbot_host.legacy_api import LegacyMigrationWebAPI
from astrbot_host.multi_controller import AstrBotMultiController
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.execution.models import TaskError
from companion_v2.foundation.clock import DeterministicClock
from companion_v2.foundation.refs import RoleOwnerRef
from companion_v2.legacy.archive import verify_v1_archive
from companion_v2.legacy.data_migration import build_data_plan
from companion_v2.legacy.migration import LegacyMigration
from companion_v2.role_work.journal import JournalKey, JournalKind
from tests.multi_host_support import MultiNativeContext, multi_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_management_access import NOW


class LegacyDataPlanTokenTests(unittest.TestCase):
    def test_group_selection_order_preserves_plan_but_binding_changes_invalidate_it(self):
        api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
        data = SimpleNamespace(source_fingerprint="source", reaction_assets=())
        scope = SimpleNamespace(installation_id="installation", platform="qq", bot_id="bot",
            account_id="100", kind="private", native_scope_id="200")
        context = SimpleNamespace(scope=scope,
            role_binding=SimpleNamespace(role=SimpleNamespace(subject_id="role")))
        service = SimpleNamespace(reaction_owner=lambda _context: "reaction-owner")
        mappings = [{"owner_id": "b" * 64, "target_id": "group-b", "role_id": "role-b"},
                    {"owner_id": "a" * 64, "target_id": "group-a", "role_id": "role-a"}]

        def token(selected):
            return api._data_plan_token(data, context, service, "", "",
                memory_group_mappings=selected)

        preview_token = token(mappings)
        self.assertEqual(preview_token, token(list(reversed(mappings))))
        self.assertNotEqual(preview_token, token(mappings[:1]))
        for field, value in (("owner_id", "c" * 64), ("target_id", "another-group"),
                             ("role_id", "another-role")):
            with self.subTest(changed_binding=field):
                changed = [{**mappings[0], field: value}, mappings[1]]
                self.assertNotEqual(preview_token, token(changed))


class LegacyJournalMigrationHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_data_plan_sync_inventory_runs_off_the_event_loop(self):
        import astrbot_host.legacy_api as legacy_api_module
        from companion_v2.foundation.outcome import Outcome

        class EmptyQuery(dict):
            def getlist(self, key):
                value = self.get(key)
                return value if isinstance(value, list) else ([] if value is None else [value])

        session = SimpleNamespace()
        controller = SimpleNamespace(
            _control_lock=asyncio.Lock(), _terminated=False, session=session,
            last_session=None, runtime=object(), now=lambda: NOW,
            web_api=SimpleNamespace(target_inventory=lambda: []))
        api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
        api.controller = controller

        async def migration(_root_override, *, session):
            return object(), Path("synthetic-v1"), "test"

        api._migration = migration
        started, release = threading.Event(), threading.Event()
        worker_threads = []
        loop_thread = threading.get_ident()

        def slow_plan(_migration, _root, _session, *_args, **_kwargs):
            worker_threads.append(threading.get_ident())
            started.set()
            release.wait(2)
            return Outcome.success({"persona_sources": []})

        api._data_plan = slow_plan
        fake_request = SimpleNamespace(username="admin", query=EmptyQuery())
        try:
            with patch.object(legacy_api_module, "request", fake_request), \
                    patch.object(legacy_api_module, "dashboard_operator"):
                task = asyncio.create_task(api.data_plan())
                self.assertTrue(await asyncio.wait_for(asyncio.to_thread(started.wait, 1), timeout=2))
                self.assertNotEqual(worker_threads[0], loop_thread)
                self.assertFalse(task.done())
                release.set()
                response = await task
        finally:
            release.set()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["data"]["persona_destination_mapping"]["sources"], [])

    async def test_data_apply_sync_work_runs_off_the_event_loop(self):
        api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
        started, release = threading.Event(), threading.Event()
        worker_threads = []
        loop_thread = threading.get_ident()

        def slow_apply(*_args):
            worker_threads.append(threading.get_ident())
            started.set()
            release.wait(2)
            return "completed"

        api._data_apply_sync = slow_apply
        task = asyncio.create_task(api._data_apply(
            None, Path("synthetic-v1"), None, "token", "", "",
            False, False, False, False, False, False))
        try:
            self.assertTrue(await asyncio.wait_for(asyncio.to_thread(started.wait, 1), timeout=2))
            self.assertNotEqual(worker_threads[0], loop_thread)
            self.assertFalse(task.done())
            release.set()
            self.assertEqual(await task, "completed")
        finally:
            release.set()

    async def test_wardrobe_only_import_writes_native_role_item_without_importing_gallery(self):
        source = TemporaryDirectory(prefix="companion-v2-legacy-wardrobe-v1-")
        target = TemporaryDirectory(prefix="companion-v2-legacy-wardrobe-v2-")
        self.addCleanup(source.cleanup)
        self.addCleanup(target.cleanup)
        v1_root = Path(source.name)
        (v1_root / "companions.json").write_text("{}\n", encoding="utf-8", newline="\n")
        image_directory = v1_root / "photo_reference_images"
        image_directory.mkdir()
        from io import BytesIO
        from PIL import Image
        payload = BytesIO()
        Image.new("RGB", (12, 12), (24, 80, 140)).save(payload, format="PNG")
        image_directory.joinpath("scarf.png").write_bytes(payload.getvalue())
        migration = LegacyMigration(v1_root=v1_root, v1_configuration={"wardrobe_items": [{
            "id": "red-scarf", "name": "红围巾", "description": "羊毛，冬季佩戴",
            "tags": ["冬季"], "source": "photo_reference_images/scarf.png",
        }]})
        native = MultiNativeContext()
        native_types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, SimpleNamespace,
            SimpleNamespace, FakeReverseApi)
        clock = DeterministicClock.at(NOW)
        controller = AstrBotMultiController(native, multi_config(), Path(target.name) / "data",
            native_types=native_types, now=clock.now)
        try:
            (await controller.initialize_profile()).unwrap()
            (await controller.start()).unwrap()
            context = controller.session.authority.context("first", "role-a")
            session = SimpleNamespace(profile=SimpleNamespace(target=context),
                                      application=controller.session.application)
            api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
            api.controller = SimpleNamespace(runtime=controller.runtime, now=clock.now,
                                             data_root=Path(target.name) / "data")
            preview = api._data_plan(migration, v1_root, session,
                reference_slots_available=24, reference_bytes_available=24 * 20 * 1024 * 1024,
                wardrobe_slots_available=24).unwrap()
            self.assertEqual(preview["wardrobe_items"]["image_count"], 1)
            from astrbot_host.management_identity import dashboard_operator
            api._operator = lambda: dashboard_operator(
                controller.runtime, "migration-test-admin", at=clock.now())

            imported = api._data_apply_sync(migration, v1_root, session,
                plan_token=preview["plan_token"], source_group_id="", source_persona_id="",
                import_reactions=False, import_group_network=False, confirm_member_ids=False,
                import_journals=False, confirm_persona_mapping=False, import_worldbook=False,
                import_wardrobe_items=True, confirm_reference_persona_mapping=True)

            self.assertTrue(imported.is_success, imported.failure if not imported.is_success else "")
            receipt = imported.unwrap()["reference_images"]
            self.assertEqual((receipt["reference_created"], receipt["wardrobe_created"],
                              receipt["wardrobe_remaining"]), (1, 1, 0))
            application = controller.session.application
            owner = application.references.owner(context)
            repository = application.references.assets
            items = repository.list_items(owner)
            self.assertEqual([(item.name, item.description, item.asset_id is not None) for item in items],
                             [("红围巾", "羊毛，冬季佩戴", True)])
        finally:
            await controller.terminate()

    async def test_private_acl_reference_imports_into_the_selected_role_gallery(self):
        source = TemporaryDirectory(prefix="companion-v2-legacy-reference-v1-")
        target = TemporaryDirectory(prefix="companion-v2-legacy-reference-v2-")
        self.addCleanup(source.cleanup)
        self.addCleanup(target.cleanup)
        v1_root = Path(source.name)
        image_directory = v1_root / "photo_reference_assets"
        image_directory.mkdir()
        from io import BytesIO
        from PIL import Image
        payload = BytesIO()
        Image.new("RGB", (12, 12), (180, 36, 92)).save(payload, format="PNG")
        image_bytes = payload.getvalue()
        (image_directory / "portrait.png").write_bytes(image_bytes)
        (v1_root / "companions.json").write_text(json.dumps({
            "photo_reference_assets": [{
                "id": "private-portrait",
                "scope": "relation_user",
                "path": "photo_reference_assets/portrait.png",
                "title": "角色形象",
                "image_access": {
                    "subject_ref": None,
                    "allow_generation": True,
                    "readers": ["person:legacy-user"],
                    "audiences": ["private:legacy-account"],
                    "routes": ["*"],
                },
            }],
        }, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        migration = LegacyMigration(v1_root=v1_root, v1_configuration={})
        native = MultiNativeContext()
        native_types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, SimpleNamespace,
            SimpleNamespace, FakeReverseApi)
        clock = DeterministicClock.at(NOW)
        controller = AstrBotMultiController(native, multi_config(), Path(target.name) / "data",
            native_types=native_types, now=clock.now)
        try:
            (await controller.initialize_profile()).unwrap()
            (await controller.start()).unwrap()
            context = controller.session.authority.context("first", "role-a")
            session = SimpleNamespace(profile=SimpleNamespace(target=context),
                                      application=controller.session.application)
            api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
            api.controller = SimpleNamespace(runtime=controller.runtime, now=clock.now,
                                             data_root=Path(target.name) / "data")
            preview = api._data_plan(migration, v1_root, session,
                reference_slots_available=24, reference_bytes_available=24 * 20 * 1024 * 1024,
                wardrobe_slots_available=24).unwrap()
            self.assertEqual(preview["reference_images"]["batch_count"], 1)
            from astrbot_host.management_identity import dashboard_operator
            api._operator = lambda: dashboard_operator(
                controller.runtime, "migration-test-admin", at=clock.now())

            imported = api._data_apply_sync(migration, v1_root, session,
                plan_token=preview["plan_token"], source_group_id="", source_persona_id="",
                import_reactions=False, import_group_network=False, confirm_member_ids=False,
                import_journals=False, confirm_persona_mapping=False, import_worldbook=False,
                import_reference_images=True, confirm_reference_persona_mapping=True)

            self.assertTrue(imported.is_success, imported.failure if not imported.is_success else "")
            receipt = imported.unwrap()["reference_images"]
            self.assertEqual((receipt["reference_created"], receipt["reference_remaining"]), (1, 0))
            application = controller.session.application
            owner = application.references.owner(context)
            repository = application.references.assets
            assets = repository.list(owner)
            self.assertEqual([(asset.label, repository.get_payload(owner, asset.asset_id))
                              for asset in assets], [("角色形象", image_bytes)])
        finally:
            await controller.terminate()

    async def test_memory_database_snapshot_uses_data_apply_and_survives_host_restart(self):
        source = TemporaryDirectory(prefix="companion-v2-legacy-memory-v1-")
        target = TemporaryDirectory(prefix="companion-v2-legacy-memory-v2-")
        self.addCleanup(source.cleanup)
        self.addCleanup(target.cleanup)
        base = Path(source.name)
        v1_root = base / "astrbot_plugin_private_companion"
        v1_root.mkdir()
        (v1_root / "companions.json").write_text("{}\n", encoding="utf-8", newline="\n")
        memory_dir = base / "astrbot_plugin_memory_companion"
        memory_dir.mkdir()
        memory_path = memory_dir / "memory_companion.db"
        memory = sqlite3.connect(memory_path)
        memory.execute("PRAGMA journal_mode=WAL")
        memory.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, body TEXT)")
        memory.execute("CREATE TABLE timeline (id TEXT PRIMARY KEY, body TEXT)")
        memory.execute("CREATE TABLE review_queue (id TEXT PRIMARY KEY, state TEXT)")
        memory.execute("INSERT INTO memories VALUES ('m1', 'private fact')")
        memory.execute("INSERT INTO timeline VALUES ('t1', 'historical event')")
        memory.execute("INSERT INTO review_queue VALUES ('r1', 'pending')")
        memory.commit()

        data_root = Path(target.name) / "data"
        native = MultiNativeContext()
        native_types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, SimpleNamespace,
            SimpleNamespace, FakeReverseApi)
        clock = DeterministicClock.at(NOW)
        controller = AstrBotMultiController(native, multi_config(), data_root,
            native_types=native_types, now=clock.now)
        restarted = None
        try:
            (await controller.initialize_profile()).unwrap()
            (await controller.start()).unwrap()
            context = controller.session.authority.context("first", "role-a")
            session = SimpleNamespace(profile=SimpleNamespace(target=context),
                                      application=controller.session.application)
            migration = LegacyMigration(v1_root=v1_root)
            api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
            api.controller = SimpleNamespace(runtime=controller.runtime, now=clock.now,
                                             data_root=data_root)
            preview = api._data_plan(migration, v1_root, session).unwrap()
            self.assertEqual(preview["memory_database"]["state"], "ready")
            self.assertEqual(preview["memory_database"]["record_count"], 3)

            applied = (await api._data_apply(migration, v1_root, session,
                preview["plan_token"], "", "", False, False, False, False, False,
                False, False, True)).unwrap()
            archived = applied["memory_archive"]
            self.assertEqual(archived["table_counts"]["timeline"], 1)
            self.assertEqual(archived["table_counts"]["review_queue"], 1)
            archive_path = data_root / "legacy-v1-archives" / archived["archive_id"]
            self.assertEqual(verify_v1_archive(archive_path)["file_count"], 1)
            await controller.terminate()
            controller = None

            restarted = AstrBotMultiController(native, multi_config(), data_root,
                native_types=native_types, now=clock.now)
            (await restarted.initialize_profile()).unwrap()
            (await restarted.start()).unwrap()
            restored = sqlite3.connect(archive_path / "files" / "memory_companion.db")
            try:
                self.assertEqual(restored.execute("SELECT COUNT(*) FROM memories").fetchone()[0], 1)
                self.assertEqual(restored.execute("SELECT COUNT(*) FROM timeline").fetchone()[0], 1)
                self.assertEqual(restored.execute("SELECT state FROM review_queue").fetchone()[0], "pending")
            finally:
                restored.close()
        finally:
            if restarted is not None:
                await restarted.terminate()
            if controller is not None:
                await controller.terminate()
            memory.close()

    async def test_archive_import_accepts_live_rewrite_and_verifies_applied_snapshot(self):
        source = TemporaryDirectory(prefix="companion-v2-legacy-archive-v1-")
        target = TemporaryDirectory(prefix="companion-v2-legacy-archive-v2-")
        self.addCleanup(source.cleanup)
        self.addCleanup(target.cleanup)
        v1_root = Path(source.name)
        (v1_root / "companions.json").write_text("{}\n", encoding="utf-8", newline="\n")
        changing_file = v1_root / "cache.json"
        changing_file.write_bytes(b"version1")
        data_root = Path(target.name) / "data"
        native = MultiNativeContext()
        native_types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, SimpleNamespace,
            SimpleNamespace, FakeReverseApi)
        clock = DeterministicClock.at(NOW)
        controller = AstrBotMultiController(native, multi_config(), data_root,
            native_types=native_types, now=clock.now)
        try:
            (await controller.initialize_profile()).unwrap()
            (await controller.start()).unwrap()
            context = controller.session.authority.context("first", "role-a")
            session = SimpleNamespace(profile=SimpleNamespace(target=context),
                                      application=controller.session.application)
            migration = LegacyMigration(v1_root=v1_root)
            api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
            api.controller = SimpleNamespace(runtime=controller.runtime, now=clock.now,
                                             data_root=data_root)
            preview = api._data_plan(migration, v1_root, session).unwrap()

            changing_file.write_bytes(b"version2")
            result = (await api._data_apply(migration, v1_root, session,
                preview["plan_token"], "", "", False, False, False, False, False, False,
                True)).unwrap()

            archive_path = data_root / "legacy-v1-archives" / result["archive"]["archive_id"]
            self.assertNotEqual(preview["archive"]["fingerprint"], result["archive"]["archive_id"])
            self.assertEqual(verify_v1_archive(archive_path)["file_count"], 2)
            self.assertEqual((archive_path / "files" / "cache.json").read_bytes(), b"version2")
        finally:
            await controller.terminate()

    async def test_diary_fragment_write_retries_without_replaying_or_overwriting(self):
        source = TemporaryDirectory(prefix="companion-v2-legacy-journal-v1-")
        target = TemporaryDirectory(prefix="companion-v2-legacy-journal-v2-")
        self.addCleanup(source.cleanup)
        self.addCleanup(target.cleanup)
        v1_root = Path(source.name)
        (v1_root / "companions.json").write_text(json.dumps({
            "bot_diaries": [{
                "date": "2026-09-20",
                "body": "迁移正文",
                "summary": "迁移摘要",
                "dream_fragments": ["迁移片段一", {"text": "迁移片段二"}],
            }],
        }, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        native = MultiNativeContext()
        native_types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, SimpleNamespace,
            SimpleNamespace, FakeReverseApi)
        clock = DeterministicClock.at(NOW)
        controller = AstrBotMultiController(native, multi_config(), Path(target.name) / "data",
            native_types=native_types, now=clock.now)
        try:
            (await controller.initialize_profile()).unwrap()
            (await controller.start()).unwrap()
            context = controller.session.authority.context("first", "role-a")
            application = controller.session.application
            v1_migration = LegacyMigration(v1_root=v1_root)
            api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
            api.controller = SimpleNamespace(runtime=controller.runtime, now=clock.now)
            session = SimpleNamespace(profile=SimpleNamespace(target=context),
                                      application=application)
            journal_service = application.role_journal
            save_derivatives = journal_service.save_derivatives
            fail_once = True

            def fail_first_derivative(material, **kwargs):
                nonlocal fail_once
                if fail_once:
                    fail_once = False
                    raise TaskError("test_derivative_write_failed", "simulated interrupted write")
                return save_derivatives(material, **kwargs)

            journal_service.save_derivatives = fail_first_derivative

            async def apply_batch():
                preview = api._data_plan(v1_migration, v1_root, session).unwrap()
                return await api._data_apply(v1_migration, v1_root, session,
                    preview["plan_token"], "", "", False, False, False, True, True, False)

            first = (await apply_batch()).unwrap()
            self.assertEqual(first["journal_created"], 1)
            self.assertEqual(first["journal_derivatives_created"], 0)
            self.assertEqual(first["journal_derivatives_remaining"], 1)
            self.assertTrue(first["journal_errors"])

            # Changing an unrelated source must not strand a committed diary
            # whose derivative write needs to resume.
            profile_path = v1_root / "companions.json"
            changed_source = json.loads(profile_path.read_text(encoding="utf-8"))
            changed_source["unrelated_metadata"] = {"revision": 2}
            profile_path.write_text(json.dumps(changed_source, ensure_ascii=False) + "\n",
                                    encoding="utf-8", newline="\n")

            retry_preview = api._data_plan(v1_migration, v1_root, session).unwrap()
            self.assertEqual(retry_preview["journals"]["derivative_retry_count"], 1)
            retried = (await api._data_apply(v1_migration, v1_root, session,
                retry_preview["plan_token"], "", "", False, False, False, True, True, False)).unwrap()
            self.assertEqual(retried["journal_created"], 0)
            self.assertEqual(retried["journal_derivatives_created"], 1)
            self.assertEqual(retried["journal_remaining"], 0)
            self.assertEqual(retried["journal_derivatives_remaining"], 0)

            owner = RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                                 context.role_binding.role.subject_id)
            key = JournalKey(owner, JournalKind.DIARY, "2026-09-20")
            entry = journal_service.get(key)
            self.assertEqual(entry.draft.body, "迁移正文")
            self.assertEqual(journal_service.derivatives(key).material.dream_fragments,
                             ("迁移片段一", "迁移片段二"))

            # Older releases used the whole catalog hash in their operation ID.
            # Identical retained content is recognized without forging a receipt.
            with patch.object(LegacyMigrationWebAPI, "_legacy_journal_operation_id",
                              return_value="legacy-journal-older-source"):
                heads = api._journal_heads(build_data_plan(v1_root), session, context)
            self.assertTrue(heads[("diary", "2026-09-20")]["content_matches"])
            self.assertFalse(heads[("diary", "2026-09-20")]["imported"])

            journal_service.save(replace(entry.draft, body="人工更新内容。"),
                expected_revision=entry.reference.revision, operation_id="manual-journal-edit",
                observed_at=clock.now())
            after_edit = api._data_plan(v1_migration, v1_root, session).unwrap()
            self.assertEqual(after_edit["journals"]["ready"], 0)
            self.assertEqual(after_edit["journals"]["already_present"], 1)
            unchanged = (await api._data_apply(v1_migration, v1_root, session,
                after_edit["plan_token"], "", "", False, False, False, True, True, False)).unwrap()
            self.assertEqual(unchanged["journal_created"], 0)
            self.assertEqual(journal_service.get(key).draft.body, "人工更新内容。")
            edited_heads = api._journal_heads(build_data_plan(v1_root), session, context)
            self.assertFalse(edited_heads[("diary", "2026-09-20")]["content_matches"])
        finally:
            await controller.terminate()


if __name__ == "__main__":
    unittest.main()
