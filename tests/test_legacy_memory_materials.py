from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.execution.models import TaskError
from companion_v2.foundation.refs import ScopeKind
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.memory.legacy_materials import (
    DATABASE_FILENAME,
    LegacyMemoryBinding,
    LegacyMemoryMaterials,
    LegacyOwnerSelector,
    _owner,
)
from tests.memory_support import MemoryFixture


MEMORY_DDL = """CREATE TABLE memories (
    id TEXT PRIMARY KEY, memory_type TEXT NOT NULL, subject_kind TEXT NOT NULL DEFAULT '',
    subject_id TEXT NOT NULL DEFAULT '', object_kind TEXT NOT NULL DEFAULT '', object_id TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL DEFAULT '', platform TEXT NOT NULL DEFAULT '',
    message_id TEXT NOT NULL DEFAULT '', group_id TEXT NOT NULL DEFAULT '', visibility TEXT NOT NULL DEFAULT '',
    sayability TEXT NOT NULL DEFAULT '', reality_level TEXT NOT NULL DEFAULT '', lifecycle TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '', confidence REAL NOT NULL DEFAULT 0.5,
    owner_bot_id TEXT NOT NULL DEFAULT '', validity_status TEXT NOT NULL DEFAULT 'active',
    valid_from TEXT NOT NULL DEFAULT '', valid_to TEXT NOT NULL DEFAULT '', sensitivity TEXT NOT NULL DEFAULT 'private',
    review_status TEXT NOT NULL DEFAULT 'auto', metadata TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT '',
    correction_ref TEXT NOT NULL DEFAULT '', supersedes_id TEXT NOT NULL DEFAULT ''
)"""

TIMELINE_DDL = """CREATE TABLE timeline (
    id TEXT PRIMARY KEY, event_type TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '', subject_id TEXT NOT NULL DEFAULT '', object_id TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '', metadata TEXT NOT NULL DEFAULT '{}', message_id TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT '',
    retention_class TEXT NOT NULL DEFAULT 'normal'
)"""


