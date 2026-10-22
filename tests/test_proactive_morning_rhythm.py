"""Routine learning and the continuous morning chain."""

from datetime import datetime, timedelta
import unittest
from zoneinfo import ZoneInfo

from companion_v2.proactive.morning_rhythm import (
    DEFAULT_WAKE_MINUTES, MORNING_INSTRUCTION, NUDGE_INSTRUCTION, MorningContact,
    RoutineSample, estimate, morning_anchor_recommendation, morning_plan,
    predict_wake_window, rhythm_adjustment, role_wake_at,
)
from companion_v2.proactive.rhythm import ContactRhythm
from types import SimpleNamespace as NS


ZONE = ZoneInfo("Asia/Shanghai")


def moment(day="2026-10-12", hour=7, minute=0):
    return datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=ZONE)


def weekday_samples():
    rows = []
    for offset in range(5):
        day = datetime(2026, 10, 5) + timedelta(days=offset)
        rows.append(RoutineSample(day.date().isoformat(), wake_minutes=7 * 60,
                                  sleep_minutes=23 * 60, morning_contact=True,
                                  replied_after_contact=True, response_delay_minutes=12))
    return rows


def weekend_samples():
    return [
        RoutineSample("2026-10-10", wake_minutes=8 * 60 + 30, sleep_minutes=23 * 60 + 40,
                      morning_contact=True, replied_after_contact=False),
        RoutineSample("2026-10-11", wake_minutes=8 * 60 + 30, sleep_minutes=23 * 60 + 40,
                      morning_contact=True, replied_after_contact=False),
    ]


class RoutineEstimateTests(unittest.TestCase):
    def test_estimate_uses_weekday_and_weekend_samples(self):
        profile = estimate([*weekday_samples(), *weekend_samples()], now=moment(hour=9))
        self.assertEqual(profile.weekday_wake.center_minutes, 7 * 60)
        self.assertEqual(profile.weekend_wake.center_minutes, 8 * 60 + 30)
        self.assertEqual(profile.weekday_wake.source, "learned_weekday")
        self.assertEqual(profile.weekend_wake.source, "learned_weekend")
        self.assertEqual(profile.sample_days, 7)
        self.assertAlmostEqual(profile.response_rate, 5 / 7, places=3)
        self.assertEqual(profile.median_response_minutes, 12)

    def test_estimate_falls_back_to_default_without_samples(self):
        profile = estimate((), now=moment(hour=9))
        self.assertEqual(profile.weekday_wake.center_minutes, DEFAULT_WAKE_MINUTES)
        self.assertEqual(profile.weekday_wake.samples, 0)
        self.assertEqual(profile.weekday_wake.confidence, 0.0)
        self.assertEqual(profile.weekday_wake.source, "default")

    def test_mad_controls_confidence(self):
        tight = estimate([
            RoutineSample(f"2026-10-0{day}", wake_minutes=value)
            for day, value in zip(range(1, 4), (410, 420, 430))
        ], now=moment(hour=9))
        noisy = estimate([
            RoutineSample(f"2026-10-0{day}", wake_minutes=value)
            for day, value in zip(range(1, 4), (360, 420, 480))
        ], now=moment(hour=9))
        self.assertGreater(tight.weekday_wake.confidence, noisy.weekday_wake.confidence)

    def test_night_sleep_median_handles_midnight_wrap(self):
        profile = estimate([
            RoutineSample("2026-10-01", sleep_minutes=23 * 60 + 30),
            RoutineSample("2026-10-02", sleep_minutes=30),
        ], now=moment(hour=9))
        self.assertEqual(profile.weekday_sleep.center_minutes, 0)


class WakeWindowTests(unittest.TestCase):
    def test_predict_wake_window_is_bounded_and_contains_center(self):
        profile = estimate([*weekday_samples(), *weekend_samples()], now=moment(hour=9))
        window = predict_wake_window(profile, at=moment(hour=7))
        self.assertLessEqual(window.start_at.hour, window.center_at.hour)
        self.assertGreaterEqual(window.end_at, window.start_at + timedelta(minutes=30))
        self.assertTrue(window.contains(window.center_at))
        self.assertGreaterEqual(window.start_at.hour, 4)
        self.assertLessEqual(window.end_at.hour, 14)

    def test_weekend_window_uses_weekend_center(self):
        profile = estimate([*weekday_samples(), *weekend_samples()], now=moment(hour=9))
        window = predict_wake_window(profile, at=moment(day="2026-10-18", hour=8))
        self.assertEqual(window.center_at.hour, 8)
        self.assertEqual(window.center_at.minute, 30)
        self.assertEqual(window.source, "learned_weekend")


