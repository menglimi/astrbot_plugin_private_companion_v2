"""External result dependencies retain their audience and publish atomically."""

from dataclasses import replace
import unittest

from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.refs import SourceRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.sources.models import SourceRecord
from tests.test_external_tools import ExternalFixture, tool_call


class ExternalSourceDependencyTests(ExternalFixture, unittest.IsolatedAsyncioTestCase):
    def input_source(self, *, scope=None, audience=None):
        reference = SourceRef("original-input", "input.owner", scope or self.context.scope,
                              VersionRef("original-input", 1), self.clock.now())
        self.messages.sources.publish(SourceRecord(reference, audience or self.context.audience,
            digest("original"), "original"), observed_at=self.clock.now()).unwrap()
        return reference

    async def invoke_once(self, reference, *, withdraw=False, unreadable=False):
        async def operation(invocation):
            if withdraw:
                self.messages.sources.revoke(reference, expected_governance_revision=1,
                                             observed_at=self.clock.now()).unwrap()
            return self.response(invocation, dependencies=(reference,))
        self.extension_behavior = operation
        _, run, completion = await self.stage(tool_call(effectful=True))
        if withdraw or unreadable:
            with self.assertRaises(TaskError) as caught:
                await self.tools.execute_async(run, completion.call_id, completion.tool_calls[0])
            self.assertEqual(caught.exception.code, "source_revoked")
        else:
            await self.tools.execute_async(run, completion.call_id, completion.tool_calls[0])
        return self.rows()[0]

    async def test_published_result_inherits_original_withdrawal(self):
        reference = self.input_source()
        row = await self.invoke_once(reference)
        self.assertEqual(row["state"], "succeeded")
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM source_dependencies", ())), 1)
        self.messages.sources.revoke(reference, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.assertEqual(self.runtime.read_one("SELECT state FROM sources WHERE owner='device'", ())[0], "revoked")

    async def test_late_withdrawal_retains_committed_receipt_without_readable_material(self):
        row = await self.invoke_once(self.input_source(), withdraw=True)
        self.assertEqual((row["state"], row["effect"]), ("succeeded", "committed"))
        self.assertIsNotNone(row["receipt_ref"])
        self.assertEqual(self.runtime.read_one("SELECT state FROM sources WHERE owner='device'", ())[0], "revoked")
        self.assertEqual(self.runtime.read_all("SELECT * FROM source_dependencies", ()), ())

    async def test_result_cannot_broaden_dependency_audience(self):
        other = SubjectRef(self.context.scope.installation_id, SubjectKind.HUMAN, "someone-else")
        audience = replace(self.context.audience, recipients=(other,))
        row = await self.invoke_once(self.input_source(audience=audience), unreadable=True)
        self.assertEqual((row["state"], row["effect"]), ("succeeded", "committed"))
        self.assertEqual(self.runtime.read_one("SELECT state FROM sources WHERE owner='device'", ())[0], "revoked")
        self.assertEqual(self.runtime.read_all("SELECT * FROM source_dependencies", ()), ())

    async def test_other_scope_dependency_is_rejected_before_publication(self):
        scope = replace(self.context.scope, session_id="different-session")
        row = await self.invoke_once(self.input_source(scope=scope, audience=replace(self.context.audience, scope=scope)))
        self.assertEqual(row["state"], "unknown")
        self.assertEqual(self.runtime.read_all("SELECT * FROM sources WHERE owner='device'", ()), ())

    async def test_dependency_storage_failure_rolls_back_result_publication(self):
        reference = self.input_source()
        with self.runtime.transaction() as connection:
            connection.execute("""CREATE TRIGGER reject_link BEFORE INSERT ON source_dependencies
                BEGIN SELECT RAISE(ABORT, 'dependency storage fault'); END""")
        row = await self.invoke_once(reference)
        self.assertEqual(row["state"], "unknown")
        self.assertEqual(self.runtime.read_all("SELECT * FROM sources WHERE owner='device'", ()), ())
        self.assertEqual(self.runtime.read_all("SELECT * FROM source_dependencies", ()), ())


if __name__ == "__main__":
    unittest.main()