class LegacyMemoryMaterialsTests(MemoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        temporary = TemporaryDirectory(prefix="companion-v2-legacy-memory-")
        self.addCleanup(temporary.cleanup)
        self.source_root = Path(temporary.name)
        self.snapshot = self.source_root / "memory_companion.db"
        self.source = sqlite3.connect(self.snapshot)
        self.source.row_factory = sqlite3.Row
        self.source.executescript(MEMORY_DDL + ";" + TIMELINE_DDL + ";")
        self.source.commit()
        self.addCleanup(self.source.close)
        self.legacy = self.recall.legacy
        self.selector = LegacyOwnerSelector(
            bot_id=self.context.scope.bot_id,
            platform=self.context.scope.platform,
            persona_id=self.context.role_binding.role.subject_id,
            scope="private",
            session_id="v1-private-session-1",
            actor_id="v1-user-1",
        )
        self.binding = LegacyMemoryBinding(
            source=self.selector,
            target_installation_id=self.context.scope.installation_id,
            target_bot_id=self.context.scope.bot_id,
            target_role_id=self.context.role_binding.role.subject_id,
            target_actor_id=self.context.actor.subject.subject_id,
            target_platform=self.context.scope.platform,
            target_account_id=self.context.scope.account_id,
        )

    def add_memory(self, memory_id, content, *, status="auto", metadata=None, scope="private",
                   session_id=None, owner_bot=None, persona=None, visibility="private_pair",
                   sensitivity="private"):
        value = {"persona_id": self.selector.persona_id if persona is None else persona,
                 **(metadata or {})}
        self.source.execute("""INSERT INTO memories(
            id,memory_type,subject_kind,subject_id,object_kind,object_id,scope,session_id,platform,
            visibility,sayability,reality_level,lifecycle,content,owner_bot_id,validity_status,
            sensitivity,review_status,metadata,occurred_at,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (memory_id, "stable_fact", "user", self.selector.actor_id, "bot", self.selector.bot_id,
             scope, session_id or self.selector.session_id, self.selector.platform, visibility, "direct",
             "real_user_fact", "stable_memory", content, owner_bot or self.selector.bot_id, "active",
             sensitivity, status, json.dumps(value, ensure_ascii=False), "2026-01-02T03:04:05+00:00",
             "2026-01-02T03:04:05+00:00"))
        self.source.commit()

    def add_timeline(self, identifier, *, event_type="journal", content="一段旧日记", metadata=None,
                     message_id="", subject_id="v1-user-1", object_id="v1-user-1"):
        value = {"platform": self.selector.platform, "owner_bot_id": self.selector.bot_id,
                 "persona_id": self.selector.persona_id, **(metadata or {})}
        self.source.execute("""INSERT INTO timeline(
            id,event_type,session_id,scope,subject_id,object_id,content,metadata,message_id,
            occurred_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (identifier, event_type, self.selector.session_id, "private", subject_id, object_id,
             content, json.dumps(value, ensure_ascii=False), message_id,
             "2026-01-03T04:05:06+00:00", "2026-01-03T04:05:06+00:00"))
        self.source.commit()

    def source_digest(self):
        self.source.commit()
        return hashlib.sha256(self.snapshot.read_bytes()).hexdigest()

    def import_materials(self, *, binding=None, fingerprint="a" * 64, preview=False):
        return self.legacy.import_snapshot(self.snapshot, source_fingerprint=fingerprint,
            bindings=(binding or self.binding,), preview=preview)

    def test_inventory_and_preview_are_read_only_and_reveal_only_exact_owner_keys(self):
        self.add_memory("private-1", "用户喜欢蓝风铃")
        self.add_memory("group-1", "群内资料", scope="group", session_id="group-session",
                        metadata={"group_id": "group-7"})
        before = self.source_digest()

        inventory = self.legacy.inspect_snapshot(self.snapshot)
        private = next(item for item in inventory["owners"] if item["source"]["scope"] == "private")
        plan = self.import_materials(preview=True)

        self.assertEqual(private["memories"], 1)
        self.assertEqual(private["timeline"], 0)
        self.assertFalse(any("content" in owner for owner in inventory["owners"]))
        self.assertEqual(plan["imported"], {"memories": 1, "timeline": 0})
        self.assertEqual(plan["excluded"], {"binding_missing": 1})
        self.assertFalse((self.runtime.data_root / DATABASE_FILENAME).exists())
        self.assertEqual(self.source_digest(), before)

    def test_private_material_is_queryable_under_exact_v2_identity_and_never_becomes_a_source_or_fact(self):
        self.add_memory("private-1", "用户喜欢蓝风铃", metadata={"profile_dimension": "preference"})
        self.add_timeline("journal-1")
        self.import_materials()
        self.recall.begin(self.context, "legacy-query")

        result = self.recall.legacy_materials(self.context, "legacy-query", query_intent="蓝风铃").unwrap()
        source_count = self.runtime.read_one("SELECT COUNT(*) AS n FROM sources", ())["n"]
        atom_count = self.runtime.read_one("SELECT COUNT(*) AS n FROM memory_atoms", ())["n"]

        self.assertEqual([item["kind"] for item in result["items"]], ["memories"])
        self.assertEqual(result["items"][0]["text"], "用户喜欢蓝风铃")
        self.assertTrue(result["items"][0]["historical_only"])
        self.assertIsNone(result["items"][0]["v2_source_ref"])
        self.assertFalse(result["items"][0]["current_fact"])
        self.assertEqual((source_count, atom_count), (0, 0))
        self.assertEqual(result["profile"], "memory.legacy-materials.v1")

    def test_archived_wal_database_stays_byte_exact_without_creating_sidecars(self):
        self.source.execute("PRAGMA journal_mode=WAL")
        self.add_memory("private-archive", "一条归档历史资料")
        self.source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.source.close()
        def files():
            return {path.name: (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
                    for path in self.source_root.iterdir() if path.is_file()}
        before = files()
        self.assertNotIn("memory_companion.db-wal", before)
        self.assertNotIn("memory_companion.db-shm", before)
        self.assertEqual(len(self.legacy.inspect_snapshot(self.snapshot)["owners"]), 1)
        self.assertEqual(self.import_materials(preview=True)["imported"]["memories"], 1)
        self.assertEqual(self.import_materials()["imported"]["memories"], 1)
        self.assertEqual(files(), before)

    def test_pending_rejected_withdrawn_policy_denied_and_unbound_records_are_excluded(self):
        self.source.executescript("""
            CREATE TABLE review_queue(id TEXT PRIMARY KEY, memory_id TEXT, status TEXT);
            CREATE TABLE memory_acl_policies(
                id TEXT, window_scope TEXT, window_id TEXT, read_mode TEXT, share_mode TEXT,
                capture_enabled INTEGER, recall_enabled INTEGER);
            CREATE TABLE message_source_tombstones(source_id TEXT, message_id TEXT);
            CREATE TABLE life_message_withdrawals(source_id TEXT);
        """)
        self.add_memory("pending", "待审核资料", status="pending")
        self.add_memory("rejected", "已拒绝资料", status="rejected")
        self.add_memory("withdrawn", "撤回来源资料", metadata={"source": "timeline:tl_deleted"})
        self.add_memory("denied", "关闭召回的资料", session_id="session-disabled")
        self.add_memory("unbound", "未映射资料", session_id="other-session")
        self.source.execute("INSERT INTO review_queue VALUES('q1','pending','pending')")
        self.source.execute("INSERT INTO review_queue VALUES('q2','rejected','rejected')")
        self.source.execute("INSERT INTO message_source_tombstones VALUES('tl_deleted','')")
        self.source.execute("INSERT INTO memory_acl_policies VALUES('p1','private','disabled-user','whitelist','whitelist',1,0)")
        self.source.execute("UPDATE memories SET subject_id='disabled-user' WHERE id='denied'")
        self.source.commit()

        disabled_selector = LegacyOwnerSelector(
            bot_id=self.selector.bot_id, platform=self.selector.platform, persona_id=self.selector.persona_id,
            scope="private", session_id="session-disabled", actor_id="disabled-user")
        disabled_binding = LegacyMemoryBinding(
            source=disabled_selector, target_installation_id=self.binding.target_installation_id,
            target_bot_id=self.binding.target_bot_id, target_role_id=self.binding.target_role_id,
            target_actor_id=self.binding.target_actor_id, target_platform=self.binding.target_platform,
            target_account_id=self.binding.target_account_id)
        plan = self.legacy.import_snapshot(self.snapshot, source_fingerprint="a" * 64,
            bindings=(self.binding, disabled_binding))

        self.assertEqual(plan["imported"]["memories"], 0, plan)
        self.assertEqual(plan["excluded"], {
            "binding_missing": 1,
            "memory_unreviewed": 2,
            "legacy_policy_reader_recall_disabled": 1,
            "source_withdrawn": 1,
        })

    def test_ambiguous_source_binding_fails_closed_and_conflicting_reimport_replaces_projection(self):
        self.add_memory("private-1", "只属于一个目标")
        conflicting = LegacyMemoryBinding(
            source=self.selector, target_installation_id=self.context.scope.installation_id,
            target_bot_id=self.context.scope.bot_id, target_role_id=self.context.role_binding.role.subject_id,
            target_actor_id="different-human", target_platform=self.context.scope.platform,
            target_account_id=self.context.scope.account_id)
        preview = self.import_materials(binding=self.binding, preview=True)
        conflict = self.legacy.plan_snapshot(self.snapshot, source_fingerprint="a" * 64,
                                               bindings=(self.binding, conflicting))
        self.assertEqual(preview["imported"]["memories"], 1)
        self.assertEqual(conflict["imported"]["memories"], 0)
        self.assertEqual(conflict["excluded"], {"binding_conflict": 1})

        first = self.import_materials()
        repeated = self.import_materials()
        replaced = self.legacy.import_snapshot(self.snapshot, source_fingerprint="a" * 64,
                                                bindings=(conflicting,))
        self.assertFalse(first["already_present"])
        self.assertTrue(repeated["already_present"])
        self.assertEqual(replaced["imported"]["memories"], 1)
        self.recall.begin(self.context, "replaced-query")
        query = self.recall.legacy_materials(self.context, "replaced-query").unwrap()
        self.assertEqual(query["items"], [])

    def test_verified_capture_chunks_are_required_for_message_timeline(self):
        self.source.executescript("""
            CREATE TABLE capture_sources(source_key TEXT, timeline_id TEXT, identity TEXT, manifest TEXT, state TEXT);
            CREATE TABLE capture_chunks(source_key TEXT, seq INTEGER, char_offset INTEGER,
                byte_offset INTEGER, body TEXT, digest TEXT);
            CREATE TABLE capture_suppression(source_key TEXT, reason TEXT, created REAL);
        """)
        body = "用户刚刚说：蓝风铃"
        chunk_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        identity = {"installation": "old-install", "platform": self.selector.platform,
                    "bot": self.selector.bot_id, "persona": self.selector.persona_id,
                    "scope": "private", "session": self.selector.session_id,
                    "speaker": self.selector.actor_id, "audience": self.selector.actor_id,
                    "direction": "incoming", "message": "m-1"}
        manifest = {"chunks": [{"seq": 0, "char_offset": 0, "byte_offset": 0,
                                 "chars": len(body), "bytes": len(body.encode("utf-8")),
                                 "digest": chunk_hash}], "chars": len(body),
                    "bytes": len(body.encode("utf-8")), "body_digest": chunk_hash}
        self.add_timeline("tl-message", event_type="user_message", content=body, message_id="m-1",
                          metadata={"source_key": "cap-1"}, subject_id=self.selector.actor_id,
                          object_id=self.selector.bot_id)
        self.source.execute("UPDATE timeline SET metadata=? WHERE id='tl-message'", (
            json.dumps({"platform": self.selector.platform, "owner_bot_id": self.selector.bot_id,
                        "persona_id": self.selector.persona_id, "source_key": "cap-1"}),))
        self.source.execute("INSERT INTO capture_sources VALUES(?,?,?,?,?)",
            ("cap-1", "tl-message", json.dumps(identity), json.dumps(manifest), "current"))
        self.source.execute("INSERT INTO capture_chunks VALUES(?,?,?,?,?,?)",
            ("cap-1", 0, 0, 0, body, chunk_hash))
        self.source.commit()

        plan = self.import_materials()
        self.recall.begin(self.context, "capture-query")
        items = self.recall.legacy_materials(self.context, "capture-query", material_kind="timeline").unwrap()["items"]

        self.assertEqual(plan["imported"]["timeline"], 1)
        self.assertEqual(items[0]["source_integrity"], "verified_capture_chunks")
        self.assertEqual(items[0]["text"], body)

    def test_capture_chunk_tampering_excludes_messages(self):
        self.source.executescript("""
            CREATE TABLE capture_sources(source_key TEXT, timeline_id TEXT, identity TEXT, manifest TEXT, state TEXT);
            CREATE TABLE capture_chunks(source_key TEXT, seq INTEGER, char_offset INTEGER,
                byte_offset INTEGER, body TEXT, digest TEXT);
            CREATE TABLE capture_suppression(source_key TEXT, reason TEXT, created REAL);
        """)
        body = "原文"
        hash_value = hashlib.sha256(body.encode("utf-8")).hexdigest()
        identity = {"installation": "old-install", "platform": self.selector.platform,
                    "bot": self.selector.bot_id, "persona": self.selector.persona_id,
                    "scope": "private", "session": self.selector.session_id,
                    "speaker": self.selector.actor_id, "audience": self.selector.actor_id,
                    "direction": "incoming", "message": "m-del"}
        manifest = {"chunks": [{"seq": 0, "char_offset": 0, "byte_offset": 0, "chars": len(body),
                                 "bytes": len(body.encode()), "digest": hash_value}], "chars": len(body),
                    "bytes": len(body.encode()), "body_digest": hash_value}
        self.add_timeline("tl-deleted", event_type="user_message", content=body, message_id="m-del",
                          subject_id=self.selector.actor_id, object_id=self.selector.bot_id)
        self.source.execute("INSERT INTO capture_sources VALUES(?,?,?,?,?)",
            ("cap-del", "tl-deleted", json.dumps(identity), json.dumps(manifest), "current"))
        self.source.execute("INSERT INTO capture_chunks VALUES(?,?,?,?,?,?)",
            ("cap-del", 0, 0, 0, body + "被改", hash_value))
        self.source.commit()

        plan = self.import_materials()

        self.assertEqual(plan["imported"]["timeline"], 0)
        self.assertEqual(plan["excluded"], {"capture_manifest_invalid": 1})

    def test_legacy_query_paginates_and_binds_cursor_to_import_generation(self):
        for index in range(3):
            self.add_memory(f"memory-{index}", f"蓝风铃偏好 {index}")
        self.import_materials()
        self.recall.begin(self.context, "page-one")

        first = self.recall.legacy_materials(self.context, "page-one", query_intent="蓝风铃", limit=1).unwrap()
        self.recall.begin(self.context, "page-two")
        second = self.recall.legacy_materials(self.context, "page-two", query_intent="蓝风铃", limit=1,
                                              cursor=first["next_cursor"]).unwrap()

        self.assertEqual(len(first["items"]), 1)
        self.assertEqual(len(second["items"]), 1)
        self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
        self.assertIsNotNone(second["next_cursor"])

    def test_group_history_binding_is_exact_and_requires_group_read_authorization(self):
        group_id, session_id = "9001", "v1-group-session-9001"
        self.add_memory("group-memory", "群里约好周末见面", scope="group", session_id=session_id,
                        metadata={"group_id": group_id}, visibility="group_public")
        timeline_metadata = {"platform": self.selector.platform,
                             "owner_bot_id": self.selector.bot_id,
                             "persona_id": self.selector.persona_id,
                             "group_id": group_id}
        self.source.execute("""INSERT INTO timeline(
            id,event_type,session_id,scope,subject_id,object_id,content,metadata,message_id,
            occurred_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            ("group-journal", "journal", session_id, "group", group_id, group_id,
             "群里记录了周末安排", json.dumps(timeline_metadata, ensure_ascii=False), "",
             "2026-01-04T05:06:07+00:00", "2026-01-04T05:06:07+00:00"))
        self.source.commit()
        selector = LegacyOwnerSelector(
            bot_id=self.selector.bot_id, platform=self.selector.platform,
            persona_id=self.selector.persona_id, scope="group", session_id=session_id,
            actor_id=group_id, group_id=group_id)
        binding = LegacyMemoryBinding(
            source=selector, target_installation_id=self.context.scope.installation_id,
            target_bot_id=self.context.scope.bot_id, target_role_id=self.context.role_binding.role.subject_id,
            target_actor_id="", target_platform=self.context.scope.platform,
            target_account_id=self.context.scope.account_id, target_scope_kind="group",
            target_native_scope_id=group_id)
        with self.assertRaisesRegex(ValueError, "legacy_memory_group_target_invalid"):
            LegacyMemoryBinding(
                source=selector, target_installation_id=self.context.scope.installation_id,
                target_bot_id=self.context.scope.bot_id, target_role_id=self.context.role_binding.role.subject_id,
                target_actor_id="", target_platform=self.context.scope.platform,
                target_account_id=self.context.scope.account_id, target_scope_kind="group")
        self.legacy.import_snapshot(self.snapshot, source_fingerprint="b" * 64, bindings=(binding,))

        group_scope = replace(
            self.context.scope, kind=ScopeKind.GROUP, native_scope_id=group_id,
            conversation_id="group:" + group_id, session_id="v2-group-session")
        self.personas.register_route(
            ConversationRoute(group_scope, group_id=group_id), observed_at=self.clock.now())
        group_context = self.context_for(self.important, group_scope)
        denied = self.legacy.query(group_context, group_read_authorized=False)
        self.assertEqual(denied.failure.code, "group_memory_access_denied")
        visible = self.legacy.query(group_context, group_read_authorized=True).unwrap()
        self.assertEqual({(item["kind"], item["text"]) for item in visible["items"]}, {
            ("memories", "群里约好周末见面"), ("timeline", "群里记录了周末安排")})
        self.assertTrue(self.legacy.verify(group_context, visible["items"], group_read_authorized=True))

        other_group_scope = replace(
            group_scope, native_scope_id="9002", conversation_id="group:9002")
        self.personas.register_route(
            ConversationRoute(other_group_scope, group_id="9002"), observed_at=self.clock.now())
        other_group = self.context_for(self.important, other_group_scope)
        self.assertEqual(self.legacy.query(other_group, group_read_authorized=True).unwrap()["items"], [])
        with self.assertRaises(TaskError) as caught:
            self.legacy.verify(group_context, visible["items"])
        self.assertEqual(caught.exception.code, "group_memory_access_denied")

    def test_v1_owner_identity_uses_session_and_actual_namespace_fallbacks(self):
        private = {
            "metadata": json.dumps({"owner_bot_id": "", "persona_id": ""}),
            "owner_bot_id": "", "platform": "", "scope": "unknown",
            "session_id": "qq:FriendMessage:v1-user-1", "group_id": "",
            "subject_kind": "user", "subject_id": "v1-user-1",
            "object_kind": "bot", "object_id": "self",
        }
        parsed_private = _owner(private, table="memories")
        self.assertEqual(parsed_private.scope, "private")
        self.assertEqual(parsed_private.session_id, private["session_id"])
        self.assertEqual(parsed_private.platform, "qq")
        self.assertEqual(parsed_private.actor_id, "v1-user-1")
        self.assertEqual(parsed_private.bot_id, "legacy-unscoped")
        self.assertEqual(parsed_private.persona_id, "legacy")

        group = {
            "metadata": json.dumps({"owner_bot_id": "bot-42", "source_group_id": "9001"}),
            "event_type": "user_message", "scope": "group", "session_id": "qq:GroupMessage:9001",
            "platform": "", "group_id": "", "subject_id": "member-id", "object_id": "9001",
        }
        parsed_group = _owner(group, table="timeline")
        self.assertEqual(parsed_group.scope, "group")
        self.assertEqual(parsed_group.platform, "qq")
        self.assertEqual(parsed_group.group_id, "9001")
        self.assertEqual(parsed_group.actor_id, "9001")
        self.assertEqual(parsed_group.bot_id, "bot-42")
        self.assertEqual(parsed_group.persona_id, "legacy")

    def test_v1_owner_inference_rejects_conflicting_or_incomplete_scope_identity(self):
        base = {
            "metadata": json.dumps({"owner_bot_id": "bot-42", "source_group_id": "9002"}),
            "scope": "group", "session_id": "qq:GroupMessage:9001", "platform": "",
            "group_id": "", "event_type": "user_message", "subject_id": "member-id", "object_id": "9001",
        }
        self.assertIsNone(_owner(base, table="timeline"))
        private_without_actor = {
            "metadata": "{}", "scope": "private", "session_id": "opaque-window",
            "platform": "qq", "group_id": "", "subject_kind": "bot", "subject_id": "self",
            "object_kind": "bot", "object_id": "self",
        }
        self.assertIsNone(_owner(private_without_actor, table="memories"))
        unknown_scope = {**base, "scope": "unknown", "session_id": "opaque-window"}
        self.assertIsNone(_owner(unknown_scope, table="timeline"))

    def test_v1_private_timeline_owner_uses_message_direction(self):
        common = {
            "metadata": "{}", "scope": "private",
            "session_id": "qq:FriendMessage:v1-user-1", "subject_id": "v1-user-1",
            "object_id": "bot-42",
        }
        incoming = _owner({**common, "event_type": "user_message"}, table="timeline")
        outgoing = _owner({**common, "event_type": "bot_response",
                           "subject_id": "bot-42", "object_id": "v1-user-1"}, table="timeline")
        imported_incoming = _owner({**common, "event_type": "user_message",
            "object_id": "v1-user-1",
            "metadata": json.dumps({"owner_bot_id": "bot-42"})}, table="timeline")

        self.assertEqual((incoming.bot_id, incoming.actor_id), ("bot-42", "v1-user-1"))
        self.assertEqual((outgoing.bot_id, outgoing.actor_id), ("bot-42", "v1-user-1"))
        self.assertEqual((imported_incoming.bot_id, imported_incoming.actor_id),
                         ("bot-42", "v1-user-1"))

    def test_verification_of_missing_archive_does_not_create_database(self):
        path = self.runtime.data_root / DATABASE_FILENAME
        self.assertFalse(path.exists())
        with self.assertRaises(TaskError) as caught:
            self.legacy.verify(self.context, [{"id": "stale-history-item"}])
        self.assertEqual(caught.exception.code, "legacy_memory_result_changed")
        self.assertFalse(path.exists())


    def test_destination_scoped_import_preserves_other_role_and_upgrades_old_shared_projection(self):
        self.add_memory('old-row', '旧历史蓝风铃')
        self.import_materials()
        other = self.alternate_context(bot_id=self.context.scope.bot_id, role_id='other-history', session_selector=True)
        self.context = self.context_for(self.context.actor, self.context.scope)
        other_binding = replace(self.binding, target_role_id=other.role_binding.role.subject_id)
        self.legacy.import_snapshot(self.snapshot, source_fingerprint='a'*64,
                                   bindings=(other_binding,), destination_scoped=True)
        self.assertEqual(len(self.legacy.query(self.context).unwrap()['items']), 1)
        self.assertEqual(len(self.legacy.query(other).unwrap()['items']), 1)
        first = self.legacy.import_snapshot(self.snapshot, source_fingerprint='a'*64,
                                            bindings=(self.binding,), destination_scoped=True)
        repeated = self.legacy.import_snapshot(self.snapshot, source_fingerprint='a'*64,
                                               bindings=(self.binding,), destination_scoped=True)
        self.assertFalse(first['already_present'])
        self.assertTrue(repeated['already_present'])
        self.assertEqual(len(self.legacy.query(self.context).unwrap()['items']), 1)
        self.assertEqual(len(self.legacy.query(other).unwrap()['items']), 1)

    def test_natural_language_history_recall_ranks_keywords_and_keeps_cursor(self):
        self.add_memory('one', '曾经一起看蓝风铃，留下往事')
        self.add_memory('two', '旧日蓝风铃')
        self.add_memory('unrelated', '明天吃什么')
        self.import_materials()
        first = self.legacy.query(self.context, query_intent='还记得蓝风铃吗', lexical=True, limit=1).unwrap()
        second = self.legacy.query(self.context, query_intent='还记得蓝风铃吗', lexical=True,
                                   limit=1, cursor=first['next_cursor']).unwrap()
        self.assertEqual((len(first['items']), len(second['items'])), (1,1))
        self.assertNotEqual(first['items'][0]['id'], second['items'][0]['id'])
        self.assertTrue(all('蓝风铃' in page['items'][0]['text'] for page in (first,second)))


if __name__ == "__main__":
    unittest.main()
