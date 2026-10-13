"""Native foreground callbacks reach existing background consumers and resets."""

from datetime import timedelta
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from astrbot_host.management_identity import dashboard_operator
from companion_v2.agenda.planning_inputs import capture as planning_capture
from companion_v2.conversation.native_history import body, reference, rows
from companion_v2.conversation.native_turns import NativeConversationTurns, latest
from companion_v2.conversation.recall_settings import DEFAULTS as RECALL_DEFAULTS
from companion_v2.conversation.recalls import MessageRecall
from companion_v2.conversation.reset import ConversationWindow, reset_window
from companion_v2.execution.models import TaskError, require, stamp
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.memory.episode_settings import recent_group_lines
from companion_v2.proactive.material_pool import read_material_pool
from companion_v2.proactive.external_materials import parse_news_response
from tests.group_host_support import GroupFixture
from tests.multi_host_support import MultiFixture


class CoreBackgroundConsumerTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = await self.start_host()
        self.observer = self.controller.session.core_reply_observations

    async def prepared(self, identifier="background-input", text="晚上想一起看看星星"):
        prepared = (await self.controller.prepare_core_reply(self.event(identifier=identifier, text=text))).unwrap()
        await prepared["native_source_future"]
        context, identity = prepared["context"], self.controller.session.authority.identities
        if not identity.authorize(context.actor, scope=context.scope, capability="proactive.contact", observed_at=self.clock.now()).is_success:
            identity.issue_grant(grant_id="background-proactive-" + context.key, subject=context.actor.subject,
                scope=context.scope, capability="proactive.contact", tier=AuthorizationTier.STANDARD,
                valid_from=self.clock.now(), expected_revision=identity.revision)
        return prepared

    def assert_core_only(self):
        self.assertEqual(self.app.runtime.read_all("SELECT batch_id FROM conversation_batches", ()), ())
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platforms["qq-main"].client._api._wsr_api.calls, [])

    async def test_completed_native_origin_reaches_proactive_pool_and_new_input_fences_it(self):
        prepared = await self.prepared()
        context, turn = prepared["context"], prepared["turn_id"]
        schedule = self.app.contact_schedule
        with self.assertRaises(TaskError):
            schedule._origin(context, turn, self.clock.now())
        await self.observer.phase(prepared, "completed")
        origin, row, event = schedule._origin(context, turn, self.clock.now())
        self.assertEqual(row["execution_path"], "astrbot_core")
        self.assertEqual(event.event_id, prepared["event_id"])
        self.assertEqual(self.app.screen_interpretation._role_instruction(turn), prepared["instruction"])
        pool = read_material_pool(schedule, context, observed_at=self.clock.now(), settings={})
        self.assertIn(prepared["text"], [item["detail"] for item in pool["items"]])
        self.clock.advance(timedelta(seconds=1))
        newer = await self.prepared("background-newer", "我现在要先忙一会儿")
        self.assertEqual(schedule.latest_conversation(context)["turn_id"], newer["turn_id"])
        with self.assertRaises(TaskError):
            schedule._origin(context, origin["batch_id"], self.clock.now())
        self.assert_core_only()

    async def test_history_records_actual_send_time_and_deduplicates_callbacks(self):
        prepared = await self.prepared()
        context = prepared["context"]
        await self.observer.output(prepared, "好呀，晚点见", state="output_observed")
        history = self.app.proactive.history
        self.assertIsNone(history.latest_reply(context, self.clock.now(), within_minutes=60))
        self.clock.advance(timedelta(seconds=5))
        sent_at = self.clock.now()
        await self.observer.output(prepared, "好呀，晚点见", state="send_returned")
        await self.observer.output(prepared, "好呀，晚点见", state="send_returned")
        reply = history.latest_reply(context, sent_at, within_minutes=60)
        self.assertEqual(reply["delivered_at"], stamp(sent_at))
        self.assertEqual(reply["delivery_state"], "send_returned")
        self.assertFalse(reply["platform_confirmed"])
        self.assertNotIn("receipt_ref", reply["reference"])
        self.assertEqual(history.verify_reply(reply["reference"], context, sent_at), reply)
        dialogue = history.conversation.capture(context, sent_at)
        items = history.conversation.read(dialogue, context, sent_at)
        self.assertEqual([(item["role"], item["text"]) for item in items],
                         [("user", prepared["text"]), ("assistant", "好呀，晚点见")])
        excluded = history.conversation.capture(context, sent_at,
            exclude_reply_part_id=reply["reference"]["observation_id"])
        self.assertEqual(len(history.conversation.read(excluded, context, sent_at)), 1)
        self.assertEqual(len(rows(self.app.runtime, context, start=stamp(sent_at), kind="assistant")), 1)
        from companion_v2.conversation.native_observations import rows_for_context
        episode_rows = rows_for_context(self.app.runtime, context, start=stamp(sent_at))
        self.assertEqual(len(episode_rows), 1)
        self.assertEqual(episode_rows[0]["sent_at"], stamp(sent_at))
        other = (await self.controller.prepare_core_reply(self.event("second", "other-window"))).unwrap()
        with self.assertRaises(TaskError):
            body(self.app.messages, reply["reference"], other["context"], sent_at)
        self.assert_core_only()

    async def test_withdrawal_revokes_native_source_and_transcription_stays_management_only(self):
        prepared = await self.prepared(text="这句原话随后撤回")
        context = prepared["context"]
        source = await prepared["native_source_future"]
        result = require(self.app.messages.recalls.accept(MessageRecall.from_scope(
            context.scope, prepared["event_id"], context.actor.principal.native_account_id)))
        self.assertEqual(result["withdrawn_inputs"], 1)
        state = self.app.runtime.read_one("SELECT state FROM sources WHERE source_id=?", (source.source_id,))
        self.assertEqual(state["state"], "revoked")
        settings = {**RECALL_DEFAULTS, "transcribe_enabled": True}
        with self.assertRaises(TaskError):
            self.app.messages.recalls.transcribe(context, context.actor, settings, at=self.clock.now())
        operator = dashboard_operator(self.app.runtime, "background-admin", at=self.clock.now())
        transcript = self.app.messages.recalls.transcribe(context, operator, settings, at=self.clock.now())
        self.assertEqual([entry["text"] for entry in transcript["entries"]], [prepared["text"]])
        self.assertIsNone(self.app.proactive.history.interaction(context, self.clock.now())["last_input_at"])
        self.assertEqual(self.app.runtime.read_one("SELECT state FROM sources WHERE source_id=?", (source.source_id,))["state"], "revoked")
        self.assert_core_only()

    async def test_planning_and_self_review_use_native_sources_and_recheck_withdrawal(self):
        prepared = await self.prepared(text="明天想安静阅读，不要安排太满")
        context = prepared["context"]
        job = planning_capture(self.app.calendar_planning, context, prepared["instruction"],
                               "daily", "native-consumer", manual=True)
        self.assertIn(prepared["text"], job["material"]["current_reports"])
        self.assertIn(await prepared["native_source_future"], job["sources"])
        await self.observer.output(prepared, "好呀，给阅读留点时间", state="output_observed")
        self.assertEqual(self.app.role_self_review_evidence.collect(context, self.clock.now()).evidence, ())
        await self.observer.output(prepared, "好呀，给阅读留点时间", state="send_returned")
        evidence = self.app.role_self_review_evidence.collect(context, self.clock.now())
        self.assertEqual(len(evidence.evidence), 1)
        self.assertIn("未获平台送达确认", evidence.evidence[0].payload)
        self.app.role_self_review_evidence.resolve(evidence, context, self.clock.now())
        require(self.app.messages.recalls.accept(MessageRecall.from_scope(
            context.scope, prepared["event_id"], context.actor.principal.native_account_id)))
        renewed = planning_capture(self.app.calendar_planning, context, prepared["instruction"],
                                   "daily", "native-withdrawn", manual=True)
        self.assertEqual(renewed["material"]["current_reports"], [])
        self.assert_core_only()

    async def test_native_habits_and_completed_life_receipts_share_store_without_breaking_recall(self):
        from companion_v2.role_work.models import RoleActivity, RoleActivityState
        from astrbot_host.core_reply_context import build_core_reply_prompt

        prepared = await self.prepared(text="我刚吃完晚饭，今天吃了米饭")
        context = prepared["context"]
        for action in ("memory.read", "memory.propose", "role.life.read"):
            self.app.tasks.identity.issue_grant(grant_id="life-recall-" + action,
                subject=context.actor.subject, scope=context.scope, capability=action,
                tier=AuthorizationTier.STANDARD, valid_from=self.clock.now(),
                expected_revision=self.app.tasks.identity.revision)
        self.assertIsNotNone(self.app.runtime.read_one(
            "SELECT 1 FROM memory_views WHERE kind='user.habit.v1'", ()))
        activity = self.app.role_life.add_activity(RoleActivity("native-recall-walk",
            context.role_binding.role.subject_id, context.scope, self.clock.now(), RoleActivityState.ACTIVE,
            description="到河边散步"))
        self.app.role_life.transition_activity(activity.activity_id, owner=activity.owner,
            expected_revision=activity.revision, state=RoleActivityState.COMPLETED,
            operation_id="native-recall-walk-done", observed_at=self.clock.now())
        self.assertEqual(require(self.app.memory.activity.advance(context))["saved"], 1)
        self.app.memory.query.begin(context, "native-life-recall")
        recalled = require(self.app.memory.query.query(context, "native-life-recall",
            query_intent="河边散步", kind="experiences"))
        self.assertEqual(len(recalled["items"]), 1)
        self.assertIn("河边散步", recalled["items"][0]["title"])
        prompt = build_core_reply_prompt(self.app, context, prepared["native_input"], at=self.clock.now())
        self.assertIn("河边散步", prompt.instruction)
        self.assertEqual(self.app.state, "running")
        self.assert_core_only()

    async def test_native_goodnight_and_new_input_drive_screen_followup(self):
        prepared = await self.prepared()
        context = prepared["context"]
        screen = self.app.contact_schedule.screen_events
        values = {"screen_glance_goodnight_enabled": True, "screen_glance_goodnight_delay_minutes": 1,
                  "screen_glance_daily_limit": 10, "screen_glance_cooldown_minutes": 0,
                  "quiet_timezone": "Asia/Shanghai"}
        preferences = NS(values=values)
        await self.observer.output(prepared, "晚安，睡个好觉呀", state="output_observed")
        self.clock.advance(timedelta(minutes=2))
        self.assertIsNone(screen._goodnight_peek(context, preferences, self.clock.now()))
        await self.observer.output(prepared, "晚安，睡个好觉呀", state="send_returned")
        self.clock.advance(timedelta(minutes=2))
        self.assertEqual(screen._goodnight_peek(context, preferences, self.clock.now())["purpose"], "goodnight")
        await self.prepared("background-after-goodnight", "我还没睡呢")
        self.assertIsNone(screen._goodnight_peek(context, preferences, self.clock.now()))
        self.assert_core_only()

    async def test_reset_expires_native_sessions_and_stops_typing_without_replaying(self):
        prepared = await self.prepared()
        context = prepared["context"]
        self.assertIsNotNone(self.app.presence.active_turn(context))
        self.app.memory.query.begin(context, "native-reset-session", expires_at=self.clock.now() + timedelta(minutes=10))
        self.clock.advance(timedelta(seconds=1))
        reset_window(self.app.runtime, ConversationWindow.from_scope(context.scope), reset_id="native-reset", at=self.clock.now())
        self.assertIsNone(self.app.presence.active_turn(context))
        self.assertEqual(latest(self.app.runtime, context.key)["generation_state"], "failed")
        session = self.app.runtime.read_one("SELECT expires_at FROM memory_sessions WHERE session_id=?", ("native-reset-session",))
        self.assertEqual(session["expires_at"], stamp(self.clock.now()))
        self.assertEqual(self.app.proactive.history.conversation.capture(context, self.clock.now())["references"], [])
        self.assert_core_only()

    async def test_interrupted_native_runner_is_closed_once_and_terminal_state_is_not_reopened(self):
        prepared = await self.prepared()
        await self.observer.phase(prepared, "running")
        turns = NativeConversationTurns(self.app.runtime)
        self.assertEqual(turns.interrupt_open(at=self.clock.now()), 1)
        self.assertEqual(turns.interrupt_open(at=self.clock.now()), 0)
        await self.observer.phase(prepared, "running")
        self.assertEqual(latest(self.app.runtime, prepared["context"].key)["generation_state"], "failed")
        self.assertFalse(self.app.state_maintenance.foreground_busy(prepared["context"]))
        self.assert_core_only()

    async def test_native_news_lookup_is_requested_explicitly_and_rechecks_its_original_source(self):
        prepared = await self.prepared(text="最近AI有什么有趣的新消息")
        context = prepared["context"]
        news = self.app.tools.semantic.news_context
        calls = []

        async def fetch():
            calls.append(True)
            return parse_news_response({"items": [{"id": "native-news", "title": "新模型发布了",
                "summary": "公开摘要", "source": "示例媒体", "url": "https://news.example/native",
                "published_at": (self.clock.now() - timedelta(minutes=5)).isoformat()}]})

        port = NS(fetch=fetch, source_label="示例资讯源", fingerprint="native-news-fixture")
        with patch.object(self.app.contact_schedule.news_events, "_source", return_value=port):
            self.assertEqual(news.catalog_for(context)[0].action, "conversation.news.lookup")
            self.assertEqual(calls, [])
            result = await news.lookup_native(context, prepared["turn_id"], "lookup-1", prepared["text"])
            self.assertEqual(calls, [True])
            self.assertEqual(result["payload"]["content"]["items"][0]["title"], "新模型发布了")
            self.assertEqual(news.validate_native(context, result), result)
            self.clock.advance(timedelta(hours=1))
            with self.assertRaises(TaskError):
                news.validate_native(context, result)
        self.assert_core_only()


class CoreGroupEpisodeConsumerTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = await self.start_host()

    async def prepared(self, identifier, sender="200", target="group-a"):
        prepared = (await self.controller.prepare_core_reply(self.group_event(
            target=target, identifier=identifier, sender=sender))).unwrap()
        await prepared["native_source_future"]
        return prepared

    async def test_group_activity_merges_members_sent_replies_and_excludes_unsent_or_other_group(self):
        first = await self.prepared("native-group-one")
        observer = self.controller.session.core_reply_observations
        await observer.output(first, "今晚一起看星星", state="output_observed")
        second = await self.prepared("native-group-two", sender="201")
        self.clock.advance(timedelta(seconds=1))
        await observer.output(second, "先查一查天气吧", state="send_returned")
        self.clock.advance(timedelta(seconds=1))
        await observer.output(first, "今晚一起看星星", state="send_returned")
        other = await self.prepared("native-group-other", target="group-b")
        await observer.output(other, "另一个群的内容", state="send_returned")
        self.clock.advance(timedelta(seconds=1))
        manifest = {"start": stamp(self.clock.now() - timedelta(minutes=10)), "end": stamp(self.clock.now())}
        self.assertEqual(recent_group_lines(self.app.runtime, first["context"], manifest),
                         ("先查一查天气吧", "今晚一起看星星"))
        sent = rows(self.app.runtime, first["context"], kind="assistant")[0]
        source = self.app.messages.sources
        from companion_v2.conversation.messages import source_from_document
        ref = source_from_document(json.loads(sent["source_json"]))
        original = self.app.runtime.read_one("SELECT governance_revision FROM sources WHERE source_id=?", (ref.source_id,))
        require(source.revoke(ref, expected_governance_revision=original["governance_revision"], observed_at=self.clock.now()))
        self.assertEqual(recent_group_lines(self.app.runtime, first["context"], manifest), ("先查一查天气吧",))
        self.assertEqual(self.app.runtime.read_all("SELECT batch_id FROM conversation_batches", ()), ())
        self.assertEqual(self.native.provider.client.state.calls, [])
