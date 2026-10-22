"""User wake-up evidence fusion and wake-contact decision."""

from datetime import datetime, timedelta
import json
import unittest
from zoneinfo import ZoneInfo

from companion_v2.proactive.wake_detection import (
    STATE_ASLEEP_LIKELY, STATE_AWAKE_LIKELY, STATE_CONFIRMED, STATE_STIRRING,
    STATE_UNKNOWN, contact_decision, evidence, evidence_from_mobile_snapshot,
    evidence_from_private_input, evidence_from_wakeup_session, intent_summary, observe,
)


ZONE = ZoneInfo("Asia/Shanghai")
MORNING = datetime(2026, 10, 18, 7, 30, tzinfo=ZONE)


def at(**delta):
    return MORNING + timedelta(**delta)


def woke_now(*, sources=("mobile.telemetry", "mobile.activity")):
    return (
        evidence("motion_activity", at(minutes=-2), source=sources[0]),
        evidence("screen_resumed", at(minutes=-1), source=sources[1]),
    )


class WakeObservationTests(unittest.TestCase):
    def test_no_evidence_is_unknown_and_never_a_contact(self):
        observation = observe((), at=MORNING)
        self.assertEqual(observation.state, STATE_UNKNOWN)
        self.assertIsNone(observation.woke_at)
        self.assertFalse(contact_decision(observation, at=MORNING).allowed)

    def test_sleep_newer_than_motion_keeps_asleep_likely(self):
        items = (
            evidence("motion_activity", at(minutes=-30), source="mobile.telemetry"),
            evidence("sleep_reported", at(minutes=-5), source="mobile.telemetry"),
        )
        observation = observe(items, at=MORNING)
        self.assertEqual(observation.state, STATE_ASLEEP_LIKELY)
        self.assertIsNone(observation.woke_at)
        self.assertEqual(contact_decision(observation, at=MORNING).reason, "not_awake_likely")

    def test_two_independent_device_signals_allow_one_wake_contact(self):
        observation = observe(woke_now(), at=MORNING)
        self.assertEqual(observation.state, STATE_AWAKE_LIKELY)
        self.assertGreaterEqual(observation.confidence, 65)
        self.assertEqual(observation.reason, "independent_signals")
        decision = contact_decision(observation, at=MORNING)
        self.assertTrue(decision.allowed, decision.reason)
        self.assertEqual(decision.reason, "wake_contact_candidate")

    def test_single_weak_signal_stays_below_threshold(self):
        observation = observe((
            evidence("device_reconnected", at(minutes=-1), source="mobile.device"),
        ), at=MORNING)
        self.assertEqual(observation.state, STATE_UNKNOWN)
        self.assertLess(observation.confidence, 65)
        self.assertEqual(contact_decision(observation, at=MORNING).reason, "not_awake_likely")

    def test_explicit_private_message_confirms_awake(self):
        observation = observe((
            evidence("explicit_input", at(minutes=-3), source="conversation.input"),
        ), at=MORNING)
        self.assertEqual(observation.state, STATE_CONFIRMED)
        self.assertEqual(observation.confidence, 100)
        self.assertEqual(observation.reason, "explicit_awake_signal")
        self.assertTrue(contact_decision(observation, at=MORNING).allowed)

    def test_quiet_hours_and_outside_morning_window_block(self):
        observation = observe(woke_now(), at=MORNING)
        self.assertEqual(contact_decision(observation, at=MORNING, quiet_hours=True).reason, "quiet_hours")
        evening = observe((
            evidence("motion_activity", at(hours=14, minutes=58), source="mobile.telemetry"),
            evidence("screen_resumed", at(hours=14, minutes=59), source="mobile.activity"),
        ), at=at(hours=15))
        self.assertEqual(contact_decision(evening, at=at(hours=15)).reason, "outside_wake_window")

    def test_window_expiry_and_already_contacted_block(self):
        observation = observe((
            evidence("explicit_input", at(minutes=-70), source="conversation.input"),
        ), at=MORNING)
        self.assertEqual(
            contact_decision(observation, at=MORNING, window_minutes=60).reason,
            "wake_window_elapsed")
        fresh = observe((
            evidence("explicit_input", at(minutes=-2), source="conversation.input"),
        ), at=MORNING)
        self.assertEqual(
            contact_decision(fresh, at=MORNING, already_contacted=True).reason,
            "wake_contact_already_sent")

    def test_stale_evidence_is_ignored(self):
        items = (
            evidence("motion_activity", at(hours=-2), source="mobile.telemetry"),
            evidence("screen_resumed", at(hours=-2), source="mobile.activity"),
        )
        observation = observe(items, at=MORNING)
        self.assertEqual(observation.state, STATE_UNKNOWN)
        self.assertEqual(observation.reason, "no_fresh_evidence")

    def test_episode_key_buckets_by_90_minutes(self):
        first = observe((
            evidence("explicit_input", at(minutes=-80), source="conversation.input"),
        ), at=MORNING)
        second = observe((
            evidence("explicit_input", at(minutes=-60), source="conversation.input"),
        ), at=MORNING)
        later = observe((
            evidence("explicit_input", at(hours=1, minutes=30), source="conversation.input"),
        ), at=at(hours=1, minutes=30))
        self.assertEqual(first.episode_key, second.episode_key)
        self.assertNotEqual(first.episode_key, later.episode_key)


