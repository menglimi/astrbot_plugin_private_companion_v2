"""Real V2 activity/contact/delivery owners with synthetic provider and transport."""

import asyncio
from dataclasses import replace
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.refs import AudienceRef, RoleOwnerRef, SourceRef, VersionRef
from companion_v2.proactive.events import ActivityContactEvents, PAGE_SIZE
from companion_v2.proactive.models import ThoughtKind
from companion_v2.relationships.models import (
    EmotionSubject,
    RelationshipMemory,
    RelationshipMemoryKind,
    RelationshipMemoryState,
)
from companion_v2.role_work.growth.models import GrowthKind, GrowthState, RoleGrowthRecord
from companion_v2.role_work.models import (
    RoleActivity,
    RoleActivityState as State,
    RoleArtifact,
    RoleArtifactJournalMeaning,
    RoleArtifactKind,
    RoleReadingReceipt,
)
from companion_v2.role_work.work_models import RoleWorkSpec
from companion_v2.sources.models import SourceRecord
from tests.contact_schedule_support import ContactScheduleFixture
from tests.test_management_access import SCOPE
from tests.test_role_tool_loop import answered


class ActivityContactTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def setup_contacts(self, **settings):
        self.grant(self.important, SCOPE, "role.reading.record")
        self.host_instance, batch = await self.scheduled()
        self.app = self.host_instance.application
        self.origin = self.context(self.app, batch)
        self.settings(self.app, {"chat.enabled": False,
            **{name + ".enabled": False for name in ("affection", "care", "play", "repair", "invitation")},
            **settings}).unwrap()
        self.assertIsInstance(self.app.contact_schedule.events, ActivityContactEvents)

    def reading(self, identifier="reading", *, state=State.ACTIVE, finish=True,
                source=None, scope=None, context_key=None, recipients=None, role_id=None):
        scope = scope or self.origin.scope
        text = "未读开头。真正读过的这一段。未读结尾。"
        source = source or SourceRef("original-" + identifier, "reading.fixture", scope,
                                    VersionRef("original-" + identifier, 1), self.clock.now())
        self.app.proactive.sources.publish(SourceRecord(source,
            AudienceRef(scope, recipients or (self.origin.actor.subject,)), digest(text), text), observed_at=self.clock.now()).unwrap()
        work = RoleWorkSpec("reading", context_key or self.origin.key, identifier, source, digest(text), 5, 14)
        activity = self.app.role_life.add_activity(RoleActivity(identifier, role_id or self.origin.role_binding.role.subject_id,
            scope, self.clock.now(), state, work=work))
        if finish:
            activity = self.app.role_reading.record_completion(self.origin, activity_id=identifier, source=source,
                content_hash=digest(text), start_offset=5, end_offset=14, completed_at=self.clock.now(),
                expected_revision=activity.revision, operation_id="finish-" + identifier,
                reflection="这让我想到海边，属于自己的联想。").unwrap()
        return activity, source

    def sleep(self, identifier="sleep"):
        now = self.clock.now()
        activity = self.app.role_life.add_activity(RoleActivity(identifier, self.origin.role_binding.role.subject_id,
            self.origin.scope, now - timedelta(minutes=1), State.ACTIVE,
            work=RoleWorkSpec("sleep", self.origin.key, identifier, due_at=now)))
        return self.app.role_life.transition_activity(identifier, owner=activity.owner, expected_revision=activity.revision,
            state=State.COMPLETED, operation_id="wake-" + identifier, observed_at=now)

    async def idle_scan(self, seconds=60):
        self.advance(self.app, seconds)
        self.app.contact_schedule.advance()
        await asyncio.sleep(0.035)

    async def test_real_reading_event_runs_with_chat_disabled_and_only_consumed_excerpt(self):
        await self.setup_contacts()
        self.reading()
        self.advance(self.app, 60)
        await self.automatic_delivery(self.app)
        request = self.contact_calls()[0].original
        evidence = [m.payload for m in request.context.materials if m.owner == "proactive.activity"]
        self.assertNotIn("_receipt", evidence[0])
        self.assertEqual(request.role_instruction, "原角色人格提示")
        self.assertTrue(any(m.payload == "输入 event-1" for m in request.context.materials if m.purpose == "contact_evidence"))
        self.assertEqual(len(evidence), 1)
        self.assertIn("真正读过的这一段", evidence[0])
        self.assertNotIn("未读开头", evidence[0])
        self.assertNotIn("未读结尾", evidence[0])
        self.assertIn("subjective_reflection", evidence[0])
        self.assertEqual(json.loads(self.contacts(self.app)[0]["record_json"])["purpose"], "creation")

    async def test_sleep_receipt_provides_only_confirmed_sleep_fact(self):
        await self.setup_contacts()
        self.sleep()
        self.advance(self.app, 60)
        await self.automatic_delivery(self.app)
        evidence = next(m.payload for m in self.contact_calls()[0].original.context.materials if m.owner == "proactive.activity")
        self.assertEqual(json.loads(evidence)["event"], "sleep_completed")
        self.assertIn("不证明做过梦", evidence)
        self.assertEqual(json.loads(self.contacts(self.app)[0]["record_json"])["purpose"], "life")

    async def test_planned_active_paused_cancelled_and_bare_completed_labels_do_not_create_contacts(self):
        await self.setup_contacts()
        for state in State:
            self.reading(state.value, state=state, finish=False)
        await self.idle_scan()
        self.assertEqual(self.contact_calls(), [])
        self.assertEqual(self.contacts(self.app), ())

    async def test_duplicate_reading_of_the_same_original_span_is_not_shared_again(self):
        await self.setup_contacts()
        _, source = self.reading()
        self.advance(self.app, 60)
        await self.automatic_delivery(self.app)
        self.reading("again", source=source)
        await self.idle_scan()
        await self.idle_scan(31)
        self.assertEqual(len(self.contact_calls()), 1)

    async def test_skip_is_durable_through_restart(self):
        await self.setup_contacts()
        self.reading()
        async def skip(envelope):
            return answered('{"decision":"skip","text":""}')
        self.model_behavior = skip
        self.advance(self.app, 60)
        await self.until(lambda: len(self.contacts(self.app)) == 1)
        await self.until(lambda: not self.app.proactive.active_handles)
        await self.app.close()
        self.app = (await self.start(self.host(runtime=self.open_runtime()), 1, 1)).application
        await self.idle_scan(61)
        self.assertEqual(len(self.contact_calls()), 1)
        self.assertEqual(len(self.sent), 1)

    async def test_expired_event_is_not_replayed_after_restart(self):
        await self.setup_contacts(event_max_age_seconds=60)
        self.reading()
        await self.app.close()
        self.clock.advance(timedelta(minutes=5))
        self.app = (await self.start(self.host(runtime=self.open_runtime()), 1, 1)).application
        await self.idle_scan(0)
        self.assertEqual(self.contact_calls(), [])

    async def test_purpose_pause_and_zero_quota_prevent_event_model_calls(self):
        await self.setup_contacts(**{"creation.enabled": False, "life.enabled": False})
        self.reading()
        self.sleep()
        await self.idle_scan()
        self.assertEqual(self.contact_calls(), [])
        self.settings(self.app, {"creation.enabled": True, "max_contacts_24h": 0}).unwrap()
        await self.idle_scan(0)
        self.assertEqual(self.contact_calls(), [])
        self.settings(self.app, {"max_contacts_24h": 3}).unwrap()
        self.app.notify()
        await self.automatic_delivery(self.app)

    async def test_revoked_original_is_not_selected(self):
        await self.setup_contacts()
        _, source = self.reading()
        self.app.proactive.sources.revoke(source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        await self.idle_scan()
        self.assertEqual(self.contact_calls(), [])

    async def test_withdrawal_during_generation_discards_model_result(self):
        await self.setup_contacts()
        _, source = self.reading()
        async def retract(envelope):
            self.app.proactive.sources.revoke(source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
            return answered('{"decision":"send","text":"应丢弃的阅读分享"}')
        self.model_behavior = retract
        self.advance(self.app, 60)
        await self.until(lambda: len(self.contact_calls()) == 1)
        await self.until(lambda: not self.app.proactive.active_handles)
        self.assertEqual(self.contacts(self.app), ())
        self.assertEqual(len(self.sent), 1)

    async def test_withdrawal_at_sender_boundary_prevents_wire_effect(self):
        await self.setup_contacts()
        _, source = self.reading()
        wire = []
        async def checked(envelope):
            if envelope.part_id.startswith("outbound-"):
                self.app.proactive.sources.revoke(source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
                try:
                    envelope.before_dispatch()
                except TaskError:
                    return self.receipt(envelope, "not_sent")
                wire.append(envelope)
            return self.receipt(envelope)
        self.send_behavior = checked
        self.advance(self.app, 60)
        await self.until(lambda: len(self.contacts(self.app)) == 1)
        await self.delivery_state(self.app, self.contacts(self.app)[0]["task_id"], "failed")
        self.assertEqual(wire, [])

    async def test_other_window_role_and_authority_events_do_not_leak(self):
        await self.setup_contacts()
        other = replace(SCOPE, session_id="foreign")
        for identifier, options in (("foreign-scope", {"scope": other}), ("foreign-role", {"role_id": "other-role"})):
            activity, source = self.reading(identifier, **options, finish=False)
            receipt = RoleReadingReceipt(source, activity.work.content_hash, 19, 5, 14, self.clock.now())
            self.app.role_life.transition_activity(identifier, owner=activity.owner, expected_revision=activity.revision,
                state=State.COMPLETED, operation_id="finish-" + identifier, observed_at=self.clock.now(), reading=receipt)
        self.reading("foreign-authority", context_key="another-principal", finish=True)
        await self.idle_scan()
        self.assertEqual(self.contact_calls(), [])

    async def test_completed_receipt_does_not_override_source_audience(self):
        await self.setup_contacts()
        activity, source = self.reading("private-book", recipients=(self.core.subject,), finish=False)
        receipt = RoleReadingReceipt(source, activity.work.content_hash, 19, 5, 14, self.clock.now())
        self.app.role_life.transition_activity(activity.activity_id, owner=activity.owner, expected_revision=activity.revision,
            state=State.COMPLETED, operation_id="private-completion", observed_at=self.clock.now(), reading=receipt)
        await self.idle_scan()
        self.assertEqual(self.contact_calls(), [])

    async def test_activity_scan_is_indexed_bounded_and_throttled_when_unchanged(self):
        await self.setup_contacts()
        self.clock.advance(timedelta(seconds=60))
        producer = self.app.contact_schedule.events
        preferences = self.preferences(self.app, self.origin)
        with patch.object(self.app.runtime, "read_all", wraps=self.app.runtime.read_all) as reads:
            for _ in range(10):
                self.assertEqual(producer.select(self.origin, preferences, self.clock.now()), (None, False))
        scans = [call for call in reads.call_args_list if "FROM role_activity_revisions" in call.args[0]]
        self.assertEqual(len(scans), 1)
        self.assertEqual(scans[0].args[1][-1], PAGE_SIZE)
        plan = self.app.runtime.read_all("EXPLAIN QUERY PLAN " + scans[0].args[0], scans[0].args[1])
        self.assertTrue(any("role_activity_history_time_idx" in row[3] for row in plan), plan)
        self.assertFalse(any("TEMP B-TREE" in row[3] for row in plan), plan)

    async def test_activity_source_rechecks_original_receipt_and_closes_with_schedule(self):
        await self.setup_contacts()
        activity = self.sleep()
        producer = self.app.contact_schedule.events
        operation_id = producer._receipt(self.origin, activity, self.clock.now())
        _, source = producer._project(self.origin, activity, operation_id, self.clock.now())
        self.assertTrue(self.app.proactive.sources.validate_reference(source, observed_at=self.clock.now()).is_success)
        await self.app.close()
        self.app = (await self.start(self.host(runtime=self.open_runtime()), 1, 1)).application
        self.assertTrue(self.app.proactive.sources.validate_reference(source, observed_at=self.clock.now()).is_success)
        with self.app.runtime.transaction() as connection:
            connection.execute("UPDATE operations SET state = 'unknown' WHERE operation_id = ?", (operation_id,))
        changed = self.app.proactive.sources.validate_reference(source, observed_at=self.clock.now())
        self.assertEqual(changed.failure.code, "contact_activity_receipt_required")
        self.app.contact_schedule.events.close()
        detached = self.app.proactive.sources.validate_reference(source, observed_at=self.clock.now())
        self.assertEqual(detached.failure.code, "source_owner_unavailable")

    async def test_filtered_pages_do_not_starve_a_real_older_completion(self):
        await self.setup_contacts()
        self.reading("aaa-real")
        for index in range(PAGE_SIZE + 2):
            self.reading("zzz-plan-" + str(index), state=State.PLANNED, finish=False)
        self.advance(self.app, 60)
        for _ in range(4):
            self.app.contact_schedule.advance()
            await asyncio.sleep(0)
        await self.automatic_delivery(self.app)
        self.assertEqual(len(self.contact_calls()), 1)

    async def test_expiry_at_sender_boundary_prevents_stale_activity_message(self):
        await self.setup_contacts(event_max_age_seconds=120)
        self.reading()
        wire = []
        async def checked(envelope):
            if envelope.part_id.startswith("outbound-"):
                self.clock.advance(timedelta(minutes=2))
                try:
                    envelope.before_dispatch()
                except TaskError:
                    return self.receipt(envelope, "not_sent")
                wire.append(envelope)
            return self.receipt(envelope)
        self.send_behavior = checked
        self.advance(self.app, 60)
        await self.until(lambda: len(self.contacts(self.app)) == 1)
        await self.delivery_state(self.app, self.contacts(self.app)[0]["task_id"], "failed")
        self.assertEqual(wire, [])

    async def test_confirmed_history_remains_after_event_expiry_but_withdrawal_removes_it(self):
        await self.setup_contacts(event_max_age_seconds=120)
        _, source = self.reading()
        self.advance(self.app, 60)
        await self.automatic_delivery(self.app)
        self.clock.advance(timedelta(minutes=5))
        self.assertEqual(len(self.app.background_history.recent(self.origin).unwrap()), 1)
        self.app.proactive.sources.revoke(source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.assertEqual(self.app.background_history.recent(self.origin).unwrap(), ())
        row = self.app.runtime.read_one("SELECT state FROM sources WHERE owner = 'proactive.activity'", ())
        self.assertEqual(row["state"], "revoked")

    async def test_cancelled_activity_contact_does_not_generate_again(self):
        await self.setup_contacts()
        self.reading()
        with patch.object(self.app.background, "advance", return_value=False):
            self.advance(self.app, 60)
            await self.until(lambda: len(self.contacts(self.app)) == 1)
            await self.until(lambda: not self.app.proactive.active_handles)
            task_id = self.contacts(self.app)[0]["task_id"]
            task = self.app.tasks.read(self.origin, task_id).unwrap()
            result = self.app.proactive.cancel(self.origin, task_id, expected_revision=task.revision).unwrap()
            self.assertEqual(result["delivery"], "cancelled")
        await self.idle_scan(61)
        self.assertEqual(len(self.contact_calls()), 1)
        self.assertEqual(len(self.sent), 1)

    async def test_shutdown_fences_a_late_activity_decision(self):
        await self.setup_contacts()
        self.reading()
        entered, release = asyncio.Event(), asyncio.Event()
        self.addCleanup(release.set)
        async def stubborn(envelope):
            entered.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    pass
            return answered('{"decision":"send","text":"停机后的阅读分享"}')
        self.model_behavior = stubborn
        self.advance(self.app, 60)
        await asyncio.wait_for(entered.wait(), 3)
        report = await self.app.close(grace_seconds=0)
        self.assertEqual(report.state, "draining")
        release.set()
        await self.until(lambda: not self.app.proactive.active_handles)
        await self.app.close(grace_seconds=0)
        self.assertEqual(len(self.sent), 1)

    async def test_creative_artifact_activity_prepares_share_candidate_and_growth_progress_selects(self):
        await self.setup_contacts()
        owner = RoleOwnerRef(self.origin.scope.installation_id, self.origin.scope.bot_id,
                             self.origin.role_binding.role.subject_id)
        now = self.clock.now()
        art_source = SourceRef("creative-text-1", "role.life", self.origin.scope,
                               VersionRef("creative-text-1", 1), now)
        art_text = "给普通的一天留一盏小灯，风吹过窗台时刚好亮着。"
        self.app.proactive.sources.publish(
            SourceRecord(art_source, self.origin.audience, digest(art_text), art_text),
            observed_at=now,
        ).unwrap()
        activity = self.app.role_life.add_activity(RoleActivity(
            "write-1", owner.persona_id, self.origin.scope, now - timedelta(minutes=5), State.ACTIVE,
            description="写一段随笔",
        ))
        self.app.role_life.add_artifact(RoleArtifact(
            "artifact-write-1", "write-1",
            RoleArtifactKind.TEXT, art_source, now,
            owner=owner,
            journal_meaning=RoleArtifactJournalMeaning.CREATIVE_TEXT,
        ), owner=owner)
        self.app.role_life.transition_activity(
            "write-1", owner=owner, expected_revision=activity.revision,
            state=State.COMPLETED, operation_id="complete-write-1", observed_at=now,
        )
        candidate, _ = self.app.contact_schedule.events.select(
            self.origin, self.preferences(self.app, self.origin), now, purpose="creation")
        self.assertIsNotNone(candidate)
        _, intents, marker = candidate
        self.assertEqual(intents[0].purpose, "creation")
        self.assertIs(intents[0].thought.kind, ThoughtKind.CONVERSATION)
        self.app.contact_schedule.events.validate(self.origin, marker, now)

        # Also verify GrowthContactEvents selects confirmed skill/goal progress and validates receipts.
        growth_source = SourceRef("growth-ev-1", "conversation.input", self.origin.scope,
                                  VersionRef("growth-ev-1", 1), now)
        self.app.proactive.sources.publish(
            SourceRecord(growth_source, self.origin.audience, digest("练琴记录"), "练琴记录"),
            observed_at=now,
        ).unwrap()
        proposed = RoleGrowthRecord(
            growth_id="skill-guitar", owner=owner, scope=self.origin.scope, kind=GrowthKind.SKILL,
            title="指弹吉他练习", description="练习和弦转换与泛音", progress_note="",
            sources=(growth_source,), created_at=now, updated_at=now, revision=1,
            state=GrowthState.PROPOSED, proposed_by=self.origin.actor.subject,
        )
        self.app.role_growth.propose(proposed, operation_id="propose-guitar")
        active = self.app.role_growth.transition(
            "skill-guitar", owner=owner, state=GrowthState.ACTIVE, expected_revision=1,
            observed_at=now, scope=self.origin.scope, actor=self.origin.actor.subject,
            operation_id="activate-guitar",
        )
        progressed = self.app.role_growth.apply_progress(
            "skill-guitar", owner=owner, expected_revision=active.revision,
            progress_note="今天换把位时小指终于不会蹭到邻弦了，慢速弹完了一整段。",
            sources=(growth_source,), observed_at=now, scope=self.origin.scope,
            actor=self.origin.actor.subject, operation_id="progress-guitar-1",
        )
        growth_candidate, _ = self.app.contact_schedule.growth_events.select(
            self.origin, self.preferences(self.app, self.origin), now, purpose="creation")
        self.assertIsNotNone(growth_candidate)
        _, g_intents, g_marker = growth_candidate
        self.assertEqual(g_marker["growth_id"], progressed.growth_id)
        self.assertEqual(g_intents[0].purpose, "creation")
        self.app.contact_schedule.growth_events.validate(self.origin, g_marker, now)

    async def test_reminiscence_events_select_aged_adopted_relationship_memory(self):
        await self.setup_contacts(**{"affection.enabled": True, "care.enabled": True})
        self.grant(self.important, SCOPE, "relationship.memory.propose")
        self.grant(self.important, SCOPE, "relationship.memory.review")
        self.grant(self.important, SCOPE, "relationship.memory.adopt")
        self.grant(self.important, SCOPE, "relationship.memory.read")
        owner = RoleOwnerRef(self.origin.scope.installation_id, self.origin.scope.bot_id,
                             self.origin.role_binding.role.subject_id)
        created_at = self.clock.now()
        mem_source = SourceRef("rel-ev-1", "conversation.input", self.origin.scope,
                               VersionRef("rel-ev-1", 1), created_at)
        self.app.proactive.sources.publish(
            SourceRecord(mem_source, self.origin.audience, digest("以前聊过雨天听爵士乐"), "以前聊过雨天听爵士乐"),
            observed_at=created_at,
        ).unwrap()
        proposal = RelationshipMemory(
            memory_id="mem-jazz-rain",
            owner=owner,
            subject=self.origin.actor.subject,
            scope=self.origin.scope,
            kind=RelationshipMemoryKind.EMOTION_EPISODE,
            interpretation="那天下雨时一起聊过窝在窗边听慢节奏爵士乐会觉得很安心。",
            sources=(mem_source,),
            created_at=created_at,
            observed_at=created_at,
            emotion_subject=EmotionSubject.HUMAN,
        )
        self.app.relationship_memories.propose(
            proposal, actor=self.origin.actor, observed_at=created_at, operation_id="prop-jazz").unwrap()
        self.app.relationship_memories.transition(
            "mem-jazz-rain", expected_revision=1, actor=self.origin.actor,
            scope=self.origin.scope, state=RelationshipMemoryState.REVIEWED,
            observed_at=created_at, operation_id="review-jazz").unwrap()
        self.app.relationship_memories.transition(
            "mem-jazz-rain", expected_revision=2, actor=self.origin.actor,
            scope=self.origin.scope, state=RelationshipMemoryState.ADOPTED,
            observed_at=created_at, operation_id="adopt-jazz").unwrap()
        self.advance(self.app, 18 * 3600)
        rem_candidate, _ = self.app.contact_schedule.reminiscence_events.select(
            self.origin, self.preferences(self.app, self.origin), self.clock.now())
        self.assertIsNotNone(rem_candidate)
        _, r_intents, r_marker = rem_candidate
        self.assertEqual(r_marker["memory_id"], "mem-jazz-rain")
        self.assertEqual(r_intents[0].purpose, "care")
        self.app.contact_schedule.reminiscence_events.validate(self.origin, r_marker, self.clock.now())
