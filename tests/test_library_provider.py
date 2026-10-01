"""The shelf as a read provider: registry contract, envelope echo and its own fences.

These go through the real ``ReadProviderRegistry`` so the request/result envelope is
checked by the same code production uses, not by a stub that agrees with itself.
"""

from datetime import timedelta
import unittest

from companion_v2.capabilities.read_providers import ReadLimits, ReadProviderRegistry
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.registry import FieldDefinition, FieldRegistry
from companion_v2.configuration.service import ConfigurationService
from companion_v2.execution.models import TaskError, require, stamp
from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.identity_policy.personas import RuntimeIdentity
from companion_v2.library.configuration import LibraryConfigurationOwner, configuration_fields as library_fields
from companion_v2.library.models import AssetReference, EntryKind, EntryState
from companion_v2.library.provider import (CATALOG_CAPABILITY, READ_CAPABILITY,
                                           make_catalog_provider, make_read_provider)
from companion_v2.library.service import ReadingArchiveService
from tests.memory_support import MemoryFixture
from tests.test_management_access import NOW


class ShelfFixture(MemoryFixture):
    """Common assembly plus the two real writes the shelf tests need."""

    def setUp(self):
        super().setUp()
        # The shelf group must be registered like any other group; the shared
        # fixture only installs its own two demonstration fields.
        self.configuration = ConfigurationService(
            self.runtime,
            FieldRegistry(version="library.v1",
                          fields=tuple(self.registry.fields.values()) + library_fields()),
            owners=(LibraryConfigurationOwner(self.runtime),))
        self.archive = ReadingArchiveService(self.runtime, self.tasks, self.configuration)
        # Two real authorization requirements, both exercised rather than bypassed:
        # reading the role's shelf settings needs configuration.read on the target's
        # role-level scope, and the shelf declares its own access actions.
        self.grant(self.important, self.library_target().authorization_scope, "configuration.read")
        self.grant(self.core, self.library_target().authorization_scope, "configuration.read")
        self.grant(self.core, self.library_target().authorization_scope, "configuration.write")
        self.grant(self.important, self.context.scope, "library.catalog")
        self.grant(self.important, self.context.scope, "library.read")

    def library_target(self):
        return ConfigTarget(self.context.scope.installation_id, ConfigLayer.ROLE,
                            self.context.role_binding.role, bot_id=self.context.scope.bot_id)

    def enable_shelf(self, **changes):
        """Turn the group on through the same patch path the page uses."""
        target = self.library_target()
        snapshot = self.configuration.read(self.core, target=target, group_id="library",
                                           observed_at=NOW).unwrap()
        return self.configuration.patch(
            self.core, target=target, group_id="library",
            operation=OperationRef("library-op-1", "library", target.authorization_scope,
                                   VersionRef("library-lineage-1", 1), "library-key-1"),
            expected_edit_token=snapshot.edit_token,
            changes={"library.enabled": True, **changes}, observed_at=NOW)
    def add_novel(self, entry_id="novel-1", *, state=EntryState.AVAILABLE):
        return self.archive.register_provider_entry(
            self.context, entry_id=entry_id, kind=EntryKind.NOVEL.value, title="长夜漫漫",
            author="某人", source=AssetReference("library.native", "1.0", "novel://" + entry_id),
            state=state).unwrap()


