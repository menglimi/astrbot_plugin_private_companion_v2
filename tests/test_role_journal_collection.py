"""Complete dated inventories feed the existing writer without silent truncation."""

from dataclasses import replace
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.execution.models import TaskError, encode
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.role_work import PersistentRoleLifeLedger, RoleArtifact, RoleArtifactJournalMeaning as Meaning, RoleArtifactKind
from companion_v2.role_work.journal import MaterialKind
from companion_v2.role_work.journal.material_producer import JournalMaterialPage
from companion_v2.role_work.journal.writing import writing_profiles
from tests.test_management_access import NOW, SCOPE
from tests.test_role_reading import ReadingFixture
from tests.test_role_tool_loop import answered


class JournalCollectionTests(ReadingFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.profiles += writing_profiles("primary", max_output_tokens=100)
        self.registry = FieldRegistry(version="collection.v1", fields=configuration_fields(self.profiles))

    async def test_collection_scans_filtered_pages_and_combines_reading_artifacts_and_dialogue(self):
        await self.setup_reading()
        self.add_activity("a-old", at=NOW - timedelta(days=1), description="昨天的事")
        self.add_activity("b-foreign", scope=replace(SCOPE, session_id="other"), description="别的窗口的事")
        self.add_activity("c-empty")
        self.record().unwrap()
        self.add_activity("story", description="创作一个短篇")
        source = self.source("story-source", "作品里的纸船飞上了月亮。")
        self.app.role_life.add_artifact(RoleArtifact("story", "story", RoleArtifactKind.TEXT, source, NOW,
            journal_meaning=Meaning.CREATIVE_TEXT), owner=self.owner)
        self.host_instance.receive(self.event("dialogue", text="我今天提到了一件事。")).unwrap()
        gathered = self.app.journal_material_collector.for_day(self.reading_context, self.target(), page_size=1)
        self.assertEqual(gathered.context, self.target())
        self.assertEqual(gathered.task_context_key, self.reading_context.key)
        self.assertFalse(gathered.requires_selection)
        self.assertGreater(dict(gathered.page_counts)["activities"], 3)
        self.assertGreater(dict(gathered.page_counts)["conversation"], 1)
        kinds = {item.kind for item in gathered.materials}
        self.assertEqual(kinds, {MaterialKind.ACTION, MaterialKind.CREATIVE_TEXT, MaterialKind.READING, MaterialKind.CONVERSATION})
        selected = gathered.select()
        self.assertEqual(selected.materials, gathered.materials)
        self.assertEqual({ref.lineage_id for ref in selected.activity_refs}, {"reading", "story"})
        self.assertEqual(len(selected.source_refs), 3)
        self.assertFalse(any("昨天的事" in item.text or "别的窗口的事" in item.text for item in selected.materials))
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_more_than_writing_capacity_stays_complete_and_requires_explicit_selection(self):
        await self.setup_reading()
        for index in range(65):
            self.add_activity(f"item-{index:03d}", description=f"当天活动 {index}")
        gathered = self.app.journal_material_collector.for_day(self.reading_context, self.target(), page_size=7)
        self.assertEqual(len(gathered.materials), 65)
        self.assertTrue(gathered.requires_selection)
        self.assertGreater(dict(gathered.page_counts)["activities"], 9)
        with self.assertRaises(TaskError) as required:
            gathered.select()
        self.assertEqual(required.exception.code, "journal_material_selection_required")
        chosen = (gathered.materials[-1].material_id, gathered.materials[0].material_id)
        selected = gathered.select(chosen)
        self.assertEqual(tuple(item.material_id for item in selected.materials), chosen)
        self.assertEqual({ref.lineage_id for ref in selected.activity_refs}, {"item-064", "item-000"})
        for invalid in ((chosen[0], chosen[0]), (True,), list(chosen)):
            with self.assertRaises(ValueError):
                gathered.select(invalid)
        with self.assertRaises(TaskError) as unknown:
            gathered.select(("not-collected",))
        self.assertEqual(unknown.exception.code, "journal_material_not_collected")

    async def test_collection_uses_one_snapshot_when_inventory_grows_between_pages(self):
        await self.setup_reading()
        self.add_activity("a-first", description="快照内的活动")
        late = replace(self.app.role_life.activity("a-first", owner=self.owner), activity_id="z-late", description="稍后加入")
        other = PersistentRoleLifeLedger(self.open_runtime())
        producer = self.app.journal_material_producer
        original = producer.for_day
        inserted = False
        def interleaved(*args, **kwargs):
            nonlocal inserted
            page = original(*args, **kwargs)
            if not inserted:
                other.add_activity(late)
                inserted = True
            return page
        with patch.object(producer, "for_day", side_effect=interleaved):
            gathered = self.app.journal_material_collector.for_day(self.reading_context, self.target(), page_size=1)
        self.assertEqual([ref.lineage_id for ref in gathered.select().activity_refs], ["a-first"])
        next_gathered = self.app.journal_material_collector.for_day(self.reading_context, self.target(), page_size=1)
        self.assertEqual([ref.lineage_id for ref in next_gathered.select().activity_refs], ["a-first", "z-late"])

    async def test_collection_rechecks_context_and_source_and_does_not_return_partial_success(self):
        await self.setup_reading()
        self.record().unwrap()
        collector = self.app.journal_material_collector
        other_target = replace(self.target(), scope=replace(SCOPE, session_id="other"))
        with self.assertRaises(TaskError) as crossed:
            collector.for_day(self.reading_context, other_target)
        self.assertEqual(crossed.exception.code, "journal_context_mismatch")
        self.identity.revoke_grant(self.writing_grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        with self.assertRaises(TaskError) as denied:
            collector.for_day(self.reading_context, self.target())
        self.assertEqual(denied.exception.code, "authorization_revoked")
        self.grant(self.important, SCOPE, "role.journal.write")
        self.app.role_journal.sources.revoke(self.original_source, expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(TaskError) as revoked:
            collector.for_day(self.reading_context, self.target())
        self.assertEqual(revoked.exception.code, "source_revoked")
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_empty_day_and_stalled_cursor_never_look_like_partial_collections(self):
        await self.setup_reading()
        collector = self.app.journal_material_collector
        self.assertEqual(collector.for_day(self.reading_context, self.target(), page_size=1).select().materials, ())
        with patch.object(self.app.journal_material_producer, "for_day", return_value=JournalMaterialPage((), "same")):
            with self.assertRaises(TaskError) as stalled:
                collector.for_day(self.reading_context, self.target())
        self.assertEqual(stalled.exception.code, "journal_material_cursor_stalled")
        await self.app.close()
        with self.assertRaises(TaskError) as stopped:
            collector.for_day(self.reading_context, self.target())
        self.assertEqual(stopped.exception.code, "host_not_running")

    async def test_collected_reading_enters_shared_writer_and_revocation_invalidates_saved_day(self):
        await self.setup_reading()
        self.record().unwrap()
        trigger = self.host_instance.inbound.ingest(self.event("trigger"), capability="text").unwrap()
        gathered = self.app.journal_material_collector.for_day(self.reading_context, self.target(), page_size=1)
        selected = gathered.select()
        async def model(envelope):
            return answered(encode(dict(body="今天读到文章中的一小段。", form="随记", recall=None, afterglow="")))
        self.model_behavior = model
        result = (await self.app.journal_writer.write(self.reading_context, trigger, self.target(),
            role_instruction="原角色人格", materials=selected.materials, request_id="collected-day")).unwrap().task
        self.assertEqual(result.state, "succeeded")
        offered = json.loads(next(item.payload for item in self.called[0].original.context.materials
                                  if item.purpose == "writing_materials"))
        self.assertEqual([item["kind"] for item in offered], ["action", "reading"])
        saved = self.app.role_journal.get(self.target().key)
        self.assertEqual(saved.draft.materials, selected.materials)
        self.assertIn(self.original_source, saved.draft.sources)
        self.app.role_journal.sources.revoke(self.original_source, expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(TaskError):
            self.app.role_journal.get(self.target().key)
        self.assertEqual(self.sent, [])
