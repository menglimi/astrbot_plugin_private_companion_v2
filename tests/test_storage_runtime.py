from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from companion_v2.foundation.refs import OperationRef, ScopeKind, ScopeRef, VersionRef
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import (
    InboxRepository,
    MigrationLedger,
    NamespaceRepository,
    OperationRepository,
)
from companion_v2.storage.runtime import StorageOpenError, StoragePathError, StorageRuntime


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
