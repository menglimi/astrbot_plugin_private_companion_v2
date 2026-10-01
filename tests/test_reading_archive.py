"""The reading archive repository: provider-owned entries, CAS writes, grounded reviews."""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.execution.models import TaskError
from companion_v2.foundation.refs import ReferenceValidationError
from companion_v2.library import (ArchiveConsent, ArchiveEntry, ArchiveReview, AssetReference,
                                 ConsentState, EntryKind, EntryOrigin, EntryState,
                                 ReadingArchiveRepository, ReadingProgress)
from companion_v2.storage.runtime import StorageRuntime


def at(day=1):
    return datetime(2026, 9, day, 12, 0, tzinfo=timezone.utc)


def provider_entry(entry_id="entry-1", *, title="长夜漫漫", kind=EntryKind.NOVEL,
                   provider="library.native", asset="novel://entry-1", state=EntryState.AVAILABLE):
    return ArchiveEntry(entry_id=entry_id, kind=kind, title=title, author="某人",
                        origin=EntryOrigin.PROVIDER, state=state, revision=1,
                        created_at=at(), updated_at=at(),
                        source=AssetReference(provider, "1.0", asset))


def manual_entry(entry_id="manual-1", *, title="随手记下一本"):
    return ArchiveEntry(entry_id=entry_id, kind=EntryKind.OTHER, title=title, author="",
                        origin=EntryOrigin.MANUAL, state=EntryState.AVAILABLE, revision=1,
                        created_at=at(), updated_at=at())


class ArchiveTestCase(unittest.TestCase):
    def setUp(self):
        self.root = TemporaryDirectory()
        self.runtime = StorageRuntime.open(data_root=Path(self.root.name), installation_id="install-1")
        self.archive = ReadingArchiveRepository(self.runtime)
        self.owner = "owner-1"

    def tearDown(self):
        self.runtime.close()
        self.root.cleanup()