class ShelfProviderTests(ShelfFixture):
    def setUp(self):
        super().setUp()
        self.enable_shelf().unwrap()
        self.runtime_identity = RuntimeIdentity("companion", "shelf-runtime", "astrbot", "host")
        self.registry = ReadProviderRegistry(
            self.tasks, require_running=lambda: require(self.tasks.check_generation()))
        self.catalog_registration = self.registry.register(
            "companion_v2.library", CATALOG_CAPABILITY,
            lambda binding: make_catalog_provider(self.archive, binding,
                                                  runtime_identity=self.runtime_identity))
        self.read_registration = self.registry.register(
            "companion_v2.library", READ_CAPABILITY,
            lambda binding: make_read_provider(self.archive, binding,
                                               runtime_identity=self.runtime_identity))

    def bind(self, capability, **changes):
        options = {"capability_id": capability.capability_id, "capability_version": capability.capability_version,
                   "provider_id": "companion_v2.library"} | changes
        return self.registry.bind(self.context, **options)

    def request(self, capability, binding, payload, *, request_id="shelf-request-1"):
        return {
            "schema_version": capability.input_schema,
            "capability_id": capability.capability_id,
            "capability_version": capability.capability_version,
            "provider_id": binding.provider.provider,
            "provider_generation": binding.provider.generation,
            "request_id": request_id,
            "trace_id": "shelf-trace-1",
            "deadline_at": stamp(NOW + timedelta(minutes=2)),
            "scope": binding.scope,
            "required_features": [],
            # Never above the binding's negotiated limits: the registry refuses that.
            "budget": {"max_input_bytes": binding.limits.max_input_bytes,
                       "max_output_bytes": binding.limits.max_output_bytes},
            "payload": payload,
        }

    # --- catalog -----------------------------------------------------------------

    def test_catalog_lists_registered_entries_without_asset_bytes(self):
        self.add_novel()
        binding = self.bind(CATALOG_CAPABILITY).unwrap()
        result = self.registry.invoke(self.context, binding.binding_ref,
                                      self.request(CATALOG_CAPABILITY, binding, {"operation": "list"})).unwrap()
        self.assertEqual(result["status"], "succeeded")
        entries = result["output"]["entries"]
        self.assertEqual([entry["entry_id"] for entry in entries], ["novel-1"])
        # A listing names the asset reference but never carries its content.
        self.assertEqual(entries[0]["source"]["asset_ref"], "novel://novel-1")
        self.assertNotIn("content", entries[0])
        self.assertNotIn("text", entries[0])

    def test_catalog_lookup_by_entry_id(self):
        self.add_novel()
        binding = self.bind(CATALOG_CAPABILITY).unwrap()
        result = self.registry.invoke(self.context, binding.binding_ref,
            self.request(CATALOG_CAPABILITY, binding, {"operation": "get", "entry_id": "novel-1"})).unwrap()
        self.assertEqual(len(result["output"]["entries"]), 1)
        self.assertEqual(result["output"]["entries"][0]["title"], "长夜漫漫")

    def test_an_unsupported_catalog_operation_is_rejected_not_raised(self):
        binding = self.bind(CATALOG_CAPABILITY).unwrap()
        result = self.registry.invoke(self.context, binding.binding_ref,
            self.request(CATALOG_CAPABILITY, binding, {"operation": "delete"})).unwrap()
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason_code"], "library_operation_unsupported")
        self.assertIsNone(result["output"])

    def test_a_missing_entry_is_a_rejected_result_with_a_reason(self):
        binding = self.bind(CATALOG_CAPABILITY).unwrap()
        result = self.registry.invoke(self.context, binding.binding_ref,
            self.request(CATALOG_CAPABILITY, binding, {"operation": "get", "entry_id": "nope"})).unwrap()
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason_code"], "archive_entry_missing")

    def test_the_declared_feature_is_required_by_the_registry(self):
        # Registry entry points return outcomes; only unwrapping turns one into a raise.
        with self.assertRaises(RuntimeError) as caught:
            self.bind(CATALOG_CAPABILITY, required_features=("asset.excerpt",)).unwrap()
        self.assertIn("provider_feature_unavailable", str(caught.exception))

    # --- read --------------------------------------------------------------------

    def test_reading_returns_the_reference_and_the_configured_excerpt_bound(self):
        self.add_novel()
        binding = self.bind(READ_CAPABILITY).unwrap()
        result = self.registry.invoke(self.context, binding.binding_ref,
            self.request(READ_CAPABILITY, binding, {"entry_id": "novel-1"})).unwrap()
        output = result["output"]
        self.assertEqual(output["source"]["provider_id"], "library.native")
        self.assertEqual(output["source"]["asset_ref"], "novel://novel-1")
        self.assertEqual(output["excerpt_chars"], 1200)
        # The bytes themselves are the provider's; the shelf never returns them.
        self.assertNotIn("content", output)

    def test_a_manual_entry_has_no_provider_asset_to_read(self):
        self.archive.add_manual_entry(self.context, entry_id="manual-1",
                                      kind=EntryKind.OTHER.value, title="随手记").unwrap()
        binding = self.bind(READ_CAPABILITY).unwrap()
        result = self.registry.invoke(self.context, binding.binding_ref,
            self.request(READ_CAPABILITY, binding, {"entry_id": "manual-1"})).unwrap()
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason_code"], "library_asset_unavailable")

    def test_a_withdrawn_entry_cannot_be_read(self):
        self.add_novel()
        self.archive.withdraw_provider(self.context, "library.native").unwrap()
        binding = self.bind(READ_CAPABILITY).unwrap()
        result = self.registry.invoke(self.context, binding.binding_ref,
            self.request(READ_CAPABILITY, binding, {"entry_id": "novel-1"})).unwrap()
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason_code"], "library_entry_withdrawn")

    def test_a_revoked_consent_stops_the_read(self):
        self.add_novel()
        self.archive.set_consent(self.context, "novel-1", subject=self.context.actor.subject,
                                 granted=False).unwrap()
        binding = self.bind(READ_CAPABILITY).unwrap()
        result = self.registry.invoke(self.context, binding.binding_ref,
            self.request(READ_CAPABILITY, binding, {"entry_id": "novel-1"})).unwrap()
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason_code"], "library_consent_revoked")

    def test_the_result_envelope_echoes_the_original_call(self):
        self.add_novel()
        binding = self.bind(READ_CAPABILITY).unwrap()
        result = self.registry.invoke(self.context, binding.binding_ref,
            self.request(READ_CAPABILITY, binding, {"entry_id": "novel-1"},
                         request_id="shelf-request-echo")).unwrap()
        self.assertEqual(result["request_id"], "shelf-request-echo")
        self.assertEqual(result["trace_id"], "shelf-trace-1")
        self.assertEqual(result["provider_id"], "companion_v2.library")
        self.assertEqual(result["provider_generation"], binding.provider.generation)
        self.assertEqual(result["capability_id"], READ_CAPABILITY.capability_id)
        self.assertEqual(result["capability_version"], READ_CAPABILITY.capability_version)
        self.assertEqual(result["schema_version"], READ_CAPABILITY.output_schema)

    def test_a_request_that_echoes_the_wrong_generation_is_refused(self):
        self.add_novel()
        binding = self.bind(READ_CAPABILITY).unwrap()
        request = self.request(READ_CAPABILITY, binding, {"entry_id": "novel-1"})
        request["provider_generation"] = "not-the-bound-generation"
        with self.assertRaises(RuntimeError) as caught:
            self.registry.invoke(self.context, binding.binding_ref, request).unwrap()
        self.assertIn("provider_request_binding_mismatch", str(caught.exception))

    def test_a_request_with_a_foreign_scope_is_refused(self):
        self.add_novel()
        binding = self.bind(READ_CAPABILITY).unwrap()
        request = self.request(READ_CAPABILITY, binding, {"entry_id": "novel-1"})
        request["scope"] = {**binding.scope, "installation_id": "another-installation"}
        with self.assertRaises(RuntimeError) as caught:
            self.registry.invoke(self.context, binding.binding_ref, request).unwrap()
        self.assertIn("provider_binding_scope_mismatch", str(caught.exception))

    def test_discovery_lists_both_shelf_capabilities(self):
        discovered = self.registry.discover(self.context, capability_id="library.read").unwrap()
        self.assertEqual([entry["capability"]["capability_id"] for entry in discovered], ["library.read"])
        catalog = self.registry.discover(self.context, capability_id="library.catalog").unwrap()
        self.assertEqual([entry["capability"]["capability_id"] for entry in catalog], ["library.catalog"])


