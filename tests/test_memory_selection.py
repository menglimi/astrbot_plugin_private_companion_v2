"""Incremental reflection preparation on temporary, synthetic private records."""

import asyncio
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from companion_v2.execution.models import encode
from companion_v2.foundation.outcome import Outcome
from companion_v2.memory.query import MemoryQuery
from companion_v2.memory.reflection import MemoryReflection
from companion_v2.memory.reflection_inputs import span_key
from companion_v2.memory.writer import MemoryWriter
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import SCHEMA_VERSION
from tests.execution_support import remove_v27
from tests.memory_support import MemoryFixture


class SelectionFixture(MemoryFixture):
    def setUp(self):
        super().setUp()
        self.clock.advance(timedelta(seconds=1))
        self.window = dict(start=self.clock.now() - timedelta(hours=1), end=self.clock.now(), role_instruction="原角色")
        self.attach_selection()

    def attach_selection(self):
        self.component = SimpleNamespace(writer=self.memory, query=self.recall, runtime=self.runtime, settings=None)
        self.reflection = MemoryReflection(self.runtime)
        tasks = self.supervisor(self.runtime, registrations=self.registrations + self.reflection.registrations)
        self.reflection.attach(self.component, SimpleNamespace(runtime=self.runtime, tasks=tasks))

    def prepare(self, request_id="selection", **options):
        return self.reflection.prepare(self.context, request_id=request_id, **self.window, **options).unwrap()

    def row(self, batch_id):
        return self.reflection._row(self.context, batch_id)

    def manifest(self, batch_id):
        return json.loads(self.row(batch_id)["manifest_json"])

    def finish(self, batch_id):
        for _ in range(1000):
            row = self.row(batch_id)
            if row["state"] != "selecting":
                return row
            self.reflection.selection.advance(self.context, row)
        self.fail("selection did not make bounded progress")

    def seed(self, count):
        batch = None
        for number in range(count):
            batch = self.accept(self.event("source-" + str(number)), batch_id=batch if number % 32 else None)

    def complete(self, batch_id):
        # Synthetic historical model completion; no provider or delivery I/O.
        with self.runtime.transaction() as db:
            db.execute("UPDATE memory_reflections SET state = 'complete' WHERE batch_id = ?", (batch_id,))