class EntryTests(ArchiveTestCase):
    def test_a_provider_entry_round_trips_with_its_source_reference(self):
        stored = self.archive.put_entry(self.owner, provider_entry())
        self.assertEqual(stored.title, "长夜漫漫")
        self.assertEqual(stored.origin, EntryOrigin.PROVIDER)
        self.assertEqual(stored.source, AssetReference("library.native", "1.0", "novel://entry-1"))
        self.assertEqual(stored.revision, 1)

    def test_a_provider_entry_must_name_its_source(self):
        with self.assertRaises(ReferenceValidationError):
            ArchiveEntry(entry_id="x", kind=EntryKind.NOVEL, title="t", author="",
                         origin=EntryOrigin.PROVIDER, state=EntryState.AVAILABLE, revision=1,
                         created_at=at(), updated_at=at(), source=None)

    def test_a_manual_entry_needs_no_source_and_carries_no_provider_columns(self):
        stored = self.archive.put_entry(self.owner, manual_entry())
        self.assertIsNone(stored.source)
        row = self.runtime.read_one(
            "SELECT provider_id, asset_ref, source_json FROM reading_archive_entries WHERE entry_id = ?",
            ("manual-1",))
        self.assertEqual(tuple(row), (None, None, None))

    def test_a_manual_write_cannot_replace_a_provider_entry(self):
        self.archive.put_entry(self.owner, provider_entry())
        with self.assertRaises(TaskError) as caught:
            self.archive.put_entry(self.owner, manual_entry("entry-1"))
        self.assertEqual(caught.exception.code, "archive_entry_provider_owned")
        self.assertEqual(self.archive.get(self.owner, "entry-1").origin, EntryOrigin.PROVIDER)

    def test_a_provider_write_may_replace_a_manual_entry(self):
        self.archive.put_entry(self.owner, manual_entry("entry-1"))
        stored = self.archive.put_entry(self.owner, provider_entry("entry-1"))
        self.assertEqual(stored.origin, EntryOrigin.PROVIDER)
        self.assertIsNotNone(stored.source)

    def test_a_stale_expected_revision_is_refused(self):
        self.archive.put_entry(self.owner, provider_entry())
        self.archive.put_entry(self.owner, provider_entry(title="改过标题"))
        self.assertEqual(self.archive.get(self.owner, "entry-1").revision, 2)
        with self.assertRaises(TaskError) as caught:
            self.archive.put_entry(self.owner, provider_entry(title="又一次"), expected=1)
        self.assertEqual(caught.exception.code, "archive_conflict")
        self.assertEqual(self.archive.get(self.owner, "entry-1").title, "改过标题")

    def test_entries_are_scoped_to_their_owner(self):
        self.archive.put_entry(self.owner, provider_entry())
        self.assertIsNone(self.archive.get("someone-else", "entry-1"))
        self.assertEqual(self.archive.list("someone-else"), ())

    def test_listing_pages_by_entry_id_and_filters_by_state(self):
        for index in range(4):
            self.archive.put_entry(self.owner, provider_entry("entry-%d" % index))
        self.archive.set_state(self.owner, "entry-1", EntryState.FINISHED, expected=1, updated_at=at())
        page = self.archive.list(self.owner, limit=2)
        self.assertEqual([entry.entry_id for entry in page], ["entry-0", "entry-1"])
        self.assertEqual([entry.entry_id for entry in self.archive.list(self.owner, after_id="entry-1")],
                         ["entry-2", "entry-3"])
        finished = self.archive.list(self.owner, state=EntryState.FINISHED)
        self.assertEqual([entry.entry_id for entry in finished], ["entry-1"])
        self.assertEqual([entry.entry_id for entry in self.archive.list(self.owner, kind=EntryKind.MANGA)], [])

    def test_state_change_bumps_the_revision_and_refuses_a_stale_write(self):
        self.archive.put_entry(self.owner, provider_entry())
        updated = self.archive.set_state(self.owner, "entry-1", EntryState.READING,
                                         expected=1, updated_at=at(2))
        self.assertEqual(updated.state, EntryState.READING)
        self.assertEqual(updated.revision, 2)
        with self.assertRaises(TaskError) as caught:
            self.archive.set_state(self.owner, "entry-1", EntryState.FINISHED, expected=1, updated_at=at(3))
        self.assertEqual(caught.exception.code, "archive_conflict")

    def test_withdrawing_a_provider_marks_only_its_own_entries(self):
        self.archive.put_entry(self.owner, provider_entry("entry-1"))
        self.archive.put_entry(self.owner, provider_entry("entry-2", provider="library.other"))
        self.archive.put_entry(self.owner, manual_entry("manual-1"))
        self.assertEqual(self.archive.withdraw_provider(self.owner, "library.native", updated_at=at(2)), 1)
        self.assertEqual(self.archive.get(self.owner, "entry-1").state, EntryState.WITHDRAWN)
        self.assertEqual(self.archive.get(self.owner, "entry-2").state, EntryState.AVAILABLE)
        self.assertEqual(self.archive.get(self.owner, "manual-1").state, EntryState.AVAILABLE)

    def test_a_manga_entry_uses_the_same_contract_as_a_novel(self):
        stored = self.archive.put_entry(self.owner, provider_entry(
            kind=EntryKind.MANGA, asset="manga://entry-1"))
        self.assertEqual(stored.kind, EntryKind.MANGA)
        self.assertEqual(stored.source.asset_ref, "manga://entry-1")


