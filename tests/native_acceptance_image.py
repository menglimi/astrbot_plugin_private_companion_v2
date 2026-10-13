"""Execute the real Image owner and V2 registry inside a disposable boundary.

Only the backend, model and sender peers are synthetic. These acceptance cases
reuse the native flow fixtures instead of replacing owner/adoption/storage code.
"""

import asyncio
import base64
from copy import deepcopy
import hashlib
import inspect
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


async def _cleanup(case):
    errors = []
    while case._cleanups:
        function, args, kwargs = case._cleanups.pop()
        try:
            value = function(*args, **kwargs)
            if inspect.isawaitable(value):
                await value
        except BaseException as error:
            errors.append(error)
    if errors:
        raise errors[0]


async def run_image(root, guard, report):
    from tests.test_native_image_flow import NativeImageFlowTests
    from companion_v2.capabilities.models import CapabilityAuthorizationState
    from companion_v2.execution.models import TaskError
    from companion_v2.capabilities.repositories import CapabilityRepository
    from tests.native_image_support import NativeImageFixture
    from tests.test_host_application import HostFixture

    class CatalogAcceptance(NativeImageFixture, HostFixture, unittest.IsolatedAsyncioTestCase):
        async def acceptance_catalog(self):
            registry = self.create_image_port(self.root.parent / "image-native-v2", self.clock.now)
            self.acceptance_backends, self.acceptance_owners = [self.image_backend], [self.image_owner]
            self.image_context.get_all_stars = lambda: guard.catalog(())
            assert self.image_context.get_all_stars() == []
            assert registry._bundled_extensions == (self.image_lease,)
            assert self.image_lease.port is self.image_port
            package = registry.declarations()[0].descriptor.package
            repository = CapabilityRepository(self.runtime)
            assert repository.descriptors(extension_id=package.extension_id) == ()
            host = self.host(tool_port=registry)
            assert registry.application is host.application
            assert repository.descriptors(extension_id=package.extension_id) == ()
            registered = registry.register_catalog(observed_at=self.clock.now()).unwrap()
            assert registered == (package,)
            assert repository.descriptors(extension_id=package.extension_id) == (package,)
            assert not repository.installation(extension_id=package.extension_id).is_success
            assert self.runtime.read_one("SELECT COUNT(*) FROM capability_authorizations WHERE extension_id = ?",
                                         (package.extension_id,))[0] == 0
            assert self.runtime.read_one("SELECT COUNT(*) FROM capability_role_selections WHERE extension_id = ?",
                                         (package.extension_id,))[0] == 0
            assert not self.image_backend.calls and not self.called and not self.sent

    class AcceptanceImage(NativeImageFlowTests):
        def create_image_port(self, directory, now):
            registry = super().create_image_port(directory, now)
            if not hasattr(self, "acceptance_backends"):
                self.acceptance_backends = []
                self.acceptance_owners = []
            self.acceptance_backends.append(self.image_backend)
            self.acceptance_owners.append(self.image_owner)
            self.image_context.get_all_stars = lambda: guard.catalog(())
            assert self.image_context.get_all_stars() == []
            assert registry._bundled_extensions == (self.image_lease,)
            assert self.image_lease.port is self.image_port
            assert all(registry.current_declaration(item.host_tool_id) == item
                       for item in registry.declarations())
            return registry

        async def acceptance_lookup_original_and_restart(self):
            host, batch, context = await self.complete_image()
            invocation = self.image_backend.calls[0][0]
            request = deepcopy(dict(invocation.envelope))
            before_dispatch_calls = []

            def authorized():
                before_dispatch_calls.append(True)
                result = self.capabilities.authorize(extension_id=self.package.extension_id,
                    capability_id=request["action"], subject=context.actor.subject, scope=context.scope)
                if result.failure is not None:
                    raise TaskError(result.failure.code, result.failure.reason)

            receipt = await self.image_port.lookup(request, before_dispatch=authorized)
            assert receipt["state"] == "succeeded" and len(receipt["artifacts"]) == 1
            artifact_request = {**request, **receipt["artifacts"][0]}
            raw = await self.image_port.read_artifact(artifact_request, before_dispatch=authorized)
            assert raw == base64.b64decode(self.sent[0].images[0].data_base64)
            assert hashlib.sha256(raw).hexdigest() == receipt["artifacts"][0]["content_hash"]
            assert len(self.image_backend.calls) == 1

            bad = {**artifact_request, "content_hash": "0" * 64}
            with self.assertRaises(ValueError):
                await self.image_port.read_artifact(bad, before_dispatch=authorized)
            assert len(self.image_backend.calls) == 1
            assert len(before_dispatch_calls) >= 4

            old_port, old_registry, old_backend = self.image_port, self.native_registry, self.image_backend
            old_declaration = old_registry.declarations()[0]
            old_registry.close()
            assert not old_registry.declarations()
            assert old_registry.current_declaration(old_declaration.host_tool_id) is None
            await old_port.close()
            assert old_backend.closed
            with self.assertRaises(ValueError):
                await old_port.lookup(request, before_dispatch=authorized)
            self.native_registry = self.create_image_port(self.image_directory, self.clock.now)
            # Rebind only the new current provider generation for receipt lookup;
            # original invocation, task, arguments, operation and bytes stay pinned.
            rebound = {**request, "binding": {**request["binding"], "generation": self.image_owner.generation}}
            restored = await self.image_port.lookup(rebound, before_dispatch=authorized)
            assert restored["operation_id"] == receipt["operation_id"]
            assert restored["receipt_ref"] == receipt["receipt_ref"]
            assert restored["artifacts"] == receipt["artifacts"]
            assert await self.image_port.read_artifact({**rebound, **restored["artifacts"][0]},
                                                       before_dispatch=authorized) == raw
            assert self.image_backend.calls == []
            self.consent("image.generate", CapabilityAuthorizationState.REVOKED, 1)
            with self.assertRaises(TaskError):
                await self.image_port.lookup(rebound, before_dispatch=authorized)
            with self.assertRaises(TaskError):
                await self.image_port.read_artifact({**rebound, **restored["artifacts"][0]},
                                                   before_dispatch=authorized)
            assert self.image_backend.calls == [] and len(self.sent) == 1

        async def acceptance_revoke_during_backend_and_stop(self):
            entered, release = asyncio.Event(), asyncio.Event()
            original_execute = self.image_backend.execute
            async def blocked(invocation, references, before_dispatch):
                await before_dispatch()
                entered.set()
                await release.wait()
                return await original_execute(invocation, references, before_dispatch)
            self.image_backend.execute = blocked
            host = await self.image_host()
            batch = host.receive(self.event()).unwrap()
            try:
                await asyncio.wait_for(entered.wait(), 8)
                self.consent("image.generate", CapabilityAuthorizationState.REVOKED, 1)
                release.set()
                await self.done(host.application, batch)
                assert self.image_backend.calls == []
                assert not any(getattr(item, "images", ()) for item in self.sent)
                rows = self.runtime.read_all("SELECT state FROM extension_tool_invocations", ())
                assert rows and all(row[0] != "succeeded" for row in rows)
                stopped = await host.application.close(grace_seconds=0)
                assert stopped.state == "stopped" and not host.application.active_handles
                await self.image_port.close()
                self.native_registry.close()
                assert self.image_backend.closed and not self.image_owner._tasks
            finally:
                release.set()

        async def acceptance_receipt_after_revoke(self):
            entered, release = asyncio.Event(), asyncio.Event()
            original_execute = self.image_backend.execute
            async def completed_remotely(invocation, references, before_dispatch):
                result = await original_execute(invocation, references, before_dispatch)
                entered.set()
                await release.wait()
                return result
            self.image_backend.execute = completed_remotely
            host = await self.image_host()
            batch = host.receive(self.event()).unwrap()
            try:
                await asyncio.wait_for(entered.wait(), 8)
                self.consent("image.generate", CapabilityAuthorizationState.REVOKED, 1)
                release.set()
                await self.done(host.application, batch)
                assert len(self.image_backend.calls) == 1
                invocation = self.image_backend.calls[0][0]
                original = self.image_owner.store.by_request(invocation.scope_key, invocation.request_id)
                assert original["state"] == "succeeded"
                row = self.runtime.read_one("SELECT * FROM extension_tool_invocations", ())
                assert row["operation_id"] == original["id"]
                assert row["receipt_ref"] == original["receipt"]["receipt_id"]
                assert row["effect"] == "committed"
                assert self.runtime.read_one("SELECT COUNT(*) FROM conversation_image_payloads", ())[0] == 0
                assert not any(getattr(item, "images", ()) for item in self.sent)
                assert all(not envelope.original.images for envelope in self.called)
                assert not any(material.owner == "image.native" for envelope in self.called
                               for material in envelope.original.context.materials)
            finally:
                release.set()

    cases = (
        ("test_native_generation_is_adopted_and_sent_once_with_original_receipt", "generate_save_adopt_and_synthetic_delivery"),
        ("test_edit_uses_same_origin_saved_artifact_and_only_selected_output_is_sent", "edit_saved_original_and_deliver_selected_output"),
        ("test_unselected_generation_stays_saved_without_automatic_image_send", "unselected_original_is_not_automatically_sent"),
        ("test_unknown_backend_produces_no_image_and_never_replays", "unknown_backend_has_no_image_or_replay"),
        ("test_revocation_before_final_adoption_prevents_entire_send", "revoke_before_final_adoption_blocks_send"),
        ("test_default_restart_reads_pending_image_and_original_receipt_without_regenerating", "restart_resumes_saved_delivery_without_regenerating"),
        ("test_unknown_send_remains_unknown_after_restart_without_resending", "unknown_delivery_is_not_replayed_after_restart"),
        ("acceptance_lookup_original_and_restart", "lookup_read_hash_verify_revoke_close_and_reopen_original"),
        ("acceptance_revoke_during_backend_and_stop", "revoke_while_waiting_blocks_backend_then_stops_all_handles"),
        ("acceptance_receipt_after_revoke", "backend_success_after_revoke_retains_receipt_without_image_adoption_or_delivery"),
    )
    selected = ((CatalogAcceptance, "acceptance_catalog", "discovery_and_explicit_catalog_do_not_acquire_or_authorize"),) + tuple(
        (AcceptanceImage, method, name) for method, name in cases)
    for case_type, method, name in selected:
        case = case_type(methodName=method)
        report["running_check"] = name
        with patch("tests.test_management_access.TemporaryDirectory",
                   side_effect=lambda **options: TemporaryDirectory(dir=root, **options)):
            try:
                case.setUp()
                await getattr(case, method)()
                guard.assert_clean()
                report["checks"].append(name)
                report["synthetic_backend_submissions"] += sum(len(backend.calls) for backend in case.acceptance_backends)
                report["synthetic_model_calls"] += len(case.called)
                report["synthetic_sender_attempts"] += len(case.sent)
            finally:
                await _cleanup(case)
        assert not case.root.exists()
        assert all(backend.closed for backend in case.acceptance_backends)
        assert all(not owner._tasks for owner in case.acceptance_owners)
    report.pop("running_check", None)
    report["passed"] = True
    report["checks"].append("all_native_case_databases_tasks_and_temporary_roots_cleaned")
    guard.assert_clean()
    return report
