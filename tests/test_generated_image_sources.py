"""Native image-source governance using real V2 storage and a bounded owner stub."""

import base64
from dataclasses import replace
import hashlib
import io
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from PIL import Image

from companion_v2.capabilities.models import CapabilityPackageDescriptor
from companion_v2.conversation.external_tools import ExtensionToolDescriptor, ExternalToolInvocation
from companion_v2.conversation.foreground import ContextContribution, ContributionState, PromptMaterial
from companion_v2.conversation.media.generated import GeneratedImages, GeneratedImageView, INSTRUCTION, OWNER
from companion_v2.conversation.media.models import CapturedImage, ImageDescriptor, ImageConversationEvent
from companion_v2.conversation.messages import source_from_document
from companion_v2.conversation.models import InboundConversationEvent
from companion_v2.execution.models import ProviderBinding, SideEffect, TaskContext, TaskError, digest, encode, stamp
from companion_v2.execution.runner import TaskRun
from companion_v2.foundation.refs import AssetRef, ScopeKind, SourceRef, VersionRef
from companion_v2.identity_policy.group_audience import group_audience
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.model_gateway.models import ToolSpec
from companion_v2.model_gateway.routing import ModelRouter
from companion_v2.model_gateway.service import LocalModelGateway
from companion_v2.sources.dependencies import key
from companion_v2.sources.models import SourceRecord
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import NOW


def capture(color="red", position=0):
    stream = io.BytesIO()
    Image.new("RGB", (3, 2), color).save(stream, "PNG")
    content = stream.getvalue()
    return CapturedImage(ImageDescriptor(position, "image/png", 3, 2, len(content), hashlib.sha256(content).hexdigest()), content)


def descriptor(action="image.generate"):
    package = CapabilityPackageDescriptor("image", "image-package", "fixture", "2", "native-image-package",
                                         ("image.generate", "image.edit"), ("image.native",))
    return ExtensionToolDescriptor(ToolSpec(action, "Return one native image original.", encode({
        "type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"],
        "additionalProperties": False})), package, ProviderBinding(action, "image.native", "2", "instance-1"),
        "image.native", SideEffect.EXTERNAL_NETWORK)


class SnapshotOwner:
    """The executor's public read contract; no SDK, V1, provider I/O or generation."""
    def __init__(self, messages):
        self.messages = messages
        self.code = None
        self.calls = []

    def snapshot(self, row, context, at):
        self.calls.append(row["invocation_id"])
        if self.code:
            raise TaskError(self.code, "the original provider is no longer admitted")
        if row["state"] != "succeeded":
            return {"state": "unknown"}, None
        reference = source_from_document(json.loads(row["result_source_json"]))
        source = self.messages._read_source(reference, context, "text", at)
        if digest(source) != row["result_hash"]:
            raise TaskError("tool_result_changed", "provider result does not match its saved hash")
        return {"state": "succeeded"}, PromptMaterial(reference.owner, "tool_source:" + row["tool_call_id"], source.payload, reference)