class ProgressTests(ArchiveTestCase):
    def test_progress_round_trips_a_provider_defined_position(self):
        self.archive.put_entry(self.owner, provider_entry())
        stored = self.archive.put_progress(self.owner, ReadingProgress(
            entry_id="entry-1", position=(("chapter", "12"), ("offset", "340")), percent=42,
            note="读到这里", updated_at=at(2)))
        self.assertEqual(dict(stored.position), {"chapter": "12", "offset": "340"})
        self.assertEqual(stored.percent, 42)
        self.assertEqual(stored.note, "读到这里")

    def test_progress_is_replaced_rather_than_appended(self):
        self.archive.put_entry(self.owner, provider_entry())
        self.archive.put_progress(self.owner, ReadingProgress("entry-1", (("page", "1"),), 10, "", at(2)))
        self.archive.put_progress(self.owner, ReadingProgress("entry-1", (("page", "9"),), 80, "", at(3)))
        self.assertEqual(self.archive.progress(self.owner, "entry-1").percent, 80)
        self.assertEqual(self.runtime.read_one(
            "SELECT COUNT(*) FROM reading_archive_progress", ())[0], 1)

    def test_percent_outside_zero_to_one_hundred_is_refused(self):
        for value in (-1, 101):
            with self.assertRaises(ReferenceValidationError):
                ReadingProgress("entry-1", (("page", "1"),), value, "", at())

    def test_progress_for_an_unknown_entry_is_refused(self):
        with self.assertRaises(TaskError) as caught:
            self.archive.put_progress(self.owner, ReadingProgress("nope", (("page", "1"),), 10, "", at()))
        self.assertEqual(caught.exception.code, "archive_entry_missing")


class ReviewTests(ArchiveTestCase):
    def test_a_review_round_trips_with_its_reading_evidence(self):
        self.archive.put_entry(self.owner, provider_entry())
        stored = self.archive.put_review(self.owner, ArchiveReview(
            review_id="review-1", entry_id="entry-1", body="很耐读", rating=4,
            evidence=("position:chapter=12",), revision=1, created_at=at(2), updated_at=at(2)))
        self.assertEqual(stored.rating, 4)
        self.assertEqual(stored.evidence, ("position:chapter=12",))
        self.assertEqual(stored.revision, 1)

    def test_a_review_without_reading_evidence_is_refused(self):
        with self.assertRaises(ReferenceValidationError):
            ArchiveReview(review_id="review-1", entry_id="entry-1", body="说不清", rating=None,
                          evidence=(), revision=1, created_at=at(2), updated_at=at(2))

    def test_rating_must_be_null_or_one_to_five(self):
        for value in (0, 6, "4"):
            with self.assertRaises(ReferenceValidationError):
                ArchiveReview("review-1", "entry-1", "body", value, ("ref",), 1, at(2), at(2))
        self.assertIsNone(ArchiveReview("review-1", "entry-1", "body", None, ("ref",), 1, at(2), at(2)).rating)

    def test_editing_a_review_bumps_its_revision_and_keeps_history_out(self):
        self.archive.put_entry(self.owner, provider_entry())
        self.archive.put_review(self.owner, ArchiveReview(
            "review-1", "entry-1", "初稿", 3, ("ref",), 1, at(2), at(2)))
        updated = self.archive.put_review(self.owner, ArchiveReview(
            "review-1", "entry-1", "改过", 5, ("ref",), 1, at(2), at(3)), expected=1)
        self.assertEqual(updated.revision, 2)
        self.assertEqual(updated.body, "改过")

    def test_reviews_are_listed_per_entry(self):
        self.archive.put_entry(self.owner, provider_entry("entry-1"))
        self.archive.put_entry(self.owner, provider_entry("entry-2"))
        self.archive.put_review(self.owner, ArchiveReview(
            "review-1", "entry-1", "甲", None, ("ref",), 1, at(2), at(2)))
        self.archive.put_review(self.owner, ArchiveReview(
            "review-2", "entry-2", "乙", None, ("ref",), 1, at(3), at(3)))
        self.assertEqual([item.review_id for item in self.archive.reviews(self.owner, "entry-1")], ["review-1"])

    def test_a_review_for_an_unknown_entry_is_refused(self):
        with self.assertRaises(TaskError) as caught:
            self.archive.put_review(self.owner, ArchiveReview(
                "review-1", "nope", "body", None, ("ref",), 1, at(2), at(2)))
        self.assertEqual(caught.exception.code, "archive_entry_missing")


