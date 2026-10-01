"""Historical semantics, page consistency and independent original-domain grants."""

from dataclasses import replace
from datetime import timedelta
import json
import unittest

from companion_v2.execution.models import TaskError, encode
from companion_v2.foundation.refs import AudienceRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.role_work.growth import GrowthKind, PersistentRoleGrowthLedger, RoleGrowthContextReader, RoleGrowthRecord
from companion_v2.role_work.journal.models import JournalKind, DreamRecall
from companion_v2.role_work.models import RoleActivityState as State
from companion_v2.role_work.timeline import RoleTimeline
from companion_v2.role_work.work_models import RoleWorkSpec
from tests.test_role_life_context import LifeContextFixture
from tests.test_management_access import NOW, SCOPE


class TimelineFixture(LifeContextFixture):
    def setUp(self):
        super().setUp()
        self.growth = PersistentRoleGrowthLedger(self.runtime, now=self.clock.now)
        self.growth_reader = RoleGrowthContextReader(self.growth, self.tasks)
        self.timeline = RoleTimeline(self.reader, self.growth_reader)

    def seed_growth(self, identifier="goal", *, context=None):
        context = context or self.context
        return self.growth.add(RoleGrowthRecord(identifier, self.reader.owner(context), context.scope, GrowthKind.GOAL,
            "练习水彩", "先从构图开始。", "尚未确认。", (self.event("growth-" + identifier, context=context).source,),
            NOW, NOW, proposed_by=context.actor.subject))

    def query(self, **kwargs):
        return self.timeline.query(self.context, **kwargs)


