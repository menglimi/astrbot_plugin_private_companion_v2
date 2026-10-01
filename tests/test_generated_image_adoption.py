"""Real executor accounting when native image output cannot be adopted."""

from dataclasses import replace
import json
import unittest

from companion_v2.conversation.media.generated import OWNER, REJECTED_ADOPTION
from companion_v2.conversation.media.models import ImageConversationEvent
from companion_v2.conversation.messages import source_from_document
from companion_v2.execution.models import TaskError, digest, encode
from companion_v2.sources.models import GovernanceState
from tests.test_generated_image_sources import capture
from tests.test_group_native_image_tools import GroupImageToolFixture, call
from tests.test_management_access import NOW


class GeneratedImageAdoptionTests(GroupImageToolFixture, unittest.IsolatedAsyncioTestCase):
    def image_event(self, count):
        incoming = tuple(capture("green", position) for position in range(count))
        event = ImageConversationEvent(**vars(self.event("input-images")), images=tuple(i.descriptor for i in incoming))
        self.messages.images.publish(self.context, event, incoming)
        return event

    def generated_count(self, table="conversation_image_payloads"):
        if table == "sources":
            return self.runtime.read_one("SELECT COUNT(*) FROM sources WHERE owner = ?", (OWNER,))[0]
        return self.runtime.read_one("SELECT COUNT(*) FROM conversation_image_payloads WHERE parent_id LIKE 'generated-images-%'", ())[0]

    def assert_receipt(self, row, response):
        self.assertEqual((row["state"], row["effect"], row["operation_id"], row["receipt_ref"]),
                         ("succeeded", "committed", response.operation_id, response.receipt_ref))

    async def test_full_original_input_preserves_continuation_without_dispatch(self):
        self.model_uses(call())
        batch = await self.generate(self.image_event(8))
        self.assertEqual(self.invocations, [])
        self.assertEqual(self.rows(), ())
        result = json.loads(self.tools._rows(batch)[0]["result_json"])
        self.assertEqual(result, {"state": "failed", "effect": "not_committed", "code": "image_turn_limit"})
        self.assertEqual(len(self.called), 2)
        self.assertEqual(len(self.called[-1][1].original.images), 8)
        self.assertEqual(self.called[-1][1].original.images, self.called[0][1].original.images)
        self.assertEqual(self.generated_count(), 0)

    async def test_earlier_generated_image_uses_the_last_slot_before_next_dispatch(self):
        self.model_uses(call(), call("image.edit", "second-image-operation"))
        batch = await self.generate(self.image_event(7))
        self.assertEqual(len(self.invocations), 1)
        self.assertEqual(len(self.rows()), 1)
        results = [json.loads(row["result_json"]) for row in self.tools._rows(batch)]
        self.assertEqual(results[0]["image_adoption"], {"state": "available", "code": None})
        self.assertEqual(results[1], {"state": "failed", "effect": "not_committed", "code": "image_turn_limit"})
        self.assertEqual(len(self.called[-1][1].original.images), 8)
        self.assertEqual(self.generated_count(), 1)

    async def test_success_over_remaining_budget_retains_receipt_and_no_new_sendable_image(self):
        response = None

        async def provider(invocation):
            nonlocal response
            response = replace(self.response(invocation), images=(capture(), capture("blue", 1)))
            return response

        self.provider_behavior = provider
        self.model_uses(call())
        self.messages.reply_images.enabled = True
        batch = await self.generate(self.image_event(7))
        self.assertEqual(len(self.invocations), 1)
        row = self.rows()[0]
        self.assert_receipt(row, response)
        result, material = self.external.snapshot(row, self.context, NOW)
        self.assertEqual(result["image_adoption"], {"state": "unavailable", "code": "image_turn_limit"})
        self.assertIsNotNone(material)
        self.assertEqual(json.loads(self.called[-1][1].tool_history[0].result_json), result)
        self.assertEqual(len(self.called[-1][1].original.images), 7)
        self.assertEqual(self.called[-1][1].original.images, self.called[0][1].original.images)
        self.assertEqual(self.messages.generated_images.read_batch(batch, self.context, NOW), ())
        self.assertEqual(self.generated_count(), 0)
        self.assertEqual(self.generated_count("sources"), 1)
        manifest = self.messages.generated_images.reference(row, self.context)
        saved = json.loads(self.messages._read_source(manifest, self.context, "text", NOW).payload)
        self.assertEqual(saved["image_adoption"], result["image_adoption"])
        # These are offered descriptors for the accounting decision; no image
        # source, asset, body or sendable handle was published from either one.
        self.assertEqual(len(saved["images"]), 2)
        self.messages.withdraw(self.context, self.image_event_key(batch)).unwrap()
        self.assertEqual(self.messages.sources.validate_reference(manifest, observed_at=NOW).failure.code, "source_revoked")

    def image_event_key(self, batch):
        return self.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))[0]

    async def test_withdrawal_after_provider_success_keeps_real_receipt_and_no_image(self):
        batch, run, completion = await self.stage()
        response = None

        async def provider(invocation):
            nonlocal response
            response = self.response(invocation)
            self.messages.withdraw(self.context, self.image_event_key(batch)).unwrap()
            return response

        self.provider_behavior = provider
        with self.assertRaises(TaskError):
            await self.tools.execute_async(run, completion.call_id, completion.tool_calls[0])
        row = self.rows()[0]
        self.assert_receipt(row, response)
        self.assertEqual(row["error_code"], REJECTED_ADOPTION + "message_withdrawn")
        reference = source_from_document(json.loads(row["result_source_json"]))
        self.assertEqual(self.messages.sources.validate_reference(reference, observed_at=NOW).failure.code, "source_revoked")
        self.assertEqual(self.generated_count(), 0)
        self.assertEqual(self.generated_count("sources"), 0)
        self.assertEqual(self.sent, [])
        with self.assertRaises(TaskError):
            self.messages.generated_images.read_batch(batch, self.context, NOW)
        self.assertEqual(len(self.invocations), 1)

    async def test_consent_revoked_during_io_cannot_revive_adoption_after_regrant(self):
        batch, run, completion = await self.stage()
        response = None

        async def provider(invocation):
            nonlocal response
            response = self.response(invocation)
            self.consent("image.generate", active=False, revision=1)
            return response

        self.provider_behavior = provider
        with self.assertRaises(TaskError):
            await self.tools.execute_async(run, completion.call_id, completion.tool_calls[0])
        row = self.rows()[0]
        self.assert_receipt(row, response)
        self.assertEqual(row["error_code"], REJECTED_ADOPTION + "capability_consent_revoked")
        self.consent("image.generate", active=True, revision=2)
        self.external.reconcile(self.context, row["invocation_id"]).unwrap()
        result, material = self.external.snapshot(row, self.context, NOW)
        self.assertEqual(result["image_adoption"], {"state": "unavailable", "code": "capability_consent_revoked"})
        self.assertIsNone(material)
        self.assertEqual(self.messages.generated_images.read_batch(batch, self.context, NOW), ())
        self.assertEqual(self.generated_count(), 0)
        self.assertEqual(self.generated_count("sources"), 0)
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.invocations), 1)

    async def test_native_revoked_source_without_images_is_receipt_only(self):
        response = None

        async def provider(invocation):
            nonlocal response
            original = self.response(invocation)
            payload = encode({"native": {"operation_id": original.operation_id},
                              "adoption": {"state": "unavailable", "code": "native_provider_changed"}})
            source = replace(original.source, payload=payload, content_hash=digest(payload), state=GovernanceState.REVOKED)
            response = replace(original, source=source, images=())
            return response

        self.provider_behavior = provider
        self.model_uses(call())
        batch = await self.generate()
        row = self.rows()[0]
        self.assert_receipt(row, response)
        result, material = self.external.snapshot(row, self.context, NOW)
        self.assertEqual(result["image_adoption"], {"state": "unavailable", "code": "native_provider_changed"})
        self.assertIsNone(material)
        self.assertEqual(self.messages.generated_images.read_batch(batch, self.context, NOW), ())
        self.assertEqual(self.generated_count(), 0)
        self.assertEqual(self.generated_count("sources"), 0)
        self.assertEqual(len(self.called), 2)
        self.assertEqual(self.called[-1][1].original.images, ())
        self.assertFalse(any(m.owner == "fixture.image" for m in self.called[-1][1].original.context.materials))
        self.assertEqual(self.sent, [])

    async def test_receipt_only_predecessor_does_not_lose_a_later_successful_receipt(self):
        responses = []

        async def provider(invocation):
            response = self.response(invocation)
            if not responses:
                payload = encode({"adoption": {"state": "unavailable", "code": "native_artifact_changed"}})
                source = replace(response.source, payload=payload, content_hash=digest(payload), state=GovernanceState.REVOKED)
                response = replace(response, source=source, images=())
            responses.append(response)
            return response

        self.provider_behavior = provider
        self.model_uses(call(), call("image.edit", "second-image-operation"))
        batch = await self.generate()
        rows = {row["invocation_id"]: row for row in self.rows()}
        for response in responses:
            self.assert_receipt(rows[response.invocation_id], response)
        self.assertEqual(len(responses), 2)
        images = self.messages.generated_images.read_batch(batch, self.context, NOW)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].descriptor, responses[1].images[0].descriptor)
        self.assertEqual(self.generated_count(), 1)
        self.assertEqual(self.generated_count("sources"), 1)
        rejected = responses[0].source.reference
        self.assertEqual(self.messages.sources.validate_reference(rejected, observed_at=NOW).failure.code, "source_revoked")
        references = self.runtime.read_all("SELECT input_id FROM source_dependencies WHERE dependent_id = ?",
                                          (images[0].parent.source_id,))
        self.assertNotIn(rejected.source_id, [row[0] for row in references])
        manifest = json.loads(self.messages._read_source(images[0].parent, self.context, "text", NOW).payload)
        self.assertEqual(manifest["previous"], [{"invocation_id": responses[0].invocation_id,
                                               "result_hash": rows[responses[0].invocation_id]["result_hash"]}])
        self.assertEqual(len(self.called[-1][1].original.images), 1)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
