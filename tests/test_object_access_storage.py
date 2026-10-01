from __future__ import annotations

from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.agenda.models import AgendaTarget, Frequency, Memo, Reminder, Schedule, encode as agenda_encode
from companion_v2.agenda.service import AgendaService

from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier, IdentityBinding, ResolvedIdentity
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    migration_count,
    MIGRATION_V1_TO_V2_ID, MIGRATION_V1_TO_V2_FINGERPRINT,
    MIGRATION_V2_TO_V3_ID, MIGRATION_V2_TO_V3_FINGERPRINT,
    MIGRATION_V3_TO_V4_ID, MIGRATION_V3_TO_V4_FINGERPRINT,
    MIGRATION_V4_TO_V5_ID, MIGRATION_V4_TO_V5_FINGERPRINT,
    SCHEMA_VERSION, SCHEMA_VERSION_V1, SCHEMA_VERSION_V2, SCHEMA_VERSION_V3, SCHEMA_VERSION_V4,
    V1_SCHEMA_STATEMENTS, V2_MIGRATION_STATEMENTS, V3_MIGRATION_STATEMENTS,
    V4_MIGRATION_STATEMENTS, V5_MIGRATION_STATEMENTS,
)


NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)
INSTALLATION = "object-policy-migration"
USER = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-a")
SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "window-a")
PRINCIPAL = AuthenticatedHostPrincipal(INSTALLATION, "host-a", "onebot", "account-a")


class ObjectAccessStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-object-migration-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v2-data"
        self.root.mkdir()
        self.database = self.root / StorageRuntime.DATABASE_FILENAME
        def encode(value):
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=lambda v: v.isoformat())
        binding = IdentityBinding("binding-a", PRINCIPAL, USER, 1, NOW)
        self.target = AgendaTarget(SCOPE, SubjectRef(INSTALLATION, SubjectKind.BOT, "role-a"), USER)
        self.target_json = agenda_encode(self.target)
        actor = ResolvedIdentity(PRINCIPAL, USER, binding.binding_id, binding.revision, 1)
        schedule = Schedule(NOW - timedelta(days=3), "Asia/Shanghai", Frequency.DAILY)
        self.memo_json = agenda_encode(Memo("memo-old", self.target, 9, "active", "升级前便签", "保留原件", True,
                                           schedule, 3, 3, actor, 9))
        reminder_json = agenda_encode(Reminder("reminder-old", self.target, 4, "active", "memo-old", "", schedule,
                                               actor, 7, "reminder.create", 3))
        with closing(sqlite3.connect(self.database)) as connection:
            for statement in V1_SCHEMA_STATEMENTS + V2_MIGRATION_STATEMENTS + V3_MIGRATION_STATEMENTS + V4_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.executemany("INSERT INTO runtime_metadata VALUES (?, ?)", (
                ("installation_id", INSTALLATION), ("schema_version", SCHEMA_VERSION_V4),
            ))
            for migration, previous, current, fingerprint in (
                (MIGRATION_V1_TO_V2_ID, SCHEMA_VERSION_V1, SCHEMA_VERSION_V2, MIGRATION_V1_TO_V2_FINGERPRINT),
                (MIGRATION_V2_TO_V3_ID, SCHEMA_VERSION_V2, SCHEMA_VERSION_V3, MIGRATION_V2_TO_V3_FINGERPRINT),
                (MIGRATION_V3_TO_V4_ID, SCHEMA_VERSION_V3, SCHEMA_VERSION_V4, MIGRATION_V3_TO_V4_FINGERPRINT),
            ):
                connection.execute("INSERT INTO schema_migrations VALUES (?, ?, ?, ?, ?)",
                                   (migration, previous, current, fingerprint, NOW.isoformat()))
            connection.execute("INSERT INTO identity_bindings VALUES (?, ?, ?, ?, ?, ?, ?)", (
                binding.binding_id, INSTALLATION, PRINCIPAL.host_id, PRINCIPAL.platform,
                PRINCIPAL.native_account_id, 1, encode(asdict(binding)),
            ))
            connection.execute("INSERT INTO role_bindings VALUES (?, ?, ?, ?, ?, ?)", (
                INSTALLATION, SCOPE.platform, SCOPE.kind.value, SCOPE.native_scope_id, self.target.role.subject_id, 7,
            ))
            connection.execute("INSERT INTO agenda_memos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                "memo-old", self.target.key, self.target_json, 9, "active", 1,
                self.memo_json, NOW.isoformat(), NOW.isoformat(),
            ))
            connection.execute("INSERT INTO agenda_reminders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                "reminder-old", self.target.key, self.target_json, "memo-old", 4, "active", reminder_json,
                NOW.isoformat(), NOW.isoformat(),
            ))
            connection.execute("INSERT INTO agenda_occurrences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                "occurrence-old", "reminder-old", 4, 3, NOW.isoformat(), "accepted", 2, 9, None, NOW.isoformat(),
            ))
            connection.commit()

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def mutate(self, statement, values=()):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(statement, values)
            connection.commit()

    def assert_v4_unchanged(self):
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V4)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 3)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name = 'object_policy_metadata'").fetchone())
            self.assertEqual(connection.execute("SELECT record_json FROM agenda_memos").fetchone()[0], self.memo_json)
            self.assertEqual(connection.execute("SELECT state FROM agenda_occurrences").fetchone()[0], "accepted")

    def test_nonempty_v4_upgrade_preserves_records_revisions_and_old_fingerprint(self):
        runtime = self.open_runtime()
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"], SCHEMA_VERSION)
        self.assertEqual(runtime.read_one("SELECT fingerprint FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V3_TO_V4_ID,))["fingerprint"], MIGRATION_V3_TO_V4_FINGERPRINT)
        self.assertEqual(runtime.read_one("SELECT fingerprint FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V4_TO_V5_ID,))["fingerprint"], MIGRATION_V4_TO_V5_FINGERPRINT)
        self.assertEqual(runtime.read_one("SELECT record_json, revision FROM agenda_memos", ())["record_json"], self.memo_json)
        self.assertEqual(runtime.read_one("SELECT revision FROM agenda_memos", ())["revision"], 9)
        self.assertEqual(runtime.read_one("SELECT revision FROM agenda_reminders", ())["revision"], 4)
        self.assertEqual(runtime.read_one("SELECT state FROM agenda_occurrences", ())["state"], "accepted")
        actor = PersistentIdentityDirectory(runtime).resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        policy = ObjectAccessPolicy(runtime)
        self.assertFalse(policy.feature_access(actor, scope=SCOPE, action="memo.read", observed_at=NOW).is_success)
        policy.set_tier(USER, AuthorizationTier.IMPORTANT, expected_revision=policy.revision, observed_at=NOW)
        runtime.close()
        reopened = self.open_runtime()
        self.assertEqual(len(reopened.read_all("SELECT * FROM schema_migrations", ())), migration_count())
        self.assertEqual(ObjectAccessPolicy(reopened).feature_access(actor, scope=SCOPE, action="memo.read", observed_at=NOW).unwrap().tier,
                         AuthorizationTier.IMPORTANT)

    def test_failed_v5_ddl_rolls_back_and_nonempty_v4_can_retry(self):
        with patch("companion_v2.storage.runtime.V5_MIGRATION_STATEMENTS", (*V5_MIGRATION_STATEMENTS[:5], "INVALID DDL")):
            with self.assertRaises(StorageOpenError):
                self.open_runtime()
        self.assert_v4_unchanged()
        self.assertEqual(self.open_runtime().read_all("SELECT * FROM subject_access_tiers", ()), ())

    def test_agenda_backfill_preserves_owner_and_recovers_previously_accepted_work_once(self):
        runtime = self.open_runtime()
        policy = ObjectAccessPolicy(runtime)
        policy.set_tier(USER, AuthorizationTier.IMPORTANT, expected_revision=policy.revision, observed_at=NOW)
        service = AgendaService(runtime)
        actor = service.identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        memo = service.read_memo(actor, target=self.target, memo_id="memo-old", observed_at=NOW).unwrap()
        self.assertEqual((memo.revision, memo.sequence, memo.completion_count), (9, 3, 3))
        self.assertEqual(memo.target.owner, USER)
        claim = service.accept_due("occurrence-old", observed_at=NOW).unwrap()
        prepared = service.prepare_local(claim, observed_at=NOW).unwrap()
        self.assertEqual(prepared.recipient, USER)
        self.assertEqual(prepared.message, "升级前便签\n保留原件")
        self.assertEqual(prepared.delivery, "not_started")
        with patch.object(runtime, "read_all", wraps=runtime.read_all) as reads:
            AgendaService(runtime)
            reads.assert_not_called()
        runtime.close()
        recovered = AgendaService(self.open_runtime())
        self.assertEqual(recovered.prepare_local(claim, observed_at=NOW).unwrap(), prepared)

    def test_old_fingerprint_is_verified_before_upgrade(self):
        self.mutate("UPDATE schema_migrations SET fingerprint = 'bad' WHERE migration_id = ?", (MIGRATION_V3_TO_V4_ID,))
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        self.assert_v4_unchanged()

    def test_partial_v5_and_unknown_version_fail_closed(self):
        self.mutate("CREATE TABLE subject_access_tiers(untrusted TEXT)")
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        self.assert_v4_unchanged()
        self.mutate("DROP TABLE subject_access_tiers")
        self.mutate("UPDATE runtime_metadata SET value = 'companion-v2.storage.v999' WHERE key = 'schema_version'")
        with self.assertRaises(StorageOpenError):
            self.open_runtime()

    def test_reopen_validates_v5_fingerprint_required_index_and_metadata(self):
        self.open_runtime().close()
        self.mutate("UPDATE schema_migrations SET fingerprint = 'bad' WHERE migration_id = ?", (MIGRATION_V4_TO_V5_ID,))
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        self.mutate("UPDATE schema_migrations SET fingerprint = ? WHERE migration_id = ?", (MIGRATION_V4_TO_V5_FINGERPRINT, MIGRATION_V4_TO_V5_ID))
        self.mutate("DELETE FROM object_policy_metadata")
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        self.mutate("INSERT INTO object_policy_metadata VALUES (1, 1)")
        self.mutate("DROP INDEX object_access_shares_subject_idx")
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
