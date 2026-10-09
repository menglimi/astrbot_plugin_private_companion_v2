from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from companion_v2.execution.models import digest, stamp
from companion_v2.conversation.style_context import ConversationExpressionStyleContext
from companion_v2.expression import feedback, style_rotation
from companion_v2.foundation.refs import RoleOwnerRef
from companion_v2.storage.runtime import StorageRuntime
from tests.test_management_access import INSTALLATION, ROLE, SCOPE


NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


class ExpressionFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="companion-v2-expression-feedback-")
        self.addCleanup(self.temporary.cleanup)
        self.runtime = StorageRuntime.open(data_root=Path(self.temporary.name) / "data",
                                           installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        self.context = SimpleNamespace(scope=SCOPE, role_binding=SimpleNamespace(role=ROLE))
        owner = RoleOwnerRef(SCOPE.installation_id, SCOPE.bot_id, ROLE.subject_id)
        self.owner_key, self.scope_key = digest(owner), digest(SCOPE)
        catalog = SimpleNamespace(runtime=self.runtime, role_owner=lambda _context: owner)
        self.style_context = ConversationExpressionStyleContext(catalog)
        self.signal_id = "expression-run:feedback:signal:0"
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO expression_style_runs
                (run_id, owner_key, scope_key, sample_json, material_hash, summary, state, created_at, decided_at)
                VALUES (?, ?, ?, '{}', 'sample-hash', '表达测试', 'pending', ?, NULL)""",
                ("expression-run:feedback", self.owner_key, self.scope_key, stamp(NOW)))
            connection.execute("""INSERT INTO expression_style_signals
                (signal_id, run_id, owner_key, scope_key, dimension, observation, proposal, confidence,
                 evidence_json, state, created_at, decided_at, decided_by, decision_key, ordinal)
                VALUES (?, ?, ?, ?, 'diction', '晚间问候时使用轻松短句', '用轻松短句问候', 0.8,
                        '[]', 'adopted', ?, ?, 'operator', 'adopted', 0)""",
                (self.signal_id, "expression-run:feedback", self.owner_key, self.scope_key,
                 stamp(NOW), stamp(NOW)))

    def record(self, connection, owner, scope, signal_ids, at):
        style_rotation.record(self.runtime, owner_key=owner, scope_key=scope,
                              signal_ids=signal_ids, at=at, connection=connection)

    def deliver(self, batch_id, at):
        feedback.stage_injection(self.runtime, batch_id=batch_id, owner_key=self.owner_key,
            scope_key=self.scope_key, signal_ids=(self.signal_id,), at=at - timedelta(seconds=1))
        with self.runtime.transaction() as connection:
            self.style_context.confirm_delivery(connection, batch_id=batch_id, context=self.context,
                                                delivered_at=at)

    def consume(self, text, at, *, owner_key=None, scope_key=None, channel="private"):
        with self.runtime.transaction() as connection:
            return feedback.consume_feedback(connection, owner_key=owner_key or self.owner_key,
                scope_key=scope_key or self.scope_key, channel=channel, text=text, received_at=at)

    def test_only_a_confirmed_delivery_starts_feedback_and_rotation(self):
        feedback.stage_injection(self.runtime, batch_id="reply-unsent", owner_key=self.owner_key,
            scope_key=self.scope_key, signal_ids=(self.signal_id,), at=NOW)
        self.assertEqual(style_rotation.usage(self.runtime, self.owner_key, self.scope_key), {})
        self.assertEqual(self.consume("别这么说", NOW + timedelta(seconds=1)), {})
        self.assertEqual(feedback.usage(self.runtime, self.owner_key, self.scope_key), {})

        self.deliver("reply-sent", NOW)
        self.assertEqual(style_rotation.usage(self.runtime, self.owner_key, self.scope_key)[self.signal_id][0], 1)
        self.assertEqual(self.consume("今天先聊点别的", NOW + timedelta(seconds=1)), {})
        self.assertEqual(feedback.usage(self.runtime, self.owner_key, self.scope_key), {})

    def test_two_clear_negative_feedbacks_return_rule_to_review(self):
        self.deliver("reply-one", NOW)
        first = self.consume("别这么说", NOW + timedelta(seconds=1))
        self.assertEqual((first["signal"], first["updated_rules"], first["demoted_rules"]),
                         ("negative", 1, 0))
        self.assertEqual(self.runtime.read_one("SELECT state FROM expression_style_signals WHERE signal_id = ?",
                                               (self.signal_id,))["state"], "adopted")

        self.deliver("reply-two", NOW + timedelta(minutes=1))
        second = self.consume("这个语气怪怪的，别这样说", NOW + timedelta(minutes=1, seconds=1))
        self.assertEqual((second["signal"], second["updated_rules"], second["demoted_rules"]),
                         ("negative", 1, 1))
        self.assertEqual(self.runtime.read_one("SELECT state FROM expression_style_signals WHERE signal_id = ?",
                                               (self.signal_id,))["state"], "pending")
        usage = feedback.usage(self.runtime, self.owner_key, self.scope_key)[self.signal_id]
        self.assertEqual((usage["negative_count"], usage["positive_count"]), (2, 0))
        self.assertIn("退回复审", usage["review_reason"])

    def test_duplicate_receipts_do_not_count_the_same_rule_twice(self):
        self.deliver("reply-segmented", NOW)
        with self.runtime.transaction() as connection:
            feedback.confirm_delivery(connection, batch_id="reply-segmented", owner_key=self.owner_key,
                scope_key=self.scope_key, delivered_at=NOW + timedelta(seconds=1),
                rotation_record=self.record)
        self.assertEqual(style_rotation.usage(self.runtime, self.owner_key, self.scope_key)[self.signal_id][0], 1)

    def test_feedback_is_scoped_to_the_same_role_and_conversation(self):
        self.deliver("reply-scoped", NOW)
        self.assertEqual(self.consume("别这么说", NOW + timedelta(seconds=1), scope_key="other-scope"), {})
        self.assertEqual(feedback.usage(self.runtime, self.owner_key, self.scope_key), {})

    def test_classifier_requires_a_direct_expression_reference(self):
        self.assertEqual(feedback.classify("这个语气很自然，我喜欢"), "positive")
        self.assertEqual(feedback.classify("别学我这样说"), "negative")
        self.assertEqual(feedback.classify("哈哈，今天挺开心"), "")


if __name__ == "__main__":
    unittest.main()
