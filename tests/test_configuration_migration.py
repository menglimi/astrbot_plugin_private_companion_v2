"""Focused contracts for the audited, broad V1 configuration converter."""

from __future__ import annotations

import csv
import json
from contextlib import closing
from pathlib import Path
import unittest

from companion_v2.configuration.models import ConfigLayer
from companion_v2.configuration.registry import FieldDefinition, FieldRegistry, ValueKind
from companion_v2.legacy.configuration_migration import (
    configuration_audit_sources,
    configuration_rules,
    configuration_exclusions,
    convert_account_configuration,
    convert_configuration,
    convert_plugin_configuration,
    convert_semantic_configuration,
    unmapped_configuration_differences,
    plugin_configuration_defaults,
    plugin_configuration_rules,
    semantic_configuration_rules,
)


def rule(source, source_type, target, confidence="high"):
    return {"source": source, "source_type": source_type, "target": target, "confidence": confidence}


def plugin_rule(source, source_type, target, transform, contract, confidence="high"):
    return {"source": source, "source_type": source_type, "target": target,
            "transform": transform, "contract": contract, "confidence": confidence}


def registry(field_id, kind, default, **bounds):
    group = field_id.rpartition(".")[0]
    return FieldRegistry(version="configuration-migration.test", fields=(
        FieldDefinition(field_id, group, group, kind, default, **bounds),
    ))


def segmentation_registry():
    group = "conversation.presentation"
    definitions = (
        ("enabled", ValueKind.BOOLEAN, False, {}),
        ("threshold", ValueKind.INTEGER, 500, {"minimum": 1, "maximum": 65536}),
        ("min_segment_chars", ValueKind.INTEGER, 5, {"minimum": 1, "maximum": 65536}),
        ("max_segments", ValueKind.INTEGER, 5, {"minimum": 1, "maximum": 64}),
        ("part_gap_mode", ValueKind.TEXT, "fixed", {}),
        ("part_gap_ms", ValueKind.INTEGER, 0, {"minimum": 0, "maximum": 60000}),
        ("part_gap_min_ms", ValueKind.INTEGER, 1500, {"minimum": 100, "maximum": 60000}),
        ("part_gap_max_ms", ValueKind.INTEGER, 3500, {"minimum": 100, "maximum": 60000}),
        ("part_gap_log_base", ValueKind.WEIGHT, 1.8, {"minimum": 1.1, "maximum": 5.0}),
    )
    return FieldRegistry(version="configuration-migration.segmentation", fields=tuple(
        FieldDefinition(f"{group}.{name}", group, group, kind, default, **bounds)
        for name, kind, default, bounds in definitions
    ))


