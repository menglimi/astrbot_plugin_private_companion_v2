"""Life records through real reply generation, governance and delivery owners."""

from dataclasses import replace
from datetime import timedelta
import json
import unittest

from companion_v2.conversation.foreground import ClaimKind, DraftClaim, ModelDraft
from companion_v2.conversation.life_context import ConversationLifeContext, LIFE_INSTRUCTION, MAX_ACTIVITIES, MAX_PAYLOAD_CHARS
from companion_v2.conversation.messages import ConversationMessages
from companion_v2.execution.models import Lane, TaskError, digest
from companion_v2.foundation.refs import AudienceRef, RoleOwnerRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.model_gateway.models import Amount, ProviderResponse
from companion_v2.role_work.journal import RoleJournalService
from companion_v2.role_work.journal.models import DreamRecall, JournalContext, JournalDerivatives, JournalDraft, JournalKey, JournalKind
from companion_v2.role_work.ledger import PersistentRoleLifeLedger
from companion_v2.role_work.life.context import RoleLifeContextReader
from companion_v2.role_work.models import RoleActivity, RoleActivityState as State, RoleReadingReceipt
from companion_v2.role_work.work_models import RoleWorkSpec
from companion_v2.sources.models import SourceRecord
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import INSTALLATION, NOW, SCOPE


class LifeContextFixture(MessageFixture):
    def components(self, runtime, *, takeover=False):
        tasks, messages, delivery = super().components(runtime, takeover=takeover)
        reader = RoleLifeContextReader(PersistentRoleLifeLedger(runtime, now=self.clock.now),
                                      RoleJournalService(runtime, now=self.clock.now), tasks)
        messages.life_context = ConversationLifeContext(reader)
        return tasks, messages, delivery

    def setUp(self):
        super().setUp()
        self.reader = self.messages.life_context.reader
        self.life, self.journal = self.reader.life, self.reader.journal
        self.owner = self.reader.owner(self.context)

    def activity(self, identifier="activity", *, context=None, state=State.ACTIVE, **values):
        context = context or self.context
        return self.life.add_activity(RoleActivity(identifier, context.role_binding.role.subject_id,
            context.scope, NOW, state, description="正在整理读书笔记。", **values))

    def diary(self, *, context=None, kind=JournalKind.DIARY, day=None, body="今天的阅读让我感到很轻松。", **values):
        context = context or self.context
        key = JournalKey(self.reader.owner(context), kind, day or NOW.date().isoformat())
        target = JournalContext(key, context.scope, "UTC")
        draft = JournalDraft(target, body=body, **values)
        self.journal.save(draft, expected_revision=0, operation_id="write-" + digest(key))
        return self.journal.get(key)

    def reading(self, identifier="book", *, start=0, end=5, expires_at=None):
        event = self.event(identifier, expires_at=expires_at)
        receipt = RoleReadingReceipt(event.source, event.input_hash, len("private input " + identifier),
                                     start, end, NOW, "这让我想到傍晚的风。")
        return self.activity(identifier, state=State.COMPLETED, reading=receipt)

    def revise(self, entry):
        return self.journal.save(replace(entry.draft, body="更正后的日记。"),
            expected_revision=entry.reference.revision, operation_id="correct-" + digest(entry.reference))

    def delete(self, entry):
        return self.journal.delete(entry.draft.context, expected_revision=entry.reference.revision,
                                   operation_id="delete-" + digest(entry.reference))

    def derive(self, entry, text="阅读后的主观感受。", *, revision=0):
        return self.journal.save_derivatives(JournalDerivatives(entry.reference, summary=text),
            expected_revision=revision, operation_id="derive-" + digest([entry.reference, revision]))

    def snapshot(self, batch):
        return json.loads(self.messages.batch(batch)["contributions_json"])["life_context"]

    def materials(self, request=None):
        request = request or self.called[-1][1].original
        return [m for m in request.context.materials if m.owner == "role.life" and m.purpose != "role_life_context"]

    def payloads(self, request=None):
        return [json.loads(m.payload) for m in self.materials(request)]

    def restrict_access(self):
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
                             expected_revision=self.policy.revision, observed_at=NOW)
        for action in ("conversation.reply", "configuration.read"):
            self.grant(self.important, SCOPE, action)
        return self.grant(self.important, SCOPE, "role.life.read")

    async def changed_during_generation(self, change, *, derived=False):
        entry = self.diary()
        if derived:
            self.derive(entry)
        async def response(envelope):
            self.assertEqual(len(self.materials(envelope.original)), 1)
            change(entry)
            return ProviderResponse("generated", ModelDraft("使用旧生活经历的草稿。", ()), Amount(15, 40), "usage")
        self.responses["primary"] = response
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        task = (await self.runner().run_once(Lane.FOREGROUND)).unwrap().task
        self.assertEqual(task.state, "failed")
        self.assertEqual(self.parts(batch), ())
        self.assertEqual(self.sent, [])
        self.assertEqual((self.call_rows()[0]["state"], self.call_rows()[0]["actual_tokens"]), ("discarded", 15))