class ShelfDisabledTests(ShelfFixture):
    """With the group off, the shelf refuses before any provider is involved."""

    def _code(self, call):
        """The refusal code for one call, whether it raises or returns an outcome."""
        try:
            result = call()
        except TaskError as error:
            return error.code
        if result.failure is not None:
            return result.failure.code
        self.fail("the shelf accepted a call while the group was off")

    def test_every_entry_point_is_closed_while_the_shelf_is_off(self):
        self.assertEqual(self._code(lambda: self.archive.list_entries(self.context)), "library_disabled")
        self.assertEqual(self._code(lambda: self.archive.register_provider_entry(
            self.context, entry_id="novel-1", kind=EntryKind.NOVEL.value, title="长夜漫漫",
            author="", source=AssetReference("library.native", "1.0", "novel://1"))), "library_disabled")
        self.assertEqual(self._code(lambda: self.archive.add_manual_entry(
            self.context, entry_id="manual-1", kind=EntryKind.OTHER.value, title="随手记")),
            "library_disabled")
        self.assertEqual(self._code(lambda: self.archive.record_review(
            self.context, review_id="review-1", entry_id="novel-1", body="读后感", rating=4,
            evidence=("position:chapter=1",))), "library_disabled")

    def test_the_shelf_is_off_until_the_group_says_otherwise(self):
        """Off is the default, so an installation that never edits the group is unaffected."""
        settings = self.archive.settings.read(self.context, self.tasks.now())
        self.assertFalse(settings["enabled"])
        self.enable_shelf().unwrap()
        self.assertTrue(self.archive.settings.read(self.context, self.tasks.now())["enabled"])

    def test_manual_entries_can_be_switched_off_without_closing_the_shelf(self):
        self.enable_shelf(**{"library.manual_entries_enabled": False}).unwrap()
        self.archive.register_provider_entry(
            self.context, entry_id="novel-1", kind=EntryKind.NOVEL.value, title="长夜漫漫",
            author="", source=AssetReference("library.native", "1.0", "novel://1")).unwrap()
        self.assertEqual(self._code(lambda: self.archive.add_manual_entry(
            self.context, entry_id="manual-1", kind=EntryKind.OTHER.value, title="随手记")),
            "library_manual_disabled")

    def test_reviews_can_be_switched_off_without_closing_the_shelf(self):
        self.enable_shelf(**{"library.reviews_enabled": False}).unwrap()
        self.add_novel()
        self.assertEqual(self._code(lambda: self.archive.record_review(
            self.context, review_id="review-1", entry_id="novel-1", body="读后感", rating=4,
            evidence=("position:chapter=1",))), "library_reviews_disabled")


if __name__ == "__main__":
    unittest.main()
