"""Cached tool originals are rechecked at actual model I/O and after its receipt."""

import asyncio
from dataclasses import replace
import unittest

from companion_v2.conversation.foreground import ModelDraft, PromptMaterial
from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.model_gateway.models import Amount, ProviderResponse
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import SourceRepository
from tests.test_management_access import NOW
from tests.test_model_gateway import ModelFixture


class ModelSourceFenceTests(ModelFixture, unittest.IsolatedAsyncioTestCase):
    def cached_request(self):
        request = self.request()
        self.tool_source = SourceRef("tool-source", "tool.owner", self.context.scope, VersionRef("tool-source", 1), NOW)
        self.sources = SourceRepository(self.runtime)
        self.sources.publish(SourceRecord(self.tool_source, self.context.audience, digest("original tool body"),
                                        "original tool body"), observed_at=NOW).unwrap()
        return replace(request, context=replace(request.context, materials=(*request.context.materials,
            PromptMaterial("tool.owner", "tool_source:read", "original tool body", self.tool_source))))

    def withdraw(self):
        self.sources.revoke(self.tool_source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()

    async def test_withdrawn_cached_tool_source_prevents_model_call(self):
        request = self.cached_request()
        self.withdraw()
        with self.assertRaises(TaskError) as caught:
            await self.gateway.generate(self.model_run(), request)
        self.assertEqual(caught.exception.code, "source_revoked")
        self.assertEqual(self.called, [])
        self.assertEqual(self.call_rows(), ())

    async def test_waiting_adapter_rechecks_cached_tool_source_before_actual_io(self):
        entered, release = asyncio.Event(), asyncio.Event()
        dispatched = []
        async def waiting(envelope):
            entered.set()
            await release.wait()
            envelope.before_dispatch()
            dispatched.append(envelope)
            return ProviderResponse("generated", ModelDraft("late", ()), Amount(15, 40), "late-receipt")
        self.responses["primary"] = waiting
        work = asyncio.create_task(self.gateway.generate(self.model_run(), self.cached_request()))
        await asyncio.wait_for(entered.wait(), 1)
        self.withdraw()
        release.set()
        with self.assertRaises(TaskError):
            await work
        self.assertEqual(dispatched, [])
        self.assertEqual(len(self.called), 1)

    async def test_late_generated_receipt_keeps_actual_usage_and_discards_draft(self):
        async def completed(envelope):
            envelope.before_dispatch()
            self.withdraw()
            return ProviderResponse("generated", ModelDraft("late body", ()), Amount(15, 40), "real-model-receipt")
        self.responses["primary"] = completed
        with self.assertRaises(TaskError) as caught:
            await self.gateway.generate(self.model_run(), self.cached_request())
        self.assertEqual(caught.exception.code, "source_revoked")
        row = self.call_rows()[0]
        self.assertEqual((row["actual_tokens"], row["actual_cost"]), (15, 40))
        self.assertEqual(row["receipt_ref"], "real-model-receipt")
        self.assertEqual(row["state"], "discarded")
        self.assertEqual(len(self.called), 1)


if __name__ == "__main__":
    unittest.main()
