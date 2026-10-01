"""Receipt-backed duplicate decisions and foreground reply ancestry."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from threading import Event, current_thread, main_thread
import unittest
from unittest.mock import patch

from companion_v2.conversation.foreground import BackgroundPromptTrigger
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.execution.models import TaskError
from companion_v2.proactive.configuration import configuration_fields, dedup_policies
from companion_v2.proactive.preferences import DEDUP_EVENT_POLICY, ContactPreferences
from tests.contact_schedule_support import ContactScheduleFixture
from tests.test_management_access import NOW
from tests.test_role_tool_loop import answered


class ProactiveDedupTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_exact_repeat_skips_with_reason_and_policy_can_exempt_route(self):
        app = await self.enabled()
        first = (await self.contact(app)).unwrap().task
        await self.delivery_state(app, first.task_id, "delivered")
        self.advance(app, 1)
        second = (await self.contact(app, self.opportunity("second"))).unwrap().task
        data = json.loads(app.runtime.read_one("SELECT record_json FROM proactive_contacts WHERE task_id = ?",
                                              (second.task_id,))[0])
        self.assertEqual((data["decision"], data["dedup_reason"]), ("skip", "exact_repeat"))
        self.assertEqual(app.proactive.observe(self.contact_context(), second.task_id).unwrap()["dedup_reason"], "exact_repeat")
        self.assertEqual(len(self.sent), 1)
        self.settings(app, {"dedup_policies": "content_fingerprint,life_event"}).unwrap()
        third = (await self.contact(app, self.opportunity("third"))).unwrap().task
        await self.delivery_state(app, third.task_id, "delivered")
        self.assertEqual(len(self.sent), 2)

    async def test_window_zero_is_unbounded_and_expired_window_allows_repeat(self):
        app = await self.enabled()
        first = (await self.contact(app)).unwrap().task
        await self.delivery_state(app, first.task_id, "delivered")
        context = self.contact_context()
        self.clock.advance(timedelta(minutes=241))
        prefs = self.preferences(app)
        self.assertFalse(app.proactive._duplicate(context, "刚想起上次的话题。", prefs, self.clock.now(), purpose="chat"))
        self.settings(app, {"dedup_sent_window_minutes": 0}).unwrap()
        prefs = self.preferences(app)
        self.assertTrue(app.proactive._duplicate(context, "刚想起上次的话题。", prefs, self.clock.now(), purpose="chat"))

    async def test_prompt_only_marks_in_window_proactive_history_for_dedup(self):
        app = await self.enabled()
        first = (await self.contact(app)).unwrap().task
        await self.delivery_state(app, first.task_id, "delivered")
        self.clock.advance(timedelta(minutes=241))
        second = (await self.contact(app, self.opportunity("after-window"))).unwrap().task
        await self.delivery_state(app, second.task_id, "delivered")
        past = [m for m in self.contact_calls()[-1].original.context.materials
                if m.owner == "delivery.history"]
        self.assertEqual([m.purpose for m in past], ["confirmed_background_message"])
        self.settings(app, {"dedup_sent_window_minutes": 0}).unwrap()
        await self.contact(app, self.opportunity("unbounded"))
        recent = [m for m in self.contact_calls()[-1].original.context.materials
                  if m.owner == "delivery.history"]
        self.assertEqual([m.purpose for m in recent], ["dedup_candidate", "dedup_candidate"])

    async def test_unresolved_blocks_repeat_but_failed_or_other_window_does_not(self):
        app = await self.enabled()
        with patch.object(app.background, "advance", return_value=False):
            first = (await self.contact(app)).unwrap().task
        context = self.contact_context()
        prefs = self.preferences(app)
        self.assertTrue(app.proactive._duplicate(context, "刚想起上次的话题。", prefs, self.clock.now(), purpose="chat"))
        other = self.other_window_context()
        self.assertFalse(app.proactive._duplicate(other, "刚想起上次的话题。",
                                                  self.preferences(app, other), self.clock.now(), purpose="chat"))
        app.proactive.cancel(context, first.task_id, expected_revision=first.revision).unwrap()
        self.assertFalse(app.proactive._duplicate(context, "刚想起上次的话题。", prefs, self.clock.now(), purpose="chat"))

    async def test_last_foreground_reply_is_scoped_and_withdrawal_invalidates_reference(self):
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        self.settings(app, {"enabled": True}).unwrap()
        batch = host.receive(self.event()).unwrap()
        await self.done(app, batch)
        context = self.context(app, batch)
        reply = app.background_history.latest_reply(context, self.clock.now(), within_minutes=0)
        self.assertEqual(reply["text"], "记住了。")
        self.assertIsNone(app.background_history.latest_reply(
            self.other_window_context(), self.clock.now(), within_minutes=0))
        async def same(envelope):
            if isinstance(envelope.original.event, BackgroundPromptTrigger):
                return answered('{"decision":"send","text":"记住了。"}')
            return answered("记住了。")
        self.model_behavior = same
        task = (await self.contact(app)).unwrap().task
        self.assertEqual(app.proactive.observe(context, task.task_id).unwrap()["dedup_reason"], "exact_repeat")
        event_key = app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))[0]
        app.withdraw(context, event_key).unwrap()
        with self.assertRaises(TaskError):
            app.background_history.verify_reply(reply["reference"], context, self.clock.now())

    async def test_reply_withdrawn_during_contact_generation_cannot_be_committed(self):
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        self.settings(app, {"enabled": True}).unwrap()
        batch = host.receive(self.event()).unwrap()
        await self.done(app, batch)
        context = self.context(app, batch)
        event_key = app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))[0]
        async def revoke(envelope):
            if isinstance(envelope.original.event, BackgroundPromptTrigger):
                self.assertTrue(any(m.purpose == "last_confirmed_reply" for m in envelope.original.context.materials))
                app.withdraw(context, event_key).unwrap()
                return answered('{"decision":"send","text":"另一个话题"}')
            return answered("记住了。")
        self.model_behavior = revoke
        result = await self.contact(app)
        self.assertNotEqual(result.unwrap().task.state, "succeeded")
        self.assertEqual(self.contacts(app), ())
        self.assertEqual(len(self.sent), 1)

    async def test_parallel_checks_of_same_reply_do_not_look_cyclic(self):
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        batch = host.receive(self.event()).unwrap()
        await self.done(app, batch)
        context = self.context(app, batch)
        entered, release = Event(), Event()
        original = app.messages.reply_images.for_part

        def hold_worker(*args, **kwargs):
            if current_thread() is not main_thread():
                entered.set()
                if not release.wait(3):
                    raise AssertionError("parallel reply check did not finish")
            return original(*args, **kwargs)

        with patch.object(app.messages.reply_images, "for_part", side_effect=hold_worker):
            with ThreadPoolExecutor(max_workers=1) as pool:
                worker = pool.submit(app.background_history.latest_reply, context, self.clock.now(),
                                     within_minutes=0)
                try:
                    self.assertTrue(entered.wait(3))
                    concurrent = app.background_history.latest_reply(context, self.clock.now(), within_minutes=0)
                finally:
                    release.set()
                first = worker.result(timeout=3)
        self.assertEqual(concurrent["reference"], first["reference"])

    async def test_policy_input_rejects_unknown_or_repeated_routes(self):
        app = await self.enabled()
        for value in ("semantic,semantic", "semantic,unknown"):
            with self.subTest(value=value):
                self.assertFalse(self.settings(app, {"dedup_policies": value}).is_success)
        self.settings(app, {"dedup_policies": "  semantic，life_event  "}).unwrap()
        self.assertEqual(self.preferences(app).values["dedup_policies"], "semantic,life_event")

    async def test_semantic_overlap_preferences_reach_the_real_contact_prompt(self):
        app = await self.enabled()
        self.settings(app, {"dedup_min_shared_tokens": 3, "dedup_min_overlap_ratio": 0.65}).unwrap()
        await self.contact(app)
        instruction = self.contact_calls()[-1].original.instruction
        self.assertIn("短话题最少共享锚点 3 个", instruction)
        self.assertIn("较长话题最低重叠比例 0.65", instruction)
        for changes in ({"dedup_min_shared_tokens": 0}, {"dedup_min_shared_tokens": 5},
                        {"dedup_min_overlap_ratio": -0.1}, {"dedup_min_overlap_ratio": 1.1}):
            with self.subTest(changes=changes):
                self.assertFalse(self.settings(app, changes).is_success)


class WeatherDedupCoverageTests(unittest.TestCase):
    """The weather window only works if its routes are enabled by default.

    ``dedup_weather_window_minutes`` is read only when the contact's origin is a
    weather one, so a route missing from ``dedup_policies`` makes the window dead
    code for that contact while the setting still looks configured. That is a silent
    failure -- nothing errors, the operator simply keeps getting repeats.
    """

    def setUp(self):
        self.defaults = {field.field_id.split(".")[-1]: field.default
                         for field in configuration_fields()}
        self.enabled = set(dedup_policies(self.defaults["dedup_policies"]))

    def test_every_weather_origin_route_is_enabled_by_default(self):
        weather_origins = ("weather_event", "weather_change_event", "official_alert_event")
        for origin in weather_origins:
            with self.subTest(origin=origin):
                route = next(route for marker, route in DEDUP_EVENT_POLICY if marker == origin)
                self.assertIn(route, self.enabled)

    def test_a_weather_window_alone_cannot_suppress_anything(self):
        """Guards the reasoning above: the window is inert without a matching route."""
        policy = ContactPreferences(
            None, {"dedup_enabled": True, "dedup_policies": "life_event"}, NOW)
        for origin in ("weather_event", "weather_change_event", "official_alert_event"):
            with self.subTest(origin=origin):
                self.assertFalse(policy.dedup_applies("environment", {origin: {}}))

    def test_disabling_dedup_outright_releases_every_route(self):
        """The off switch must be a full release, not a narrower window."""
        policy = ContactPreferences(
            None, {"dedup_enabled": False, "dedup_policies": self.defaults["dedup_policies"]}, NOW)
        for origin in ("weather_event", "weather_change_event", "official_alert_event"):
            with self.subTest(origin=origin):
                self.assertFalse(policy.dedup_applies("environment", {origin: {}}))

    def test_the_default_policy_string_survives_a_round_trip(self):
        self.assertEqual(dedup_policies(self.defaults["dedup_policies"]),
                         tuple(dedup_policies(self.defaults["dedup_policies"])))