class RuleTableTests(unittest.TestCase):
    def _ledger_rows(self):
        path = Path(__file__).resolve().parents[1] / "docs" / "V1_V2_CONFIG_RESOLVED_20260928.csv"
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_generated_table_covers_the_audited_registry_mappings(self):
        rules = configuration_rules()

        self.assertEqual(len(rules), 346)
        self.assertEqual(sum(item["confidence"] == "high" for item in rules), 280)
        self.assertEqual(sum(item["confidence"] == "medium" for item in rules), 66)
        self.assertEqual(len({item["source"] for item in rules}), len(rules))

        expected = {row["v1_key"] for row in self._ledger_rows()
                    if row["resolved_kind"] == "registry"
                    and row["verified_verdict"] in {"already-in-v2", "renamed-equivalent"}
                    and row["verified_confidence"] in {"high", "medium"}}
        specialized = {
            "legacy_compat_config.segmented_proactive_image_strategy",
            "legacy_compat_config.segmented_proactive_voice_strategy",
            "legacy_compat_config.segmented_proactive_at_strategy",
        }
        self.assertEqual({item["source"] for item in rules}, expected - specialized
                         - {"voice_action_config.tts_message_scope"})
        self.assertEqual({item["source"] for item in configuration_exclusions()}, {
            "emotion_relationship_config.enable_smart_silence",
            "voice_action_config.tts_message_scope",
        })

    def test_audit_inventory_covers_every_ledger_source_once(self):
        sources = configuration_audit_sources()
        ledger = {row["v1_key"] for row in self._ledger_rows()}
        self.assertEqual(len(sources), len(ledger))
        self.assertEqual({item["source"] for item in sources}, ledger)
        self.assertEqual(len({item["source"] for item in sources}), len(sources))

    def test_native_image_api_queue_is_audited_as_v2_owned(self):
        by_source = {item["source"]: item for item in configuration_audit_sources()}
        endpoints = by_source["photo_action_config.external_image_api_endpoints"]
        self.assertEqual(endpoints["resolved_kind"], "external")
        self.assertEqual(endpoints["target"], "image.output.endpoints")
        self.assertEqual(endpoints["verdict"], "implemented-elsewhere")
        self.assertIn("V2 原生 Image 拓展", endpoints["summary"])

        headers = by_source["photo_action_config.external_image_api_custom_headers"]
        self.assertEqual(headers["verdict"], "not-migrated-by-design")

    def test_new_image_and_mood_fields_have_audited_targets(self):
        by_source = {item["source"]: item for item in configuration_rules()}
        self.assertEqual(by_source["message_debounce_config.enable_private_image_self_recognition"]["target"],
                         "conversation.presentation.enable_private_image_self_recognition")
        self.assertEqual(by_source["group_observation_config.enable_group_image_understanding"]["target"],
                         "conversation.presentation.image_understanding_group_enabled")
        self.assertEqual(by_source["experimental_motivation_config.enable_emotion_simulation"]["target"],
                         "role.state.mood_enabled")
        self.assertNotIn("emotion_relationship_config.enable_smart_silence", by_source)

    def test_audit_differences_explain_unmapped_values_without_exposing_them(self):
        config = {"forward_message_config": {"forward_message_image_vision_timeout_seconds": 37},
                  "reactive_poke_config": {"reactive_poke_back_prompts": ["private prompt"]},
                  "emotion_relationship_config": {"enable_smart_silence": True}}
        differences = unmapped_configuration_differences(config)
        by_source = {item.source_key: item for item in differences}
        expected = {
            "forward_message_config.forward_message_image_vision_timeout_seconds",
            "reactive_poke_config.reactive_poke_back_prompts",
            "emotion_relationship_config.enable_smart_silence",
        }
        self.assertEqual(set(by_source), expected)
        self.assertEqual(by_source["emotion_relationship_config.enable_smart_silence"].kind, "not_migrated")
        self.assertIn("独立阻塞步骤", by_source[
            "forward_message_config.forward_message_image_vision_timeout_seconds"].summary)
        self.assertNotIn("private prompt", json.dumps([item.document() for item in differences], ensure_ascii=False))

    def test_partial_image_and_state_mappings_are_explained(self):
        image = next(item for item in configuration_rules()
                     if item["source"] == "message_debounce_config.enable_private_image_self_recognition")
        state = next(item for item in configuration_rules()
                     if item["source"] == "humanized_state_config.enable_humanized_states")
        image_result = convert_configuration(
            {"message_debounce_config": {"enable_private_image_self_recognition": False}},
            registry=registry(image["target"], ValueKind.BOOLEAN, True), rules=(image,),
        )
        state_result = convert_configuration(
            {"humanized_state_config": {"enable_humanized_states": False}},
            registry=registry(state["target"], ValueKind.BOOLEAN, True), rules=(state,),
        )

        self.assertFalse(image_result.changes[image["target"]])
        self.assertIn("partial_mapping", {item.kind for item in image_result.differences})
        self.assertFalse(state_result.changes[state["target"]])
        self.assertIn("partial_mapping", {item.kind for item in state_result.differences})

    def test_recent_targets_exist_in_the_live_domain_field_contracts(self):
        from companion_v2.conversation.reply_settings import configuration_fields as reply_fields
        from companion_v2.conversation.segmentation import SegmentationPolicy
        from companion_v2.role_work.state.configuration import configuration_fields as state_fields

        runtime_registry = FieldRegistry(version="configuration-migration.live-fields",
            fields=(*reply_fields(SegmentationPolicy(enabled=False), True, 1.5), *state_fields()))
        rules = {item["source"]: item for item in configuration_rules()}
        sources = (
            "message_debounce_config.enable_private_image_self_recognition",
            "group_observation_config.enable_group_image_understanding",
            "experimental_motivation_config.enable_emotion_simulation",
        )
        config = {
            "message_debounce_config": {"enable_private_image_self_recognition": False},
            "group_observation_config": {"enable_group_image_understanding": False},
            "experimental_motivation_config": {"enable_emotion_simulation": True},
        }
        migration = convert_configuration(config, registry=runtime_registry,
            rules=tuple(rules[source] for source in sources))

        self.assertEqual(migration.changes, {
            "conversation.presentation.enable_private_image_self_recognition": False,
            "conversation.presentation.image_understanding_group_enabled": False,
            "role.state.mood_enabled": True,
        })
        for field_id, value in migration.changes.items():
            self.assertEqual(runtime_registry.fields[field_id].validate(value), value)

    def test_plugin_rules_point_to_schema_fields_with_explicit_contracts(self):
        rules = plugin_configuration_rules()
        schema = json.loads((Path(__file__).resolve().parents[1] / "_conf_schema.json").read_text(encoding="utf-8"))

        self.assertEqual(len(rules), 45)
        for rule in rules:
            section, _, name = rule["target"].partition(".")
            self.assertIn(name, schema[section]["items"], rule["target"])
            self.assertEqual(rule["contract"]["type"], schema[section]["items"][name]["type"])

    def test_tts_message_scope_is_reported_without_changing_the_v2_proactive_voice_switch(self):
        source = "voice_action_config.tts_message_scope"
        migration = convert_configuration({
            "voice_action_config": {"tts_message_scope": "replies_and_proactive"},
        }, registry=registry("proactive.contact.voice_action_enabled", ValueKind.BOOLEAN, False))
        self.assertEqual(migration.changes, {})
        self.assertEqual(len(migration.differences), 1)
        self.assertEqual(migration.differences[0].kind, "not_migrated")
        self.assertEqual(migration.differences[0].source_key, source)
        self.assertIn("主动语音使用独立授权策略", migration.differences[0].summary)

    def test_weather_context_is_reserved_for_the_weather_converter(self):
        migration = convert_configuration({
            "weather_config": {"enable_weather_context": True},
        }, registry=registry("proactive.contact.weather_checkin_enabled", ValueKind.BOOLEAN, False))
        self.assertNotIn("proactive.contact.weather_checkin_enabled", migration.changes)

    def test_semantic_rules_point_to_store_settings_with_explicit_contracts(self):
        from companion_v2.storage.semantic import DEFAULTS, INTEGER_LIMITS, PROBABILITY_FIELDS, SETTING_OPTIONS

        rules = semantic_configuration_rules()
        self.assertEqual(len(rules), 15)
        expected = {row["v1_key"] for row in self._ledger_rows()
                    if row["resolved_kind"] == "semantic-config"}
        self.assertEqual({item["source"] for item in rules}, expected)
        for rule in rules:
            group, _, field = rule["target"].partition(".")
            self.assertEqual(group, "semantic")
            self.assertIn(field, DEFAULTS)
            self.assertEqual(rule["contract"]["default"], DEFAULTS[field])
            if field in INTEGER_LIMITS:
                self.assertEqual((rule["contract"]["minimum"], rule["contract"]["maximum"]),
                                 INTEGER_LIMITS[field])
            if field in PROBABILITY_FIELDS:
                self.assertEqual((rule["contract"]["minimum"], rule["contract"]["maximum"]), (0, 1))
            if field in SETTING_OPTIONS:
                self.assertEqual(tuple(rule["contract"]["options"]), SETTING_OPTIONS[field])

    def test_plugin_mapping_exclusions_require_deliberate_reclassification(self):
        eligible = {row["v1_key"] for row in self._ledger_rows()
                    if row["resolved_kind"] == "plugin-config"
                    and row["verified_verdict"] in {"already-in-v2", "renamed-equivalent"}
                    and row["verified_confidence"] in {"high", "medium"}}
        actual = {item["source"] for item in plugin_configuration_rules()}
        account_configuration = {
            "basic_config.bot_scope_mode",
            "basic_config.bot_scope_ids",
            "basic_config.plugin_specific_persona_id",
            "basic_config.enable_multi_persona_mode",
            "basic_config.multi_persona_ids",
            "basic_config.target_user_ids",
            "group_observation_config.enable_group_companion",
            "group_observation_config.group_whitelist_ids",
            "legacy_compat_config.target_group_ids",
        }
        manual_review = {
            "message_debounce_config.enable_message_debounce",
            "model_fallback_overrides",
            "model_token_limit_overrides",
            "task_prompt_overrides",
        }

        self.assertEqual(eligible - actual, manual_review | account_configuration)
        self.assertIn("forward_message_config.forward_message_max_messages", actual)

    def test_account_migration_rules_cover_the_audited_identity_settings(self):
        eligible = {row["v1_key"] for row in self._ledger_rows()
                    if row["resolved_kind"] == "plugin-config"
                    and row["verified_verdict"] in {"already-in-v2", "renamed-equivalent"}
                    and row["verified_confidence"] in {"high", "medium"}}
        handled = {
            "basic_config.bot_scope_mode", "basic_config.bot_scope_ids",
            "basic_config.plugin_specific_persona_id", "basic_config.enable_multi_persona_mode",
            "basic_config.multi_persona_ids", "basic_config.target_user_ids",
            "group_observation_config.enable_group_companion",
            "group_observation_config.group_whitelist_ids", "legacy_compat_config.target_group_ids",
        }

        self.assertTrue(handled.issubset(eligible))


