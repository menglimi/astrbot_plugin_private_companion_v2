import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest
from unittest.mock import Mock
from types import SimpleNamespace

from astrbot_host.native_extensions import NativeExtensionRegistry
from companion_v2.capabilities import native_reads
from companion_v2.execution.models import TaskError, digest, encode
from companion_v2.foundation.refs import AudienceRef, ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.sources.models import GovernanceState

from tests.test_native_provider_contract import FakeContext, manifest
from tests.test_daily_token_soft_limit import ModelFixture
from tests.test_management_access import NOW


SYNTHETIC_IMAGE_PLUGIN = "synthetic.image_provider"


class Port:
    def __init__(self):
        self.before = 0
        self.content = b"PNG"
        self.document = manifest()
        self.document["plugin_id"] = SYNTHETIC_IMAGE_PLUGIN
        self.document["package"]["package_id"] = SYNTHETIC_IMAGE_PLUGIN
        self.prepare = self.after = self.prepare_read = None
        self.saved_guard = None
        self.with_artifact = True
        # Read-only providers return a result document; adopting ports return artifacts.
        self.result = {"provider": "image"}
        # A declaration whose side effect is ``none`` must answer with effect ``none`` and
        # no operation id, so the stub keeps those overridable.
        self.state = "succeeded"
        self.effect = "committed"
        self.operation_id = "op-1"

    def manifest(self):
        return deepcopy(self.document)

    async def execute(self, request, *, before_dispatch):
        if self.prepare:
            await self.prepare()
        before_dispatch()
        self.saved_guard = before_dispatch
        self.before += 1
        if self.after:
            self.after(request)
        return {"schema": request["schema"], "invocation_id": request["invocation_id"],
                "origin_key": request["origin_key"], "arguments_hash": request["arguments_hash"],
                "binding": request["binding"], "state": self.state, "effect": self.effect,
                "operation_id": self.operation_id, "receipt_ref": "receipt-1", "result": self.result,
                "artifacts": [{
                    "artifact_id": "artifact-1", "operation_id": "op-1",
                    "content_hash": hashlib.sha256(self.content).hexdigest(),
                    "mime_type": "image/png", "size_bytes": len(self.content)}] if self.with_artifact else []}

    async def read_artifact(self, request, *, before_dispatch):
        if self.prepare_read:
            await self.prepare_read()
        before_dispatch()
        self.before += 1
        return self.content


class Api:
    def __init__(self, port):
        self.port = port

    def companion_v2_native(self):
        return self.port


class StarClass:
    def __init__(self, api):
        self.extension_api = api


class Star:
    root_dir_name = SYNTHETIC_IMAGE_PLUGIN
    name = root_dir_name
    version = "0.5.0"
    activated = True

    def __init__(self, port):
        self.star_cls = StarClass(Api(port))


class Context:
    def __init__(self, star):
        self.star = star

    def get_all_stars(self):
        return (self.star,)


class NativeImageManagementApiTests(unittest.TestCase):
    def test_management_api_requires_a_live_v2_native_image_declaration(self):
        registry = NativeExtensionRegistry(Context(Star(None)))
        self.addCleanup(registry.close)

        self.assertIsNone(registry.image_extension_api())