class RoleTimelineTests(TimelineFixture, unittest.IsolatedAsyncioTestCase):
    async def test_collects_only_recorded_states_reading_spans_and_subjective_journal_metadata(self):
        activity = self.activity("walk")
        self.life.transition_activity("walk", owner=activity.owner, expected_revision=1, state=State.PAUSED, operation_id="pause")
        self.reading()
        self.activity("sleep", work=RoleWorkSpec("sleep", self.context.key, "sleep", due_at=NOW + timedelta(seconds=1)))
        diary = self.diary()
        self.derive(diary)
        self.diary(kind=JournalKind.DREAM, body="蓝色的梦境。", recall=DreamRecall.FRAGMENTS)
        self.seed_growth()
        self.clock.advance(timedelta(seconds=2))
        result = self.query(limit=20)
        items = result["items"]
        self.assertEqual(len(items), 7)
        walk = [i["detail"]["state"] for i in items if i["reference"]["identifier"] == "walk"]
        self.assertEqual(walk, ["paused", "active"])
        sleep = next(i["detail"] for i in items if i["reference"]["identifier"] == "sleep")
        self.assertEqual(sleep["state"], "active")
        reading = next(i["detail"]["reading"] for i in items if i["reference"]["identifier"] == "book")
        self.assertEqual((reading["start_offset"], reading["end_offset"], reading["covers_source"]), (0, 5, False))
        self.assertNotIn(diary.draft.body, json.dumps(result, ensure_ascii=False))
        self.assertNotIn("蓝色的梦境", json.dumps(result, ensure_ascii=False))
        growth = next(i["detail"] for i in items if i["reference"]["kind"] == "growth")
        self.assertTrue(growth["requires_human_confirmation"])

    async def test_historical_activity_and_growth_remain_valid_after_newer_states(self):
        activity, growth = self.activity(), self.seed_growth()
        original = self.query()
        self.life.transition_activity(activity.activity_id, owner=activity.owner, expected_revision=1, state=State.PAUSED, operation_id="pause")
        self.growth.confirm(growth.growth_id, owner=growth.owner, scope=SCOPE, expected_revision=1,
            operation_id="confirm", actor=self.core.subject, observed_at=NOW)
        self.timeline.validate(self.context, original)
        self.assertEqual([i["detail"]["state"] for i in self.query(kinds=["growth"])["items"]], ["active", "proposed"])

    async def test_journal_edits_deletes_and_restore_keep_metadata_without_recovering_bodies(self):
        diary = self.diary()
        original = self.query(kinds=["diary"])
        self.revise(diary)
        self.delete(self.journal.get(diary.reference.key))
        self.timeline.validate(self.context, original)
        self.journal.restore(replace(diary.draft, body="明确恢复后的新正文。"), expected_revision=3, operation_id="restore")
        result = self.query(kinds=["diary"])
        self.assertEqual([i["detail"]["action"] for i in result["items"]], ["restore", "delete", "save", "save"])
        self.assertTrue(all(i["detail"]["content_form"] == "operation_metadata_only" for i in result["items"]))
        self.assertNotIn("正文", json.dumps(result, ensure_ascii=False))

    async def test_pages_have_no_duplicates_and_exclude_late_backdated_inserts_across_domains(self):
        for i in range(4):
            self.activity("walk-" + str(i))
        self.diary()
        self.seed_growth()
        expected = self.query(limit=20)["items"]
        page = self.query(limit=2)
        self.activity("late")
        self.seed_growth("late")
        self.diary(kind=JournalKind.DREAM, body="后来写入。", recall=DreamRecall.FULL)
        items = list(page["items"])
        while page["next_cursor"]:
            page = self.query(cursor=page["next_cursor"], limit=2)
            items.extend(page["items"])
        self.assertEqual(items, expected)
        self.assertEqual(len(self.query(limit=20)["items"]), 9)

    async def test_cursors_bind_filters_context_and_runtime_but_do_not_replace_grants(self):
        self.activity("one")
        self.activity("two")
        token = self.query(kinds=["activity"], limit=1)["next_cursor"]
        other_scope = replace(SCOPE, session_id="other")
        other = replace(self.context, role_binding=replace(self.context.role_binding, scope=other_scope),
                        audience=replace(self.context.audience, scope=other_scope))
        for target, args in ((self.context, {"kinds": ["growth"], "cursor": token}), (other, {"cursor": token}),
                             (self.context, {"cursor": token[:-2] + "!?"})):
            with self.assertRaises(TaskError) as error:
                self.timeline.query(target, **args)
            self.assertEqual(error.exception.code, "timeline_cursor_invalid")
        with self.assertRaises(TaskError):
            RoleTimeline(self.reader, self.growth_reader).query(self.context, cursor=token)
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD, expected_revision=self.policy.revision, observed_at=NOW)
        with self.assertRaises(TaskError):
            self.query(cursor=token)

    async def test_separate_permissions_do_not_expand_read_access(self):
        self.activity()
        self.seed_growth()
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD, expected_revision=self.policy.revision, observed_at=NOW)
        self.assertEqual(self.timeline.available(self.context, NOW), [])
        self.grant(self.important, SCOPE, "role.growth.read")
        result = self.query()
        self.assertEqual(result["included_kinds"], ["growth"])
        self.assertEqual(result["unavailable_kinds"], ["activity", "diary", "dream"])
        self.assertEqual([i["reference"]["kind"] for i in result["items"]], ["growth"])
        with self.assertRaises(TaskError):
            self.query(kinds=["activity"])

    async def test_other_scope_role_or_recipient_cannot_read_selected_history(self):
        other_scope = replace(SCOPE, session_id="other")
        other = replace(self.context, role_binding=replace(self.context.role_binding, scope=other_scope),
                        audience=replace(self.context.audience, scope=other_scope))
        self.activity("other", context=other)
        self.seed_growth("other", context=other)
        self.diary(context=other)
        self.assertEqual(self.query()["items"], [])
        self.activity("ours")
        result = self.query()
        wrong_role = replace(self.context, role_binding=replace(self.context.role_binding,
            role=SubjectRef(SCOPE.installation_id, SubjectKind.BOT, "another-role")))
        wrong_audience = replace(self.context, audience=AudienceRef(SCOPE, (self.core.subject,)))
        for target in (other, wrong_role, wrong_audience):
            with self.assertRaises(TaskError):
                self.timeline.validate(target, result)

    async def test_revoked_source_blocks_sealed_selection_and_skips_fresh_query(self):
        activity = self.reading()
        growth = self.seed_growth()
        original = self.query()
        for source in (activity.reading.source, growth.sources[0]):
            self.messages.sources.revoke(source, expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(TaskError):
            self.timeline.validate(self.context, original)
        result = self.query()
        self.assertEqual((result["items"], result["skipped"], result["selection_partial"]), ([], 2, True))

    async def test_range_requires_timezone_and_filters_by_record_time(self):
        self.activity("first")
        self.clock.advance(timedelta(hours=1))
        self.activity("second", updated_at=self.clock.now())
        page = self.query(time_start="2026-09-21T09:00:00+08:00", time_end="2026-09-21T01:00:00Z")
        self.assertEqual([i["reference"]["identifier"] for i in page["items"]], ["second"])
        for args in ({"time_start": "2026-09-21T00:00:00"}, {"limit": True}, {"kinds": ["activity", "activity"]},
                     {"time_start": "2026-09-22T00:00:00Z", "time_end": NOW.isoformat()}):
            with self.assertRaises(ValueError):
                self.query(**args)

    async def test_history_gap_is_explicit_and_large_records_page_within_tool_budget(self):
        for i in range(10):
            self.activity(str(i), checkpoint="长文本" * 5000)
        activity = self.life.activity("0", owner=self.owner)
        self.life.transition_activity("0", owner=activity.owner, expected_revision=1, state=State.PAUSED, operation_id="pause")
        with self.runtime.transaction() as connection:
            connection.execute("DELETE FROM role_activity_revisions WHERE activity_id = '0' AND revision = 1")
            connection.execute("UPDATE role_activity_revisions SET provenance = 'legacy_receipt' WHERE activity_id = '0'")
        page = self.query(limit=20)
        self.assertLess(len(encode(page).encode("utf-8")), 65536)
        items = list(page["items"])
        while page["next_cursor"]:
            page = self.query(cursor=page["next_cursor"], limit=20)
            items.extend(page["items"])
        self.assertEqual(len(items), 10)
        gap = next(i["detail"] for i in items if i["reference"]["identifier"] == "0")
        self.assertEqual((gap["history_incomplete"], gap["missing_prior_revisions"]), (True, 1))
        self.assertTrue(all(i["detail"]["truncated_fields"] == ["checkpoint"] for i in items))

    async def test_empty_page_from_withdrawn_sources_can_continue_without_rescanning_them(self):
        self.reading("000")
        for index in range(1, 66):
            activity = self.reading(f"{index:03}")
            self.messages.sources.revoke(activity.reading.source, expected_governance_revision=1, observed_at=NOW).unwrap()
        first = self.query(kinds=["activity"], limit=1)
        self.assertEqual((first["items"], first["skipped"]), ([], 64))
        self.assertTrue(first["next_cursor"])
        second = self.query(cursor=first["next_cursor"], limit=1)
        self.assertEqual([i["reference"]["identifier"] for i in second["items"]], ["000"])
        self.assertEqual(second["skipped"], 1)
        self.assertIsNone(second["next_cursor"])