class AccountConfigurationMigrationTests(unittest.TestCase):
    @staticmethod
    def accounts():
        return [
            {"platform_id": "qq-main", "account_id": "100", "bot_id": "bot-100",
             "persona_roles": {"persona-a": "role-100-a", "persona-b": "role-100-b",
                               "[%None]": "role-100-default", "": "role-100-default"}},
            {"platform_id": "qq-main", "account_id": "101", "bot_id": "bot-101",
             "persona_roles": {"persona-a": "role-101-a", "persona-b": "role-101-b",
                               "[%None]": "role-101-default", "": "role-101-default"}},
        ]

    def test_scope_targets_groups_and_loaded_personas_are_mapped_precisely(self):
        result = convert_account_configuration({
            "basic_config": {
                "bot_scope_mode": "allowlist",
                "bot_scope_ids": ["100"],
                "target_user_ids": ["200", "invalid-id"],
                "plugin_specific_persona_id": "persona-b",
                "enable_multi_persona_mode": True,
                "multi_persona_ids": ["persona-a", "persona-missing"],
            },
            "group_observation_config": {
                "enable_group_companion": True,
                "group_access_mode": "whitelist",
                "group_whitelist_ids": ["300"],
            },
            "legacy_compat_config": {"target_group_ids": ["301"]},
        }, accounts=self.accounts())

        self.assertEqual(result.changes["multi_host.targets"][0]["account_id"], "100")
        self.assertEqual(result.changes["multi_host.targets"][0]["participant_id"], "200")
        self.assertEqual(len(result.changes["multi_host.targets"]), 1)
        self.assertEqual([item["group_id"] for item in result.changes["multi_host.group_targets"]], ["300"])
        self.assertEqual(result.changes["multi_host.personas"], [
            {"bot_id": "bot-100", "persona_id": "persona-b", "role_id": "role-100-b"},
            {"bot_id": "bot-100", "persona_id": "persona-a", "role_id": "role-100-a"},
        ])
        self.assertIn("basic_config.plugin_specific_persona_id", result.sources["multi_host.personas"])
        self.assertIn("basic_config.multi_persona_ids", result.sources["multi_host.personas"])
        self.assertNotIn("multi_host.enabled", result.changes)
        self.assertIn("group_precedence", {item.kind for item in result.differences})
        self.assertIn("invalid_value", {item.kind for item in result.differences})
        self.assertIn("unavailable_persona", {item.kind for item in result.differences})

    def test_unknown_scope_mode_and_unloaded_persona_do_not_create_routes(self):
        result = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "unknown", "target_user_ids": ["200"],
                             "plugin_specific_persona_id": "not-loaded"},
        }, accounts=self.accounts())

        self.assertEqual(result.changes, {})
        self.assertIn("invalid_value", {item.kind for item in result.differences})
        self.assertIn("unavailable", {item.kind for item in result.differences})

    def test_one_private_target_maps_to_the_single_target_identity(self):
        result = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "allowlist", "bot_scope_ids": ["100"],
                             "target_user_ids": ["200"], "plugin_specific_persona_id": "persona-a"},
        }, accounts=self.accounts())

        self.assertEqual(result.changes["target.platform_id"], "qq-main")
        self.assertEqual(result.changes["target.account_id"], "100")
        self.assertEqual(result.changes["target.participant_id"], "200")
        self.assertEqual(result.changes["target.role_id"], "role-100-a")
        self.assertEqual(result.changes["target.persona_id"], "persona-a")

    def test_group_blacklist_and_disabled_group_companion_are_not_widened(self):
        base = {"basic_config": {"bot_scope_mode": "all"},
                "group_observation_config": {"enable_group_companion": True,
                                              "group_access_mode": "blacklist",
                                              "group_whitelist_ids": ["300"]}}
        blacklisted = convert_account_configuration(base, accounts=self.accounts())
        self.assertNotIn("multi_host.group_targets", blacklisted.changes)
        self.assertIn("unsupported_mode", {item.kind for item in blacklisted.differences})

        base["group_observation_config"]["group_access_mode"] = "whitelist"
        base["group_observation_config"]["enable_group_companion"] = False
        disabled = convert_account_configuration(base, accounts=self.accounts())
        self.assertNotIn("multi_host.group_targets", disabled.changes)
        self.assertIn("disabled_source", {item.kind for item in disabled.differences})

        legacy_blacklist = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "all"},
            "group_observation_config": {"enable_group_companion": True,
                                          "group_whitelist_ids": ["300"]},
            "legacy_compat_config": {"require_target_group": False},
        }, accounts=self.accounts())
        self.assertNotIn("multi_host.group_targets", legacy_blacklist.changes)
        self.assertIn("unsupported_mode", {item.kind for item in legacy_blacklist.differences})

    def test_legacy_group_target_alias_fills_an_empty_new_whitelist(self):
        result = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "all", "plugin_specific_persona_id": "persona-a"},
            "group_observation_config": {"enable_group_companion": True,
                                          "group_whitelist_ids": []},
            "legacy_compat_config": {"target_group_ids": ["301"]},
        }, accounts=self.accounts())

        self.assertEqual({item["group_id"] for item in result.changes["multi_host.group_targets"]}, {"301"})

    def test_bot_denylist_excludes_matching_accounts(self):
        result = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "denylist", "bot_scope_ids": ["100"],
                             "target_user_ids": ["200"], "plugin_specific_persona_id": "persona-a"},
        }, accounts=self.accounts())

        self.assertEqual({item["account_id"] for item in result.changes["multi_host.targets"]}, {"101"})

    def test_multi_platform_accounts_and_personas_map_from_one_configuration(self):
        accounts = [
            {"platform_id": "qq-onebot", "account_id": "100", "bot_id": "bot-qq",
             "persona_roles": {"persona-a": "role-qq-a", "persona-b": "role-qq-b"}},
            {"platform_id": "other-onebot", "account_id": "200", "bot_id": "bot-other",
             "persona_roles": {"persona-a": "role-other-a", "persona-b": "role-other-b"}},
        ]
        result = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "all", "target_user_ids": ["300"],
                             "enable_multi_persona_mode": True,
                             "multi_persona_ids": ["persona-a", "persona-b"]},
        }, accounts=accounts)

        self.assertEqual({item["platform_id"] for item in result.changes["multi_host.targets"]},
                         {"qq-onebot", "other-onebot"})
        self.assertEqual({(item["bot_id"], item["persona_id"]) for item in
                          result.changes["multi_host.personas"]},
                         {("bot-qq", "persona-a"), ("bot-qq", "persona-b"),
                          ("bot-other", "persona-a"), ("bot-other", "persona-b")})

    def test_ambiguous_allowlist_id_does_not_fan_out_across_platforms(self):
        accounts = [
            {"platform_id": "qq-onebot", "account_id": "100", "bot_id": "bot-qq",
             "persona_roles": {"persona-a": "role-qq-a"}},
            {"platform_id": "other-onebot", "account_id": "100", "bot_id": "bot-other",
             "persona_roles": {"persona-a": "role-other-a"}},
        ]
        result = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "allowlist", "bot_scope_ids": ["100"],
                             "target_user_ids": ["300"], "plugin_specific_persona_id": "persona-a"},
        }, accounts=accounts)

        self.assertNotIn("multi_host.targets", result.changes)
        self.assertIn("ambiguous_account", {item.kind for item in result.differences})

    def test_missing_scope_with_multiple_accounts_is_not_guessed(self):
        result = convert_account_configuration({"basic_config": {"target_user_ids": ["200"]}},
                                               accounts=self.accounts())

        self.assertEqual(result.changes, {})
        self.assertIn("needs_input", {item.kind for item in result.differences})

    def test_missing_persona_selection_never_expands_the_loaded_catalog(self):
        result = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "all", "target_user_ids": ["200"]},
        }, accounts=self.accounts())

        self.assertEqual(result.changes, {})
        self.assertIn("needs_input", {item.kind for item in result.differences})

    def test_authoritative_default_persona_maps_only_that_persona_and_its_role(self):
        accounts = self.accounts()[:1]
        accounts[0]["default_persona_id"] = "persona-b"
        accounts[0]["default_role_id"] = "unused-no-persona-role"
        result = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "all", "target_user_ids": ["200"]},
        }, accounts=accounts)

        self.assertEqual(result.changes["multi_host.personas"], [
            {"bot_id": "bot-100", "persona_id": "persona-b", "role_id": "role-100-b"},
        ])
        self.assertEqual(result.changes["target.persona_id"], "persona-b")
        self.assertEqual(result.changes["target.role_id"], "role-100-b")

    def test_authoritative_no_persona_binding_keeps_the_default_role(self):
        accounts = self.accounts()[:1]
        accounts[0]["default_persona_id"] = ""
        result = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "all", "target_user_ids": ["200"]},
        }, accounts=accounts)

        self.assertEqual(result.changes["multi_host.personas"], [
            {"bot_id": "bot-100", "persona_id": "[%None]", "role_id": "role-100-default"},
        ])
        self.assertEqual(result.changes["target.persona_id"], "")
        self.assertEqual(result.changes["target.role_id"], "role-100-default")

    def test_primary_persona_in_the_multi_list_is_not_mapped_twice(self):
        result = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "all", "target_user_ids": ["200"],
                             "plugin_specific_persona_id": "persona-a", "enable_multi_persona_mode": True,
                             "multi_persona_ids": ["persona-a", "persona-b"]},
        }, accounts=self.accounts()[:1])

        self.assertEqual([row["persona_id"] for row in result.changes["multi_host.personas"]],
                         ["persona-a", "persona-b"])


class SemanticStoreMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_existing_settings_as_explicit(self):
        import sqlite3
        from tempfile import TemporaryDirectory

        from companion_v2.storage.semantic import SemanticStore

        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "semantic-catalog.sqlite3"
            with closing(sqlite3.connect(path)) as connection:
                with connection as db:
                    db.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)")
                    db.execute("INSERT INTO settings VALUES (1, 7, ?)",
                               (json.dumps({"reactions_enabled": False, "timeout_seconds": 12}),))
                    db.execute("PRAGMA user_version=4")

            store = SemanticStore(Path(temporary))
            snapshot = store.configuration_snapshot()

            self.assertEqual(snapshot["revision"], 7)
            self.assertFalse(snapshot["values"]["reactions_enabled"])
            self.assertEqual(snapshot["values"]["timeout_seconds"], 12)
            self.assertEqual(snapshot["explicit"], {"reactions_enabled", "timeout_seconds"})
            with store.db() as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 8)

    def test_newly_configured_settings_are_marked_explicit(self):
        from tempfile import TemporaryDirectory

        from companion_v2.storage.semantic import SemanticStore

        with TemporaryDirectory() as temporary:
            store = SemanticStore(Path(temporary))
            before = store.configuration_snapshot()
            store.configure({"reactions_enabled": False}, before["revision"])

            after = store.configuration_snapshot()
            self.assertFalse(after["values"]["reactions_enabled"])
            self.assertIn("reactions_enabled", after["explicit"])