class LifeContextTests(LifeContextFixture, unittest.IsolatedAsyncioTestCase):
    async def test_current_activity_read_span_and_subjective_writing_reach_original_role(self):
        reading = self.reading()
        self.activity("sleep", work=RoleWorkSpec("sleep", self.context.key, "sleep-request", due_at=NOW + timedelta(minutes=1)))
        self.diary()
        self.diary(kind=JournalKind.DREAM, body="", recall=DreamRecall.AFTERGLOW, afterglow="梦醒后还记得一片蓝色。")
        event = self.event()
        batch = await self.generate(event)
        request = self.called[0][1].original
        self.assertEqual(request.role_instruction, "Original role prompt")
        self.assertEqual(request.role_binding, self.context.role_binding)
        self.assertIn(LIFE_INSTRUCTION, request.instruction)
        self.assertEqual(request.context.evidence_sources, (event.source,))
        self.assertTrue(all(m.source is None for m in self.materials()))
        items = {p["kind"]: p for p in self.payloads()}
        self.assertEqual(items["sleep"]["state"], "active")
        self.assertEqual(items["reading"]["reading"]["end_offset"], 5)
        self.assertFalse(items["reading"]["reading"]["covers_source"])
        self.assertEqual(items["reading"]["reading"]["reflection"], reading.reading.reflection)
        self.assertEqual(items["dream"]["basis"], "subjective_dream")
        self.assertEqual((items["dream"]["recall"], items["dream"]["body"]), ("afterglow", ""))
        self.assertEqual(items["diary"]["basis"], "subjective_diary")
        saved = self.messages.batch(batch)["contributions_json"]
        self.assertEqual(len(self.snapshot(batch)["references"]), 4)
        for item in ("整理", "傍晚", "轻松", "蓝色"):
            self.assertNotIn(item, saved)
            self.assertNotIn(item, json.dumps(self.messages.observe(self.context, batch).unwrap(), ensure_ascii=False))

    async def test_plans_pauses_and_elapsed_wake_time_do_not_create_completion(self):
        event = self.event("unread")
        self.activity("unread", state=State.PAUSED, checkpoint="unknown", work=RoleWorkSpec(
            "reading", self.context.key, "read-request", event.source, event.input_hash, 0, 4))
        self.activity("sleep", work=RoleWorkSpec("sleep", self.context.key, "sleep-request", due_at=NOW + timedelta(seconds=1)))
        self.clock.advance(timedelta(seconds=2))
        await self.generate()
        items = {p["kind"]: p for p in self.payloads()}
        self.assertEqual(items["sleep"]["state"], "active")
        self.assertEqual(items["reading"]["state"], "paused")
        self.assertIn("planned_reading_span", items["reading"])
        self.assertNotIn("reading", items["reading"])
        self.assertEqual(len(self.called), 1)
        self.assertEqual(self.journal.context_days(self.owner, SCOPE, observed_at=self.clock.now()), ())

    async def test_journal_correction_during_generation_discards_draft_and_retains_usage(self):
        await self.changed_during_generation(self.revise)

    async def test_journal_deletion_during_generation_discards_draft(self):
        await self.changed_during_generation(self.delete)

    async def test_selected_summary_correction_during_generation_discards_draft(self):
        await self.changed_during_generation(lambda e: self.derive(e, "更正摘要", revision=1), derived=True)

    async def test_activity_change_before_dispatch_blocks_stale_status(self):
        activity = self.activity()
        batch = await self.generate()
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        self.life.transition_activity(activity.activity_id, owner=self.owner, expected_revision=1,
            state=State.PAUSED, operation_id="pause", observed_at=NOW)
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code, "life_context_changed")
        await self.generate(self.event("fresh"))
        self.assertEqual(self.payloads()[0]["state"], "paused")

    async def test_deletion_between_parts_keeps_original_receipt_and_hides_stale_history(self):
        entry = self.diary()
        batch = await self.generate()
        await self.deliver_next(batch)
        original = self.history()[0]
        receipt = dict(self.runtime.read_one("SELECT * FROM conversation_delivery_receipts WHERE part_id = ?", (original["part_id"],)))
        self.delete(entry)
        self.assertFalse(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.history()[0]["part_id"], original["part_id"])
        self.assertFalse(self.history()[0]["body_available"])
        self.assertIsNone(self.history()[0]["text"])
        self.assertEqual(dict(self.runtime.read_one("SELECT * FROM conversation_delivery_receipts WHERE part_id = ?", (original["part_id"],))), receipt)
        await self.generate(self.event("fresh"))
        self.assertEqual(self.materials(), [])

    async def test_read_permission_unavailable_at_capture_is_optional_but_revoke_after_capture_blocks(self):
        self.diary()
        grant = self.restrict_access()
        batch = await self.generate()
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        self.identity.revoke_grant(grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.sent, [])
        fresh = await self.generate(self.event("fresh"))
        self.assertEqual(self.snapshot(fresh)["reason"], "authorization_revoked")
        self.assertEqual(self.materials(), [])
        self.assertNotIn(LIFE_INSTRUCTION, self.called[-1][1].original.instruction)
        await self.deliver_next(fresh)
        self.assertEqual(len(self.sent), 1)

    async def test_reading_source_withdrawal_removes_reflection_and_dependent_diary(self):
        event = self.event("book")
        self.accept(event)
        reading = self.reading()
        self.diary(sources=(reading.reading.source,))
        batch = await self.generate()
        self.messages.withdraw(self.context, event.scoped_key).unwrap()
        self.assertFalse(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        fresh = await self.generate(self.event("fresh"))
        self.assertEqual(self.materials(), [])
        self.assertEqual(self.snapshot(fresh)["skipped"], 2)

    async def test_reading_source_expiry_after_queue_prevents_dispatch(self):
        self.reading(expires_at=NOW + timedelta(seconds=1))
        batch = await self.generate()
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        self.clock.advance(timedelta(seconds=2))
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code, "source_expired")

    async def test_reading_hash_mismatch_is_not_exposed(self):
        reading = self.reading()
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE sources SET content_hash = 'changed' WHERE source_id = ?", (reading.reading.source.source_id,))
        batch = await self.generate()
        self.assertEqual(self.materials(), [])
        self.assertEqual(self.snapshot(batch)["skipped"], 1)

    async def test_nested_journal_source_audience_is_checked(self):
        event = self.event("private-original")
        with self.runtime.transaction() as connection:
            connection.execute("DELETE FROM sources WHERE source_id = ?", (event.source.source_id,))
        self.messages.sources.publish(SourceRecord(event.source, AudienceRef(SCOPE, (self.standard.subject,)),
            event.input_hash, "private input private-original"), observed_at=NOW).unwrap()
        parent = self.diary(day=(NOW - timedelta(days=1)).date().isoformat(), sources=(event.source,))
        self.diary(kind=JournalKind.DREAM, body="梦里只剩下一盏灯。", recall=DreamRecall.FRAGMENTS,
                   journals=(parent.reference,))
        batch = await self.generate()
        self.assertEqual(self.materials(), [])
        self.assertEqual(self.snapshot(batch)["skipped"], 2)

    async def test_other_scope_journal_ancestry_is_excluded(self):
        other = self.context_for(self.important, replace(SCOPE, session_id="elsewhere"))
        parent = self.diary(context=other, day=(NOW - timedelta(days=1)).date().isoformat())
        self.diary(journals=(parent.reference,))
        batch = await self.generate()
        self.assertEqual(self.materials(), [])
        self.assertEqual(self.snapshot(batch)["skipped"], 1)

    async def test_foreign_activity_inventory_does_not_starve_current_scope(self):
        other = self.context_for(self.important, replace(SCOPE, session_id="elsewhere"))
        for index in range(40):
            self.activity("foreign-" + str(index), context=other)
        selected = self.activity("local")
        batch = await self.generate()
        self.assertEqual(self.snapshot(batch)["references"], [{"kind": "activity", "activity_id": selected.activity_id, "revision": 1}])

    async def test_unavailable_journal_does_not_hide_other_valid_life_materials(self):
        source = self.event("expired", expires_at=NOW + timedelta(seconds=1)).source
        self.diary(sources=(source,))
        self.activity()
        self.clock.advance(timedelta(seconds=2))
        batch = await self.generate()
        self.assertEqual([p["kind"] for p in self.payloads()], ["activity"])
        self.assertEqual(self.snapshot(batch)["skipped"], 1)
        await self.deliver_next(batch)

    async def test_future_dated_journal_and_its_derived_dream_are_not_past_experiences(self):
        parent = self.diary(day=(NOW + timedelta(days=1)).date().isoformat())
        self.diary(kind=JournalKind.DREAM, body="梦里的一小段。", recall=DreamRecall.FRAGMENTS,
                   journals=(parent.reference,))
        batch = await self.generate()
        self.assertEqual(self.materials(), [])
        self.assertEqual(self.snapshot(batch)["skipped"], 2)

    async def test_unicode_scope_preserves_exact_inventory_and_text(self):
        self.context = self.context_for(self.important, replace(SCOPE, session_id="中文会话"))
        self.grant(self.important, self.context.scope, "text")
        self.activity()
        entry = self.diary()
        await self.generate()
        self.assertEqual(len(self.materials()), 2)
        self.assertEqual(next(p for p in self.payloads() if p["kind"] == "diary")["body"], entry.draft.body)

    async def test_persona_switch_does_not_claim_previous_life(self):
        self.activity()
        self.diary()
        current = self.personas.binding("base")
        role = SubjectRef(INSTALLATION, SubjectKind.BOT, "another-persona")
        self.personas.set_binding(replace(current, role=role, revision=current.revision + 1),
                                  expected_revision=current.revision, observed_at=NOW)
        self.context = self.context_for(self.important)
        await self.generate()
        self.assertEqual(self.materials(), [])

    def test_expanded_audience_cannot_reuse_private_references(self):
        self.diary()
        consumer = self.messages.life_context
        snapshot = consumer.capture(self.context, NOW)
        expanded = replace(self.context, audience=AudienceRef(SCOPE, (self.important.subject, self.standard.subject)))
        self.assertEqual(consumer.capture(expanded, NOW)["state"], "unavailable")
        with self.assertRaises(TaskError):
            consumer.contributions(snapshot, expanded, NOW)

    async def test_complete_summary_fits_when_body_exceeds_budget(self):
        entry = self.diary(body="长" * MAX_PAYLOAD_CHARS)
        self.derive(entry, "保留语义完整的短摘要。")
        batch = await self.generate()
        self.assertEqual(self.snapshot(batch)["references"][0]["derivative_revision"], 1)
        self.assertEqual(self.payloads()[0]["summary"], "保留语义完整的短摘要。")
        self.assertNotIn("body", self.payloads()[0])

    async def test_body_fallback_is_pinned_and_unused_summary_changes_do_not_block(self):
        entry = self.diary()
        self.derive(entry, "长" * MAX_PAYLOAD_CHARS)
        batch = await self.generate()
        self.assertEqual(self.snapshot(batch)["references"][0]["derivative_revision"], 0)
        self.assertEqual(self.payloads()[0]["body"], entry.draft.body)
        self.derive(entry, "后来变短的摘要。", revision=1)
        await self.deliver_next(batch)
        self.assertEqual(len(self.sent), 1)

    async def test_selection_limits_do_not_cut_bodies_or_add_new_records_after_seal(self):
        self.diary(body="长" * MAX_PAYLOAD_CHARS)
        for index in range(MAX_ACTIVITIES + 1):
            self.activity("active-" + str(index))
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        original = self.snapshot(batch)
        self.assertEqual(len(original["references"]), MAX_ACTIVITIES)
        self.assertTrue(original["truncated"])
        self.activity("new-after-seal")
        await self.generate(batch=batch)
        self.assertEqual(self.snapshot(batch), original)
        self.assertLessEqual(sum(len(m.payload) for m in self.materials()), MAX_PAYLOAD_CHARS)

    async def test_reopen_reconstructs_original_selection_and_checks_correction(self):
        entry = self.diary()
        batch = await self.generate()
        self.activity("new-after-seal")
        _, messages, delivery = self.components(self.open_runtime())
        request = messages._request(messages.batch(batch), self.context, NOW)
        self.assertEqual(self.payloads(request)[0]["body"], entry.draft.body)
        self.assertEqual(len(self.materials(request)), 1)
        self.revise(entry)
        self.assertEqual(delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code, "life_context_changed")

    async def test_missing_owner_and_corrupt_snapshots_cannot_erase_dependencies(self):
        self.diary()
        batch = await self.generate()
        with self.assertRaises(TaskError) as error:
            ConversationMessages(self.tasks)._request(self.messages.batch(batch), self.context, NOW)
        self.assertEqual(error.exception.code, "life_context_unavailable")
        row = self.messages.batch(batch)
        saved = json.loads(row["contributions_json"])
        snapshot = saved["life_context"]
        ref = snapshot["references"][0]
        for invalid in (None, {**snapshot, "context_key": "other"}, {**snapshot, "captured_at": "2026-09-21"},
                        {**snapshot, "references": [ref, ref]},
                        {**snapshot, "references": [{**ref, "kind": []}]},
                        {**snapshot, "references": [{**ref, "derivative_revision": True}]}):
            with self.subTest(snapshot=invalid):
                changed = dict(row)
                changed["contributions_json"] = json.dumps({**saved, "life_context": invalid})
                with self.assertRaises(TaskError) as error:
                    self.messages._request(changed, self.context, NOW)
                self.assertEqual(error.exception.code, "life_context_invalid")

    async def test_legacy_batch_without_snapshot_is_not_enriched(self):
        consumer = self.messages.life_context
        self.messages.life_context = None
        batch = await self.generate()
        self.diary()
        self.messages.life_context = consumer
        request = self.messages._request(self.messages.batch(batch), self.context, NOW)
        self.assertEqual(self.materials(request), [])
        await self.deliver_next(batch)

    async def test_subjective_writing_cannot_ground_an_observed_claim(self):
        source = self.event("journal-basis").source
        self.diary(sources=(source,))
        self.responses["primary"] = ProviderResponse("generated", ModelDraft("这是你的现实经历。", (
            DraftClaim("claim", ClaimKind.OBSERVED, "这是你的现实经历。", source),)), Amount(15, 40), "usage")
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.assertEqual((await self.runner().run_once(Lane.FOREGROUND)).unwrap().task.state, "failed")
        self.assertEqual(self.parts(batch), ())


if __name__ == "__main__":
    unittest.main()
