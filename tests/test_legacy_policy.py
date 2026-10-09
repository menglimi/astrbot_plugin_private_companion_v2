import unittest

from companion_v2.memory.legacy_policy import evaluate_legacy_memory_access


PRIVATE_OWNER = ("private", "user-1")
PRIVATE_READER = ("private", "user-2")
GROUP_OWNER = ("group", "group-1")
GROUP_READER = ("group", "group-2")


def policy(scope, window_id, *, read_mode="whitelist", share_mode="whitelist",
           recall_enabled=None, capture_enabled=None):
    return {"window_scope": scope, "window_id": window_id,
            "read_mode": read_mode, "share_mode": share_mode,
            "recall_enabled": recall_enabled, "capture_enabled": capture_enabled}


def rule(owner, reader, effect="allow", *, enabled=1):
    return {"owner_scope": owner[0], "owner_id": owner[1],
            "reader_scope": reader[0], "reader_id": reader[1],
            "effect": effect, "enabled": enabled}


def evaluate(owner, reader, *, policies=(), rules=(), known=None):
    return evaluate_legacy_memory_access(owner, reader, policies=policies, rules=rules,
                                         known_readers=(owner, reader) if known is None else known)


class LegacyPolicyTests(unittest.TestCase):
    def test_private_default_is_whitelist_and_blocks_other_private_reader(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_READER)

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "policy_default_deny")

    def test_exact_allow_grants_a_private_reader(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_READER,
                            rules=(rule(PRIVATE_OWNER, PRIVATE_READER),))

        self.assertTrue(decision.readable)
        self.assertEqual(decision.reason_code, "acl_allow")

    def test_exact_reader_identity_is_required_for_allow_rule(self):
        decision = evaluate(PRIVATE_OWNER, ("private", "user-3"),
                            rules=(rule(PRIVATE_OWNER, PRIVATE_READER),))

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "policy_default_deny")

    def test_deny_has_priority_over_allow_for_same_exact_pair(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_READER, rules=(
            rule(PRIVATE_OWNER, PRIVATE_READER, "allow"),
            rule(PRIVATE_OWNER, PRIVATE_READER, "deny"),
        ))

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "acl_deny")

    def test_disabled_deny_rule_is_ignored(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_READER, rules=(
            rule(PRIVATE_OWNER, PRIVATE_READER, "deny", enabled=0),
            rule(PRIVATE_OWNER, PRIVATE_READER, "allow"),
        ))

        self.assertTrue(decision.readable)
        self.assertEqual(decision.reason_code, "acl_allow")

    def test_blacklist_owner_and_reader_allow_default_cross_window_read(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_READER, policies=(
            policy(*PRIVATE_OWNER, share_mode="blacklist"),
            policy(*PRIVATE_READER, read_mode="blacklist"),
        ))

        self.assertTrue(decision.readable)
        self.assertEqual(decision.reason_code, "blacklist_default_allowed")

    def test_private_to_group_requires_explicit_allow_even_with_blacklists(self):
        decision = evaluate(PRIVATE_OWNER, GROUP_READER, policies=(
            policy(*PRIVATE_OWNER, share_mode="blacklist"),
            policy(*GROUP_READER, read_mode="blacklist"),
        ))

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "private_group_allow_required")

    def test_private_to_group_explicit_allow_overrides_blacklist_default(self):
        decision = evaluate(PRIVATE_OWNER, GROUP_READER, policies=(
            policy(*PRIVATE_OWNER, share_mode="blacklist"),
            policy(*GROUP_READER, read_mode="blacklist"),
        ), rules=(rule(PRIVATE_OWNER, GROUP_READER),))

        self.assertTrue(decision.readable)
        self.assertEqual(decision.reason_code, "acl_allow")

    def test_group_defaults_to_blacklist_for_both_window_modes(self):
        decision = evaluate(GROUP_OWNER, GROUP_READER)

        self.assertTrue(decision.readable)
        self.assertEqual(decision.reason_code, "blacklist_default_allowed")

    def test_unknown_reader_is_denied_even_if_its_modes_would_allow(self):
        decision = evaluate(GROUP_OWNER, GROUP_READER, known=(GROUP_OWNER,), rules=(
            rule(GROUP_OWNER, GROUP_READER),
        ))

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "reader_unknown")

    def test_unknown_owner_is_denied_even_with_group_blacklist_defaults(self):
        decision = evaluate(GROUP_OWNER, GROUP_READER, known=(GROUP_READER,))

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "owner_unknown")

    def test_reader_recall_disabled_blocks_explicit_allow(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_READER, policies=(
            policy(*PRIVATE_READER, recall_enabled=0),
        ), rules=(rule(PRIVATE_OWNER, PRIVATE_READER),))

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "reader_recall_disabled")

    def test_capture_disabled_does_not_disable_reading_existing_material(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_READER, policies=(
            policy(*PRIVATE_READER, capture_enabled=0),
        ), rules=(rule(PRIVATE_OWNER, PRIVATE_READER),))

        self.assertTrue(decision.readable)

    def test_unknown_policy_mode_fails_closed(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_READER, policies=(
            policy(*PRIVATE_OWNER, share_mode="open"),
        ), rules=(rule(PRIVATE_OWNER, PRIVATE_READER),))

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "policy_mode_unknown")

    def test_unknown_recall_override_fails_closed(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_READER, policies=(
            policy(*PRIVATE_READER, recall_enabled="sometimes"),
        ), rules=(rule(PRIVATE_OWNER, PRIVATE_READER),))

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "policy_value_unknown")

    def test_unknown_matching_acl_effect_fails_closed(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_READER, rules=(
            rule(PRIVATE_OWNER, PRIVATE_READER, "maybe"),
        ))

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "acl_effect_unknown")

    def test_same_window_ignores_acl_rules_as_v1_does(self):
        decision = evaluate(PRIVATE_OWNER, PRIVATE_OWNER, rules=(
            rule(PRIVATE_OWNER, PRIVATE_OWNER, "deny"),
        ))

        self.assertTrue(decision.readable)
        self.assertEqual(decision.reason_code, "same_window")

    def test_invalid_reader_fails_closed(self):
        decision = evaluate(PRIVATE_OWNER, ("private", ""))

        self.assertFalse(decision.readable)
        self.assertEqual(decision.reason_code, "identity_invalid")


if __name__ == "__main__":
    unittest.main()