class ValueConversionTests(unittest.TestCase):
    def test_grouped_value_wins_over_a_conflicting_flat_compatibility_value(self):
        result = convert_configuration(
            {"settings": {"enabled": True}, "settings.enabled": False},
            registry=registry("settings.enabled", ValueKind.BOOLEAN, False),
            rules=(rule("settings.enabled", "bool", "settings.enabled"),),
        )

        self.assertEqual(result.changes, {"settings.enabled": True})
        self.assertEqual([item.kind for item in result.differences], ["group_precedence"])

    def test_conflicting_aliases_are_reported_and_not_arbitrarily_overwritten(self):
        result = convert_configuration(
            {"old_a": {"value": True}, "old_b": {"value": False}},
            registry=registry("target.settings.enabled", ValueKind.BOOLEAN, False),
            rules=(rule("old_a.value", "bool", "target.settings.enabled"),
                   rule("old_b.value", "bool", "target.settings.enabled")),
        )

        self.assertEqual(result.changes, {})
        self.assertEqual([item.kind for item in result.differences], ["conflict"])
        self.assertIn("old_a.value", result.differences[0].summary)
        self.assertIn("old_b.value", result.differences[0].summary)


class WindowedSegmentationMigrationTests(unittest.TestCase):
    def component_registry(self):
        fields = (
            FieldDefinition("conversation.presentation.image_position", "conversation.presentation",
                            "conversation.presentation", ValueKind.TEXT, "after_text"),
            FieldDefinition("conversation.presentation.voice_position", "conversation.presentation",
                            "conversation.presentation", ValueKind.TEXT, "after_media"),
        )
        return FieldRegistry(version="configuration-migration.components", fields=fields)

    def test_inline_media_strategies_map_to_v2_component_positions(self):
        result = convert_configuration({"legacy_compat_config": {
            "segmented_proactive_image_strategy": "inline",
            "segmented_proactive_voice_strategy": "inline",
        }}, registry=self.component_registry())

        self.assertEqual(result.changes, {
            "conversation.presentation.image_position": "after_text",
            "conversation.presentation.voice_position": "after_text",
        })
        self.assertNotIn("conflict", {item.kind for item in result.differences})

    def test_separate_and_cross_part_media_strategies_are_reported_without_guessing(self):
        for strategy in ("separate", "previous", "next"):
            with self.subTest(strategy=strategy):
                result = convert_configuration({"legacy_compat_config": {
                    "segmented_proactive_image_strategy": strategy,
                }}, registry=self.component_registry())
                self.assertEqual(result.changes, {})
                self.assertEqual([item.kind for item in result.differences], ["strategy_not_representable"])

    def test_inline_at_strategy_is_already_covered_by_v2_default_order(self):
        result = convert_configuration({"legacy_compat_config": {
            "segmented_proactive_at_strategy": "inline",
        }}, registry=self.component_registry())

        self.assertEqual(result.changes, {})
        self.assertEqual([item.kind for item in result.differences], ["already_represented"])

    def test_profile_defaults_do_not_conflict_with_the_global_master_switch(self):
        result = convert_configuration({"legacy_compat_config": {
            "enable_segmented_proactive_reply": False,
            "enable_segmented_proactive_chat_profiles": True,
            "segmented_proactive_private_enabled": True,
            "segmented_proactive_group_enabled": True,
            "segmented_proactive_threshold": 500,
            "segmented_proactive_private_threshold": 320,
            "segmented_proactive_group_threshold": 680,
        }}, registry=segmentation_registry(), window_kind="private")

        self.assertFalse(result.changes["conversation.presentation.enabled"])
        self.assertEqual(result.changes["conversation.presentation.threshold"], 320)
        self.assertNotIn("conflict", {item.kind for item in result.differences})

        group = convert_configuration({"legacy_compat_config": {
            "enable_segmented_proactive_reply": False,
            "enable_segmented_proactive_chat_profiles": True,
            "segmented_proactive_private_enabled": True,
            "segmented_proactive_group_enabled": True,
            "segmented_proactive_threshold": 500,
            "segmented_proactive_private_threshold": 320,
            "segmented_proactive_group_threshold": 680,
        }}, registry=segmentation_registry(), window_kind="group")
        self.assertFalse(group.changes["conversation.presentation.enabled"])
        self.assertEqual(group.changes["conversation.presentation.threshold"], 680)

    def test_private_and_group_profile_values_migrate_to_the_selected_window(self):
        config = {"legacy_compat_config": {
            "enable_segmented_proactive_reply": True,
            "enable_segmented_proactive_chat_profiles": True,
            "segmented_proactive_private_enabled": False,
            "segmented_proactive_group_enabled": True,
            "segmented_proactive_threshold": 500,
            "segmented_proactive_private_threshold": 300,
            "segmented_proactive_group_threshold": 700,
            "segmented_proactive_private_min_segment_chars": 4,
            "segmented_proactive_group_min_segment_chars": 9,
            "segmented_proactive_private_max_segments": 2,
            "segmented_proactive_group_max_segments": 6,
        }}

        private = convert_configuration(config, registry=segmentation_registry(), window_kind="private")
        group = convert_configuration(config, registry=segmentation_registry(), window_kind="group")
        self.assertFalse(private.changes["conversation.presentation.enabled"])
        self.assertEqual(private.changes["conversation.presentation.threshold"], 300)
        self.assertEqual(private.changes["conversation.presentation.min_segment_chars"], 4)
        self.assertEqual(private.changes["conversation.presentation.max_segments"], 2)
        self.assertTrue(group.changes["conversation.presentation.enabled"])
        self.assertEqual(group.changes["conversation.presentation.threshold"], 700)
        self.assertEqual(group.changes["conversation.presentation.min_segment_chars"], 9)
        self.assertEqual(group.changes["conversation.presentation.max_segments"], 6)
        self.assertNotIn("conflict", {item.kind for item in private.differences + group.differences})

    def test_legacy_chat_scope_and_global_settings_apply_when_profiles_are_off(self):
        config = {"legacy_compat_config": {
            "enable_segmented_proactive_reply": True,
            "enable_segmented_proactive_chat_profiles": False,
            "segmented_proactive_chat_scope": "private",
            "segmented_proactive_threshold": 425,
            "segmented_proactive_private_threshold": 300,
            "segmented_proactive_group_threshold": 800,
        }}

        private = convert_configuration(config, registry=segmentation_registry(), window_kind="private")
        group = convert_configuration(config, registry=segmentation_registry(), window_kind="group")
        self.assertTrue(private.changes["conversation.presentation.enabled"])
        self.assertFalse(group.changes["conversation.presentation.enabled"])
        self.assertEqual(private.changes["conversation.presentation.threshold"], 425)
        self.assertEqual(group.changes["conversation.presentation.threshold"], 425)

    def test_profile_interval_seconds_map_to_v2_random_spacing_fields(self):
        result = convert_configuration({"legacy_compat_config": {
            "enable_segmented_proactive_reply": True,
            "enable_segmented_proactive_chat_profiles": True,
            "segmented_proactive_private_interval_method": "random",
            "segmented_proactive_private_interval_min": 0.4,
            "segmented_proactive_private_interval_max": 1.25,
        }}, registry=segmentation_registry(), window_kind="private")

        self.assertEqual(result.changes["conversation.presentation.part_gap_mode"], "random")
        self.assertEqual(result.changes["conversation.presentation.part_gap_min_ms"], 400)
        self.assertEqual(result.changes["conversation.presentation.part_gap_max_ms"], 1250)
        self.assertNotIn("conversation.presentation.part_gap_ms", result.changes)
        self.assertNotIn("conflict", {item.kind for item in result.differences})

    def test_missing_interval_method_uses_v1_log_default_if_spacing_values_exist(self):
        result = convert_configuration({"legacy_compat_config": {
            "enable_segmented_proactive_chat_profiles": True,
            "segmented_proactive_group_interval_min": 0.8,
            "segmented_proactive_group_interval_max": 2.2,
        }}, registry=segmentation_registry(), window_kind="group")

        self.assertEqual(result.changes["conversation.presentation.part_gap_mode"], "log")
        self.assertEqual(result.changes["conversation.presentation.part_gap_min_ms"], 800)
        self.assertEqual(result.changes["conversation.presentation.part_gap_max_ms"], 2200)

    def test_invalid_window_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            convert_configuration({}, registry=segmentation_registry(), window_kind="all")

    def test_integer_percent_probability_is_converted_to_a_fraction(self):
        result = convert_configuration(
            {"old": {"chance": 72}},
            registry=registry("target.settings.chance", ValueKind.PROBABILITY, 0.5),
            rules=(rule("old.chance", "int", "target.settings.chance"),),
        )

        self.assertEqual(result.changes, {"target.settings.chance": 0.72})

    def test_duration_units_are_converted_when_both_fields_name_their_units(self):
        result = convert_configuration(
            {"old": {"interval_minutes": 3}},
            registry=registry("target.settings.interval_seconds", ValueKind.INTEGER, 60, minimum=60, maximum=600),
            rules=(rule("old.interval_minutes", "int", "target.settings.interval_seconds"),),
        )

        self.assertEqual(result.changes, {"target.settings.interval_seconds": 180})

    def test_json_list_values_are_encoded_for_json_text_fields(self):
        result = convert_configuration(
            {"old": {"words": ["别复读", "先确认"]}},
            registry=registry("target.settings.words", ValueKind.TEXT, "[]"),
            rules=({**rule("old.words", "list", "target.settings.words", "medium"), "list_format": "json"},),
        )

        self.assertEqual(json.loads(result.changes["target.settings.words"]), ["别复读", "先确认"])
        self.assertEqual(result.confidence["target.settings.words"], "medium")

    def test_knowledge_source_ids_use_the_consumers_delimited_format(self):
        source_rule = next(item for item in configuration_rules() if item["target"] == "knowledge.source_ids")
        result = convert_configuration(
            {"life_schedule_config": {"roleplay_knowledge_source_ids": ["lore-a", "lore-b"]}},
            registry=registry("knowledge.source_ids", ValueKind.TEXT, "", maximum_chars=4000),
            rules=(source_rule,),
        )

        self.assertEqual(result.changes["knowledge.source_ids"], "lore-a\nlore-b")
        from companion_v2.knowledge.configuration import _configured_list
        self.assertEqual(_configured_list(result.changes["knowledge.source_ids"], limit=8),
                         ("lore-a", "lore-b"))

    def test_plugin_configuration_converts_percentages_and_boolean_modes(self):
        result = convert_plugin_configuration({
            "voice_action_config": {"tts_trigger_probability": 72},
            "auto_voice_config": {"auto_voice_enabled": True},
        }, rules=(
            plugin_rule("voice_action_config.tts_trigger_probability", "int",
                        "voice_reply.probability", "percent",
                        {"type": "float", "minimum": 0, "maximum": 1}),
            plugin_rule("auto_voice_config.auto_voice_enabled", "bool",
                        "voice_reply.trigger_mode", "bool_to_voice_trigger",
                        {"type": "string", "options": ["always", "request", "adaptive"]}),
        ))

        self.assertEqual(result.changes, {
            "voice_reply.probability": 0.72,
            "voice_reply.trigger_mode": "always",
        })

    def test_weather_source_maps_to_the_global_plugin_setting(self):
        result = convert_plugin_configuration({
            "weather_config": {"weather_source": "qweather"},
        })

        self.assertEqual(result.changes, {"weather.provider": "qweather"})
        self.assertEqual(result.sources["weather.provider"], ("weather_config.weather_source",))
        self.assertEqual(plugin_configuration_defaults()["weather.provider"], "auto")

    def test_v1_global_full_probability_preserves_automatic_voice_when_auto_switch_is_off(self):
        source = {"voice_action_config": {"tts_frequency_control_mode": "global", "tts_trigger_probability": 100,
                  "tts_private_trigger_probability": -1, "tts_group_trigger_probability": -1},
                  "auto_voice_config": {"auto_voice_enabled": False}}
        converted = convert_plugin_configuration(source)
        self.assertEqual(converted.changes["voice_reply.trigger_mode"], "always")
        self.assertEqual(converted.changes["voice_reply.private_probability"], -1.0)
        self.assertEqual(converted.changes["voice_reply.group_probability"], -1.0)
        self.assertIn("voice_action_config.tts_frequency_control_mode", converted.sources["voice_reply.trigger_mode"])
        source["voice_action_config"]["tts_frequency_control_mode"] = "legacy"
        self.assertEqual(convert_plugin_configuration(source).changes["voice_reply.trigger_mode"], "request")

    def test_v1_voice_probability_force_respects_the_window_override(self):
        source = {"voice_action_config": {"tts_frequency_control_mode": "global", "tts_trigger_probability": 100,
                  "tts_private_trigger_probability": -1, "tts_group_trigger_probability": 20},
                  "auto_voice_config": {"auto_voice_enabled": False}}
        self.assertEqual(convert_plugin_configuration(source).changes["voice_reply.trigger_mode"], "request")
        self.assertEqual(convert_plugin_configuration(source, window_kind="private").changes["voice_reply.trigger_mode"], "always")
        self.assertEqual(convert_plugin_configuration(source, window_kind="group").changes["voice_reply.trigger_mode"], "request")

    def test_weather_source_aliases_are_normalized_and_unsupported_sources_are_explained(self):
        for source in ("open-meteo", "open_meteo", "openmeteo"):
            with self.subTest(source=source):
                result = convert_plugin_configuration({"weather_config": {"weather_source": source}})
                self.assertEqual(result.changes, {"weather.provider": "open-meteo"})

        unsupported = convert_plugin_configuration({
            "weather_config": {"weather_source": "openweathermap"},
        })
        self.assertEqual(unsupported.changes, {})
        self.assertEqual(unsupported.differences[0].kind, "invalid_value")
        self.assertIn("没有与此旧天气来源等价", unsupported.differences[0].summary)

    def test_qweather_host_and_credential_map_to_host_only_weather_settings(self):
        credential = "a" * 32
        result = convert_plugin_configuration({
            "weather_config": {
                "weather_source": "qweather",
                "weather_api_host": "api.qweatherapi.com",
                "weather_token": credential,
            },
        })

        self.assertEqual(result.changes, {
            "weather.api_host": "api.qweatherapi.com",
            "weather.credential": credential,
            "weather.provider": "qweather",
        })
        self.assertEqual(plugin_configuration_defaults()["weather.api_host"], "")
        self.assertEqual(plugin_configuration_defaults()["weather.credential"], "")

    def test_plugin_configuration_accepts_reviewed_legacy_number_formats(self):
        rules = {item["source"]: item for item in plugin_configuration_rules()}
        result = convert_plugin_configuration({
            "forward_message_config": {"forward_message_max_messages": 48},
            "legacy_compat_config": {"maintenance_token_soft_limit": "640000"},
        }, rules=(rules["forward_message_config.forward_message_max_messages"],
                 rules["legacy_compat_config.maintenance_token_soft_limit"]))

        self.assertEqual(result.changes, {
            "runtime.forward_max_nodes": 48,
            "runtime.daily_token_soft_limit": 640000,
        })
        self.assertEqual(result.confidence["runtime.forward_max_nodes"], "medium")

    def test_plugin_mapping_conflicts_and_invalid_enum_values_are_reported(self):
        result = convert_plugin_configuration({
            "voice_action_config": {"tts_session_min_interval_seconds": 30,
                                     "tts_private_min_interval_seconds": 45,
                                     "tts_generation_mode": "unrecognized"},
        }, rules=(
            plugin_rule("voice_action_config.tts_session_min_interval_seconds", "float",
                        "voice_reply.cooldown_seconds", "integer",
                        {"type": "int", "minimum": 0, "maximum": 86400}),
            plugin_rule("voice_action_config.tts_private_min_interval_seconds", "float",
                        "voice_reply.cooldown_seconds", "integer",
                        {"type": "int", "minimum": 0, "maximum": 86400}),
            plugin_rule("voice_action_config.tts_generation_mode", "string",
                        "voice_reply.generation_mode", "identity",
                        {"type": "string", "options": ["plain", "model_tag"]}),
        ))

        self.assertEqual(result.changes, {})
        self.assertEqual({item.kind for item in result.differences}, {"conflict", "invalid_value"})

    def test_semantic_settings_convert_units_and_keep_conflicting_provider_aliases_out(self):
        result = convert_semantic_configuration({
            "model_assignment_config": {"EMBEDDING_PROVIDER_ID": "embed-a"},
            "experimental_motivation_config": {
                "REACTION_EXPRESSION_EMBEDDING_PROVIDER_ID": "embed-b",
                "reaction_expression_trigger_probability": 0.65,
                "reaction_expression_cooldown_seconds": 240,
                "reaction_expression_embedding_timeout_ms": 5000,
            },
            "relay_bridge_config": {"group_slang_summary_minutes": 20},
            "group_slang_topic_config": {"enable_group_slang_learning": False},
        })

        self.assertEqual(result.changes, {
            "semantic.reactions_trigger_probability": 0.65,
            "semantic.reactions_cooldown_seconds": 240,
            "semantic.timeout_seconds": 5,
            "semantic.learning_interval_seconds": 1200,
            "semantic.slang_learning": False,
        })
        self.assertEqual([item.kind for item in result.differences], ["conflict"])
        self.assertIn("EMBEDDING_PROVIDER_ID", result.differences[0].summary)

    def test_semantic_mapping_rejects_values_that_v2_cannot_represent(self):
        result = convert_semantic_configuration({
            "experimental_motivation_config": {"reaction_expression_embedding_timeout_ms": 0},
            "relay_bridge_config": {"group_slang_summary_minutes": 2000},
        })

        self.assertEqual(result.changes, {})
        self.assertEqual({item.kind for item in result.differences}, {"invalid_value"})

    def test_out_of_range_values_are_explained_instead_of_written(self):
        result = convert_configuration(
            {"old": {"limit": 101}},
            registry=registry("target.settings.limit", ValueKind.INTEGER, 10, minimum=0, maximum=100),
            rules=(rule("old.limit", "int", "target.settings.limit"),),
        )

        self.assertEqual(result.changes, {})
        self.assertEqual(result.differences[0].kind, "invalid_value")

    def test_missing_runtime_field_is_reported_as_unavailable(self):
        result = convert_configuration(
            {"old": {"limit": 2}}, registry=registry("other.settings.enabled", ValueKind.BOOLEAN, False),
            rules=(rule("old.limit", "int", "target.settings.limit"),),
        )

        self.assertEqual(result.changes, {})
        self.assertEqual(result.differences[0].kind, "unavailable")