class GeneratedImageSourceFixture(MessageFixture):
    def setUp(self):
        super().setUp()
        self.providers = tuple(replace(p, capabilities=("text", "image", "tools")) for p in self.providers)
        self.router = ModelRouter(self.configuration, self.profiles, self.providers)
        self.router.start(expected_generation=2)
        self.gateway = LocalModelGateway(self.router, self.ledger, self.tasks)
        self.generated = GeneratedImages(self.messages)
        self.owner = SnapshotOwner(self.messages)
        self.messages.tools = NS(external=self.owner)
        self.sequence = 0
        self.stages = {}
        self.sessions = {}

    async def prepare(self, *, action="image.generate", images=None, batch=None, event=None, contributions=()):
        if batch is None:
            event = event or self.event("image-request-" + str(self.sequence))
            batch = self.accept(event)
            task = self.messages.seal(self.context, batch, deadline_at=self.deadline, contributions=contributions).unwrap()
            claim = self.tasks.claim_task(self.context, task.task_id).unwrap().claim
            run = TaskRun(self.tasks, claim, self.tasks.begin(claim).unwrap())
            request = self.messages.request(run, include_tools=False)
            session = self.gateway.open_session(run, request, tools=(descriptor(action).tool,))
            completion = await session.generate(request)
            self.stages[batch] = (run, completion.call_id, event)
            self.sessions[batch] = session
        run, call_id, event = self.stages[batch]
        self.sequence += 1
        identifier = "native-image-" + str(self.sequence)
        desc = descriptor(action)
        invocation = ExternalToolInvocation(identifier, run.task.task_id, "tool-" + identifier, self.context,
                                            desc, encode({"prompt": "生成测试图"}), self.deadline)
        source = SourceRef("result-" + identifier, desc.source_owner, self.context.scope, VersionRef(identifier, 1), NOW)
        body = encode({"operation_id": "operation-" + identifier, "result": {"created": True}})
        response = NS(invocation_id=identifier, origin_key=self.context.key, arguments_hash=invocation.arguments_hash,
            binding=desc.binding, state="succeeded", effect="committed", source=SourceRecord(source, self.context.audience, digest(body), body),
            operation_id="operation-" + identifier, receipt_ref="receipt-" + identifier,
            images=images if images is not None else (capture(),))
        with self.runtime.transaction() as connection:
            sequence = connection.execute("SELECT COUNT(*) FROM conversation_tool_calls WHERE batch_id = ?", (batch,)).fetchone()[0] + 1
            connection.execute("""INSERT INTO conversation_tool_calls(task_id,tool_call_id,batch_id,sequence,model_call_id,
                attempt_id,action,arguments_json,state,effect,created_at) VALUES(?,?,?,?,?,?,?,?,'started','unknown',?)""",
                (run.task.task_id, invocation.tool_call_id, batch, sequence, call_id, run.claim.attempt_id,
                 action, invocation.arguments_json, stamp(NOW)))
            connection.execute("""INSERT INTO extension_tool_invocations(invocation_id,parent_task_id,tool_call_id,batch_id,
                task_id,action,descriptor_json,provider_json,arguments_json,state,effect,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,'running','unknown',?)""", (identifier, run.task.task_id, invocation.tool_call_id,
                batch, "child-" + identifier, action, encode(desc), encode(desc.binding), invocation.arguments_json, stamp(NOW)))
        return batch, event, invocation, response

    def publish(self, invocation, response):
        with self.runtime.transaction() as connection:
            self.messages.sources.publish(response.source, observed_at=NOW).unwrap()
            reference = self.generated.accept(invocation, response)
            connection.execute("""UPDATE extension_tool_invocations SET state='succeeded',effect=?,operation_id=?,receipt_ref=?,
                result_source_json=?,result_hash=?,finished_at=? WHERE invocation_id=?""", (response.effect,
                response.operation_id, response.receipt_ref, encode(response.source.reference), digest(response.source),
                stamp(NOW), invocation.invocation_id))
            return reference

    def read(self, batch):
        return self.generated.read_batch(self.messages.batch(batch), self.context, NOW)

    def count(self, table):
        return self.runtime.read_one(f"SELECT COUNT(*) FROM {table}", ())[0]


