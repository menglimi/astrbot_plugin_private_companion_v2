"""跨窗口递话的计划与审计字段。"""

import unittest

from companion_v2.conversation.relay_policy import RelayRequest
from companion_v2.conversation.relay import plan_relay


SETTINGS = {"enabled": True, "require_confirm": True, "max_text_chars": 500,
            "core_target_id": "1001", "allowed_targets": ["2002", "3003"]}


def ask(destination="2002", text="帮我带句话：今晚不打了", source="5005"):
    return RelayRequest("private", destination, text, source)


class RelayPlanTests(unittest.TestCase):
    def test_core_admin_plan_needs_confirmation_and_records_audit(self):
        plan = plan_relay(ask(), SETTINGS, actor_is_core=True, actor_id="1001")
        self.assertTrue(plan.allowed)
        self.assertTrue(plan.needs_confirm)
        self.assertEqual(plan.text, "帮我带句话：今晚不打了")
        self.assertEqual(plan.audit["audience"], "admin_target")
        self.assertEqual(plan.audit["destination"], "2002")

    def test_member_plan_goes_to_the_admin_without_confirmation(self):
        plan = plan_relay(ask("1001"), SETTINGS, actor_is_core=False, actor_id="5005")
        self.assertTrue(plan.allowed)
        self.assertFalse(plan.needs_confirm)
        self.assertEqual(plan.audit["audience"], "owner")

    def test_string_allowlist_is_parsed(self):
        settings = dict(SETTINGS, allowed_targets='["2002"]')
        self.assertTrue(plan_relay(ask(), settings, actor_is_core=True).allowed)
        denied = plan_relay(ask("3003"), settings, actor_is_core=True)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.decision.code, "relay_target_not_allowed")

    def test_disabled_window_yields_no_destination(self):
        plan = plan_relay(ask(), {"enabled": False}, actor_is_core=True)
        self.assertFalse(plan.allowed)
        self.assertEqual(plan.destination_id, "")
        self.assertEqual(plan.audit["code"], "relay_disabled")

    def test_member_cannot_reach_a_whitelisted_target(self):
        plan = plan_relay(ask("2002"), SETTINGS, actor_is_core=False, actor_id="5005")
        self.assertFalse(plan.allowed)
        self.assertEqual(plan.decision.code, "relay_target_not_allowed")


if __name__ == "__main__":
    unittest.main()