class SkillGrowthScheduleMigrationTests(unittest.TestCase):
    target = "role.growth.skills.schedule_influence_strength"
    master_switch = "role.growth.skills.enabled"

    def convert(self, config):
        return convert_configuration(
            config,
            registry=registry(self.target, ValueKind.INTEGER, 0, minimum=0, maximum=3),
        )

    def test_disabled_v1_switch_migrates_to_zero_and_ignores_saved_strength(self):
        result = self.convert({"skill_growth_config": {
            "enable_skill_growth_schedule_influence": False,
            "skill_growth_schedule_influence_strength": 0.8,
        }})

        self.assertEqual(result.changes[self.target], 0)
        self.assertEqual(result.confidence[self.target], "high")
        self.assertIn("inactive_source", {item.kind for item in result.differences})

    def test_fractional_v1_strength_is_quantized_to_the_v2_tier(self):
        result = self.convert({"skill_growth_config": {
            "enable_skill_growth_schedule_influence": True,
            "skill_growth_schedule_influence_strength": 0.35,
        }})

        self.assertEqual(result.changes[self.target], 2)
        self.assertEqual(result.confidence[self.target], "medium")
        self.assertIn("quantized", {item.kind for item in result.differences})

    def test_enabled_v1_switch_uses_its_default_strength_when_missing(self):
        result = self.convert({"skill_growth_config": {
            "enable_skill_growth_schedule_influence": True,
        }})

        self.assertEqual(result.changes[self.target], 2)
        self.assertEqual(result.confidence[self.target], "medium")
        self.assertIn("derived_default", {item.kind for item in result.differences})

    def test_quantization_is_reported_in_the_upper_tier_too(self):
        result = self.convert({"skill_growth_config": {
            "enable_skill_growth_schedule_influence": True,
            "skill_growth_schedule_influence_strength": 0.9,
        }})

        self.assertEqual(result.changes[self.target], 3)
        self.assertIn("quantized", {item.kind for item in result.differences})

    def test_exact_endpoint_strength_does_not_report_quantization(self):
        result = self.convert({"skill_growth_config": {
            "enable_skill_growth_schedule_influence": True,
            "skill_growth_schedule_influence_strength": 1.0,
        }})

        self.assertEqual(result.changes[self.target], 3)
        self.assertNotIn("quantized", {item.kind for item in result.differences})

    def test_out_of_range_v1_strength_is_reported_and_not_migrated(self):
        for strength in (-0.01, 1.01):
            with self.subTest(strength=strength):
                result = self.convert({"skill_growth_config": {
                    "enable_skill_growth_schedule_influence": True,
                    "skill_growth_schedule_influence_strength": strength,
                }})

                self.assertNotIn(self.target, result.changes)
                self.assertIn("invalid_value", {item.kind for item in result.differences})

    def test_legacy_master_switch_maps_to_the_v2_automatic_consumption_switch(self):
        migration_rules = tuple(item for item in configuration_rules()
                                if item["target"] == self.master_switch)
        result = convert_configuration(
            {"skill_growth_config": {"enable_skill_growth_simulation": False}},
            registry=registry(self.master_switch, ValueKind.BOOLEAN, True),
            rules=migration_rules,
        )

        self.assertEqual(result.changes, {self.master_switch: False})
        self.assertEqual(result.confidence[self.master_switch], "medium")

    def test_missing_legacy_master_switch_keeps_the_v2_default(self):
        migration_rules = tuple(item for item in configuration_rules()
                                if item["target"] == self.master_switch)
        result = convert_configuration(
            {"skill_growth_config": {}},
            registry=registry(self.master_switch, ValueKind.BOOLEAN, True),
            rules=migration_rules,
        )

        self.assertEqual(result.changes, {})


if __name__ == "__main__":
    unittest.main()
