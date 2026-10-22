"""Morning contact producer: role greeting, one nudge, conversation-aware stop."""

from datetime import datetime, timedelta
import json
import unittest
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

from companion_v2.proactive.wake_events import WakeContactEvents


ZONE = ZoneInfo("Asia/Shanghai")
DAY = "2026-10-12"
AT = datetime(2026, 10, 12, 7, 10, tzinfo=ZONE)
ROLE_WOKE = AT - timedelta(minutes=5)


class FakeOutcome:
    is_success = True

    def __init__(self, value):
        self.value = value

    def unwrap(self):
        return self.value


def values(**changes):
    base = {
        "morning_chain_enabled": True,
        "morning_role_greeting_enabled": True,
        "morning_nudge_enabled": True,
        "routine_learning_enabled": True,
        "routine_window_days": 60,
        "quiet_timezone": "Asia/Shanghai",
        "morning_nudge_delay_minutes": 25,
        "morning_nudge_max_attempts": 1,
        "wake_morning_start": "05:00",
        "wake_morning_end": "11:30",
        "wake_contact_min_confidence": 65,
        "wake_contact_window_minutes": 90,
        "wake_require_device_evidence": False,
        "wake_contact_max_daily": 1,
        "morning_wake_confidence_floor": 0.25,
        "_reason": None,
    }
    base.update(changes)
    return base


class FakePreferences:
    def __init__(self, settings):
        self.values = settings

    def reason(self, purpose):
        return self.values.get("_reason")

    def require_contact(self, purpose):
        if self.reason(purpose):
            raise AssertionError("purpose blocked")


class FakeRuntime:
    def __init__(self, morning_rows=()):
        self.morning_rows = tuple(morning_rows)

    def read_all(self, sql, params):
        if "SELECT c.contact_id, c.created_at, c.record_json" in sql:
            return self.morning_rows
        return ()

    def read_one(self, sql, params):
        return None


class FakeRoleState:
    def __init__(self, wake_at):
        self.wake_at = wake_at

    def read(self, context, at=None):
        return {"body_sleep": {"state": "awake",
                               "last_completed": {"completed_at": self.wake_at.isoformat()}}}


def morning_record(sent_at, *, action="role_morning", episode="morning-role:" + DAY):
    marker = {"kind": "morning", "action": action, "episode_key": episode,
              "local_date": DAY, "window_start": "", "window_end": "",
              "confidence": 0, "source": "default", "samples": 0}
    return {"created_at": sent_at.isoformat(), "delivered_at": None,
            "record_json": json.dumps({"decision": "send",
                "automatic_origin": {"morning_event": marker}}, ensure_ascii=False)}


class MorningChainTests(unittest.TestCase):
    def make_events(self, *, settings=None, interaction=None, port=None, morning_rows=()):
        self.preferences = FakePreferences(settings or values())
        runtime = FakeRuntime(morning_rows)
        contacts = NS(runtime=runtime,
            task_id=lambda context, opportunity: "task-" + opportunity.opportunity_id,
            preferences=NS(read=lambda context, observed_at: FakeOutcome(self.preferences)),
            history=NS(interaction=lambda context, at, action: interaction))
        events = WakeContactEvents(contacts, FakeRoleState(ROLE_WOKE), port or (lambda context: {}))
        context = NS(key="ctx", scope=NS(key="scope"),
                     actor=NS(principal=NS(native_account_id="200")))
        return events, context

    def test_role_morning_is_produced_after_the_role_wakes(self):
        events, context = self.make_events()
        candidate = events.select(context, self.preferences, AT)
        self.assertIsNotNone(candidate, events.last_diagnostic)
        opportunity, intents, marker = candidate
        self.assertEqual(marker["action"], "role_morning")
        self.assertEqual(marker["episode_key"], "morning-role:" + DAY)
        self.assertEqual(intents[0].purpose, "greeting")
        self.assertEqual((opportunity.opened_at, opportunity.expires_at - opportunity.opened_at),
                         (AT.astimezone(ZoneInfo("UTC")), timedelta(minutes=5)))

    def test_role_morning_can_be_disabled(self):
        events, context = self.make_events(settings=values(morning_role_greeting_enabled=False))
        self.assertIsNone(events.select(context, self.preferences, AT))
        self.assertEqual(events.last_diagnostic["reason"], "role_morning_disabled")

    def test_nudge_requires_a_prior_role_morning_and_no_reply(self):
        sent = AT - timedelta(minutes=25)
        interaction = {"last_input_at": (sent - timedelta(minutes=30)).isoformat()}
        port = lambda context: {"mobile": {
            "activity": {"available": True, "stale": False, "age_seconds": 20},
            "telemetry": {"available": True, "activity": {"state": "walking"}}}}
        events, context = self.make_events(interaction=interaction, port=port,
                                           morning_rows=(morning_record(sent),))
        candidate = events.select(context, self.preferences, AT)
        self.assertIsNotNone(candidate, events.last_diagnostic)
        _opportunity, _intents, marker = candidate
        self.assertEqual(marker["action"], "wake_nudge")
        self.assertTrue(marker["episode_key"].startswith("wake:"))

    def test_user_reply_stops_the_nudge(self):
        sent = AT - timedelta(minutes=25)
        interaction = {"last_input_at": (sent + timedelta(minutes=10)).isoformat()}
        port = lambda context: {"mobile": {
            "telemetry": {"available": True, "activity": {"state": "walking"}}}}
        events, context = self.make_events(interaction=interaction, port=port,
                                           morning_rows=(morning_record(sent),))
        self.assertIsNone(events.select(context, self.preferences, AT))
        self.assertEqual(events.last_diagnostic["reason"], "user_engaged")

    def test_nudge_can_be_disabled(self):
        events, context = self.make_events(
            settings=values(morning_nudge_enabled=False, morning_role_greeting_enabled=False))
        self.assertIsNone(events.select(context, self.preferences, AT))
        self.assertEqual(events.last_diagnostic["reason"], "morning_actions_disabled")

    def test_no_chain_when_switch_is_off(self):
        events, context = self.make_events(settings=values(morning_chain_enabled=False))
        self.assertIsNone(events.select(context, self.preferences, AT))
        self.assertEqual(events.last_diagnostic["reason"], "morning_chain_disabled")

    def test_quiet_hours_and_disabled_greeting_are_respected(self):
        events, context = self.make_events(settings=values(_reason="proactive_quiet_hours"))
        self.assertIsNone(events.select(context, self.preferences, AT))
        self.assertEqual(events.last_diagnostic["reason"], "proactive_quiet_hours")


if __name__ == "__main__":
    unittest.main()