class WakeEvidenceAdapterTests(unittest.TestCase):
    def test_mobile_snapshot_mapping_uses_typed_states_only(self):
        captured = MORNING.timestamp() - 30
        snapshot = {
            "device": {"available": True, "online": True, "age_seconds": 10},
            "activity": {"available": True, "stale": False, "age_seconds": 20},
            "telemetry": {
                "available": True,
                "activity": {"state": "walking", "duration_minutes": 5},
                "measurements": [{"type": "steps", "value": 420, "unit": "steps",
                                  "captured_at": captured}],
                "label": "我已经醒了起床了",
                "app_label": "awake and up",
            },
        }
        kinds = {item.kind for item in evidence_from_mobile_snapshot(snapshot, at=MORNING)}
        self.assertEqual(kinds, {"device_reconnected", "screen_resumed",
                                 "motion_activity", "steps_increased"})
        sleeping = dict(snapshot, telemetry={"available": True, "activity": {"state": "sleeping"}})
        self.assertIn("sleep_reported",
                      {item.kind for item in evidence_from_mobile_snapshot(sleeping, at=MORNING)})
        resting = dict(snapshot, telemetry={"available": True, "activity": {"state": "resting"}})
        self.assertIn("resting_reported",
                      {item.kind for item in evidence_from_mobile_snapshot(resting, at=MORNING)})

    def test_mobile_snapshot_ignores_unavailable_or_text_only_payloads(self):
        self.assertEqual(evidence_from_mobile_snapshot(
            {"device": {"available": False}, "activity": {"available": False},
             "telemetry": {"available": False, "label": "awake"}}, at=MORNING), ())

    def test_wakeup_session_acknowledgement_and_snooze(self):
        acknowledged = {"contact_session": {"status": "acknowledged",
                                            "feedback_at": MORNING.timestamp() - 60}}
        self.assertEqual([item.kind for item in evidence_from_wakeup_session(acknowledged, at=MORNING)],
                         ["alarm_acknowledged"])
        snoozed = {"contact_session": {"status": "snoozed",
                                       "feedback_at": MORNING.timestamp() - 60}}
        self.assertEqual([item.kind for item in evidence_from_wakeup_session(snoozed, at=MORNING)],
                         ["sleep_reported"])

    def test_private_input_gap_creates_transition_only_after_quiet_gap(self):
        self.assertEqual(evidence_from_private_input(
            received_at=MORNING, previous_input_at=at(minutes=-10)), ())
        items = evidence_from_private_input(
            received_at=MORNING, previous_input_at=at(minutes=-90))
        self.assertEqual([item.kind for item in items], ["explicit_input"])

    def test_intent_summary_states_the_evidence_boundary(self):
        observation = observe(woke_now(), at=MORNING)
        summary = intent_summary(observation)
        self.assertIn("不证明你亲眼看见", summary)
        self.assertIn("不要说出「我看到你醒了」", summary)
        self.assertIn(str(observation.confidence), summary)
        self.assertNotIn("awake is up", summary)
        json.dumps(observation.document(), ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()