"""Existing source reads and diagnostics retain their native turn boundaries."""

from datetime import timedelta
import unittest

from companion_v2.conversation.recalls import MessageRecall
from companion_v2.diagnostics.models import DiagnosticQuery
from companion_v2.execution.models import require
from tests.multi_host_support import MultiFixture
from tests.test_core_reply_owner_tools import NativeOwnerCalls


class CoreReplyDiagnosticToolsTests(NativeOwnerCalls, MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = await self.start_host()

    async def test_offered_source_read_replays_and_rechecks_withdrawal(self):
        event = self.event(identifier="native-source-read", text="刚刚看完了一篇新闻")
        prepared, request = await self.bind(event)
        evidence = await self.call(event, request, "turn.evidence", {})
        handle = evidence["evidence_handles"][0]
        result = await self.call(event, request, "source.read", {"handle": handle}, "read-current-input")
        self.assertEqual((result["state"], result["effect"]), ("succeeded", "none"), result)
        self.assertIn("刚刚看完了一篇新闻", result["payload"])
        replay = await self.call(event, request, "source.read", {"handle": handle}, "read-current-input")
        self.assertTrue(replay["replayed"], replay)
        self.assertEqual(result["content_hash"], replay["content_hash"])
        require(self.app.messages.recalls.accept(MessageRecall.from_scope(prepared["context"].scope,
            prepared["event_id"], prepared["context"].actor.principal.native_account_id)))
        withdrawn = await self.call(event, request, "source.read", {"handle": handle}, "read-current-input")
        self.assertEqual(withdrawn["state"], "failed", withdrawn)
        self.assertNotIn("payload", withdrawn)
        self.assert_no_reply_work()

    async def test_source_handle_from_another_native_turn_is_unavailable(self):
        event = self.event(identifier="native-source-first")
        _, request = await self.bind(event)
        evidence = await self.call(event, request, "turn.evidence", {})
        second = self.event(identifier="native-source-second")
        _, second_request = await self.bind(second)
        result = await self.call(second, second_request, "source.read",
            {"handle": evidence["evidence_handles"][0]})
        self.assertEqual(result["code"], "tool_source_unavailable", result)
        self.assert_no_reply_work()

    async def test_design_explanation_and_actual_inspection_use_the_existing_owner(self):
        event = self.event(identifier="native-diagnostic-tools")
        _, request = await self.bind(event)
        explanation = await self.call(event, request, "diagnostics.explain", {"topic": "capability"})
        self.assertEqual(explanation["state"], "succeeded", explanation)
        self.assertEqual(explanation["report"]["mode"], "explain", explanation)
        self.assertEqual(explanation["report"]["results"], [], explanation)
        query = DiagnosticQuery(execution=True).document()
        inspected = await self.call(event, request, "diagnostics.inspect", {"query": query})
        self.assertEqual(inspected["state"], "succeeded", inspected)
        self.assertEqual(inspected["report"]["mode"], "self_check", inspected)
        self.assertTrue(inspected["report"]["results"], inspected)
        replay = await self.call(event, request, "diagnostics.inspect", {"query": query})
        self.assertTrue(replay["replayed"], replay)
        self.assertEqual(replay["report"]["report_id"], inspected["report"]["report_id"])
        self.assert_no_reply_work()

    async def test_expired_diagnostic_report_is_not_replaced_during_replay(self):
        event = self.event(identifier="native-diagnostic-expiry")
        _, request = await self.bind(event)
        explanation = await self.call(event, request, "diagnostics.explain", {"topic": "operation"})
        self.assertEqual(explanation["state"], "succeeded", explanation)
        self.clock.advance(timedelta(minutes=2))
        expired = await self.call(event, request, "diagnostics.explain", {"topic": "operation"})
        self.assertEqual(expired["code"], "diagnostic_report_expired", expired)
        self.assertNotIn("report", expired)
        self.assert_no_reply_work()

    async def test_invalid_arguments_return_failure_and_partial_query_uses_defaults(self):
        event = self.event(identifier="native-diagnostic-arguments")
        _, request = await self.bind(event)
        for action, arguments in (("source.read", {"handle": []}),
                                  ("diagnostics.explain", {"topic": []}),
                                  ("diagnostics.inspect", {"query": {"window": {}}})):
            result = await self.call(event, request, action, arguments, "invalid-" + action)
            self.assertEqual(result["code"], "invalid_tool_arguments", result)
        denied = await self.call(event, request, "diagnostics.inspect", {"query": {"extension_id": "content"}})
        self.assertEqual(denied["code"], "authorization_denied", denied)
        self.assertNotIn("report", denied)
        result = await self.call(event, request, "diagnostics.inspect", {"query": {"execution": True}}, "inspect-local-execution")
        self.assertEqual(result["state"], "succeeded", result)
        self.assert_no_reply_work()


if __name__ == "__main__":
    unittest.main()