class MemorySelectionTests(SelectionFixture, unittest.TestCase):
    def test_cold_build_resumes_without_full_source_or_fact_owner_reads(self):
        self.seed(260)
        with patch.object(self.recall, "_documents", side_effect=AssertionError("full source scan")), \
                patch.object(self.memory, "read", wraps=self.memory.read) as facts:
            first = self.prepare(maximum_sources=2)
            self.assertEqual(first["state"], "selecting")
            self.assertIsNone(first["remaining_sources"])
            self.assertEqual(self.manifest(first["batch_id"])["evidence"], [])
            last = self.finish(first["batch_id"])
        self.assertEqual(last["state"], "prepared")
        self.assertEqual(len(self.manifest(first["batch_id"])["evidence"]), 2)
        self.assertEqual(self.manifest(first["batch_id"])["remaining_sources"], 258)
        self.assertEqual(facts.call_count, 0)

    def test_warm_selection_skips_completed_and_held_originals_in_sql(self):
        self.seed(8)
        first = self.prepare("first", maximum_sources=3)
        self.complete(first["batch_id"])
        held = self.prepare("held", maximum_sources=2)
        with patch.object(self.recall.objects, "read", wraps=self.recall.objects.read) as originals, \
                patch.object(self.recall, "_documents", side_effect=AssertionError("full source scan")):
            last = self.prepare("last", maximum_sources=2)
        self.assertEqual(originals.call_count, 2)
        manifest = self.manifest(last["batch_id"])
        self.assertEqual(manifest["deferred_sources"], 2)
        self.assertEqual(manifest["remaining_sources"], 1)
        earlier = set()
        for batch in (first, held):
            earlier.update(encode(e) for e in self.manifest(batch["batch_id"])["evidence"])
        self.assertTrue(earlier.isdisjoint(encode(e) for e in manifest["evidence"]))

    def test_long_source_continues_in_original_span_order_across_batches(self):
        self.evidence("正文" * 2300)
        first = self.prepare("first", maximum_chars=2000)
        self.assertEqual(self.manifest(first["batch_id"])["evidence"][0]["start"], 0)
        self.complete(first["batch_id"])
        second = self.prepare("second", maximum_chars=2000)
        self.assertEqual(self.manifest(second["batch_id"])["evidence"][0]["start"], 1900)
        self.complete(second["batch_id"])
        last = self.prepare("last", maximum_chars=2000)
        self.assertEqual(self.manifest(last["batch_id"])["evidence"][0]["start"], 3800)
        self.assertEqual(last["remaining_sources"], 0)

    def test_partial_selection_survives_restart_and_reserves_its_sources(self):
        self.seed(4)
        self.reflection.selection.candidate_items = 1
        first = self.prepare("partial")
        self.assertEqual(first["state"], "selecting")
        original = self.manifest(first["batch_id"])["evidence"]
        root, installation = self.runtime.data_root, self.runtime.installation_id
        self.runtime.close()
        self.runtime = StorageRuntime.open(data_root=root, installation_id=installation)
        self.addCleanup(self.runtime.close)
        self.memory = MemoryWriter(self.supervisor(self.runtime))
        self.recall = MemoryQuery(self.memory)
        self.attach_selection()
        second = self.prepare("other")
        self.assertTrue(set(map(encode, original)).isdisjoint(map(encode, self.manifest(second["batch_id"])["evidence"])))
        self.assertEqual(self.finish(first["batch_id"])["state"], "prepared")
        self.assertEqual(self.manifest(first["batch_id"])["evidence"], original)

    def test_uncommitted_reservations_are_rechecked_on_authoritative_connection(self):
        self.seed(2)
        with self.runtime.transaction():
            first = self.prepare("first")
            second = self.prepare("second")
            self.assertEqual(second["state"], "empty")
            self.assertEqual(self.manifest(second["batch_id"])["evidence"], [])
            self.assertGreater(self.manifest(second["batch_id"])["deferred_sources"], 0)
        self.assertEqual(len(self.manifest(first["batch_id"])["evidence"]), 2)

    def test_outer_rollback_does_not_leave_durable_reservations(self):
        self.seed(2)
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with self.runtime.transaction():
                self.prepare("rolled-back")
                raise RuntimeError("rollback")
        self.assertEqual(self.runtime.read_all("SELECT * FROM memory_reflection_inputs", ()), ())
        next_batch = self.prepare("real")
        self.assertEqual(len(self.manifest(next_batch["batch_id"])["evidence"]), 2)

    def test_busy_cache_preserves_pending_inputs_and_retries_same_batch(self):
        base = self.proposed(defer_until_boundary=True)
        pending = self.memory.submit(self.context, base, operation_key="pending").unwrap()
        with closing(sqlite3.connect(self.recall.index.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            first = self.prepare("busy")
            self.assertEqual(first["state"], "selecting")
            saved = self.manifest(first["batch_id"])
            self.assertEqual(saved["selection"]["blocked_code"], "memory_index_busy")
            self.assertEqual(saved["pending"][0]["operation_id"], pending["operation_id"])
        self.assertEqual(self.prepare("busy")["state"], "prepared")

    def test_fact_index_build_does_not_read_all_facts_or_dispatch_model_early(self):
        base = self.proposed()
        for number in range(5):
            self.remember(replace(base, predicate="偏好" + str(number)), str(number))
        self.recall.fact_index.sync_items = 1
        with patch.object(self.memory, "read", wraps=self.memory.read) as reads:
            first = self.prepare()
        self.assertEqual(first["state"], "selecting")
        self.assertEqual(self.manifest(first["batch_id"])["selection"]["phase"], "facts")
        self.assertEqual(reads.call_count, 0)
        result = asyncio.run(self.reflection.run(self.context, first["batch_id"])).unwrap()
        self.assertEqual(result["state"], "selecting")
        self.assertIsNone(self.row(first["batch_id"])["task_id"])
        self.assertEqual(self.finish(first["batch_id"])["state"], "prepared")
        self.assertEqual(len(self.manifest(first["batch_id"])["facts"]), 5)

    def test_revoked_candidates_are_bounded_and_later_source_is_reached(self):
        self.seed(5)
        snapshot = self.recall.recall_index.advance(self.context, "personal", "sources")
        with self.recall.index.reflection_snapshot(self.runtime.database_path) as db:
            rows = db.execute("SELECT * FROM recall_documents WHERE owner = ? ORDER BY json_extract(metadata_json, '$.source_id')", (snapshot["partition"],)).fetchall()
        for row in rows[:4]:
            reference = self.recall.objects.source(self.context, "human", row["object_id"])[0]
            self.memory.sources.revoke(reference, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.reflection.selection.candidate_items = 2
        with patch.object(self.recall.objects, "read", wraps=self.recall.objects.read) as originals:
            first = self.prepare()
        self.assertEqual(first["state"], "selecting")
        self.assertEqual(originals.call_count, 2)
        self.finish(first["batch_id"])
        self.assertEqual(len(self.manifest(first["batch_id"])["evidence"]), 1)
        self.assertTrue(self.manifest(first["batch_id"])["unavailable_sources"])

    def test_revoking_selected_source_before_next_step_stops_preparation(self):
        evidence = self.evidence()
        for number in range(3):
            self.remember(replace(self.proposed(), predicate=str(number)), str(number))
        self.recall.fact_index.sync_items = 1
        first = self.prepare()
        self.assertEqual(first["state"], "selecting")
        self.memory.sources.revoke(evidence.source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        result = asyncio.run(self.reflection.run(self.context, first["batch_id"]))
        self.assertFalse(result.is_success)
        self.assertEqual(self.row(first["batch_id"])["state"], "failed")
        self.assertIsNone(self.row(first["batch_id"])["task_id"])

    def test_changed_window_cannot_take_over_partial_selection(self):
        self.seed(3)
        self.recall.recall_index.sync_items = 1
        first = self.prepare()
        changed = {**self.window, "start": self.window["start"] - timedelta(hours=1)}
        result = self.reflection.prepare(self.context, request_id="selection", **changed)
        self.assertEqual(result.failure.code, "memory_reflection_conflict")
        self.assertEqual(self.row(first["batch_id"])["state"], "selecting")

    def test_original_time_is_checked_after_tampered_cache_filter(self):
        self.evidence()
        self.window["end"] -= timedelta(seconds=2)
        self.recall.recall_index.advance(self.context, "personal", "sources")
        with closing(self.recall.index._open()) as db, db:
            db.execute("UPDATE recall_documents SET metadata_json = json_set(metadata_json, '$.message_time', ?)",
                       ((self.window["end"] - timedelta(seconds=1)).isoformat(timespec="microseconds"),))
        first = self.prepare()
        self.assertEqual(first["state"], "empty")
        self.assertEqual(self.manifest(first["batch_id"])["evidence"], [])
        self.assertTrue(self.manifest(first["batch_id"])["unavailable_sources"])

    def test_new_arrivals_during_fact_preparation_require_another_batch(self):
        base = self.proposed()
        for number in range(5):
            self.remember(replace(base, predicate=str(number)), str(number))
        self.recall.fact_index.sync_items = 1
        first = self.prepare()
        self.assertEqual(first["state"], "selecting")
        original = self.manifest(first["batch_id"])["evidence"]
        new = self.evidence("准备期间新增")
        self.finish(first["batch_id"])
        self.assertEqual(self.manifest(first["batch_id"])["evidence"], original)
        self.assertTrue(self.reflection.status(self.context, first["batch_id"]).unwrap()["continuation_needed"])
        self.complete(first["batch_id"])
        second = self.prepare("next")
        self.assertIn(json.loads(encode(new)), self.manifest(second["batch_id"])["evidence"])
        self.assertFalse(self.reflection.status(self.context, second["batch_id"]).unwrap()["continuation_needed"])

    def test_idempotent_prepare_quarantines_withdrawn_partial_inputs(self):
        self.seed(3)
        self.reflection.selection.candidate_items = 1
        first = self.prepare()
        from companion_v2.memory import codec
        original = codec.evidence(self.manifest(first["batch_id"])["evidence"][0])
        self.memory.sources.revoke(original.source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        result = self.reflection.prepare(self.context, request_id="selection", **self.window)
        self.assertEqual(result.failure.code, "source_revoked")
        self.assertEqual(self.row(first["batch_id"])["state"], "failed")

    def test_pending_selection_reaches_items_beyond_held_first_page(self):
        base = self.proposed(defer_until_boundary=True)
        for number in range(33):
            self.memory.submit(self.context, replace(base, predicate=str(number)), operation_key=str(number)).unwrap()
        first = self.prepare("pending-first")
        self.assertEqual(len(self.manifest(first["batch_id"])["pending"]), 32)
        second = self.prepare("pending-second")
        self.assertEqual(len(self.manifest(second["batch_id"])["pending"]), 1)
        self.assertTrue({v["operation_id"] for v in self.manifest(first["batch_id"])["pending"]}.isdisjoint(
            v["operation_id"] for v in self.manifest(second["batch_id"])["pending"]))

    def test_unrelated_cache_epoch_does_not_restart_candidate_seek(self):
        self.seed(5)
        snapshot = self.recall.recall_index.advance(self.context, "personal", "sources")
        with closing(self.recall.index._open()) as db:
            rows = db.execute("SELECT * FROM recall_documents WHERE owner = ? ORDER BY json_extract(metadata_json, '$.source_id')",
                              (snapshot["partition"],)).fetchall()
        for row in rows[:4]:
            reference = self.recall.objects.source(self.context, "human", row["object_id"])[0]
            self.memory.sources.revoke(reference, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.reflection.selection.candidate_items = 2
        with patch.object(self.recall.objects, "read", wraps=self.recall.objects.read) as originals:
            first = self.prepare()
            for _ in range(2):
                with closing(self.recall.index._open()) as db, db:
                    db.execute("UPDATE recall_epoch SET revision = revision + 1 WHERE singleton = 1")
                self.reflection.selection.advance(self.context, self.row(first["batch_id"]))
        self.assertEqual(self.row(first["batch_id"])["state"], "prepared")
        self.assertEqual(originals.call_count, 5)
        self.assertEqual(len(self.manifest(first["batch_id"])["evidence"]), 1)

    def test_related_fact_query_busy_does_not_discard_selected_material(self):
        self.seed(2)
        with patch.object(self.recall, "query", return_value=Outcome.failed("memory_index_busy", "synthetic cache lock")):
            first = self.prepare()
        self.assertEqual(first["state"], "selecting")
        saved = self.manifest(first["batch_id"])
        self.assertEqual(saved["selection"]["phase"], "facts")
        self.assertEqual(saved["selection"]["blocked_code"], "memory_index_busy")
        self.assertEqual(len(saved["evidence"]), 2)
        self.assertEqual(self.prepare()["state"], "prepared")
        self.assertEqual(self.manifest(first["batch_id"])["evidence"], saved["evidence"])

    def test_chinese_identifiers_use_same_membership_key_as_sql_triggers(self):
        self.context = self.alternate_context(bot_id="机器人甲", role_id="原角色")
        self.grant(self.context.actor, self.context.scope, "text")
        evidence = self.evidence("中文资料")
        first = self.prepare("中文整理")
        keys = {r["input_key"] for r in self.runtime.read_all("SELECT input_key FROM memory_reflection_inputs WHERE batch_id = ?", (first["batch_id"],))}
        self.assertIn(span_key(evidence), keys)
        self.complete(first["batch_id"])
        self.assertEqual(self.prepare("下一批")["state"], "empty")


class SelectionMigrationTests(SelectionFixture, unittest.TestCase):
    def historical(self):
        database, root, installation = self.runtime.database_path, self.runtime.data_root, self.runtime.installation_id
        self.runtime.close()
        with closing(sqlite3.connect(database)) as db, db:
            remove_v27(db)
            db.execute("UPDATE runtime_metadata SET value = 'companion-v2.storage.v26' WHERE key = 'schema_version'")
        return database, root, installation

    def test_v26_upgrade_backfills_prepared_complete_and_pending_membership(self):
        base = self.proposed(defer_until_boundary=True)
        self.memory.submit(self.context, base, operation_key="pending").unwrap()
        self.evidence("尚未反思的另一份资料")
        first = self.prepare(maximum_sources=1)
        self.complete(first["batch_id"])
        held = self.prepare("held")
        expected = [tuple(r) for r in self.runtime.read_all("SELECT * FROM memory_reflection_inputs ORDER BY batch_id, kind, input_key", ())]
        database, root, installation = self.historical()
        reopened = StorageRuntime.open(data_root=root, installation_id=installation)
        self.addCleanup(reopened.close)
        self.assertEqual([tuple(r) for r in reopened.read_all("SELECT * FROM memory_reflection_inputs ORDER BY batch_id, kind, input_key", ())], expected)
        self.assertEqual({r[2] for r in expected}, {"evidence", "pending", "pending_evidence"})
        self.assertEqual(reopened.read_one("SELECT state FROM memory_reflections WHERE batch_id = ?", (first["batch_id"],))[0], "complete")
        self.assertEqual(reopened.read_one("SELECT state FROM memory_reflections WHERE batch_id = ?", (held["batch_id"],))[0], "prepared")
        self.assertEqual(reopened.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())[0], SCHEMA_VERSION)

    def test_failed_v27_upgrade_rolls_back_reservations_and_receipt(self):
        self.evidence()
        self.prepare()
        database, root, installation = self.historical()
        original = StorageRuntime._migrate_v26_to_v27
        def fail(runtime, db):
            original(runtime, db)
            raise StorageOpenError("synthetic reservation failure")
        with patch.object(StorageRuntime, "_migrate_v26_to_v27", fail), self.assertRaisesRegex(StorageOpenError, "synthetic"):
            StorageRuntime.open(data_root=root, installation_id=installation)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], "companion-v2.storage.v26")
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name = 'memory_reflection_inputs'").fetchone())
            self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v26-to-v27'").fetchone())
        reopened = StorageRuntime.open(data_root=root, installation_id=installation)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.read_one("SELECT COUNT(*) FROM memory_reflection_inputs", ())[0], 1)

    def test_missing_reservation_trigger_is_rejected_on_reopen(self):
        database, root, installation = self.runtime.database_path, self.runtime.data_root, self.runtime.installation_id
        self.runtime.close()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("DROP TRIGGER reflection_inputs_update")
        with self.assertRaisesRegex(StorageOpenError, "reservations are incomplete"):
            StorageRuntime.open(data_root=root, installation_id=installation)