class GeneratedImageSourceTests(GeneratedImageSourceFixture, unittest.IsolatedAsyncioTestCase):
    async def test_success_preserves_order_operation_provenance_and_does_not_create_user_inputs(self):
        batch, _, invocation, response = await self.prepare(images=(capture(), capture("blue", 3)))
        self.publish(invocation, response)
        evidence = []
        images = self.generated.read_batch(batch, self.context, NOW, evidence=evidence)
        self.assertEqual([base64.b64decode(i.data_base64) for i in images], [i.content for i in response.images])
        self.assertEqual([i.descriptor.position for i in images], [0, 3])
        self.assertEqual(self.count("conversation_inputs"), 1)
        self.assertEqual(self.count("conversation_parts"), 0)
        materials = [c for image in images for c in self.generated.contributions(image)]
        self.assertEqual([c.owner for c in materials], [OWNER, "conversation.image", "conversation.image"])
        data = json.loads(materials[1].payload)
        self.assertTrue(data["generated"])
        self.assertFalse(data["edited"])
        self.assertIsNone(data["sender"])
        self.assertEqual(data["provider_operation"]["operation_id"], response.operation_id)
        self.assertNotIn(base64.b64encode(response.images[0].content).decode("ascii"), encode([c.payload for c in materials]))
        self.assertIn(response.source.reference, evidence)
        self.assertIn(images[0].source, evidence)
        self.assertFalse(issubclass(GeneratedImageView, InboundConversationEvent))

    async def test_only_explicit_edit_action_marks_edited(self):
        batch, _, invocation, response = await self.prepare(action="image.edit")
        self.publish(invocation, response)
        metadata = json.loads(self.generated.contributions(self.read(batch)[0])[-1].payload)
        self.assertTrue(metadata["edited"])
        self.assertEqual(metadata["provider_operation"]["action"], "image.edit")

    async def test_duplicate_is_identical_and_conflicting_image_or_receipt_cannot_replace(self):
        batch, _, invocation, response = await self.prepare()
        reference = self.publish(invocation, response)
        self.assertEqual(self.generated.accept(invocation, response), reference)
        for changes in ({"images": (capture("blue"),)}, {"receipt_ref": "replacement-receipt"},
                        {"operation_id": "replacement-operation"}):
            with self.subTest(changes=tuple(changes)):
                with self.assertRaises(TaskError):
                    self.generated.accept(invocation, NS(**{**vars(response), **changes}))
        self.assertEqual(base64.b64decode(self.read(batch)[0].data_base64), response.images[0].content)
        self.assertEqual(self.count("conversation_image_payloads"), 1)

    async def test_outer_transaction_rolls_back_result_manifest_asset_and_bytes(self):
        _, _, invocation, response = await self.prepare()
        counts = {table: self.count(table) for table in ("sources", "assets", "conversation_image_payloads", "source_dependencies")}
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with self.runtime.transaction():
                self.publish(invocation, response)
                raise RuntimeError("rollback")
        self.assertEqual({table: self.count(table) for table in counts}, counts)
        row = self.runtime.read_one("SELECT state, result_source_json FROM extension_tool_invocations", ())
        self.assertEqual(tuple(row), ("running", None))

    async def test_unknown_and_failed_receipts_never_publish_images(self):
        batch, _, invocation, response = await self.prepare()
        for state in ("unknown", "failed"):
            with self.subTest(state=state):
                with self.assertRaises(TaskError) as caught:
                    self.generated.accept(invocation, NS(**{**vars(response), "state": state}))
                self.assertEqual(caught.exception.code, "generated_image_receipt")
        self.assertEqual(self.read(batch), ())
        self.assertEqual(self.count("conversation_image_payloads"), 0)
        self.assertEqual(self.count("assets"), 0)

    async def test_mixed_order_and_animation_are_rejected_before_publication(self):
        _, _, invocation, response = await self.prepare()
        with self.assertRaises(TaskError) as caught:
            self.generated.accept(invocation, NS(**{**vars(response), "images": (capture(position=1), capture("blue", 0))}))
        self.assertEqual(caught.exception.code, "image_manifest_invalid")
        from companion_v2.conversation.media.animation import AnimationDescriptor, CapturedAnimation, FrameDescriptor
        frame = capture()
        animation = AnimationDescriptor(0, "image/png", 3, 2, len(frame.content), frame.descriptor.content_hash,
                                       1, 100, 0, False, (FrameDescriptor(0, 0, 100, frame.descriptor),))
        with self.assertRaises(TaskError) as caught:
            self.generated.accept(invocation, NS(**{**vars(response), "images": (CapturedAnimation(animation, frame.content, (frame,)),)}))
        self.assertEqual(caught.exception.code, "generated_image_manifest")
        self.assertEqual(self.count("conversation_image_payloads"), 0)

    async def test_another_context_and_source_audience_are_rejected(self):
        batch, _, invocation, response = await self.prepare()
        self.publish(invocation, response)
        other = self.context_for(self.standard)
        self.grant(self.standard, other.scope, "conversation.reply")
        self.grant(self.standard, other.scope, "text")
        with self.assertRaises(TaskError):
            self.generated.read_batch(batch, other, NOW)
        source = replace(response.source, reference=replace(response.source.reference, scope=other.scope), audience=other.audience)
        with self.assertRaises(TaskError) as caught:
            self.generated.accept(invocation, NS(**{**vars(response), "source": source}))
        self.assertEqual(caught.exception.code, "generated_image_context")

    async def test_withdrawal_revokes_generated_sources_and_reopen_keeps_original_bytes(self):
        batch, event, invocation, response = await self.prepare()
        self.publish(invocation, response)
        original = self.read(batch)[0]
        _, messages, _ = self.components(self.open_runtime())
        owner = SnapshotOwner(messages)
        messages.tools = NS(external=owner)
        generated = GeneratedImages(messages)
        self.assertEqual(generated.read_batch(batch, self.context, NOW)[0], original)
        self.messages.withdraw(self.context, event.scoped_key).unwrap()
        self.assertEqual(messages.sources.validate_reference(original.source, observed_at=NOW).failure.code, "source_revoked")
        with self.assertRaises(TaskError):
            generated.read_batch(batch, self.context, NOW)

    async def test_asset_revocation_and_byte_corruption_block_reuse(self):
        batch, _, invocation, response = await self.prepare()
        self.publish(invocation, response)
        image = self.read(batch)[0]
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE conversation_image_payloads SET content = ?", (b"corrupted",))
        with self.assertRaises(TaskError) as caught:
            self.read(batch)
        self.assertEqual(caught.exception.code, "image_content_changed")
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE conversation_image_payloads SET content = ?", (response.images[0].content,))
        asset = AssetRef(image.source.source_id, image.source.owner, image.source.scope, image.source.version, image.descriptor.content_hash)
        self.messages.images.assets.revoke(asset, expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(TaskError) as caught:
            self.read(batch)
        self.assertEqual(caught.exception.code, "asset_revoked")

    async def test_input_image_asset_remains_a_live_dependency(self):
        event = self.event("edit-original")
        incoming = capture("green")
        event = ImageConversationEvent(**vars(event), images=(incoming.descriptor,))
        self.messages.images.publish(self.context, event, (incoming,))
        batch, _, invocation, response = await self.prepare(event=event, action="image.edit")
        self.publish(invocation, response)
        self.assertEqual(len(self.read(batch)), 1)
        _, asset = self.messages.images.references(event, incoming.descriptor)
        self.messages.images.assets.revoke(asset, expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(TaskError) as caught:
            self.read(batch)
        self.assertEqual(caught.exception.code, "asset_revoked")

    async def test_provider_change_revoke_or_unresolved_child_never_exposes_bytes(self):
        batch, _, invocation, response = await self.prepare()
        self.publish(invocation, response)
        for code in ("external_provider_changed", "external_package_changed", "capability_role_not_enabled", "capability_not_admissible"):
            with self.subTest(code=code):
                self.owner.code = code
                evidence = []
                with self.assertRaises(TaskError) as caught:
                    self.generated.read_batch(batch, self.context, NOW, evidence=evidence)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(evidence, [])
        self.owner.code = None
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE extension_tool_invocations SET state='unknown'")
        with self.assertRaises(TaskError) as caught:
            self.read(batch)
        self.assertEqual(caught.exception.code, "generated_image_unresolved")

    async def test_result_hash_and_manifest_identity_are_verified(self):
        batch, _, invocation, response = await self.prepare()
        reference = self.publish(invocation, response)
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE extension_tool_invocations SET result_hash='changed'")
        with self.assertRaises(TaskError) as caught:
            self.read(batch)
        self.assertEqual(caught.exception.code, "tool_result_changed")
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE extension_tool_invocations SET result_hash=?", (digest(response.source),))
            connection.execute("UPDATE sources SET content_hash='changed' WHERE source_id=?", (reference.source_id,))
        with self.assertRaises(TaskError) as caught:
            self.read(batch)
        self.assertEqual(caught.exception.code, "generated_image_changed")

    async def test_missing_manifest_does_not_silently_become_a_text_result(self):
        batch, _, invocation, response = await self.prepare()
        reference = self.publish(invocation, response)
        with self.runtime.transaction() as connection:
            connection.execute("DELETE FROM conversation_image_payloads WHERE parent_id=?", (reference.source_id,))
            connection.execute("DELETE FROM source_dependencies WHERE dependent_id=? OR input_id=?",
                               (reference.source_id, reference.source_id))
            connection.execute("DELETE FROM sources WHERE source_id=?", (reference.source_id,))
        with self.assertRaises(TaskError) as caught:
            self.read(batch)
        self.assertEqual(caught.exception.code, "generated_image_unavailable")

    async def test_saved_evidence_and_previous_provider_results_are_linked(self):
        extra = self.event("referenced-source").source
        contribution = ContextContribution("fixture-material", "conversation", "reference", ContributionState.READY,
                                           "bound source", extra, True)
        batch, _, first, response = await self.prepare(contributions=(contribution,))
        first_manifest = self.publish(first, response)
        _, _, second, another = await self.prepare(batch=batch, images=(capture("blue"),))
        second_manifest = self.publish(second, another)
        self.assertEqual(len(self.read(batch)), 2)
        links = self.runtime.read_all("SELECT input_id,input_lineage,input_revision FROM source_dependencies WHERE dependent_id=?",
                                     (second_manifest.source_id,))
        self.assertIn(key(response.source.reference), [tuple(row) for row in links])
        self.assertIn(key(extra), [tuple(row) for row in links])
        self.messages.sources.revoke(extra, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertEqual(self.messages.sources.validate_reference(first_manifest, observed_at=NOW).failure.code, "source_revoked")
        with self.assertRaises(TaskError):
            self.read(batch)

    async def test_refresh_accepts_only_this_batchs_governed_images_and_matching_contributions(self):
        batch, _, invocation, response = await self.prepare()
        original = self.messages._request(self.messages.batch(batch), self.context, NOW, include_tools=False)
        self.messages.reply_images.enabled = True
        self.publish(invocation, response)
        images = self.read(batch)
        materials = tuple(PromptMaterial(c.owner, c.purpose, c.payload, c.source)
                          for image in images for c in self.generated.contributions(image))
        current = replace(original, images=images, reply_images=True, instruction=original.instruction + "\n" + INSTRUCTION,
                          context=replace(original.context, materials=original.context.materials + materials))
        self.assertTrue(self.generated.validate_refresh(batch, self.context, NOW, original, current))
        self.assertFalse(self.generated.validate_refresh(batch, self.context, NOW, original, replace(current, reply_images=False)))
        changed = tuple(replace(m, payload="unproven attribution") if m.source == images[0].source else m for m in current.context.materials)
        self.assertFalse(self.generated.validate_refresh(batch, self.context, NOW, original,
                                                        replace(current, context=replace(current.context, materials=changed))))
        with patch.object(self.messages, "_request", side_effect=AssertionError("do not compile history")):
            self.assertEqual(self.read(batch), images)

    async def test_non_image_action_cannot_publish_generated_artifacts(self):
        _, _, invocation, response = await self.prepare()
        desc = replace(invocation.descriptor, tool=replace(invocation.descriptor.tool, action="image.inspect"))
        with self.assertRaises(TaskError) as caught:
            self.generated.accept(replace(invocation, descriptor=desc), response)
        self.assertEqual(caught.exception.code, "generated_image_action")
        self.assertEqual(self.count("conversation_image_payloads"), 0)

    async def test_original_model_call_order_cannot_be_changed_after_acceptance(self):
        batch, _, invocation, response = await self.prepare()
        self.publish(invocation, response)
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE conversation_tool_calls SET sequence=2")
        with self.assertRaises(TaskError) as caught:
            self.read(batch)
        self.assertEqual(caught.exception.code, "generated_image_changed")

    async def test_missing_original_bytes_does_not_return_a_handle(self):
        batch, _, invocation, response = await self.prepare()
        self.publish(invocation, response)
        with self.runtime.transaction() as connection:
            connection.execute("DELETE FROM conversation_image_payloads")
        with self.assertRaises(TaskError) as caught:
            self.read(batch)
        self.assertEqual(caught.exception.code, "image_original_unavailable")

    async def test_deferred_material_does_not_become_generator_evidence(self):
        extra = self.event("deferred-source").source
        contribution = ContextContribution("not-observed", "conversation", "reference", ContributionState.DEFERRED,
                                           None, extra, True)
        batch, _, invocation, response = await self.prepare(contributions=(contribution,))
        self.messages.sources.revoke(extra, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.publish(invocation, response)
        self.assertEqual(len(self.read(batch)), 1)

    async def test_source_read_result_is_preserved_as_a_generator_dependency(self):
        extra = self.event("tool-offered-source").source
        original = self.messages._read_source(extra, self.context, "text", NOW)
        batch, _, invocation, response = await self.prepare()
        run, call_id, _ = self.stages[batch]
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE conversation_tool_calls SET sequence=2 WHERE task_id=?", (run.task.task_id,))
            connection.execute("INSERT INTO conversation_tool_sources VALUES(?,?,?,?)", (batch, "offered", encode(extra), "text"))
            connection.execute("""INSERT INTO conversation_tool_calls(task_id,tool_call_id,batch_id,sequence,model_call_id,
                attempt_id,action,arguments_json,state,effect,result_json,created_at) VALUES(?,?,?,1,?,?,'source.read',?,
                'succeeded','none',?,?)""", (run.task.task_id, "original-source-read", batch, call_id, run.claim.attempt_id,
                encode({"handle": "offered"}), encode({"state": "succeeded", "effect": "none", "payload": original.payload,
                    "content_hash": original.content_hash, "payload_hash": digest(original.payload)}), stamp(NOW)))
        manifest = self.publish(invocation, response)
        self.assertEqual(len(self.read(batch)), 1)
        self.messages.sources.revoke(extra, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertEqual(self.messages.sources.validate_reference(manifest, observed_at=NOW).failure.code, "source_revoked")
        with self.assertRaises(TaskError):
            self.read(batch)

    async def test_group_history_uses_original_member_authority_and_links_withdrawal(self):
        scope = replace(self.context.scope, kind=ScopeKind.GROUP, native_scope_id="fixture-group",
                        conversation_id="group-conversation", session_id="shared-group-session")
        self.personas.register_route(ConversationRoute(scope, group_id=scope.native_scope_id), observed_at=NOW)
        role = self.identity.resolve_role(scope, observed_at=NOW).unwrap()
        self.context = TaskContext(self.important, role, group_audience(scope, self.important.subject))
        earlier = TaskContext(self.standard, role, group_audience(scope, self.standard.subject))
        for actor in (self.important, self.standard):
            self.grant(actor, scope, "conversation.reply")
            self.grant(actor, scope, "text")
        self.grant(self.important, scope, "configuration.read")
        event = self.event("earlier-member", context=earlier)
        self.accept(event, context=earlier)
        direct = self.messages.sources.read(event.source, resolved=self.context.actor, capability="text", observed_at=NOW,
                                            authorizer=self.tasks.identity)
        self.assertEqual(direct.failure.code, "source_audience_denied")
        batch, _, invocation, response = await self.prepare()
        manifest = self.publish(invocation, response)
        self.assertEqual(len(self.read(batch)), 1)
        links = self.runtime.read_all("SELECT input_id,input_lineage,input_revision FROM source_dependencies WHERE dependent_id=?",
                                     (manifest.source_id,))
        self.assertIn(key(event.source), [tuple(row) for row in links])
        self.messages.withdraw(earlier, event.scoped_key).unwrap()
        self.assertEqual(self.messages.sources.validate_reference(manifest, observed_at=NOW).failure.code, "source_revoked")
        with self.assertRaises(TaskError):
            self.read(batch)

    async def test_current_policy_revision_keeps_the_original_empty_batch_readable(self):
        batch = self.accept()
        self.grant(self.important, self.context.scope, "fixture.extra")
        current = replace(self.context, actor=self.identity.resolve_authenticated(
            self.context.actor.principal, observed_at=NOW).unwrap())
        self.assertEqual(current.key, self.context.key)
        self.assertNotEqual(current.actor.policy_revision, self.context.actor.policy_revision)
        self.assertEqual(self.generated.read_batch(batch, current, NOW), ())

    async def test_current_policy_revision_keeps_governed_image_originals_readable(self):
        batch, _, invocation, response = await self.prepare()
        self.publish(invocation, response)
        originals = self.read(batch)
        self.grant(self.important, self.context.scope, "fixture.extra")
        current = replace(self.context, actor=self.identity.resolve_authenticated(
            self.context.actor.principal, observed_at=NOW).unwrap())
        self.assertNotEqual(current.actor.policy_revision, self.context.actor.policy_revision)
        self.assertEqual(self.generated.read_batch(batch, current, NOW), originals)

    async def test_same_row_key_cannot_hide_a_changed_stored_original_identity(self):
        batch, _, invocation, response = await self.prepare()
        self.publish(invocation, response)
        changed = replace(self.context, actor=replace(self.context.actor, binding_revision=self.context.actor.binding_revision + 1))
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE conversation_batches SET context_json=? WHERE batch_id=?", (encode(changed), batch))
        with self.assertRaises(TaskError) as caught:
            self.read(batch)
        self.assertEqual(caught.exception.code, "generated_image_context")


if __name__ == "__main__":
    unittest.main()
