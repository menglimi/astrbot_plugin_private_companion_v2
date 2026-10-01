from dataclasses import replace
from datetime import timedelta
import unittest

from companion_v2.capabilities.models import CapabilityAuthorizationState, CapabilityPackageDescriptor
from companion_v2.capabilities.read_providers import ReadLimits, ReadProviderRegistry
from companion_v2.execution.models import TaskError, require, stamp
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.personas import RuntimeIdentity
from companion_v2.memory.provider import CAPABILITY, make_provider
from companion_v2.memory.service import MemoryService
from tests.memory_support import MemoryFixture
from tests.test_management_access import NOW


class ReadProviderRegistryTests(MemoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.memory_service = MemoryService(self.tasks, policy=self.memory.policy)
        self.runtime_identity = RuntimeIdentity("companion", "registry-runtime", "astrbot", "host")
        self.registry = ReadProviderRegistry(self.tasks, require_running=lambda: require(self.tasks.check_generation()))
        self.registration = self.registry.register(
            "companion_v2.memory", CAPABILITY,
            self.read_provider,
        )

    def read_provider(self, binding):
        return make_provider(self.memory_service, binding, runtime_identity=self.runtime_identity)

    def bind(self, **changes):
        return self.registry.bind(self.context, **(dict(capability_id="memory.query", capability_version="1.0",
            provider_id="companion_v2.memory") | changes))

    def request(self, binding):
        scope = binding.scope
        return {
            "schema_version": CAPABILITY.input_schema,
            "capability_id": CAPABILITY.capability_id,
            "capability_version": CAPABILITY.capability_version,
            "provider_id": binding.provider.provider,
            "provider_generation": binding.provider.generation,
            "request_id": "registry-request-1",
            "trace_id": "registry-trace-1",
            "deadline_at": stamp(NOW + timedelta(minutes=2)),
            "scope": scope,
            "required_features": [],
            "budget": {"max_input_bytes": 16384, "max_model_calls": 0, "max_output_bytes": 20000},
            "payload": {
                "namespace": "personal", "visibility": "private", "purpose": "reply",
                "query_intent": "咖啡", "time_range": None, "at_time": None,
                "allowed_retention": [], "include_pending": False,
                "conflict_policy": "current_only", "confidence_floor": None,
                "evidence_budget": {"max_items": 8, "max_chars": 2400, "max_tokens": 800},
                "cursor": None, "extensions": {},
            },
        }

    def test_discovery_binding_and_invocation_share_the_same_provider_generation(self):
        self.remember()
        discovered = self.registry.discover(self.context, capability_id="memory.query").unwrap()
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["provider"]["generation"], self.registration.binding.generation)

        binding = self.registry.bind(
            self.context, capability_id="memory.query", capability_version="1.0",
            provider_id="companion_v2.memory", limits=ReadLimits(16384, 20000),
        ).unwrap()
        result = self.registry.invoke(self.context, binding.binding_ref, self.request(binding)).unwrap()
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["provider_generation"], binding.provider.generation)
        self.assertEqual(len(result["output"]["items"]), 1)

    def test_release_and_stale_scope_cannot_reuse_a_read_binding(self):
        binding = self.registry.bind(
            self.context, capability_id="memory.query", capability_version="1.0",
            provider_id="companion_v2.memory",
        ).unwrap()
        self.assertTrue(self.registry.release(self.context, binding.binding_ref).unwrap())
        failed = self.registry.invoke(self.context, binding.binding_ref, self.request(binding))
        self.assertEqual(failed.failure.code, "provider_binding_unavailable")

        binding = self.registry.bind(
            self.context, capability_id="memory.query", capability_version="1.0",
            provider_id="companion_v2.memory",
        ).unwrap()
        request = self.request(binding)
        request["scope"] = dict(request["scope"], installation_id="other-installation")
        failed = self.registry.invoke(self.context, binding.binding_ref, request)
        self.assertEqual(failed.failure.code, "provider_binding_scope_mismatch")

    def test_close_invalidates_discovery_and_all_existing_leases(self):
        binding = self.registry.bind(
            self.context, capability_id="memory.query", capability_version="1.0",
            provider_id="companion_v2.memory",
        ).unwrap()
        self.registry.close()
        self.assertEqual(self.registry.discover(self.context, capability_id="memory.query").failure.code,
                         "provider_registry_closed")
        self.assertEqual(self.registry.invoke(self.context, binding.binding_ref, self.request(binding)).failure.code,
                         "provider_registry_closed")

    def test_unregister_old_registration_cannot_remove_replacement_or_redirect_old_calls(self):
        old = self.bind().unwrap()
        self.assertTrue(self.registry.unregister(self.registration))
        replacement = self.registry.register("companion_v2.memory", CAPABILITY, self.read_provider)
        self.assertNotEqual(old.provider.generation, replacement.binding.generation)
        self.assertFalse(self.registry.unregister(self.registration))
        current = self.bind().unwrap()
        self.assertEqual(current.provider, replacement.binding)
        self.assertEqual(self.registry.invoke(self.context, old.binding_ref, self.request(old)).failure.code,
                         "provider_binding_unavailable")
        self.assertEqual(self.registry.invoke(self.context, current.binding_ref, self.request(old)).failure.code,
                         "provider_request_binding_mismatch")

    def test_duplicate_registration_and_missing_features_do_not_silently_choose_a_provider(self):
        with self.assertRaisesRegex(TaskError, "unregister"):
            self.registry.register("companion_v2.memory", CAPABILITY, self.read_provider)
        self.assertEqual(self.bind(required_features=("memory.pending@1",)).failure.code, "provider_feature_unavailable")
        self.assertEqual(self.bind(capability_version="2.0").failure.code, "provider_unavailable")
        self.assertEqual(self.bind(provider_id="missing").failure.code, "provider_unavailable")
        self.assertEqual(len(self.registry.discover(self.context, capability_id="memory.query").unwrap()), 1)

    def test_other_callers_cannot_invoke_or_release_someone_elses_binding(self):
        other = self.context_for(self.core)
        bound = self.bind().unwrap()
        for result in (self.registry.invoke(other, bound.binding_ref, self.request(bound)),
                       self.registry.release(other, bound.binding_ref)):
            self.assertEqual(result.failure.code, "provider_binding_scope_mismatch")
        self.assertTrue(self.registry.release(self.context, bound.binding_ref).unwrap())

    def test_expired_leases_free_capacity_without_reviving_an_old_handle(self):
        self.registry.max_bindings = 1
        bound = self.bind(ttl_seconds=10).unwrap()
        self.assertEqual(self.bind().failure.code, "provider_bindings_full")
        self.clock.advance(timedelta(seconds=11))
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, self.request(bound)).failure.code,
                         "provider_binding_expired")
        new = self.bind().unwrap()
        self.assertNotEqual(new.binding_ref, bound.binding_ref)
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, self.request(bound)).failure.code,
                         "provider_binding_unavailable")

    def test_revoke_then_restore_permissions_requires_a_new_binding(self):
        bound = self.bind().unwrap()
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
            expected_revision=self.policy.revision, observed_at=self.clock.now())
        self.assertEqual(self.registry.discover(self.context, capability_id="memory.query").unwrap(), ())
        self.assertFalse(self.registry.invoke(self.context, bound.binding_ref, self.request(bound)).is_success)
        self.policy.set_tier(self.important.subject, AuthorizationTier.IMPORTANT,
            expected_revision=self.policy.revision, observed_at=self.clock.now())
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, self.request(bound)).failure.code,
                         "provider_binding_unavailable")
        self.assertTrue(self.bind().is_success)

    def test_permission_loss_during_the_handler_discards_its_result(self):
        self.remember()
        def factory(binding):
            provider = self.read_provider(binding)
            def invoke(context, request):
                result = provider.invoke(context, request)
                self.identity.revoke_binding(context.actor.binding_id, revoked_at=self.clock.now(),
                    expected_revision=self.identity.revision)
                return result
            return replace(provider, invoke=invoke)
        self.registry.unregister(self.registration)
        self.registry.register("companion_v2.memory", CAPABILITY, factory)
        bound = self.bind().unwrap()
        result = self.registry.invoke(self.context, bound.binding_ref, self.request(bound))
        self.assertIsNone(result.value)
        self.assertEqual(result.failure.code, "binding_revoked")

    def test_replacing_provider_during_call_discards_the_original_result(self):
        def factory(binding):
            provider = self.read_provider(binding)
            def invoke(context, request):
                result = provider.invoke(context, request)
                self.registry.unregister(registration)
                self.registry.register("companion_v2.memory", CAPABILITY, self.read_provider)
                return result
            return replace(provider, invoke=invoke)
        self.registry.unregister(self.registration)
        registration = self.registry.register("companion_v2.memory", CAPABILITY, factory)
        bound = self.bind().unwrap()
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, self.request(bound)).failure.code,
                         "provider_binding_unavailable")

    def test_byte_budgets_and_deadlines_are_enforced_before_the_handler(self):
        calls = []
        def factory(binding):
            provider = self.read_provider(binding)
            def invoke(context, request):
                calls.append(request)
                return provider.invoke(context, request)
            return replace(provider, invoke=invoke)
        self.registry.unregister(self.registration)
        self.registry.register("companion_v2.memory", CAPABILITY, factory)
        bound = self.bind(limits=ReadLimits(16384, 20000)).unwrap()
        request = self.request(bound)
        bad = dict(request, budget=dict(request["budget"], max_output_bytes=20001))
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, bad).failure.code,
                         "provider_budget_exceeds_binding")
        bad = dict(request, budget=dict(request["budget"], max_input_bytes=1))
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, bad).failure.code,
                         "provider_input_budget_exceeded")
        bad = dict(request, deadline_at=stamp(bound.expires_at + timedelta(seconds=1)))
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, bad).failure.code,
                         "provider_deadline_exceeds_lease")
        self.assertEqual(calls, [])

    def test_malformed_correlated_results_and_private_exceptions_are_not_exposed(self):
        for mutate in (
            lambda result: dict(result, request_id="another-request"),
            lambda result: dict(result, provider_generation="another-generation"),
            lambda result: dict(result, status="failed", output={"private": "must not escape"}),
            lambda result: dict(result, status=[]),
        ):
            with self.subTest(mutate=mutate):
                self.registry.unregister(self.registration)
                def factory(binding):
                    provider = self.read_provider(binding)
                    return replace(provider, invoke=lambda context, request: mutate(provider.invoke(context, request)))
                self.registration = self.registry.register("companion_v2.memory", CAPABILITY, factory)
                bound = self.bind().unwrap()
                self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, self.request(bound)).failure.code,
                                 "provider_result_invalid")
        self.registry.unregister(self.registration)
        def fail(context, request):
            raise RuntimeError("private database path and secrets")
        self.registry.register("companion_v2.memory", CAPABILITY,
            lambda binding: replace(self.read_provider(binding), invoke=fail))
        bound = self.bind().unwrap()
        result = self.registry.invoke(self.context, bound.binding_ref, self.request(bound))
        self.assertEqual(result.failure.code, "provider_invocation_failed")
        self.assertNotIn("secrets", str(result))

    def test_invalid_json_field_types_return_errors_and_do_not_damage_a_valid_lease(self):
        bound = self.bind().unwrap()
        for field, invalid in (("deadline_at", 100), ("budget", None), ("required_features", {}),
                               ("request_id", "x" * 257)):
            with self.subTest(field=field):
                request = self.request(bound) | {field: invalid}
                self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, request).failure.code,
                                 "provider_request_invalid")
        request = self.request(bound)
        request["scope"]["persona_binding_revision"] = float(request["scope"]["persona_binding_revision"])
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, request).failure.code,
                         "provider_binding_scope_mismatch")
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, self.request(bound)).unwrap()["status"],
                         "succeeded")

    def test_late_and_oversized_results_are_not_returned(self):
        def factory(binding):
            provider = self.read_provider(binding)
            def invoke(context, request):
                result = provider.invoke(context, request)
                self.clock.advance(timedelta(seconds=121))
                return result
            return replace(provider, invoke=invoke)
        self.registry.unregister(self.registration)
        self.registration = self.registry.register("companion_v2.memory", CAPABILITY, factory)
        bound = self.bind().unwrap()
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, self.request(bound)).failure.code,
                         "provider_deadline_expired")
        self.registry.unregister(self.registration)
        self.registry.register("companion_v2.memory", CAPABILITY, self.read_provider)
        fresh = self.bind().unwrap()
        request = self.request(fresh)
        request["deadline_at"] = stamp(self.clock.now() + timedelta(seconds=30))
        request["budget"]["max_output_bytes"] = 10
        self.assertEqual(self.registry.invoke(self.context, fresh.binding_ref, request).failure.code,
                         "provider_output_budget_exceeded")

    def test_packaged_readers_require_installation_role_selection_and_exact_consent(self):
        package = CapabilityPackageDescriptor("fixture.memory", "fixture-memory", "publisher", "1", "hash",
                                               ("memory.query",), ("memory",))
        self.registry.unregister(self.registration)
        self.registry.register("companion_v2.memory", CAPABILITY,
            lambda binding: replace(self.read_provider(binding), package=package))
        repo = self.registry.packages
        self.assertEqual(self.registry.discover(self.context, capability_id="memory.query").unwrap(), ())
        repo.register_descriptor(package, registered_at=NOW).unwrap()
        repo.acquire(extension_id=package.extension_id, package_id=package.package_id,
            package_version=package.package_version, expected_revision=0, observed_at=NOW).unwrap()
        repo.set_role_enabled(extension_id=package.extension_id, role=self.context.role_binding.role,
            bot_id=self.context.scope.bot_id, enabled=True, expected_revision=0, observed_at=NOW).unwrap()
        self.assertEqual(self.registry.discover(self.context, capability_id="memory.query").unwrap(), ())
        args = dict(extension_id=package.extension_id, capability_id="memory.query",
                    subject=self.context.actor.subject, scope=self.context.scope, observed_at=NOW)
        repo.set_authorization(**args, state=CapabilityAuthorizationState.ACTIVE, expected_revision=0).unwrap()
        bound = self.bind().unwrap()
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, self.request(bound)).unwrap()["status"], "succeeded")
        repo.set_authorization(**args, state=CapabilityAuthorizationState.REVOKED, expected_revision=1).unwrap()
        self.assertEqual(self.registry.invoke(self.context, bound.binding_ref, self.request(bound)).failure.code,
                         "capability_consent_revoked")

    def test_utf8_profile_conservatively_accounts_for_multibyte_evidence(self):
        self.remember()
        bound = self.bind().unwrap()
        request = self.request(bound)
        request["payload"]["evidence_budget"] = {"max_items": 8, "max_chars": 2400, "max_tokens": 18}
        result = self.registry.invoke(self.context, bound.binding_ref, request).unwrap()
        self.assertEqual(result["status"], "partial", result)
        excerpt = result["output"]["items"][0]["evidence"][0]["excerpt"]
        self.assertLessEqual(len(excerpt.encode("utf-8")), 18)
        self.assertEqual(result["output"]["usage"]["evidence_tokens"], len(excerpt.encode("utf-8")))
        self.assertIn("evidence_tokens_estimated_utf8_bytes", result["warnings"])


if __name__ == "__main__":
    unittest.main()
