import unittest

from diagnostic_envelope import normalize_diagnostic_result


class PendingDiagnosticTests(unittest.TestCase):
    def test_scheduled_proactive_result_keeps_ok_and_pending(self):
        result = normalize_diagnostic_result({
            "ok": True,
            "pending": True,
            "outcome_type": "waiting_schedule",
            "detail": "已预约 15 秒后的测试",
        }, test_type="proactive_message")
        self.assertTrue(result["ok"])
        self.assertTrue(result["pending"])
        self.assertEqual(result["phase"], "scheduled")

    def test_completed_proactive_result_is_no_longer_pending(self):
        result = normalize_diagnostic_result({
            "ok": True,
            "pending": False,
            "outcome_type": "completed",
        }, test_type="proactive_message")
        self.assertFalse(result["pending"])
        self.assertEqual(result["phase"], "completed")


if __name__ == "__main__":
    unittest.main()
