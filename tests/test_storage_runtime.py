from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.foundation.refs import OperationRef, ScopeKind, ScopeRef, VersionRef
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import (
    InboxRepository,
    MigrationLedger,
    NamespaceRepository,
    OperationRepository,
)
from companion_v2.storage.runtime import SCHEMA_VERSION, StorageOpenError, StoragePathError, StorageRuntime


NOW = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
INSTALLATION_ID = "installation-alpha"


def private_scope() -> ScopeRef:
    return ScopeRef(
        installation_id=INSTALLATION_ID,
        platform="onebot",
        kind=ScopeKind.PRIVATE,
        native_scope_id="private-a",
    )


def operation() -> OperationRef:
    return OperationRef(
        operation_id="operation-a",
        owner="conversation",
        scope=private_scope(),
        version=VersionRef(lineage_id="operation-lineage-a", revision=1),
        idempotency_key="operation-key-a",
    )


class StorageRuntimeTests(unittest.TestCase):
    def test_wal_checkpoints_run_outside_commits_without_weakening_durability(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-storage-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary) / "v2-data", installation_id=INSTALLATION_ID)
            try:
                self.assertEqual(runtime.read_one("PRAGMA wal_autocheckpoint", ())[0], 0)
                self.assertEqual(runtime.read_one("PRAGMA synchronous", ())[0], 2)
                result = runtime.checkpoint_passive()
                self.assertEqual(len(result), 3)
                self.assertGreaterEqual(result[1], result[2])
            finally:
                runtime.close()

    def test_current_schema_reopen_skips_full_integrity_scan(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-storage-") as temporary:
            root = Path(temporary) / "v2-data"
            runtime = StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
            runtime.close()

            with patch("companion_v2.storage.runtime._validate_integrity") as integrity_check:
                reopened = StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
            try:
                integrity_check.assert_not_called()
                self.assertEqual(reopened.read_one(
                    "SELECT value FROM runtime_metadata WHERE key = ?", ("schema_version",))["value"],
                    SCHEMA_VERSION)
            finally:
                reopened.close()

    def test_slow_sqlite_diagnostics_include_safe_timing_fields(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-storage-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary) / "v2-data", installation_id=INSTALLATION_ID)
            runtime.SLOW_OPERATION_SECONDS = 0
            try:
                with self.assertLogs("companion_v2.storage.runtime", level="WARNING") as captured:
                    runtime.read_one("SELECT 1", ())
                message = captured.output[0]
                self.assertIn("operation=read_one", message)
                self.assertIn("lock_wait_ms=", message)
                self.assertIn("caller=test_storage_runtime.py:", message)
                self.assertNotIn("SELECT 1", message)

                with self.assertLogs("companion_v2.storage.runtime", level="WARNING") as captured:
                    with runtime.read_snapshot():
                        runtime.read_one("SELECT 1", ())
                self.assertEqual(len(captured.output), 1)
                self.assertIn("operation=read_one", captured.output[0])

                with self.assertLogs("companion_v2.storage.runtime", level="WARNING") as captured:
                    with runtime.transaction():
                        pass
                self.assertIn("caller=test_storage_runtime.py:", captured.output[0])
                self.assertIn("begin_ms=", captured.output[0])
                self.assertIn("body_ms=", captured.output[0])
                self.assertIn("commit_ms=", captured.output[0])
            finally:
                runtime.SLOW_OPERATION_SECONDS = 1.0
                runtime.close()

    def test_namespace_operation_outbox_and_inbox_survive_a_restart(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-storage-") as temporary:
            root = Path(temporary) / "v2-data"
            runtime = StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
            namespaces = NamespaceRepository(runtime)
            operations = OperationRepository(runtime)
            inbox = InboxRepository(runtime)

            first_namespace = namespaces.ensure(
                owner="conversation", scope=private_scope(), created_at=NOW
            )
            same_namespace = namespaces.ensure(
                owner="conversation", scope=private_scope(), created_at=NOW
            )
            first = operations.reserve(
                operation(),
                parameter_hash="parameters-a",
                observed_at=NOW,
                outbox_part_id="part-a",
                outbox_payload_hash="payload-a",
            )
            first_inbox = inbox.accept(
                consumer="conversation", event_id="event-a", payload_hash="event-payload-a", observed_at=NOW
            )

            self.assertTrue(runtime.database_path.exists())
            self.assertEqual(first_namespace.namespace_id, same_namespace.namespace_id)
            self.assertFalse(first.unwrap().replayed)
            self.assertEqual(len(operations.pending_outbox()), 1)
            self.assertFalse(first_inbox.unwrap().replayed)
            runtime.close()

            restarted = StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
            restarted_operations = OperationRepository(restarted)
            restarted_inbox = InboxRepository(restarted)
            replay = restarted_operations.reserve(
                operation(),
                parameter_hash="parameters-a",
                observed_at=NOW,
                outbox_part_id="part-a",
                outbox_payload_hash="payload-a",
            )
            replayed_inbox = restarted_inbox.accept(
                consumer="conversation", event_id="event-a", payload_hash="event-payload-a", observed_at=NOW
            )

            self.assertTrue(replay.unwrap().replayed)
            self.assertTrue(replayed_inbox.unwrap().replayed)
            self.assertEqual(len(restarted_operations.pending_outbox()), 1)
            restarted.close()

    def test_idempotency_and_state_conflicts_are_explicit(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-storage-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary) / "v2-data", installation_id=INSTALLATION_ID)
            operations = OperationRepository(runtime)
            first = operations.reserve(operation(), parameter_hash="parameters-a", observed_at=NOW)
            conflict = operations.reserve(operation(), parameter_hash="parameters-b", observed_at=NOW)
            completed = operations.transition(
                "operation-a",
                expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED,
                observed_at=NOW,
            )
            stale_transition = operations.transition(
                "operation-a",
                expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED,
                observed_at=NOW,
            )

            self.assertTrue(first.is_success)
            self.assertEqual(conflict.failure.code, "idempotency_key_conflict")
            self.assertEqual(completed.unwrap().state, OperationState.COMPLETED)
            self.assertEqual(stale_transition.failure.code, "operation_state_conflict")
            runtime.close()

    def test_outbox_acceptance_persists_the_platform_receipt_across_restart(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-outbox-receipt-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary) / "v2-data", installation_id=INSTALLATION_ID)
            operations = OperationRepository(runtime)
            operations.reserve(operation(), parameter_hash="parameters-a", observed_at=NOW,
                               outbox_part_id="part-a", outbox_payload_hash="payload-a").unwrap()
            dispatched = operations.transition_outbox("operation-a", "part-a",
                expected_operation_state=OperationState.ACCEPTED,
                next_operation_state=OperationState.UNKNOWN,
                expected_outbox_state="pending", next_outbox_state="unknown", observed_at=NOW)
            self.assertTrue(dispatched.is_success)

            missing_receipt = operations.transition_outbox("operation-a", "part-a",
                expected_operation_state=OperationState.UNKNOWN,
                next_operation_state=OperationState.COMPLETED,
                expected_outbox_state="unknown", next_outbox_state="accepted", observed_at=NOW + timedelta(seconds=1))
            self.assertEqual(missing_receipt.failure.code, "outbox_receipt_invalid")

            completed = operations.transition_outbox("operation-a", "part-a",
                expected_operation_state=OperationState.UNKNOWN,
                next_operation_state=OperationState.COMPLETED,
                expected_outbox_state="unknown", next_outbox_state="accepted",
                observed_at=NOW + timedelta(seconds=1), receipt_ref="onebot-message:248610")
            self.assertTrue(completed.is_success)
            self.assertEqual(operations.outbox("operation-a", "part-a").unwrap().receipt_ref,
                             "onebot-message:248610")
            runtime.close()

            with StorageRuntime.open(data_root=Path(temporary) / "v2-data",
                                     installation_id=INSTALLATION_ID) as restarted:
                self.assertEqual(OperationRepository(restarted).outbox("operation-a", "part-a").unwrap().receipt_ref,
                                 "onebot-message:248610")

    def test_checkpoint_compare_and_swap_preserves_recovery_cursor(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-storage-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary) / "v2-data", installation_id=INSTALLATION_ID)
            ledger = MigrationLedger(runtime)
            created = ledger.advance(
                checkpoint_id="checkpoint-a",
                owner="legacy-private",
                source_fingerprint="snapshot-hash-a",
                cursor="source-a:1",
                state="baseline_imported",
                expected_revision=0,
                observed_at=NOW,
            )
            conflict = ledger.advance(
                checkpoint_id="checkpoint-a",
                owner="legacy-private",
                source_fingerprint="snapshot-hash-a",
                cursor="source-a:2",
                state="baseline_imported",
                expected_revision=0,
                observed_at=NOW,
            )
            advanced = ledger.advance(
                checkpoint_id="checkpoint-a",
                owner="legacy-private",
                source_fingerprint="snapshot-hash-a",
                cursor="source-a:2",
                state="final_reconciled",
                expected_revision=1,
                observed_at=NOW,
            )

            self.assertEqual(created.unwrap().revision, 1)
            self.assertEqual(conflict.failure.code, "checkpoint_revision_conflict")
            self.assertEqual(advanced.unwrap().cursor, "source-a:2")
            self.assertEqual(advanced.unwrap().revision, 2)
            runtime.close()

    def test_runtime_refuses_v1_directory_and_foreign_installation(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-storage-") as temporary:
            root = Path(temporary) / "v2-data"
            runtime = StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
            runtime.close()
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=root, installation_id="installation-beta")
            with self.assertRaises(StoragePathError):
                StorageRuntime.open(
                    data_root=Path(temporary) / "astrbot_plugin_private_companion",
                    installation_id=INSTALLATION_ID,
                )

    def test_takeover_child_and_fresh_public_name_can_open_without_touching_legacy_data(self):
        with TemporaryDirectory(prefix="companion-storage-takeover-") as temporary:
            public = Path(temporary) / "astrbot_plugin_private_companion"
            public.mkdir()
            source = public / "companions.json"
            source.write_bytes(b'{"legacy":true}\n')
            source_bytes = source.read_bytes()
            with self.assertRaises(StoragePathError):
                StorageRuntime.open(data_root=public / "profiles" / "main" / "runtime",
                                    installation_id=INSTALLATION_ID)
            child = public / "companion-7" / "profiles" / "main" / "runtime"
            runtime = StorageRuntime.open(data_root=child, installation_id=INSTALLATION_ID)
            runtime.close()
            runtime = StorageRuntime.open(data_root=child, installation_id=INSTALLATION_ID)
            runtime.close()
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertFalse((public / StorageRuntime.DATABASE_FILENAME).exists())
            source.unlink()
            runtime = StorageRuntime.open(data_root=public / "profiles" / "main" / "runtime",
                                          installation_id=INSTALLATION_ID)
            runtime.close()

    def test_isolated_child_rejects_legacy_markers_inside_its_boundary(self):
        with TemporaryDirectory(prefix="companion-storage-boundary-") as temporary:
            public = Path(temporary) / "astrbot_plugin_private_companion"
            child = public / "companion-7"
            child.mkdir(parents=True)
            (child / "companions.db").write_bytes(b"legacy sentinel")
            for root in (child, child / "profiles" / "main" / "runtime", public / "arbitrary"):
                with self.assertRaises(StoragePathError):
                    StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
            foreign = Path(temporary) / "astrbot_plugin_remember_you" / "companion-7" / "runtime"
            with self.assertRaises(StoragePathError):
                StorageRuntime.open(data_root=foreign, installation_id=INSTALLATION_ID)

    def test_existing_owned_profiles_allow_parent_legacy_files_but_not_runtime_contamination(self):
        for marker in (".companion-v2-storage-owner.json", ".companion-v2-storage-location.json"):
            with self.subTest(marker=marker), TemporaryDirectory() as temporary:
                public = Path(temporary) / "astrbot_plugin_private_companion"
                public.mkdir()
                source = public / "companions.json"
                source.write_bytes(b'{"legacy":true}\n')
                (public / marker).write_text("{}\n", encoding="utf-8")
                root = public / "profiles" / "main" / "runtime"
                runtime = StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
                runtime.close()
                runtime = StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
                runtime.close()
                self.assertEqual(source.read_bytes(), b'{"legacy":true}\n')
                (root / "companions.db").write_bytes(b"legacy sentinel")
                with self.assertRaises(StoragePathError):
                    StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)

    def test_runtime_fails_closed_for_a_partially_initialized_database(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-storage-") as temporary:
            root = Path(temporary) / "v2-data"
            runtime = StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
            database_path = runtime.database_path
            runtime.close()
            connection = sqlite3.connect(database_path)
            connection.execute("DROP TABLE outbox")
            connection.commit()
            connection.close()

            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=root, installation_id=INSTALLATION_ID)
