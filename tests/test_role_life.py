from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.execution.models import encode
from companion_v2.foundation.refs import AssetRef, ReferenceValidationError, RoleOwnerRef, SourceRef, VersionRef
from companion_v2.role_work import (
    PersistentRoleLifeLedger, RoleActivity, RoleActivityState as State, RoleArtifact,
    RoleArtifactJournalMeaning as Meaning, RoleArtifactKind, RoleLifeLedger,
)
from companion_v2.storage.runtime import StorageRuntime
from tests.test_management_access import INSTALLATION, NOW, ROLE, SCOPE


class RoleLifeTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="companion-v2-life-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "runtime"
        self.runtime = self.open_runtime()
        self.ledger = PersistentRoleLifeLedger(self.runtime, now=lambda: NOW)
        self.original = RoleActivity("reading", ROLE.subject_id, SCOPE, NOW, State.ACTIVE, description="阅读一本书")
        self.owner = self.original.owner

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def transition(self, state=State.PAUSED, *, revision=1, operation="pause", **changes):
        return self.ledger.transition_activity("reading", owner=self.owner, expected_revision=revision,
            state=state, operation_id=operation, **changes)

    def test_pause_restart_resume_and_old_operation_replay_keep_original_progress(self):
        self.ledger.add_activity(self.original)
        paused = self.transition(checkpoint="第三章读到一半", observed_at=NOW + timedelta(minutes=5))
        self.runtime.close()
        self.runtime = self.open_runtime()
        self.ledger = PersistentRoleLifeLedger(self.runtime, now=lambda: NOW + timedelta(days=3))
        self.assertEqual(self.ledger.activity("reading", owner=self.owner), paused)
        self.assertEqual(self.ledger.activities_for_role(self.owner), (paused,))
        self.assertEqual(self.transition(checkpoint="第三章读到一半"), paused)
        resumed = self.transition(State.ACTIVE, revision=2, operation="resume")
        self.assertEqual((resumed.state, resumed.revision, resumed.checkpoint), (State.ACTIVE, 3, paused.checkpoint))
        self.assertEqual(self.transition(checkpoint="第三章读到一半"), paused)
        self.assertEqual(self.ledger.activity("reading", owner=self.owner), resumed)
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM role_life_operations", ())), 2)

    def test_same_operation_with_changed_parameters_cannot_overwrite_progress(self):
        self.ledger.add_activity(self.original)
        paused = self.transition(checkpoint="第三章")
        with self.assertRaises(ValueError):
            self.transition(checkpoint="第十章")
        self.assertEqual(self.ledger.activity("reading", owner=self.owner), paused)

    def test_two_connections_reject_stale_writer_and_rollback_its_operation(self):
        self.ledger.add_activity(self.original)
        other = PersistentRoleLifeLedger(self.open_runtime(), now=lambda: NOW)
        paused = self.transition()
        with self.assertRaises(ReferenceValidationError):
            other.transition_activity("reading", owner=self.owner, expected_revision=1, state=State.COMPLETED,
                                      operation_id="stale-completion")
        self.assertEqual(other.activity("reading", owner=self.owner), paused)
        self.assertEqual(other.operations.get("stale-completion").failure.code, "operation_not_found")

    def test_owner_change_and_operation_result_share_outer_rollback(self):
        self.ledger.add_activity(self.original)
        with self.assertRaises(RuntimeError):
            with self.runtime.transaction():
                self.transition(checkpoint="不应留下的进度")
                raise RuntimeError("abort enclosing owner command")
        self.assertEqual(self.ledger.activity("reading", owner=self.owner), self.original)
        self.assertEqual(self.ledger.operations.get("pause").failure.code, "operation_not_found")
        self.assertEqual(self.runtime.read_all("SELECT * FROM role_life_operations", ()), ())

    def test_same_role_cross_window_continuity_and_same_ids_in_other_owners(self):
        variants = (
            self.original,
            replace(self.original, activity_id="walking", scope=replace(SCOPE, session_id="second-window")),
            replace(self.original, role_id="another-role"),
            replace(self.original, scope=replace(SCOPE, bot_id="another-bot")),
        )
        for activity in variants:
            self.ledger.add_activity(activity)
        self.assertEqual(self.ledger.activities_for_role(self.owner), variants[:2])
        self.assertEqual(self.ledger.activities_for_role(variants[2].owner), (variants[2],))
        self.assertEqual(self.ledger.activities_for_role(variants[3].owner), (variants[3],))
        with self.assertRaises(KeyError):
            self.ledger.activity("walking", owner=variants[2].owner)
        with self.assertRaises(ReferenceValidationError):
            self.ledger.activities_for_role(RoleOwnerRef("other-installation", self.owner.bot_id, self.owner.persona_id))

    def test_stable_inventory_pages_and_state_filter(self):
        for name in ("a", "b", "c"):
            self.ledger.add_activity(replace(self.original, activity_id=name, state=State.PLANNED))
        self.ledger.add_activity(self.original)
        first = self.ledger.activities_for_role(self.owner, state=State.PLANNED, limit=2)
        second = self.ledger.activities_for_role(self.owner, state=State.PLANNED, limit=2, after_id=first[-1].activity_id)
        self.assertEqual([a.activity_id for a in first + second], ["a", "b", "c"])
        for invalid in (0, 101, True):
            with self.assertRaises(ReferenceValidationError):
                self.ledger.activities_for_role(self.owner, limit=invalid)

    def test_plans_do_not_complete_due_to_time_and_closed_activities_do_not_restart(self):
        planned = replace(self.original, state=State.PLANNED)
        self.ledger.add_activity(planned)
        future = PersistentRoleLifeLedger(self.runtime, now=lambda: NOW + timedelta(days=365))
        self.assertEqual(future.activity("reading", owner=self.owner), planned)
        with self.assertRaises(ReferenceValidationError):
            self.transition(State.COMPLETED, operation="skip-work")
        self.transition(State.ACTIVE, operation="start")
        completed = self.transition(State.COMPLETED, revision=2, operation="complete", checkpoint="实际已完成")
        with self.assertRaises(ReferenceValidationError):
            self.transition(State.ACTIVE, revision=3, operation="resurrect")
        self.assertEqual(self.ledger.activity("reading", owner=self.owner), completed)

    def test_artifact_survives_reopen_with_original_source_asset_owner_and_scope(self):
        self.ledger.add_activity(self.original)
        source = SourceRef("image-source", "role.life", SCOPE, VersionRef("image-source", 2), NOW,
                           NOW + timedelta(days=1))
        asset = AssetRef("image-asset", "role.life", SCOPE, VersionRef("image-asset", 3), "actual-content-hash")
        artifact = RoleArtifact("image", "reading", RoleArtifactKind.IMAGE, source, NOW, asset)
        saved = self.ledger.add_artifact(artifact, owner=self.owner)
        self.assertEqual(self.ledger.add_artifact(artifact, owner=self.owner), saved)
        self.assertEqual(self.ledger.activity("reading", owner=self.owner), self.original)
        self.runtime.close()
        self.ledger = PersistentRoleLifeLedger(self.open_runtime())
        self.assertEqual(self.ledger.artifact("image", owner=self.owner), saved)
        self.assertEqual(self.ledger.artifacts_for_role(self.owner), (saved,))
        self.assertEqual(self.ledger.artifacts_for_scope(SCOPE, owner=self.owner), (saved,))
        self.assertEqual(self.ledger.artifacts_for_scope(replace(SCOPE, session_id="other"), owner=self.owner), ())

    def test_artifact_cannot_be_rebound_to_another_original_or_role(self):
        self.ledger.add_activity(self.original)
        source = SourceRef("source", "role.life", SCOPE, VersionRef("source", 1), NOW)
        artifact = RoleArtifact("text", "reading", RoleArtifactKind.TEXT, source, NOW)
        saved = self.ledger.add_artifact(artifact, owner=self.owner)
        for forged in (replace(artifact, owner=replace(self.owner, persona_id="other")),
                       replace(artifact, journal_meaning=Meaning.CREATIVE_TEXT),
                       replace(artifact, source=replace(source, source_id="replacement")),
                       replace(artifact, artifact_id="cross-scope", source=replace(source, scope=replace(SCOPE, session_id="other")))):
            with self.assertRaises(ReferenceValidationError):
                self.ledger.add_artifact(forged, owner=self.owner)
        self.assertEqual(self.ledger.artifacts_for_role(self.owner), (saved,))

    def test_artifact_meaning_survives_reopen_and_is_immutable_in_both_ledgers(self):
        memory = RoleLifeLedger()
        for ledger in (self.ledger, memory):
            ledger.add_activity(self.original)
        saved = []
        for meaning in (Meaning.CREATIVE_TEXT, Meaning.READING):
            source = SourceRef(meaning.value, "role.life", SCOPE, VersionRef(meaning.value, 1), NOW)
            artifact = RoleArtifact(meaning.value, "reading", RoleArtifactKind.TEXT, source, NOW,
                                    journal_meaning=meaning)
            saved.append(self.ledger.add_artifact(artifact, owner=self.owner))
            self.assertEqual(memory.add_artifact(artifact), saved[-1])
            with self.assertRaises(ReferenceValidationError):
                memory.add_artifact(replace(artifact, journal_meaning=Meaning.UNCLASSIFIED))
        self.runtime.close()
        self.ledger = PersistentRoleLifeLedger(self.open_runtime())
        for artifact in saved:
            self.assertEqual(self.ledger.artifact(artifact.artifact_id, owner=self.owner), artifact)
            self.assertEqual(self.ledger.add_artifact(artifact, owner=self.owner), artifact)
            with self.assertRaises(ReferenceValidationError):
                self.ledger.add_artifact(replace(artifact, journal_meaning=Meaning.UNCLASSIFIED), owner=self.owner)

    def test_legacy_artifact_without_meaning_reopens_unclassified_and_replays_without_rewrite(self):
        self.ledger.add_activity(self.original)
        source = SourceRef("legacy", "role.life", SCOPE, VersionRef("legacy", 1), NOW)
        artifact = RoleArtifact("legacy", "reading", RoleArtifactKind.TEXT, source, NOW)
        saved = self.ledger.add_artifact(artifact, owner=self.owner)
        old = json.loads(encode(saved))
        old.pop("journal_meaning")
        old_json = encode(old)
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE role_artifacts SET record_json = ? WHERE artifact_id = ?",
                               (old_json, "legacy"))
        self.runtime.close()
        runtime = self.open_runtime()
        ledger = PersistentRoleLifeLedger(runtime)
        restored = ledger.artifact("legacy", owner=self.owner)
        self.assertEqual(restored, saved)
        self.assertEqual(restored.journal_meaning, Meaning.UNCLASSIFIED)
        self.assertEqual(ledger.add_artifact(artifact, owner=self.owner), saved)
        self.assertEqual(runtime.read_one("SELECT record_json FROM role_artifacts", ())["record_json"], old_json)

    def test_artifact_classification_requires_the_explicit_host_enum(self):
        source = SourceRef("source", "role.life", SCOPE, VersionRef("source", 1), NOW)
        for invalid in ("creative_text", "reading", "published_text", None):
            with self.subTest(meaning=invalid), self.assertRaises(ReferenceValidationError):
                RoleArtifact("text", "reading", RoleArtifactKind.TEXT, source, NOW, journal_meaning=invalid)

    def test_legacy_activity_and_operation_without_reading_receipt_remain_replayable(self):
        self.ledger.add_activity(self.original)
        paused = self.transition(checkpoint="旧版进度")
        with self.runtime.transaction() as connection:
            for table, column in (("role_activities", "record_json"), ("role_life_operations", "result_json")):
                row = connection.execute(f"SELECT {column} FROM {table}").fetchone()
                old = json.loads(row[column])
                old.pop("reading")
                connection.execute(f"UPDATE {table} SET {column} = ?", (encode(old),))
        self.runtime.close()
        self.ledger = PersistentRoleLifeLedger(self.open_runtime())
        self.assertEqual(self.transition(checkpoint="旧版进度"), paused)
        self.assertIsNone(self.ledger.activity("reading", owner=self.owner).reading)


if __name__ == "__main__":
    unittest.main()
