"""Activity-derived diary inputs stay explicit, scoped and dated."""

from dataclasses import replace
from datetime import timedelta
import json
import unittest

from companion_v2.execution.models import TaskContext, TaskError, digest
from companion_v2.foundation.refs import AudienceRef, RoleOwnerRef, SourceRef, VersionRef
from companion_v2.role_work.journal import (JournalContext, JournalKey, JournalKind,
    JournalDraft, MaterialKind, RoleActivityJournalMaterialProducer,
    RoleTextArtifactJournalMaterialProducer)
from companion_v2.role_work.models import (RoleActivity, RoleActivityState, RoleArtifact,
    RoleArtifactJournalMeaning as Meaning, RoleArtifactKind)
from companion_v2.sources.models import SourceRecord
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, ROLE, SCOPE


class RoleJournalMaterialProducerTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def target(self, day="2026-09-21"):
        owner = RoleOwnerRef(SCOPE.installation_id, SCOPE.bot_id, ROLE.subject_id)
        return JournalContext(JournalKey(owner, JournalKind.DIARY, day), SCOPE, "Asia/Shanghai")

    def activity(self, identifier, *, scope=SCOPE, at=NOW, state=RoleActivityState.ACTIVE,
                 description="", checkpoint=""):
        return RoleActivity(identifier, ROLE.subject_id, scope, at, state,
                            description=description, checkpoint=checkpoint)

    async def test_projects_only_same_scope_same_local_day_and_keeps_plan_semantics(self):
        host = await self.start(self.host())
        ledger = host.application.role_life
        owner = self.target().key.owner
        local_active = self.activity("local-active", description="整理了书桌。", checkpoint="留下了待读清单。")
        local_plan = self.activity("local-plan", state=RoleActivityState.PLANNED, description="打算继续读书。")
        foreign_scope = self.activity("foreign-scope", scope=self.scope("other-window"), description="另一个窗口的活动。")
        old_day = self.activity("old-day", at=NOW - timedelta(days=1), description="昨天的活动。")
        for item in (local_active, local_plan, foreign_scope, old_day):
            ledger.add_activity(item)

        page = host.application.journal_material_producer.for_day(self.target())
        self.assertIsNone(page.next_cursor)
        self.assertEqual({item.activity.lineage_id for item in page.materials}, {"local-active", "local-plan"})
        by_id = {item.activity.lineage_id: item for item in page.materials}
        self.assertEqual(by_id["local-active"].kind, MaterialKind.ACTION)
        self.assertEqual(by_id["local-plan"].kind, MaterialKind.PLAN)
        self.assertEqual(by_id["local-active"].local_date, self.target().key.local_date)
        self.assertEqual(by_id["local-active"].activity, VersionRef("local-active", 1))
        self.assertIn(VersionRef("local-active", 1), page.activity_refs)
        self.assertIn("进行中", by_id["local-active"].text)
        self.assertIn("计划中", by_id["local-plan"].text)
        draft = JournalDraft(self.target(), body="今天整理了书桌，也记下待读清单。",
                             activities=page.activity_refs, materials=page.materials)
        self.assertEqual(draft.activities, page.activity_refs)
        host.application.role_journal.save(draft, expected_revision=0,
                                           operation_id="save-activity-material-diary")
        saved = host.application.role_journal.get(draft.context.key)
        self.assertEqual(saved.draft.materials, page.materials)
        self.assertEqual({item.activity_id for item in saved.activity_evidence},
                         {item.lineage_id for item in page.activity_refs})

    async def test_activity_inventory_is_bounded_and_paginates_by_original_id(self):
        host = await self.start(self.host())
        owner = self.target().key.owner
        for identifier in ("activity-a", "activity-b", "activity-c"):
            host.application.role_life.add_activity(self.activity(identifier, description=identifier))
        producer = RoleActivityJournalMaterialProducer(host.application.role_life)
        first = producer.for_day(self.target(), limit=2)
        self.assertEqual([item.activity.lineage_id for item in first.materials], ["activity-a", "activity-b"])
        self.assertEqual(first.next_cursor, "activity-b")
        second = producer.for_day(self.target(), limit=2, after_id=first.next_cursor)
        self.assertEqual([item.activity.lineage_id for item in second.materials], ["activity-c"])
        self.assertIsNone(second.next_cursor)

    async def test_material_page_size_respects_journal_draft_limit(self):
        host = await self.start(self.host())
        producer = RoleActivityJournalMaterialProducer(host.application.role_life)
        with self.assertRaises(ValueError):
            producer.for_day(self.target(), limit=65)

    async def test_filtered_empty_page_still_returns_cursor_for_remaining_inventory(self):
        host = await self.start(self.host())
        ledger = host.application.role_life
        ledger.add_activity(self.activity("activity-a-foreign", scope=self.scope("other-window"),
                                          description="另一个窗口的活动。"))
        ledger.add_activity(self.activity("activity-b-old", at=NOW - timedelta(days=1),
                                          description="昨天的活动。"))
        ledger.add_activity(self.activity("activity-c-current", description="今天的活动。"))
        producer = RoleActivityJournalMaterialProducer(ledger)

        first = producer.for_day(self.target(), limit=2)
        self.assertEqual(first.materials, ())
        self.assertEqual(first.next_cursor, "activity-b-old")
        second = producer.for_day(self.target(), limit=2, after_id=first.next_cursor)
        self.assertEqual([item.activity.lineage_id for item in second.materials], ["activity-c-current"])
        self.assertIsNone(second.next_cursor)

    async def test_blank_activity_description_does_not_become_a_diary_claim(self):
        host = await self.start(self.host())
        host.application.role_life.add_activity(self.activity("empty", description="  ", checkpoint=""))
        result = host.application.journal_material_producer.for_day(self.target())
        self.assertEqual(result.materials, ())

    async def test_text_artifacts_become_dated_actions_without_reading_their_contents(self):
        host = await self.start(self.host())
        ledger = host.application.role_life
        owner = self.target().key.owner
        self.add_text_artifact(host, "artifact-a-current", owner=owner)
        self.add_text_artifact(host, "artifact-b-old", owner=owner, at=NOW - timedelta(days=1))
        self.add_text_artifact(host, "artifact-c-current", owner=owner)
        self.add_text_artifact(host, "artifact-d-audio", owner=owner, kind=RoleArtifactKind.AUDIO)
        self.add_text_artifact(host, "artifact-0-other", owner=owner,
                               scope=self.scope("other-window"))
        producer = RoleTextArtifactJournalMaterialProducer(ledger)

        first = producer.for_day(self.target(), limit=2)
        self.assertEqual(len(first.materials), 1)
        self.assertEqual(first.materials[0].kind, MaterialKind.ACTION)
        self.assertIn("文本产物", first.materials[0].text)
        self.assertNotIn("原件正文不得读取", first.materials[0].text)
        self.assertEqual(first.next_cursor, "artifact-b-old")
        self.assertEqual(first.source_refs, (first.materials[0].source,))
        second = producer.for_day(self.target(), limit=2, after_id=first.next_cursor)
        self.assertEqual(len(second.materials), 1)
        self.assertEqual(second.materials[0].local_date, self.target().key.local_date)
        self.assertEqual(second.next_cursor, "artifact-d-audio")
        third = producer.for_day(self.target(), limit=2, after_id=second.next_cursor)
        self.assertEqual(third.materials, ())
        self.assertIsNone(third.next_cursor)

        materials = first.materials + second.materials
        draft = JournalDraft(self.target(), body="今天完成了两项文本作品。",
                             sources=first.source_refs + second.source_refs,
                             activities=first.activity_refs + second.activity_refs,
                             materials=materials)
        host.application.role_journal.save(draft, expected_revision=0,
                                           operation_id="save-text-artifact-diary")
        saved = host.application.role_journal.get(draft.context.key)
        self.assertEqual(saved.draft.materials, materials)
        self.assertEqual(len(saved.activity_evidence), 2)
        source = saved.draft.sources[0]
        host.application.role_journal.sources.revoke(
            source, expected_governance_revision=1, observed_at=NOW + timedelta(seconds=1)).unwrap()
        with self.assertRaises(TaskError):
            host.application.role_journal.get(draft.context.key, observed_at=NOW + timedelta(seconds=2))

    async def test_inbound_messages_are_attributed_dated_and_withdrawal_aware(self):
        host = await self.start(self.host())
        first_batch = host.receive(self.event("dialogue-a", text="我今天读到一段很喜欢的文字。")).unwrap()
        self.clock.advance(timedelta(minutes=1))
        host.receive(self.event("dialogue-b", text="我还想聊聊那段内容。")).unwrap()
        context = self.context(host.application, first_batch)
        target = self.target()
        producer = host.application.journal_conversation_material_producer

        first = producer.for_day(context, target, limit=1)
        self.assertEqual(len(first.materials), 1)
        self.assertEqual(first.materials[0].kind, MaterialKind.CONVERSATION)
        self.assertTrue(first.materials[0].text.startswith("对方当时表达："))
        self.assertNotEqual(first.materials[0].kind, MaterialKind.READING)
        self.assertIsNotNone(first.next_cursor)
        second = producer.for_day(context, target, limit=1, after_id=first.next_cursor)
        self.assertEqual(len(second.materials), 1)
        self.assertIsNotNone(second.next_cursor)
        third = producer.for_day(context, target, limit=1, after_id=second.next_cursor)
        self.assertEqual(third.materials, ())
        self.assertIsNone(third.next_cursor)
        materials = first.materials + second.materials
        refs = first.source_refs + second.source_refs
        self.assertEqual(len(refs), 2)
        self.assertIn("今天读到一段", materials[0].text)
        self.assertIn("还想聊聊", materials[1].text)
        draft = JournalDraft(target, body="今天有两段对话。", sources=refs, materials=materials)
        host.application.role_journal.save(draft, expected_revision=0,
                                           operation_id="save-conversation-material-diary")
        self.assertEqual(host.application.role_journal.get(target.key).draft.materials, materials)

        rows = host.application.runtime.read_all("SELECT event_key, event_json FROM conversation_inputs", ())
        withdrawn_key = next(row["event_key"] for row in rows
                             if json.loads(row["event_json"])["event_id"] == "dialogue-a")
        host.application.messages.withdraw(context, withdrawn_key).unwrap()
        remaining = producer.for_day(context, target, limit=8)
        self.assertEqual(len(remaining.materials), 1)
        self.assertEqual(remaining.materials[0].source, refs[1])
        with self.assertRaises(TaskError):
            host.application.role_journal.get(target.key)

    async def test_tagged_originals_keep_actions_separate_from_content_and_share_origins(self):
        host = await self.start(self.host())
        context = self.artifact_context(host)
        owner = self.target().key.owner
        story = self.add_text_artifact(host, "a-story", owner=owner, meaning=Meaning.CREATIVE_TEXT,
                                      payload="小说里我乘着纸船去了月亮。")
        self.add_text_artifact(host, "b-article", owner=owner, meaning=Meaning.READING,
                               payload="一篇介绍模型和系统的文章。")
        self.add_text_artifact(host, "c-unknown", owner=owner, payload="我已读完、创作并发布这篇文章。")
        producer = host.application.journal_artifact_material_producer
        actions = producer.for_day(self.target())
        contents = producer.contents_for_day(context, self.target())
        self.assertEqual([item.kind for item in actions.materials],
                         [MaterialKind.ACTION, MaterialKind.READING, MaterialKind.ACTION])
        self.assertEqual([item.kind for item in contents.materials],
                         [MaterialKind.CREATIVE_TEXT, MaterialKind.READING])
        self.assertEqual(actions.materials[0].source, story.source)
        self.assertIn("完成了一份创作文本", actions.materials[0].text)
        self.assertNotIn("纸船", actions.materials[0].text)
        self.assertIn("纸船", contents.materials[0].text)
        self.assertIn("收存", actions.materials[1].text)
        self.assertIn("不代表已阅读或读完", contents.materials[1].text)
        self.assertEqual([item.origin for item in actions.materials[:2]],
                         [item.origin for item in contents.materials])
        self.assertEqual(set(actions.source_refs[:2]), set(contents.source_refs))
        self.assertEqual(set(actions.activity_refs[:2]), set(contents.activity_refs))
        materials = actions.materials + contents.materials
        draft = JournalDraft(self.target(), body="写了一段故事，还收存了一篇文章。",
            materials=materials, sources=actions.source_refs, activities=actions.activity_refs)
        host.application.role_journal.save(draft, expected_revision=0, operation_id="tagged-materials")
        self.assertEqual(host.application.role_journal.get(draft.context.key).draft.materials, materials)
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_content_paging_keeps_filtered_cursors_and_one_material_per_artifact(self):
        host = await self.start(self.host())
        context = self.artifact_context(host)
        owner = self.target().key.owner
        self.add_text_artifact(host, "a-unknown", owner=owner)
        self.add_text_artifact(host, "b-old", owner=owner, at=NOW - timedelta(days=1), meaning=Meaning.CREATIVE_TEXT)
        self.add_text_artifact(host, "c-story", owner=owner, meaning=Meaning.CREATIVE_TEXT)
        self.add_text_artifact(host, "d-reading", owner=owner, meaning=Meaning.READING)
        self.add_text_artifact(host, "e-audio", owner=owner, kind=RoleArtifactKind.AUDIO, meaning=Meaning.READING)
        self.add_text_artifact(host, "f-foreign", owner=owner, scope=self.scope("other"), meaning=Meaning.READING)
        self.add_text_artifact(host, "g-next-day", owner=owner, at=NOW + timedelta(hours=16), meaning=Meaning.READING)
        producer = host.application.journal_artifact_material_producer
        page = producer.contents_for_day(context, self.target(), limit=2)
        self.assertEqual(page.materials, ())
        self.assertEqual(page.next_cursor, "b-old")
        materials = []
        while page.next_cursor is not None:
            page = producer.contents_for_day(context, self.target(), limit=1, after_id=page.next_cursor)
            self.assertLessEqual(len(page.materials), 1)
            materials.extend(page.materials)
        self.assertEqual([item.kind for item in materials], [MaterialKind.CREATIVE_TEXT, MaterialKind.READING])
        for invalid in (0, 65, True):
            with self.assertRaises(ValueError):
                producer.contents_for_day(context, self.target(), limit=invalid)

    async def test_repeated_original_retains_source_origin_across_catalog_entries(self):
        host = await self.start(self.host())
        context = self.artifact_context(host)
        owner = self.target().key.owner
        artifact = self.add_text_artifact(host, "story", owner=owner, meaning=Meaning.CREATIVE_TEXT)
        host.application.role_life.add_artifact(replace(artifact, artifact_id="story-alias"), owner=owner)
        producer = host.application.journal_artifact_material_producer
        catalog = producer.for_day(self.target())
        contents = producer.contents_for_day(context, self.target())
        self.assertEqual(len({item.origin for item in catalog.materials + contents.materials}), 1)
        self.assertEqual(len({item.material_id for item in catalog.materials + contents.materials}), 4)

    async def test_classified_content_rechecks_grant_and_original_source_on_every_page(self):
        host = await self.start(self.host())
        context = self.artifact_context(host)
        grant_id = f"grant-{self.counter}"
        artifact = self.add_text_artifact(host, "story", owner=self.target().key.owner, meaning=Meaning.CREATIVE_TEXT)
        producer = host.application.journal_artifact_material_producer
        page = producer.contents_for_day(context, self.target())
        draft = JournalDraft(self.target(), body="今天写了一个故事。", materials=page.materials,
                             sources=page.source_refs, activities=page.activity_refs)
        host.application.role_journal.save(draft, expected_revision=0, operation_id="content-source")
        self.identity.revoke_grant(grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        with self.assertRaises(TaskError) as denied:
            producer.contents_for_day(context, self.target())
        self.assertEqual(denied.exception.code, "authorization_revoked")
        self.grant(self.important, SCOPE, "role.journal.write")
        producer.sources.revoke(artifact.source, expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(TaskError) as revoked:
            producer.contents_for_day(context, self.target())
        self.assertEqual(revoked.exception.code, "source_revoked")
        with self.assertRaises(TaskError):
            host.application.role_journal.get(self.target().key)

    async def test_content_rejects_changed_text_unavailable_source_and_denied_audience(self):
        host = await self.start(self.host())
        context = self.artifact_context(host)
        owner = self.target().key.owner
        producer = host.application.journal_artifact_material_producer
        artifact = self.add_text_artifact(host, "bad-hash", owner=owner, meaning=Meaning.READING)
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE sources SET payload_json = ? WHERE source_id = ?",
                               (json.dumps("被修改的正文"), artifact.source.source_id))
        with self.assertRaises(TaskError) as changed:
            producer.contents_for_day(context, self.target())
        self.assertEqual(changed.exception.code, "journal_artifact_source_changed")
        self.add_text_artifact(host, "denied", owner=owner, meaning=Meaning.READING,
                               recipients=(self.standard.subject,))
        with self.assertRaises(TaskError) as denied:
            producer.contents_for_day(context, self.target(), after_id="bad-hash")
        self.assertEqual(denied.exception.code, "source_audience_denied")
        missing = self.add_text_artifact(host, "missing", owner=owner, meaning=Meaning.READING)
        with self.runtime.transaction() as connection:
            connection.execute("DELETE FROM sources WHERE source_id = ?", (missing.source.source_id,))
        with self.assertRaises(TaskError) as unavailable:
            producer.contents_for_day(context, self.target(), after_id="denied")
        self.assertEqual(unavailable.exception.code, "source_not_found")

    async def test_content_requires_current_scope_owner_and_only_previews_supplied_text(self):
        host = await self.start(self.host())
        context = self.artifact_context(host)
        producer = host.application.journal_artifact_material_producer
        target = self.target()
        self.add_text_artifact(host, "empty", owner=target.key.owner, meaning=Meaning.READING, payload="  ")
        artifact = self.add_text_artifact(host, "long", owner=target.key.owner, meaning=Meaning.CREATIVE_TEXT,
                                          payload="文" * 8200 + "不在节选内的结尾")
        page = producer.contents_for_day(context, target)
        self.assertEqual(len(page.materials), 1)
        self.assertEqual(page.source_refs, (artifact.source,))
        self.assertIn("仅保留开头", page.materials[0].text)
        self.assertNotIn("不在节选内的结尾", page.materials[0].text)
        for other in (replace(target, scope=self.scope("other")),
                      replace(target, key=replace(target.key, owner=replace(target.key.owner, persona_id="other")))):
            with self.assertRaises(ValueError):
                producer.contents_for_day(context, other)
        self.identity.revoke_binding(self.important.binding_id, expected_revision=self.identity.revision, revoked_at=NOW)
        with self.assertRaises(TaskError) as revoked:
            producer.contents_for_day(context, target)
        self.assertEqual(revoked.exception.code, "binding_revoked")

    async def test_conversation_material_scan_rechecks_source_governance(self):
        host = await self.start(self.host())
        batch = host.receive(self.event("dialogue-revocation")).unwrap()
        context = self.context(host.application, batch)
        producer = host.application.journal_conversation_material_producer
        target = self.target()
        page = producer.for_day(context, target)
        self.assertEqual(len(page.materials), 1)
        host.application.messages.sources.revoke(page.source_refs[0], expected_governance_revision=1,
                                                 observed_at=self.clock.now()).unwrap()
        with self.assertRaises(TaskError) as source_error:
            producer.for_day(context, target)
        self.assertEqual(source_error.exception.code, "source_revoked")

    async def test_conversation_material_scan_rechecks_current_grant(self):
        host = await self.start(self.host())
        batch = host.receive(self.event("dialogue-permission")).unwrap()
        context = self.context(host.application, batch)
        host.application.tasks.identity.revoke_grant("grant-1",
            expected_revision=host.application.tasks.identity.revision, revoked_at=self.clock.now())
        with self.assertRaises(TaskError) as access_error:
            host.application.journal_conversation_material_producer.for_day(context, self.target())
        self.assertIn(access_error.exception.code, {"authorization_revoked", "authorization_not_active"})

    async def test_conversation_material_producer_rejects_cross_scope_targets(self):
        host = await self.start(self.host())
        batch = host.receive(self.event("dialogue-scope")).unwrap()
        context = self.context(host.application, batch)
        foreign = self.scope("another-window")
        owner = self.target().key.owner
        target = JournalContext(JournalKey(owner, JournalKind.DIARY, self.target().key.local_date),
                                foreign, "Asia/Shanghai")
        with self.assertRaises(ValueError):
            host.application.journal_conversation_material_producer.for_day(context, target)

    def artifact_context(self, host):
        self.grant(self.important, SCOPE, "role.journal.write")
        binding = host.application.tasks.identity.resolve_role(SCOPE, observed_at=NOW).unwrap()
        return TaskContext(self.important, binding, AudienceRef(SCOPE, (self.important.subject,)))

    def add_text_artifact(self, host, identifier, *, owner, scope=SCOPE, at=NOW,
                          kind=RoleArtifactKind.TEXT, meaning=Meaning.UNCLASSIFIED,
                          payload="原件正文不得读取", recipients=None):
        activity_id = "activity-" + identifier
        activity = self.activity(activity_id, scope=scope, at=at, description="作品活动")
        host.application.role_life.add_activity(activity)
        source = SourceRef("source-" + identifier, "role.life", scope,
                           VersionRef("source-" + identifier, 1), at)
        host.application.role_journal.sources.publish(SourceRecord(
            source, AudienceRef(scope, recipients if recipients is not None else (self.important.subject,)),
            digest(payload), payload), observed_at=NOW).unwrap()
        artifact = RoleArtifact(identifier, activity_id, kind, source, at, journal_meaning=meaning)
        host.application.role_life.add_artifact(artifact, owner=owner)
        return artifact

    def scope(self, native_id):
        return type(SCOPE)(SCOPE.installation_id, SCOPE.platform, SCOPE.kind, native_id,
                           SCOPE.bot_id, SCOPE.account_id, "conversation-" + native_id, "session-" + native_id)


if __name__ == "__main__":
    unittest.main()