class LiveReadTests(unittest.IsolatedAsyncioTestCase):
    """A read-only provider result is checked by the domain reader, then sealed."""

    def setUp(self):
        self.port = Port()
        self.port.with_artifact = False
        self.port.document = deepcopy(self.port.document)
        self.port.document["tools"] = [{
            "action": "live.events.recent", "capability": "live.events.recent", "source_owner": "live.native",
            "description": "recent events", "side_effect": "none", "timeout_seconds": 10,
            "parameters": {"type": "object", "properties": {"platform": {"type": "string"},
                "limit": {"type": "integer"}, "after_event_id": {"type": "string"}},
                "required": ["platform", "limit"], "additionalProperties": False}}]
        self.registry = NativeExtensionRegistry(Context(Star(self.port)), now=lambda: NOW)
        self.addCleanup(self.registry.close)

    def request(self, **arguments):
        return {"schema": "companion.native-invocation.v1", "invocation_id": "invocation-1",
                "parent_task_id": "task-1", "tool_call_id": "call-1", "action": "live.events.recent",
                "origin_key": "origin-1", "context": {}, "binding": {}, "arguments": arguments,
                "arguments_hash": digest(encode(arguments)), "deadline_at": NOW.isoformat()}

    def page(self, *identifiers, platform="bilibili", **extra):
        return {"platform": platform, "events": [{"event_id": i, "text": "观众原话", "trust": "untrusted"}
                                                for i in identifiers], **extra}

    def test_the_reader_is_installed_for_read_only_actions_by_default(self):
        self.assertIn("live.events.recent", self.registry.result_handlers)
        self.assertIn("reality.device.list", self.registry.result_handlers)
        # An image action keeps its own adopter.
        self.assertIn("image.generate", self.registry.result_handlers)

    def test_a_result_carrying_credentials_is_refused_before_it_reaches_the_model(self):
        for result in ({"device": {"access_token": "x"}}, {"devices": [{"cookie": "y"}]},
                       {"platform": {"credentials": {"api_key": "z"}}}):
            with self.subTest(result=result), self.assertRaises(TaskError) as error:
                native_reads.check_no_credentials(result, action="reality.device.list")
            self.assertEqual(error.exception.code, "native_read_credential")

    def test_a_live_page_must_mark_viewer_text_as_material(self):
        for marker in ("trusted", "instruction"):
            with self.assertRaises(TaskError) as error:
                native_reads.check_untrusted_material(
                    {"events": [{"event_id": "e-1", "trust": marker}]}, action="live.events.recent")
            self.assertEqual(error.exception.code, "native_read_untrusted")
        # No marker and an explicit untrusted marker are both acceptable.
        native_reads.check_untrusted_material({"events": [{"event_id": "e-1"}]}, action="live.events.recent")
        native_reads.check_untrusted_material(
            {"events": [{"event_id": "e-1", "trust": "untrusted"}]}, action="live.events.recent")

    def test_a_delivered_event_cannot_be_ingested_twice(self):
        context = SimpleNamespace(key="origin-1")
        runtime = Mock()
        runtime.read_one.return_value = None
        runtime.transaction.return_value.__enter__ = lambda state: state
        runtime.transaction.return_value.__exit__ = lambda *args: False
        journal = native_reads.NativeReadJournal(runtime, context=context)
        self.assertEqual(journal.advance("bilibili", event_ids=("e-1", "e-2"), after_event_id=None), "e-2")
        # The same page again is a replay, exactly like an unknown external action.
        stored = {"version": 1, "delivered": ["e-1", "e-2"], "cursor": "e-2"}
        runtime.read_one.return_value = {"value": json.dumps(stored)}
        with self.assertRaises(TaskError) as error:
            journal.advance("bilibili", event_ids=("e-1",), after_event_id="e-1")
        self.assertEqual(error.exception.code, "native_read_replayed")
        # Continuing from an id this relationship never received is a replay by another name.
        with self.assertRaises(TaskError):
            journal.advance("bilibili", event_ids=("e-9",), after_event_id="e-7")
        # A page repeating its own id is refused as well.
        runtime.read_one.return_value = None
        with self.assertRaises(TaskError):
            journal.advance("bilibili", event_ids=("e-3", "e-3"), after_event_id=None)

    def test_a_live_page_needs_stable_event_ids(self):
        with self.assertRaises(TaskError) as error:
            native_reads.event_ids({"events": [{"text": "no id"}]})
        self.assertEqual(error.exception.code, "native_read_untrusted")
        self.assertEqual(native_reads.event_ids({"events": [{"event_id": "e-1"}]}), ("e-1",))
        self.assertEqual(native_reads.event_ids({"events": []}), ())


class NativeRegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.port = Port()
        self.registry = NativeExtensionRegistry(Context(Star(self.port)), result_handlers={})

    def _invocation(self):
        declaration = self.registry.declarations()[0]
        scope = ScopeRef("install", "aiocqhttp", ScopeKind.PRIVATE, "user", "bot", "100", "conversation", "user")
        subject = SubjectRef("install", SubjectKind.HUMAN, "user")
        audience = AudienceRef(scope, (subject,))
        context = FakeContext(scope, audience)
        return declaration, SimpleNamespace(
            invocation_id="inv-1", parent_task_id="task-1", tool_call_id="call-1",
            context=context, descriptor=declaration.descriptor,
            arguments_json='{"prompt":"sunset"}',
            arguments_hash=digest({"prompt": "sunset"}),
            deadline_at=datetime.now(timezone.utc) + timedelta(minutes=1),
            before_dispatch=lambda: None,
        )

    def assert_unavailable(self, result, code):
        self.assertEqual((result.state, result.effect, result.operation_id, result.receipt_ref),
                         ("succeeded", "committed", "op-1", "receipt-1"))
        self.assertIs(result.source.state, GovernanceState.REVOKED)
        self.assertEqual(result.source.content_hash, digest(result.source.payload))
        self.assertEqual(json.loads(result.source.payload)["adoption"], {"state": "unavailable", "code": code})
        self.assertEqual(result.images, ())

    async def test_discovery_is_metadata_only_and_missing_adopter_revokes_material(self):
        self.assertEqual([item.host_tool_id for item in self.registry.declarations()],
                         ["native:synthetic.image_provider:image.generate"])
        declaration, invocation = self._invocation()
        result = await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assert_unavailable(result, "native_artifact_unadopted")
        self.assertGreaterEqual(self.port.before, 2)

    async def test_close_invalidates_current_declaration(self):
        declaration = self.registry.declarations()[0]
        self.registry.close()
        self.assertEqual(self.registry.declarations(), ())
        self.assertIsNone(self.registry.current_declaration(declaration.host_tool_id))

    async def test_same_generation_from_a_replaced_port_is_rejected(self):
        declaration = self.registry.declarations()[0]
        self.registry.context = Context(Star(Port()))
        self.assertIsNone(self.registry.current_declaration(declaration.host_tool_id))

    async def test_replacement_during_provider_preparation_cannot_reach_effect(self):
        async def replace_port():
            await asyncio.sleep(0)
            self.registry.context.star.star_cls.extension_api.port = Port()
        self.port.prepare = replace_port
        declaration, invocation = self._invocation()
        with self.assertRaises(TaskError) as caught:
            await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assertEqual(caught.exception.code, "native_provider_changed")
        self.assertEqual(self.port.before, 0)

    async def test_stopping_during_preparation_cannot_reach_effect(self):
        async def stop():
            await asyncio.sleep(0)
            self.registry.close()
        self.port.prepare = stop
        declaration, invocation = self._invocation()
        with self.assertRaises(TaskError):
            await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assertEqual(self.port.before, 0)

    async def test_original_permission_guard_rechecked_after_async_preparation(self):
        permitted = True
        def guard():
            if not permitted:
                raise TaskError("revoked", "synthetic permission revoked")
        async def revoke():
            nonlocal permitted
            await asyncio.sleep(0)
            permitted = False
        self.port.prepare = revoke
        declaration, invocation = self._invocation()
        invocation.before_dispatch = guard
        with self.assertRaises(TaskError) as caught:
            await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assertEqual(caught.exception.code, "revoked")
        self.assertEqual(self.port.before, 0)

    async def test_reader_rechecks_instance_after_wait_before_bytes(self):
        async def replace_instance():
            await asyncio.sleep(0)
            star = self.registry.context.star
            star.star_cls = StarClass(star.star_cls.extension_api)
        self.port.prepare_read = replace_instance
        declaration, invocation = self._invocation()
        result = await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assert_unavailable(result, "native_provider_changed")
        self.assertEqual(self.port.before, 1)

    async def test_request_mutation_cannot_retarget_original_receipt(self):
        self.port.after = lambda request: request.update(origin_key="other-context")
        declaration, invocation = self._invocation()
        with self.assertRaises(TaskError) as caught:
            await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assertEqual(caught.exception.code, "native_receipt_mismatch")
        self.assertEqual(self.port.before, 1)

    async def test_completed_provider_guard_expires(self):
        self.port.with_artifact = False
        declaration, invocation = self._invocation()
        result = await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assertEqual(result.operation_id, "op-1")
        with self.assertRaises(TaskError) as caught:
            self.port.saved_guard()
        self.assertEqual(caught.exception.code, "native_guard_expired")

    async def test_deadline_and_missing_guard_prevent_dispatch(self):
        declaration, invocation = self._invocation()
        invocation.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        with self.assertRaises(TaskError) as caught:
            await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assertEqual(caught.exception.code, "native_deadline_expired")
        invocation.deadline_at += timedelta(minutes=1)
        invocation.before_dispatch = None
        with self.assertRaises(TaskError) as caught:
            await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assertEqual(caught.exception.code, "native_guard_missing")
        self.assertEqual(self.port.before, 0)

    async def test_native_role_guard_rechecked_after_result(self):
        checks = []
        async def role_guard(scope, binding):
            checks.append(scope)
            if len(checks) == 2:
                raise TaskError("role_binding_changed", "synthetic native role changed")
        self.registry.bind_role_guard(role_guard)
        declaration, invocation = self._invocation()
        invocation.context = SimpleNamespace(scope=invocation.context.scope, role_binding="role", key="context-key")
        # Use the original serializable fixture with a role binding for the wire.
        from dataclasses import dataclass
        @dataclass(frozen=True)
        class ContextWithRole(FakeContext):
            role_binding: str = "role"
        scope = invocation.context.scope
        invocation.context = ContextWithRole(scope, AudienceRef(scope, (SubjectRef("install", SubjectKind.HUMAN, "user"),)))
        result = await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assert_unavailable(result, "role_binding_changed")
        self.assertEqual(self.port.before, 1)

    async def test_revocation_after_success_keeps_receipt_without_read_or_adoption(self):
        permitted = True
        def guard():
            if not permitted:
                raise TaskError("revoked", "synthetic permission revoked")
        def revoke(request):
            nonlocal permitted
            permitted = False
        adopter = Mock(side_effect=AssertionError("revoked output cannot reach adoption"))
        self.registry = NativeExtensionRegistry(self.registry.context, result_handlers={"image.generate": adopter})
        self.port.after = revoke
        declaration, invocation = self._invocation()
        invocation.before_dispatch = guard
        result = await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assert_unavailable(result, "revoked")
        self.assertEqual(result.source.audience, invocation.context.audience)
        self.assertEqual(json.loads(result.source.payload)["native"]["artifacts"][0]["artifact_id"], "artifact-1")
        self.assertEqual(self.port.before, 1)
        adopter.assert_not_called()

    async def test_replacement_after_success_preserves_original_receipt(self):
        self.port.after = lambda request: setattr(self.registry.context, "star", Star(Port()))
        declaration, invocation = self._invocation()
        result = await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assert_unavailable(result, "native_provider_changed")
        self.assertEqual(self.port.before, 1)
        self.assertIsNone(self.registry.current_declaration(declaration.host_tool_id))

    async def test_corrupt_artifact_keeps_operation_but_never_reaches_adopter(self):
        original_hash = hashlib.sha256(self.port.content).hexdigest()
        async def corrupt():
            await asyncio.sleep(0)
            self.port.content = b"BAD"
        adopter = Mock(side_effect=AssertionError("corrupt bytes cannot reach adoption"))
        self.registry = NativeExtensionRegistry(self.registry.context, result_handlers={"image.generate": adopter})
        self.port.prepare_read = corrupt
        declaration, invocation = self._invocation()
        result = await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assert_unavailable(result, "native_artifact_changed")
        self.assertEqual(json.loads(result.source.payload)["native"]["artifacts"][0]["content_hash"], original_hash)
        self.assertEqual(self.port.before, 2)
        adopter.assert_not_called()

    async def test_adopter_cannot_replace_provider_receipt(self):
        from dataclasses import replace
        def change_receipt(invocation, native):
            return replace(self.registry._source_response(invocation, native), receipt_ref="invented-receipt")
        self.port.with_artifact = False
        self.registry = NativeExtensionRegistry(self.registry.context, result_handlers={"image.generate": change_receipt})
        declaration, invocation = self._invocation()
        result = await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assert_unavailable(result, "native_handler_invalid")

    async def test_missing_provider_dispatch_check_revokes_success_material(self):
        original = self.port.execute
        async def unguarded(request, *, before_dispatch):
            return await original(request, before_dispatch=lambda: None)
        self.port.execute = unguarded
        declaration, invocation = self._invocation()
        result = await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assert_unavailable(result, "native_guard_unused")
        self.assertEqual(self.port.before, 1)

    async def test_known_failure_and_unknown_keep_no_material_after_revocation(self):
        original = self.port.execute
        for state, effect in (("failed", "not_committed"), ("unknown", "unknown")):
            with self.subTest(state=state):
                self.port.before = 0
                permitted = True
                def guard():
                    if not permitted:
                        raise TaskError("revoked", "synthetic permission revoked")
                async def outcome(request, *, before_dispatch):
                    nonlocal permitted
                    response = await original(request, before_dispatch=before_dispatch)
                    response.update(state=state, effect=effect, result=None, artifacts=[])
                    permitted = False
                    return response
                self.port.execute = outcome
                declaration, invocation = self._invocation()
                invocation.before_dispatch = guard
                result = await self.registry.invoke(declaration.host_tool_id, invocation)
                self.assertEqual((result.state, result.effect), (state, effect))
                self.assertEqual((result.operation_id, result.receipt_ref), ("op-1", "receipt-1"))
                self.assertIsNone(result.source)
                self.assertEqual(result.images, ())
                self.assertEqual(self.port.before, 1)

    async def test_cancellation_after_receipt_preserves_receipt_without_material(self):
        from dataclasses import dataclass
        @dataclass(frozen=True)
        class ContextWithRole(FakeContext):
            role_binding: str = "role"
        waiting = asyncio.Event()
        checks = 0
        async def role_guard(scope, binding):
            nonlocal checks
            checks += 1
            if checks == 2:
                waiting.set()
                await asyncio.Event().wait()
        self.registry.bind_role_guard(role_guard)
        declaration, invocation = self._invocation()
        invocation.context = ContextWithRole(invocation.context.scope, invocation.context.audience)
        task = asyncio.create_task(self.registry.invoke(declaration.host_tool_id, invocation))
        await asyncio.wait_for(waiting.wait(), timeout=1)
        task.cancel()
        result = await task
        self.assert_unavailable(result, "native_adoption_cancelled")
        self.assertEqual(self.port.before, 1)

    async def test_cancellation_before_receipt_still_propagates(self):
        async def cancel():
            raise asyncio.CancelledError()
        self.port.prepare = cancel
        declaration, invocation = self._invocation()
        with self.assertRaises(asyncio.CancelledError):
            await self.registry.invoke(declaration.host_tool_id, invocation)
        self.assertEqual(self.port.before, 0)

    async def test_discovery_does_not_promote_status_or_duplicate_instances(self):
        self.registry.context.star.star_cls.extension_api = SimpleNamespace(
            companion_v2_status=lambda: self.fail("status must not be consulted for native execution"))
        self.assertEqual(NativeExtensionRegistry(self.registry.context).declarations(), ())
        context = SimpleNamespace(get_all_stars=lambda: (Star(Port()), Star(Port())))
        duplicate = NativeExtensionRegistry(context)
        self.assertEqual(duplicate.declarations(), ())
        self.assertEqual(duplicate.issues[0][1], "native_instance_conflict")

    async def test_explicitly_disabled_native_port_is_not_a_declaration_error(self):
        disabled = NativeExtensionRegistry(Context(Star(None)))
        self.assertEqual(disabled.declarations(), ())
        self.assertEqual(disabled.issues, ())

    async def test_stable_generation_reopens_only_with_new_registry(self):
        old = self.registry.declarations()[0]
        self.registry.context.star = Star(Port())
        self.assertIsNone(self.registry.current_declaration(old.host_tool_id))
        new = NativeExtensionRegistry(self.registry.context)
        self.assertEqual(new.current_declaration(old.host_tool_id), old)


if __name__ == "__main__":
    unittest.main()
