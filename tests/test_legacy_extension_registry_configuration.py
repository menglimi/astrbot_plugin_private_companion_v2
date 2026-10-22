"""Standalone preferences must reach the shared owner and its real consumers."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest

from companion_v2.configuration.models import ConfigLayer
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.content import authoring_service, cover_assets
from companion_v2.conversation.content.authoring_tasks import authoring_profiles
from companion_v2.legacy.content_configuration import convert_content_configuration
from companion_v2.legacy.memory_configuration import convert_memory_configuration
from companion_v2.legacy.migration import LegacyMigration, MigrationState
from companion_v2.memory.configuration import MemorySettings, configuration_fields as memory_fields
from companion_v2.memory.reflection import reflection_profile
from companion_v2.model_gateway.routing import configuration_fields as model_fields
from tests.proactive_support import ContactFixture


def registry():
    return FieldRegistry(version="legacy-extensions-test", fields=(
        *cover_assets.group_fields(), *memory_fields(),
        *model_fields((*authoring_profiles("primary", draft_tokens=100),
                       reflection_profile("primary", max_output_tokens=100)))))


class RegistryConversionTests(unittest.TestCase):
    def test_summary_models_and_timeout_reach_the_registered_reflection_fields(self):
        result = convert_memory_configuration({"memory_summary": {
            "provider_id": " old-summary ", "fallback_provider_id": "old-backup",
            "private_provider_id": "", "group_provider_id": "", "provider_timeout_seconds": 240}}, registry())
        self.assertEqual(result.changes, {"model.memory.reflect.provider": "old-summary",
            "model.memory.reflect.fallback": "old-backup", "model.memory.reflect.timeout_seconds": 240})
        self.assertNotIn("old-summary", json.dumps(result.differences))

    def test_different_scene_models_are_not_flattened_and_invalid_timeouts_are_not_clamped(self):
        result = convert_memory_configuration({"memory_summary": {
            "provider_id": "common", "private_provider_id": "private-model",
            "provider_timeout_seconds": 601}}, registry())
        self.assertFalse(result.changes)
        self.assertEqual({item["kind"] for item in result.differences},
                         {"scope_review_required", "invalid_value"})
        same = convert_memory_configuration({"memory_summary": {
            "provider_id": "common", "private_provider_id": "common",
            "group_provider_id": "common", "fallback_provider_id": "common"}}, registry())
        self.assertEqual(same.changes, {"model.memory.reflect.provider": "common"})

    def test_content_maps_effective_switches_empty_guidance_and_main_writer(self):
        result = convert_content_configuration({"enabled": False, "creative": {
            "enable_creative_writing": True, "creative_direction_prompt": "",
            "enable_creative_cover_generation": True, "CREATIVE_PROVIDER_ID": " old-writer "},
            "qzone": {"cookie": "secret-marker"}}, registry())
        self.assertEqual(result.changes, {"content.authoring.enabled": False,
            "content.authoring.direction_prompt": "", "content.authoring.cover_enabled": False,
            "model.content.authoring.draft.provider": "old-writer"})
        self.assertNotIn("secret-marker", json.dumps(result.differences))
        self.assertIn("manual_review_required", {item["kind"] for item in result.differences})
        disabled = convert_content_configuration({"enabled": False}, registry())
        self.assertEqual(set(disabled.changes.values()), {False})
        self.assertTrue(all(paths == ("astrbot_plugin_content_companion_config.json:enabled",)
                            for paths in disabled.sources.values()))

    def test_memory_carries_recall_budget_and_accounts_for_scope_semantics(self):
        source = {"memory_injection": {"enabled": True, "top_k": 6, "max_chars": 1800},
                  "scope_control": {"private_recall_enabled": True, "group_recall_enabled": True},
                  "retrieval": {"embedding_provider_id": "private-model-marker"}}
        result = convert_memory_configuration(source, registry())
        self.assertEqual(result.changes, {"memory.context_items": 6, "memory.context_chars": 1800,
                                           "memory.automatic_context": True})
        self.assertNotIn("private-model-marker", json.dumps(result.differences))
        source["scope_control"]["group_recall_enabled"] = False
        result = convert_memory_configuration(source, registry())
        self.assertNotIn("memory.automatic_context", result.changes)
        self.assertIn("scope_review_required", {item["kind"] for item in result.differences})
        source["scope_control"]["private_recall_enabled"] = False
        source["memory_injection"].pop("enabled")
        result = convert_memory_configuration(source, registry())
        self.assertFalse(result.changes["memory.automatic_context"])
        self.assertTrue(all("memory_injection.enabled" not in path
                            for path in result.sources["memory.automatic_context"]))

    def test_wrong_types_and_out_of_range_values_are_reported_without_clamping(self):
        for source in ({"memory_injection": {"top_k": True, "max_chars": 1, "enabled": "false"}},
                       {"memory_injection": {"top_k": 17, "max_chars": 24001}}):
            result = convert_memory_configuration(source, registry())
            self.assertFalse(result.changes)
            self.assertTrue(all(item["kind"] == "invalid_value" for item in result.differences))
        result = convert_content_configuration({"creative": {
            "enable_creative_writing": 1, "CREATIVE_PROVIDER_ID": 42}}, registry())
        self.assertFalse(result.changes)

    def test_standalone_sources_merge_once_per_group_and_win_over_core_defaults(self):
        with TemporaryDirectory() as root:
            plan = LegacyMigration(v1_root=root, configuration_registry=registry(),
                v1_configuration={"model_assignment_config": {"CREATIVE_MODEL_PROVIDER_ID": "core-writer"},
                    "external_memory_config": {"memory_companion_context_top_k": 3}},
                v1_native_configurations={"content": {"creative": {
                    "CREATIVE_PROVIDER_ID": "standalone-writer", "creative_direction_prompt": "prompt-marker"}},
                    "memory": {"memory_injection": {"top_k": 6}}}).plan().unwrap()
        groups = [item.group_id for item in plan.intents if item.target_kind == "configuration_registry"]
        self.assertEqual(len(groups), len(set(groups)))
        by_group = {item.group_id: item for item in plan.intents}
        self.assertEqual(by_group["memory"].changes["context_items"], 6)
        self.assertEqual(by_group["model.content.authoring.draft"].changes["provider"], "standalone-writer")
        self.assertEqual(sum(item["kind"] == "source_precedence" for item in plan.differences), 2)
        self.assertNotIn("prompt-marker", json.dumps(plan.document()))
        states = {item.source_id: item.state for item in plan.findings}
        for name in ("content", "memory"):
            self.assertEqual(states[name + ".configuration"], MigrationState.READY.value)

    def test_changes_to_writable_sources_invalidate_the_review(self):
        with TemporaryDirectory() as root:
            for name, source, changed in (
                ("content", {"enabled": True}, {"enabled": False}),
                ("memory", {"memory_injection": {"top_k": 4}}, {"memory_injection": {"top_k": 6}})):
                with self.subTest(name=name):
                    before = LegacyMigration(v1_root=root, v1_native_configurations={name: source})
                    after = LegacyMigration(v1_root=root, v1_native_configurations={name: changed})
                    self.assertNotEqual(before.configuration_context_fingerprint,
                                        after.configuration_context_fingerprint)


class RegistryHostMigrationTests(ContactFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from astrbot_host.legacy_api import LegacyMigrationWebAPI
        self.profiles += authoring_profiles("primary", draft_tokens=100)
        self.profiles += (reflection_profile("primary", max_output_tokens=100),)
        self.registry = FieldRegistry(version="extension-host-test", fields=model_fields(self.profiles))
        self.providers += (replace(self.providers[0], binding=replace(
            self.providers[0].binding, provider="legacy-writer")),)
        self.providers += tuple(replace(self.providers[0], binding=replace(
            self.providers[0].binding, provider=name)) for name in ("legacy-summary", "legacy-backup"))
        self.app = self.host().application
        self.context = self.contact_context()
        self.session = NS(application=self.app, profile=NS(target=self.context))
        self.api = LegacyMigrationWebAPI(NS(runtime=self.runtime, now=self.clock.now))
        self.api._operator = lambda: self.core
        temporary = TemporaryDirectory(prefix="extension-registry-host-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def plan(self):
        return LegacyMigration(v1_root=self.root, configuration_registry=self.app.configuration.registry,
            v1_native_configurations={"content": {"creative": {"enable_creative_writing": False,
                "creative_direction_prompt": "private-instruction-marker",
                "enable_creative_cover_generation": True, "CREATIVE_PROVIDER_ID": "legacy-writer"}},
                "memory": {"memory_injection": {"enabled": False, "top_k": 6, "max_chars": 1800}}}
            ).plan().unwrap()

    def apply(self, intents):
        for intent in intents:
            target = self.api._scope_target(self.session, intent)
            self.assertIn(target.layer, (ConfigLayer.INSTALLATION, ConfigLayer.ROLE))
            before = self.app.configuration._snapshot(self.core, target, intent.group_id,
                                                       self.clock.now(), "configuration.read")
            self.api._apply_intent(intent, self.session, before)

    async def test_saved_preferences_reach_consumers_in_other_windows_and_are_idempotent(self):
        plan = self.plan()
        intents, _, _, _ = self.api._prepare_intents(self.session, plan)
        self.assertEqual({item.group_id for item in intents}, {
            "memory", "content.authoring", "model.content.authoring.draft"})
        self.apply(intents)
        for context in (self.context, self.other_window_context()):
            settings = authoring_service.effective_settings(self.runtime, context)
            self.assertFalse(settings.enabled)
            self.assertEqual(settings.direction_prompt, "private-instruction-marker")
            policy = MemorySettings(self.app.configuration).policy(context)
            self.assertFalse(policy.automatic_context)
            self.assertEqual((policy.context_items, policy.context_chars), (6, 1800))
            request = NS(event=NS(source=None), context=NS(materials=()))
            route = self.app.router.selected_route(context, "content.authoring.draft", request, at=self.clock.now())
            self.assertEqual(route[0], "legacy-writer")
        again, differences, _, _ = self.api._prepare_intents(self.session, plan)
        self.assertFalse(again)
        self.assertIn("already_present", {item["kind"] for item in differences})
        self.assertNotIn("private-instruction-marker", json.dumps(differences))
        self.assertFalse(self.called)
        self.assertFalse(self.sent)

    async def test_newer_explicit_preferences_are_preserved_and_prompts_stay_redacted(self):
        initial, _, _, _ = self.api._prepare_intents(self.session, self.plan())
        modified = [replace(item, changes={key: ("new-instruction-marker" if key == "direction_prompt" else value)
                    for key, value in item.changes.items()}) for item in initial]
        self.apply(modified)
        intents, differences, _, _ = self.api._prepare_intents(self.session, self.plan())
        self.assertFalse(intents)
        self.assertTrue(any(item["kind"] == "preserved_v2" for item in differences))
        self.assertNotIn("instruction-marker", json.dumps(differences))
        self.assertEqual(authoring_service.effective_settings(self.runtime, self.context).direction_prompt,
                         "new-instruction-marker")

    async def test_summary_routes_are_saved_for_the_role_and_used_from_other_windows(self):
        plan = LegacyMigration(v1_root=self.root, configuration_registry=self.app.configuration.registry,
            v1_native_configurations={"memory": {"memory_summary": {
                "provider_id": "legacy-summary", "fallback_provider_id": "legacy-backup",
                "provider_timeout_seconds": 240}}}).plan().unwrap()
        intents, _, _, _ = self.api._prepare_intents(self.session, plan)
        self.assertEqual(len(intents), 1)
        self.apply(intents)
        for context in (self.context, self.other_window_context()):
            request = NS(event=NS(source=None), context=NS(materials=()))
            route = self.app.router.selected_route(context, "memory.reflect", request, at=self.clock.now())
            self.assertEqual(route[0], "legacy-summary")
            self.assertEqual(tuple(provider.binding.provider for provider in route[2]),
                             ("legacy-summary", "legacy-backup"))
        target = self.api._scope_target(self.session, intents[0])
        saved = self.app.configuration.read(self.core, target=target,
            group_id="model.memory.reflect", observed_at=self.clock.now()).unwrap()
        self.assertEqual(saved.fields["model.memory.reflect.timeout_seconds"].value, 240)
        self.assertFalse(self.called)
        self.assertFalse(self.sent)


if __name__ == "__main__":
    unittest.main()
