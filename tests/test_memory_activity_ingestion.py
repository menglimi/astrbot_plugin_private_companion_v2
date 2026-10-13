"""Actual owner receipts, governed experiences and incremental restart recovery."""

from dataclasses import replace
from contextlib import closing
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from companion_v2.execution.models import digest, encode
from companion_v2.foundation.outcome import Outcome
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.memory.activity_ingestion import MemoryActivityIngestion, OWNER
from companion_v2.memory.models import AtomRef, Proposal
from companion_v2.memory.service import MemoryService
from companion_v2.role_work.journal.models import JournalContext, JournalDraft, JournalKey, JournalKind
from companion_v2.role_work.journal.service import RoleJournalService
from companion_v2.role_work.ledger import PersistentRoleLifeLedger
from companion_v2.role_work.life.context import RoleLifeContextReader
from companion_v2.role_work.models import RoleActivity, RoleActivityState as State, RoleReadingReceipt
from companion_v2.role_work.work_models import RoleWorkSpec
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord
from tests.memory_support import MemoryFixture
from tests.test_management_access import NOW
from tests.test_host_application import HostFixture
from tests.test_role_tool_loop import answered


class ActivityMemoryTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.service = MemoryService(self.tasks)
        self.reader = RoleLifeContextReader(PersistentRoleLifeLedger(self.runtime, now=self.clock.now),
            RoleJournalService(self.runtime, now=self.clock.now), self.tasks)
        self.producer = self.service.attach_life(self.reader)
        self.addCleanup(self.producer.close)
        self.owner = self.reader.owner(self.context)

    def activity(self, identifier="walk", *, context=None, state=State.ACTIVE, **changes):
        context = context or self.context
        return self.reader.life.add_activity(RoleActivity(identifier, context.role_binding.role.subject_id,
            context.scope, NOW, state, description="在河边散步", **changes))

    def complete(self, activity, *, operation=None, reading=None, checkpoint="走到桥边，回来后记下想法。"):
        return self.reader.life.transition_activity(activity.activity_id, owner=activity.owner,
            expected_revision=activity.revision, state=State.COMPLETED, operation_id=operation or "complete-" + activity.activity_id,
            observed_at=self.clock.now(), checkpoint=checkpoint, reading=reading)

    def read_receipt(self, identifier="book", *, source=None, context=None):
        context = context or self.context
        event = self.event("夜航船", context=context)
        source = source or event.source
        record = self.service.writer.access.source(context, source)
        activity = self.activity(identifier, context=context, work=RoleWorkSpec("reading", context.key,
            "read-" + identifier, source=source, content_hash=record.content_hash, start_offset=1, end_offset=5))
        reading = RoleReadingReceipt(source, record.content_hash, len(record.payload), 1, 5, self.clock.now(), "读到这里想起了晚风。")
        self.complete(activity, reading=reading)
        return source

    def diary(self, *, body="梦中我拥有三百艘船。", sources=(), revision=0, operation="diary-save"):
        key = JournalKey(self.owner, JournalKind.DIARY, NOW.date().isoformat())
        context = JournalContext(key, self.context.scope, "UTC")
        return self.reader.journal.save(JournalDraft(context, body=body, sources=sources),
            expected_revision=revision, operation_id=operation, observed_at=self.clock.now())

    def views(self):
        return self.service.experiences.list(self.context).unwrap()["items"]

    def query(self, intent="", *, kind="experiences"):
        self.service.query.begin(self.context, "activity-query")
        return self.service.query.query(self.context, "activity-query", query_intent=intent, kind=kind).unwrap()

    def test_real_completed_receipt_reaches_recall_with_exact_evidence_and_no_model(self):
        source = self.read_receipt()
        report = self.producer.advance(self.context).unwrap()
        self.assertEqual((report["saved"], report["examined"], report["blocked"]), (1, 1, []))
        view = self.views()[0]
        self.assertEqual(view["occurred_at"], NOW.isoformat(timespec="microseconds"))
        self.assertIn("只确认该片段", view["statements"][2]["text"])
        self.assertIn("主观感想", view["statements"][3]["text"])
        result = self.query("阅读")
        self.assertEqual(result["items"][0]["view_id"], view["view_id"])
        handle = result["items"][0]["statements"][2]["sources"][0]
        original = self.service.query.source(self.context, "activity-query", handle=handle).unwrap()["text"]
        self.assertIn("[1, 5)", original)
        self.assertNotIn('"context"', original)
        self.assertEqual(self.called, [])
        links = self.runtime.read_all("SELECT input_id FROM source_dependencies WHERE dependent_id = ?", (view["view_id"],))
        self.assertIn(source.source_id, [r["input_id"] for r in links])

    def test_planned_active_paused_cancelled_and_elapsed_time_do_not_complete_an_experience(self):
        planned = self.activity("planned", state=State.PLANNED)
        active = self.activity("paused")
        self.reader.life.transition_activity(active.activity_id, owner=self.owner, expected_revision=1,
            state=State.PAUSED, operation_id="pause", observed_at=NOW)
        self.reader.life.transition_activity(planned.activity_id, owner=self.owner, expected_revision=1,
            state=State.CANCELLED, operation_id="cancel", observed_at=NOW)
        self.clock.advance(timedelta(days=1))
        report = self.producer.advance(self.context).unwrap()
        self.assertEqual((report["saved"], report["skipped"]), (0, 2))
        self.assertEqual(self.views(), [])

    def test_duplicate_and_reopened_runtime_resume_same_cursor_without_replaying_history(self):
        self.complete(self.activity())
        original = self.producer.record(self.context, stream="activity", operation_id="complete-walk").unwrap()
        self.assertEqual(self.producer.record(self.context, stream="activity", operation_id="complete-walk").unwrap(), original)
        self.producer.advance(self.context).unwrap()
        other_runtime = self.open_runtime()
        tasks, _, _ = self.components(other_runtime)
        service = MemoryService(tasks)
        reader = RoleLifeContextReader(PersistentRoleLifeLedger(other_runtime, now=self.clock.now),
            RoleJournalService(other_runtime, now=self.clock.now), tasks)
        producer = service.attach_life(reader)
        self.addCleanup(producer.close)
        report = producer.advance(self.context).unwrap()
        self.assertEqual((report["examined"], report["saved"]), (0, 0))
        self.assertEqual(len(service.experiences.list(self.context).unwrap()["items"]), 1)

    def test_source_revocation_hides_experience_and_already_issued_handle(self):
        source = self.read_receipt()
        self.producer.advance(self.context).unwrap()
        result = self.query("阅读", kind="all")
        view = next(item for item in result["items"] if item["kind"] == "experience")
        handle = view["statements"][0]["sources"][0]
        self.service.writer.sources.revoke(source, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertFalse(self.service.experiences.read(self.context, view["view_id"]).is_success)
        self.assertFalse(self.service.query.source(self.context, "activity-query", handle=handle).is_success)
        self.assertEqual(self.query("阅读")["items"], [])

    def test_close_and_reopen_without_owner_guard_never_make_old_experience_readable(self):
        self.complete(self.activity())
        self.producer.advance(self.context).unwrap()
        view = self.views()[0]
        self.producer.close()
        self.assertFalse(self.service.experiences.read(self.context, view["view_id"]).is_success)
        self.assertEqual(self.producer.advance(self.context).failure.code, "memory_activity_closed")
        runtime = self.open_runtime()
        tasks, _, _ = self.components(runtime)
        memory = MemoryService(tasks)
        result = memory.experiences.read(self.context, view["view_id"])
        self.assertFalse(result.is_success)
        self.assertEqual(result.failure.code, "source_owner_unavailable")

    def test_other_human_and_role_cannot_copy_or_read_the_experience(self):
        self.complete(self.activity())
        self.producer.advance(self.context).unwrap()
        view = self.views()[0]
        other_context = self.context_for(self.core)
        self.assertFalse(self.service.experiences.read(other_context, view["view_id"]).is_success)
        self.assertFalse(self.producer.record(other_context, stream="activity", operation_id="complete-walk").is_success)
        changed = self.alternate_context(bot_id=self.context.scope.bot_id, role_id="other-persona", session_selector=True)
        self.assertFalse(self.producer.record(changed, stream="activity", operation_id="complete-walk").is_success)

    def test_unconfirmed_or_changed_operation_cannot_certify_completed_experience(self):
        self.complete(self.activity())
        with self.runtime.transaction() as db:
            db.execute("UPDATE operations SET state = 'unknown' WHERE operation_id = 'complete-walk'")
        result = self.producer.record(self.context, stream="activity", operation_id="complete-walk")
        self.assertEqual(result.failure.code, "memory_activity_receipt_unconfirmed")
        self.assertEqual(self.views(), [])

    def test_journal_produces_only_saved_writing_navigation_and_tracks_revision_and_deletion(self):
        first = self.diary()
        self.producer.advance(self.context).unwrap()
        old_view = self.views()[0]
        self.assertNotIn("三百艘船", encode(old_view))
        self.assertIn("只确认保存操作", old_view["statements"][0]["text"])
        second = self.diary(body="改写后的幻想。", revision=1, operation="diary-revise")
        self.assertFalse(self.service.experiences.read(self.context, old_view["view_id"]).is_success)
        self.producer.advance(self.context).unwrap()
        current = self.views()[0]
        self.assertNotEqual(current["view_id"], old_view["view_id"])
        self.reader.journal.delete(JournalContext(first.head.key, self.context.scope, "UTC"), expected_revision=second.head.revision,
            operation_id="delete-diary", observed_at=NOW)
        self.producer.advance(self.context).unwrap()
        self.assertEqual(self.views(), [])

    def test_failed_memory_commit_rolls_back_source_and_leaves_receipt_for_retry(self):
        self.complete(self.activity())
        with patch.object(self.service.experiences, "save", return_value=Outcome.failed("temporary_failure", "retry locally")):
            report = self.producer.advance(self.context).unwrap()
        self.assertEqual(report["blocked"][0]["code"], "temporary_failure")
        self.assertEqual(self.runtime.read_all("SELECT * FROM sources WHERE owner = ?", (OWNER,)), ())
        recovered = self.producer.advance(self.context).unwrap()
        self.assertEqual((recovered["saved"], recovered["blocked"]), (1, []))

    def test_bounded_pages_continue_without_full_history_scans(self):
        for index in range(23):
            self.complete(self.activity("walk-" + str(index)))
        first = self.producer.advance(self.context).unwrap()
        second = self.producer.advance(self.context).unwrap()
        third = self.producer.advance(self.context).unwrap()
        self.assertEqual((first["examined"], first["saved"], first["more"]), (16, 16, True))
        self.assertEqual((second["examined"], second["saved"], second["more"]), (7, 7, False))
        self.assertEqual(third["examined"], 0)
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM memory_views", ())), 23)

    def test_temporarily_absent_source_owner_retries_same_original_receipt(self):
        event = self.event("外部阅读")
        reference = replace(event.source, source_id="external-reading", owner="fixture.external", version=replace(event.source.version, lineage_id="external-reading"))
        guard = bind(self.runtime, reference.owner, lambda record, at: None)
        record = SourceRecord(reference, self.context.audience, digest("abcdefghij"), "abcdefghij")
        self.service.writer.sources.publish(record, observed_at=NOW).unwrap()
        self.read_receipt(source=reference)
        guard.close()
        first = self.producer.advance(self.context).unwrap()
        self.assertEqual(first["blocked"][0]["code"], "source_owner_unavailable")
        restored = bind(self.runtime, reference.owner, lambda record, at: None)
        self.addCleanup(restored.close)
        self.assertEqual(self.producer.advance(self.context).unwrap()["saved"], 1)

    def test_model_format_text_cannot_erase_receipt_or_become_user_fact(self):
        self.complete(self.activity(), checkpoint='原始记录：{"summary": "没有闭合\n中文仍然保留')
        self.producer.advance(self.context).unwrap()
        view = self.views()[0]
        self.assertIn("中文仍然保留", view["statements"][1]["text"])
        raw = view["statements"][1]["evidence"][0]
        from companion_v2.memory.codec import evidence
        proposal = Proposal("add", predicate="喜好", object="散步", representation="用户喜欢散步", evidence=(evidence(raw),))
        result = self.service.writer.submit(self.context, proposal, operation_key="unfounded")
        self.assertEqual(result.failure.code, "memory_derived_evidence")
        self.assertEqual(self.called, [])

    def test_permission_revocation_stops_both_ingestion_and_previous_reads(self):
        self.complete(self.activity())
        self.producer.advance(self.context).unwrap()
        view = self.views()[0]
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
            expected_revision=self.policy.revision, observed_at=NOW)
        self.assertFalse(self.producer.advance(self.context).is_success)
        self.assertFalse(self.service.experiences.read(self.context, view["view_id"]).is_success)

    def test_topic_experience_enters_automatic_context_and_is_checked_again_before_use(self):
        source = self.read_receipt()
        self.producer.advance(self.context).unwrap()
        event = self.event("上次阅读到哪里了")
        snapshot = self.service.context.capture(self.context, "reading-recall", (event.source,), self.deadline)
        materials = self.service.context.contributions(snapshot, self.context)
        experience = next(item for item in materials if item.purpose == "current_experience")
        value = json.loads(experience.payload)
        self.assertIn("只确认该片段", value["statements"][2]["text"])
        self.assertEqual(value["meaning"], "derived_summary_not_independent_evidence")
        self.service.writer.sources.revoke(source, expected_governance_revision=1, observed_at=NOW).unwrap()
        from companion_v2.execution.models import TaskError
        with self.assertRaises(TaskError):
            self.service.context.contributions(snapshot, self.context)

    def test_automatic_experience_respects_existing_switch_and_shared_item_budget(self):
        self.complete(self.activity())
        self.producer.advance(self.context).unwrap()
        event = self.event("河边散步")
        self.service.writer.access.policy = replace(self.service.policy, automatic_context=False)
        disabled = self.service.context.capture(self.context, "disabled-experience", (event.source,), self.deadline)
        self.assertEqual(disabled["experience_references"], [])
        self.service.writer.access.policy = replace(self.service.policy, context_items=1)
        enabled = self.service.context.capture(self.context, "one-experience", (event.source,), self.deadline)
        materials = self.service.context.contributions(enabled, self.context)
        self.assertEqual(len([m for m in materials if m.purpose in ("current_memory", "current_experience")]), 1)

    def test_forgetting_original_reading_evidence_also_stops_derived_experiences(self):
        source = self.read_receipt()
        self.accept(self.event("夜航船"))
        evidence = self.service.writer.access.capture(self.context, source)
        fact = self.service.writer.submit(self.context, Proposal("add", predicate="阅读材料", object="夜航船",
            representation="用户提到了夜航船", evidence=(evidence,)), operation_key="reading-source").unwrap()
        self.producer.advance(self.context).unwrap()
        view = self.views()[0]
        self.service.writer.forget(self.context, AtomRef(fact["atom_id"], fact["revision"]),
            evidence=(self.evidence("请忘记那份原文"),), operation_key="forget-reading-source").unwrap()
        self.assertFalse(self.service.experiences.read(self.context, view["view_id"]).is_success)
        self.assertFalse(self.producer.record(self.context, stream="activity", operation_id="complete-book").is_success)
        self.assertEqual(self.query("阅读")["items"], [])
        with closing(self.service.query.index._open()) as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM recall_documents WHERE producer = 'experience'").fetchone()[0], 0)

    def test_bound_polling_rotates_and_throttles_without_production_writes_on_each_tick(self):
        self.complete(self.activity())
        windows = [(self.context, "original role", None)]
        self.assertEqual(self.producer.advance_bound(windows).unwrap()["saved"], 1)
        with patch.object(self.producer, "advance", side_effect=AssertionError("throttled tick must not write")):
            self.assertEqual(self.producer.advance_bound(windows).unwrap()["advanced"], 0)
        self.clock.advance(timedelta(seconds=30))
        self.assertEqual(self.producer.advance_bound(windows).unwrap()["advanced"], 1)
        # Explicit duplicate binding values must not duplicate local projection.
        self.clock.advance(timedelta(seconds=30))
        many = windows * 20
        result = self.producer.advance_bound(many).unwrap()
        self.assertEqual((result["considered"], result["advanced"]), (16, 1))
        self.producer.close()
        self.assertEqual(self.producer._last_advance, {})
        self.assertFalse(self.producer.advance_bound(windows).is_success)


class ActivityMemoryConversationTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_next_real_conversation_flow_uses_receipt_experience_without_a_tool_or_second_model_call(self):
        host = await self.start()
        app = host.application
        first = host.receive(self.event("greet", text="早上好")).unwrap()
        self.advance(app)
        await self.done(app, first)
        context = self.context(app, first)
        producer = app.memory.activity or app.memory.attach_life(app.life_context, require_running=app.require_running)
        self.addCleanup(producer.close)
        activity = app.role_life.add_activity(RoleActivity("actual-walk", context.role_binding.role.subject_id,
            context.scope, app.now(), State.ACTIVE, description="到河边散步"))
        app.role_life.transition_activity(activity.activity_id, owner=activity.owner, expected_revision=1,
            state=State.COMPLETED, operation_id="walk-finished", observed_at=app.now(), checkpoint="走到小桥边就回来了。")
        producer.advance(context).unwrap()

        async def respond(envelope):
            material = next(m for m in envelope.original.context.materials if m.purpose == "current_experience")
            self.assertIn("小桥", json.loads(material.payload)["statements"][1]["text"])
            self.assertEqual(envelope.original.role_binding.role, context.role_binding.role)
            self.assertEqual(envelope.tool_history, ())
            return answered("我走到了小桥边，然后就回来了。")

        self.model_behavior = respond
        calls = len(self.called)
        later = host.receive(self.event("remember-walk", text="刚才散步走到了哪里？")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, later))["state"], "complete")
        self.assertEqual(len(self.called), calls + 1)
        self.assertEqual(self.sent[-1].text, "我走到了小桥边，然后就回来了。")

    async def test_revocation_during_reply_prevents_delivery_of_recalled_experience(self):
        host = await self.start()
        app = host.application
        first = host.receive(self.event("reading-original", text="阅读材料：夜航船第一章，窗外的夜色很安静。")).unwrap()
        self.advance(app)
        await self.done(app, first)
        context = self.context(app, first)
        producer = app.memory.activity or app.memory.attach_life(app.life_context, require_running=app.require_running)
        self.addCleanup(producer.close)
        from companion_v2.memory.codec import source as source_from_json
        original = app.runtime.read_one("SELECT event_json FROM conversation_inputs WHERE batch_id = ?", (first,))
        source = source_from_json(json.loads(original["event_json"])["source"])
        record = app.memory.writer.access.source(context, source)
        activity = app.role_life.add_activity(RoleActivity("actual-reading", context.role_binding.role.subject_id,
            context.scope, app.now(), State.ACTIVE, description="阅读夜航船", work=RoleWorkSpec("reading", context.key,
                "actual-read", source=source, content_hash=record.content_hash, start_offset=0, end_offset=5)))
        app.role_life.transition_activity(activity.activity_id, owner=activity.owner, expected_revision=1,
            state=State.COMPLETED, operation_id="reading-finished", observed_at=app.now(),
            reading=RoleReadingReceipt(source, record.content_hash, len(record.payload), 0, 5, app.now()))
        producer.advance(context).unwrap()
        # Isolate the memory-owned path from the separate recent-life injection.
        app.messages.life_context = None

        async def respond(envelope):
            self.assertTrue(any(m.purpose == "current_experience" for m in envelope.original.context.materials))
            app.role_journal.sources.revoke(source, expected_governance_revision=1, observed_at=app.now()).unwrap()
            return answered("这份已撤回材料里的阅读印象不应发出去。")

        self.model_behavior = respond
        sent = len(self.sent)
        later = host.receive(self.event("remember-reading", text="还记得阅读夜航船时读到哪里吗？")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, later))["state"], "blocked")
        self.assertEqual(len(self.sent), sent)
        self.assertEqual(app.runtime.read_all("SELECT * FROM conversation_parts WHERE batch_id = ?", (later,)), ())

    async def test_host_driver_automatically_ingests_bound_receipts_and_restart_restores_the_guard(self):
        host = await self.start()
        app = host.application
        first = host.receive(self.event("bind-life", text="我们今天慢慢聊吧")).unwrap()
        self.advance(app)
        await self.done(app, first)
        context = self.context(app, first)
        self.assertIsNotNone(app.memory.activity)
        self.assertIn(context.key, app.state_maintenance.bindings)
        activity = app.role_life.add_activity(RoleActivity("driver-walk", context.role_binding.role.subject_id,
            context.scope, app.now(), State.ACTIVE, description="到河边散步"))
        app.role_life.transition_activity(activity.activity_id, owner=activity.owner, expected_revision=1,
            state=State.COMPLETED, operation_id="driver-complete", observed_at=app.now())
        calls, sends = len(self.called), len(self.sent)
        self.advance(app, 31)
        await self.until(lambda: bool(app.memory.experiences.list(context).unwrap()["items"]))
        view = app.memory.experiences.list(context).unwrap()["items"][0]
        self.assertEqual((len(self.called), len(self.sent)), (calls, sends))
        await app.close()
        self.assertTrue(app.memory.activity.closed)
        restarted = await self.start(self.host(runtime=self.open_runtime()), task_generation=1, model_generation=1)
        current = restarted.application
        self.assertEqual(current.memory.experiences.read(context, view["view_id"]).unwrap()["view_id"], view["view_id"])
        self.assertEqual(current.memory.activity.advance(context).unwrap()["examined"], 0)
        self.assertEqual((len(self.called), len(self.sent)), (calls, sends))