class MorningPlanTests(unittest.TestCase):
    def setUp(self):
        self.profile = estimate([*weekday_samples(), *weekend_samples()], now=moment(hour=9))

    def test_role_morning_waits_until_predicted_window(self):
        step = morning_plan(self.profile, at=moment(hour=5, minute=30),
                            role_woke_at=moment(hour=5, minute=20))
        self.assertEqual(step.action, "hold")
        self.assertEqual(step.reason, "before_wake_window")

    def test_role_morning_sends_after_bot_wakes_in_window(self):
        step = morning_plan(self.profile, at=moment(hour=7, minute=10),
                            role_woke_at=moment(hour=7, minute=5))
        self.assertEqual((step.action, step.reason), ("role_morning", "role_woke_in_wake_window"))

    def test_role_morning_requires_a_role_wake_receipt(self):
        step = morning_plan(self.profile, at=moment(hour=7, minute=10), role_woke_at=None)
        self.assertEqual((step.action, step.reason), ("hold", "role_not_awake"))

    def test_role_wake_window_elapsed_skips(self):
        step = morning_plan(self.profile, at=moment(hour=7, minute=10),
                            role_woke_at=moment(hour=2, minute=0))
        self.assertEqual((step.action, step.reason), ("skip", "role_wake_window_elapsed"))

    def test_nudge_requires_delay_and_no_reply(self):
        contact = MorningContact(sent_at=moment(hour=7, minute=0))
        early = morning_plan(self.profile, at=moment(hour=7, minute=20), contact=contact)
        self.assertEqual((early.action, early.reason), ("hold", "nudge_delay_not_elapsed"))
        ready = morning_plan(self.profile, at=moment(hour=7, minute=25), contact=contact)
        self.assertEqual((ready.action, ready.reason), ("wake_nudge", "no_user_reply_yet"))

    def test_user_reply_cancels_nudge(self):
        contact = MorningContact(sent_at=moment(hour=7, minute=0),
                                 user_replied_at=moment(hour=7, minute=15))
        step = morning_plan(self.profile, at=moment(hour=7, minute=25), contact=contact)
        self.assertEqual((step.action, step.reason), ("skip", "user_engaged"))
        via_input = morning_plan(self.profile, at=moment(hour=7, minute=25), contact=contact,
                                 user_last_input_at=moment(hour=7, minute=18))
        self.assertEqual(via_input.action, "skip")

    def test_nudge_budget_and_cooldown(self):
        used = MorningContact(sent_at=moment(hour=7, minute=0), nudge_count=1)
        self.assertEqual(morning_plan(self.profile, at=moment(hour=7, minute=25),
                                      contact=used).reason, "nudge_budget_exhausted")
        cooling = MorningContact(sent_at=moment(hour=7, minute=0),
                                 last_nudge_at=moment(hour=7, minute=10))
        self.assertEqual(morning_plan(self.profile, at=moment(hour=7, minute=25),
                                      contact=cooling).reason, "nudge_cooldown")

    def test_negative_sleep_evidence_holds(self):
        step = morning_plan(self.profile, at=moment(hour=7, minute=10),
                            role_woke_at=moment(hour=7, minute=5),
                            negative_evidence_at=moment(hour=7, minute=0))
        self.assertEqual((step.action, step.reason), ("hold", "recent_sleep_evidence"))

    def test_window_closed_skips(self):
        step = morning_plan(self.profile, at=moment(hour=9, minute=30),
                            role_woke_at=moment(hour=7, minute=0))
        self.assertEqual((step.action, step.reason), ("skip", "wake_window_closed"))


class RhythmAdjustmentTests(unittest.TestCase):
    def test_rhythm_adjustment_is_bounded(self):
        profile = estimate(weekday_samples(), now=moment(hour=9))
        adjustment = rhythm_adjustment(profile)
        self.assertEqual(adjustment.active_start_minutes, 6 * 60 + 30)
        self.assertEqual(adjustment.active_end_minutes, 22 * 60)
        self.assertEqual(adjustment.hour_factors[7], 1.15)
        self.assertEqual(adjustment.hour_factors[3], 0.45)
        scaled = adjustment.apply(tuple(1.0 for _ in range(24)))
        self.assertEqual(scaled[7], 1.15)
        self.assertTrue(all(0.05 <= value <= 2.0 for value in scaled))

    def test_morning_anchor_recommendation_uses_learned_center(self):
        profile = estimate(weekday_samples(), now=moment(hour=9))
        self.assertEqual(morning_anchor_recommendation(profile), "06:15-08:15")
        empty = estimate((), now=moment(hour=9))
        self.assertEqual(morning_anchor_recommendation(empty), "")


class HourCurveAdjustmentTests(unittest.TestCase):
    def test_hour_allows_accepts_the_adjusted_curve(self):
        preferences = NS(values={
            "proactive_hour_activity_enabled": True,
            "proactive_hour_activity_curve": ",".join("1.0" for _ in range(24)),
            "quiet_timezone": "Asia/Shanghai",
        })
        curve = [0.05] * 24
        curve[7] = 2.0
        rhythm = ContactRhythm.__new__(ContactRhythm)
        context = NS(key="context")
        self.assertTrue(rhythm.hour_allows(context, preferences, moment(hour=7),
                                           observed_at=moment(hour=7), curve=curve))
        self.assertFalse(rhythm.hour_allows(context, preferences, moment(hour=3),
                                            observed_at=moment(hour=3), curve=curve))


class ReceiptAndInstructionTests(unittest.TestCase):
    def test_role_wake_at_reads_body_sleep_receipt(self):
        body = {"state": "awake", "last_completed": {"completed_at": "2026-10-12T06:40:00+08:00"}}
        self.assertEqual(role_wake_at(body), datetime(2026, 10, 11, 22, 40, tzinfo=ZoneInfo("UTC")))
        self.assertIsNone(role_wake_at({"state": "sleeping", "last_completed": {}}))
        self.assertIsNone(role_wake_at({"state": "awake", "last_completed": {"completed_at": "2026-10-12T06:40:00"}}))

    def test_instructions_keep_the_evidence_boundary(self):
        self.assertIn("角色自己醒来", MORNING_INSTRUCTION)
        self.assertIn("不是催促打卡", NUDGE_INSTRUCTION)
        self.assertIn("对方没回就不再发", NUDGE_INSTRUCTION)
        self.assertIn("不要提设备", NUDGE_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()