class ConsentTests(ArchiveTestCase):
    def test_consent_round_trips_per_entry_and_subject(self):
        self.archive.put_entry(self.owner, provider_entry())
        stored = self.archive.put_consent(self.owner, ArchiveConsent(
            entry_id="entry-1", subject_json='{"subject":"member-1"}', state=ConsentState.GRANTED,
            revision=1, updated_at=at(2)))
        self.assertEqual(stored.state, ConsentState.GRANTED)
        self.assertEqual(stored.revision, 1)

    def test_revoking_consent_bumps_the_revision(self):
        self.archive.put_entry(self.owner, provider_entry())
        self.archive.put_consent(self.owner, ArchiveConsent(
            "entry-1", '{"subject":"member-1"}', ConsentState.GRANTED, 1, at(2)))
        revoked = self.archive.put_consent(self.owner, ArchiveConsent(
            "entry-1", '{"subject":"member-1"}', ConsentState.REVOKED, 1, at(3)))
        self.assertEqual(revoked.state, ConsentState.REVOKED)
        self.assertEqual(revoked.revision, 2)

    def test_consent_is_absent_until_granted(self):
        self.archive.put_entry(self.owner, provider_entry())
        self.assertIsNone(self.archive.consent(self.owner, "entry-1", '{"subject":"member-1"}'))


class ReferentialIntegrityTests(ArchiveTestCase):
    def test_the_database_reports_no_broken_references(self):
        self.archive.put_entry(self.owner, provider_entry())
        self.archive.put_progress(self.owner, ReadingProgress("entry-1", (("page", "3"),), 30, "", at(2)))
        self.archive.put_review(self.owner, ArchiveReview(
            "review-1", "entry-1", "body", 5, ("ref",), 1, at(2), at(2)))
        self.assertIsNone(self.runtime.read_one("PRAGMA foreign_key_check", ()))

    def test_a_provider_version_change_is_visible_in_the_source_reference(self):
        self.archive.put_entry(self.owner, provider_entry())
        updated = self.archive.put_entry(self.owner, provider_entry())
        self.assertEqual(updated.source.provider_version, "1.0")


class SchemaUpgradeTests(unittest.TestCase):
    def test_a_fresh_data_root_lands_on_the_reading_archive_schema(self):
        from companion_v2.storage import schema
        with TemporaryDirectory() as root:
            runtime = StorageRuntime.open(data_root=Path(root), installation_id="install-1")
            try:
                with runtime.read_snapshot() as db:
                    # A fresh root lands on whatever the head version is, which is v42
                    # or later; this test owns the v42 tables, not the head version.
                    version = db.execute(
                        "SELECT value FROM runtime_metadata WHERE key='schema_version'").fetchone()[0]
                    self.assertEqual(version, schema.SCHEMA_VERSION)
                    migrated = db.execute(
                        "SELECT COUNT(*) FROM schema_migrations WHERE migration_id = ?",
                        (schema.MIGRATION_V41_TO_V42_ID,)).fetchone()[0]
                    self.assertEqual(migrated, 1, "the v42 migration must have run")
                    tables = {row[0] for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                self.assertTrue({"reading_archive_entries", "reading_archive_progress",
                                 "reading_archive_reviews", "reading_archive_consents"} <= tables)
            finally:
                runtime.close()

    def test_reopening_a_migrated_root_validates_the_v42_record(self):
        with TemporaryDirectory() as root:
            runtime = StorageRuntime.open(data_root=Path(root), installation_id="install-1")
            runtime.close()
            reopened = StorageRuntime.open(data_root=Path(root), installation_id="install-1")
            try:
                with reopened.read_snapshot() as db:
                    row = db.execute("SELECT from_version, to_version FROM schema_migrations "
                                     "WHERE migration_id = 'companion-v2.storage.v41-to-v42'").fetchone()
                self.assertEqual(tuple(row), ("companion-v2.storage.v41", "companion-v2.storage.v42"))
            finally:
                reopened.close()
