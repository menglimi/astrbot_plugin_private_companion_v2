from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from companion_v2.configuration.models import ApplyMode, ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.configuration.contract import contract_of
from companion_v2.configuration.registry import FieldDefinition, FieldRegistry, LegacyProbabilityRule, LegacyProbabilityUnit, ValueKind
from companion_v2.configuration.service import ConfigurationService
from companion_v2.foundation.refs import OperationRef, ScopeKind, ScopeRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)
INSTALLATION = "installation-config"
PRINCIPAL = AuthenticatedHostPrincipal(INSTALLATION, "host-a", "onebot", "account-a")
USER = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-a")
ROLE_A = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-a")
ROLE_B = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-b")
WINDOW = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "window-a")
GLOBAL = ConfigTarget(INSTALLATION, ConfigLayer.INSTALLATION)
ROLE_TARGET = ConfigTarget(INSTALLATION, ConfigLayer.ROLE, ROLE_A)
WINDOW_TARGET = ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE_A, WINDOW)


def registry(*, mode=ApplyMode.NEXT_TASK) -> FieldRegistry:
    return FieldRegistry(version="test-config.v1", fields=(
        FieldDefinition("output.probability", "output", "output", ValueKind.PROBABILITY, 0.25, apply_mode=mode),
        FieldDefinition("output.enabled", "output", "output", ValueKind.BOOLEAN, True, apply_mode=mode),
        FieldDefinition("output.prompt", "output", "output", ValueKind.TEXT, "default", apply_mode=mode),
        FieldDefinition("thought.weight", "thought", "thought", ValueKind.WEIGHT, 1.0),
    ))


class ConfigurationTests(unittest.TestCase):
    def test_text_field_character_limit_is_validated_and_published(self) -> None:
        field = FieldDefinition("prompt.body", "prompt", "prompt", ValueKind.TEXT, "",
                                maximum_chars=4)
        self.assertEqual(field.validate("four"), "four")
        with self.assertRaises(ConfigurationError):
            field.validate("longer")
        registry = FieldRegistry(version="test-config.v1", fields=(field,))
        self.assertEqual(contract_of(registry, "prompt")["body"]["maximum_chars"], 4)

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory(prefix="companion-v2-configuration-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v2-data"
        self.runtime = self.open_runtime()
        self.identity = PersistentIdentityDirectory(self.runtime)
        self.identity.bind(binding_id="binding-a", principal=PRINCIPAL, subject=USER, valid_from=NOW, expected_revision=1)
        self.identity.bind_role(scope=WINDOW, role=ROLE_A, expected_revision=0)
        for index, target in enumerate((GLOBAL, ROLE_TARGET, WINDOW_TARGET, ConfigTarget(INSTALLATION, ConfigLayer.ROLE, ROLE_B))):
            for capability in ("configuration.read", "configuration.write"):
                self.identity.issue_grant(grant_id=f"grant-{index}-{capability}", subject=USER,
                    scope=target.authorization_scope, capability=capability, tier=AuthorizationTier.CORE,
                    valid_from=NOW, expected_revision=self.identity.revision)
        self.actor = self.identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        self.service = ConfigurationService(self.runtime, registry())
        self.operation_sequence = 0

    def open_runtime(self) -> StorageRuntime:
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def read(self, target=WINDOW_TARGET, group="output"):
        return self.service.read(self.actor, target=target, group_id=group, observed_at=NOW).unwrap()

    def operation(self, target):
        self.operation_sequence += 1
        return OperationRef(f"config-op-{self.operation_sequence}", "configuration", target.authorization_scope,
                            VersionRef(f"config-lineage-{self.operation_sequence}", 1), f"config-key-{self.operation_sequence}")

    def save(self, changes, target=WINDOW_TARGET, *, group="output", reset=(), snapshot=None, operation=None):
        snapshot = snapshot or self.read(target, group)
        return self.service.patch(self.actor, target=target, group_id=group,
            operation=operation or self.operation(target), expected_edit_token=snapshot.edit_token,
            changes=changes, reset_to_inherit=reset, observed_at=NOW)

    def status(self, target=WINDOW_TARGET):
        return self.service.application_status(self.actor, target=target, group_id="output", observed_at=NOW).unwrap()

    def report(self, snapshot, generation=1, succeeded=True):
        return self.service.report_application(self.actor, snapshot=snapshot, generation=generation,
                                               succeeded=succeeded, observed_at=NOW)

    def test_inheritance_preserves_zero_false_empty_and_explicit_reset(self) -> None:
        self.save({"output.probability": 0.8}, GLOBAL).unwrap()
        self.save({"output.probability": 0.1}, ROLE_TARGET).unwrap()
        self.assertEqual(self.read().fields["output.probability"].source, ROLE_TARGET)
        self.save({"output.probability": 0, "output.enabled": False, "output.prompt": ""}).unwrap()
        values = self.read()
        self.assertEqual(values.values, {"output.enabled": False, "output.probability": 0.0, "output.prompt": ""})
        self.assertTrue(all(field.explicit for field in values.fields.values()))
        self.save({}, reset=("output.probability",)).unwrap()
        self.assertEqual(self.read().values["output.probability"], 0.1)
        self.assertEqual(self.read().values["output.prompt"], "")
        self.save({}, ROLE_TARGET, reset=("output.probability",)).unwrap()
        self.assertEqual(self.read().values["output.probability"], 0.8)

    def test_stale_page_and_parent_change_roll_back_operation_reservation(self) -> None:
        old = self.read()
        self.save({"output.probability": 0.4}, GLOBAL).unwrap()
        operation = self.operation(WINDOW_TARGET)
        result = self.save({"output.prompt": "stale"}, snapshot=old, operation=operation)
        self.assertEqual(result.failure.code, "configuration_revision_conflict")
        self.assertFalse(self.service.operations.get(operation.operation_id).is_success)
        self.assertEqual(self.read().values["output.prompt"], "default")

    def test_two_connections_cannot_overwrite_each_others_saved_choice(self) -> None:
        other = ConfigurationService(self.open_runtime(), registry())
        stale = self.read()
        other_snapshot = other.read(self.actor, target=WINDOW_TARGET, group_id="output", observed_at=NOW).unwrap()
        other.patch(self.actor, target=WINDOW_TARGET, group_id="output", operation=self.operation(WINDOW_TARGET),
                    expected_edit_token=other_snapshot.edit_token, changes={"output.prompt": "other-manager"},
                    observed_at=NOW).unwrap()
        result = self.save({"output.prompt": "old-page"}, snapshot=stale)
        self.assertEqual(result.failure.code, "configuration_revision_conflict")
        self.assertEqual(self.read().values["output.prompt"], "other-manager")

    def test_lost_response_replay_and_lookup_do_not_reapply_old_value(self) -> None:
        snapshot = self.read()
        operation = self.operation(WINDOW_TARGET)
        first = self.save({"output.probability": 0.01}, snapshot=snapshot, operation=operation).unwrap()
        self.save({"output.probability": 0.7}).unwrap()
        replay = self.save({"output.probability": 0.01}, snapshot=snapshot, operation=operation).unwrap()
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.revision, first.revision)
        self.assertEqual(self.read().values["output.probability"], 0.7)
        found = self.service.receipt(self.actor, target=WINDOW_TARGET, operation_id=operation.operation_id, observed_at=NOW).unwrap()
        self.assertEqual(found.revision, first.revision)
        conflict = self.save({"output.probability": 0.5}, snapshot=snapshot, operation=operation)
        self.assertEqual(conflict.failure.code, "idempotency_key_conflict")

    def test_persistence_failure_rolls_back_values_operation_and_change_event(self) -> None:
        with self.runtime.transaction() as connection:
            connection.execute("""CREATE TRIGGER reject_configuration_change BEFORE INSERT ON configuration_changes
                                  BEGIN SELECT RAISE(ABORT, 'injected change-log failure'); END""")
        operation = self.operation(WINDOW_TARGET)
        with self.assertRaises(sqlite3.IntegrityError):
            self.save({"output.probability": 0.01, "output.enabled": False}, operation=operation)
        self.assertEqual(self.read().values["output.probability"], 0.25)
        self.assertTrue(self.read().values["output.enabled"])
        self.assertFalse(self.service.operations.get(operation.operation_id).is_success)
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) AS n FROM configuration_changes", ())["n"], 0)

    def test_noop_does_not_invalidate_current_consumer_snapshot(self) -> None:
        self.save({"output.probability": 0.1}).unwrap()
        self.service.start_consumer("output", expected_generation=0)
        before = self.read()
        self.report(before).unwrap()
        noop = self.save({"output.probability": 0.1}).unwrap()
        self.assertEqual(noop.changed_fields, ())
        self.assertEqual(self.read().revision, before.revision)
        self.assertEqual(self.status().state, "applied")

    def test_save_is_not_adoption_and_failure_retains_last_adopted_values(self) -> None:
        self.assertEqual(self.status().state, "consumer_not_started")
        self.service.start_consumer("output", expected_generation=0)
        self.assertEqual(self.status().state, "next_task")
        self.report(self.read()).unwrap()
        self.save({"output.probability": 0.01}).unwrap()
        self.assertEqual(self.status().state, "next_task")
        self.assertEqual(self.status().adopted_values["output.probability"], 0.25)
        self.report(self.read(), succeeded=False).unwrap()
        self.assertEqual(self.status().state, "failed")
        self.assertEqual(self.status().adopted_values["output.probability"], 0.25)
        self.report(self.read()).unwrap()
        self.assertEqual(self.status().adopted_values["output.probability"], 0.01)

    def test_stale_and_old_generation_reports_cannot_claim_success(self) -> None:
        self.service.start_consumer("output", expected_generation=0)
        old = self.read()
        self.save({"output.probability": 0.2}).unwrap()
        self.assertEqual(self.report(old).failure.code, "configuration_revision_conflict")
        self.service.start_consumer("output", expected_generation=1)
        self.assertEqual(self.report(self.read(), generation=1).failure.code, "consumer_generation_conflict")
        self.assertEqual(self.status().adopted_values, {})
        self.report(self.read(), generation=2).unwrap()
        other = ConfigurationService(self.open_runtime(), registry())
        self.assertEqual(other.application_status(self.actor, target=WINDOW_TARGET, group_id="output", observed_at=NOW).unwrap().state, "consumer_not_started")

    def test_restart_only_setting_requires_a_new_consumer_generation(self) -> None:
        self.service = ConfigurationService(self.runtime, registry(mode=ApplyMode.RESTART))
        self.service.start_consumer("output", expected_generation=0)
        self.report(self.read()).unwrap()
        self.save({"output.enabled": False}).unwrap()
        self.assertEqual(self.status().state, "restart_required")
        self.assertEqual(self.report(self.read()).failure.code, "configuration_restart_required")
        self.service.start_consumer("output", expected_generation=1)
        self.report(self.read(), generation=2).unwrap()
        self.assertEqual(self.status().state, "applied")

    def test_parent_change_does_not_invalidate_overridden_effective_value(self) -> None:
        self.save({"output.probability": 0.1}).unwrap()
        self.service.start_consumer("output", expected_generation=0)
        self.report(self.read()).unwrap()
        self.save({"output.probability": 0.8}, GLOBAL).unwrap()
        self.assertEqual(self.status().state, "applied")
        self.assertEqual(self.read().values["output.probability"], 0.1)

    def test_change_away_and_back_does_not_reuse_old_application_receipt(self) -> None:
        self.save({"output.probability": 0.1}).unwrap()
        self.service.start_consumer("output", expected_generation=0)
        original = self.read()
        self.report(original).unwrap()
        self.save({"output.probability": 0.2}).unwrap()
        self.save({"output.probability": 0.1}).unwrap()
        self.assertNotEqual(self.read().resolution_token, original.resolution_token)
        self.assertEqual(self.status().state, "next_task")
        self.assertEqual(self.report(original).failure.code, "configuration_revision_conflict")

    def test_change_feed_pages_authorized_group_ancestors_and_excludes_noops(self) -> None:
        self.save({"output.probability": 0.5}, GLOBAL).unwrap()
        self.save({"output.probability": 0.3}, ROLE_TARGET).unwrap()
        self.save({"output.probability": 0.4}).unwrap()
        self.save({"output.probability": 0.4}).unwrap()
        self.save({"thought.weight": 2}, group="thought").unwrap()
        other_role = ConfigTarget(INSTALLATION, ConfigLayer.ROLE, ROLE_B)
        self.save({"output.prompt": "other role only"}, other_role).unwrap()
        first = self.service.changes_since(self.actor, target=WINDOW_TARGET, group_id="output", after=0, limit=2, observed_at=NOW).unwrap()
        self.assertEqual(first.sequences, (1, 2))
        self.assertTrue(first.has_more)
        second = self.service.changes_since(self.actor, target=WINDOW_TARGET, group_id="output", after=first.next_cursor, limit=2, observed_at=NOW).unwrap()
        self.assertEqual(second.sequences, (3,))
        self.assertFalse(second.has_more)
        empty = self.service.changes_since(self.actor, target=WINDOW_TARGET, group_id="output", after=second.next_cursor, observed_at=NOW).unwrap()
        self.assertEqual(empty.sequences, ())
        self.assertEqual(empty.next_cursor, second.next_cursor)

    def test_change_feed_rechecks_permission_and_rejects_unbounded_queries(self) -> None:
        for cursor, limit in ((-1, 10), (True, 10), (0, 0), (0, 101)):
            result = self.service.changes_since(self.actor, target=WINDOW_TARGET, group_id="output", after=cursor, limit=limit, observed_at=NOW)
            self.assertEqual(result.failure.code, "invalid_configuration_cursor")
        self.identity.revoke_grant("grant-2-configuration.read", revoked_at=NOW, expected_revision=self.identity.revision)
        result = self.service.changes_since(self.actor, target=WINDOW_TARGET, group_id="output", after=0, observed_at=NOW)
        self.assertEqual(result.failure.code, "authorization_revoked")

    def test_rebound_role_cannot_receive_old_window_values_or_late_write(self) -> None:
        self.save({"output.prompt": "role-a-only"}).unwrap()
        snapshot = self.read()
        other = PersistentIdentityDirectory(self.open_runtime())
        other.bind_role(scope=WINDOW, role=ROLE_B, expected_revision=1)
        self.assertEqual(self.save({"output.prompt": "late"}, snapshot=snapshot).failure.code, "role_binding_changed")
        new_target = ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE_B, WINDOW)
        self.assertEqual(self.read(new_target).values["output.prompt"], "default")
        other.bind_role(scope=WINDOW, role=ROLE_A, expected_revision=2)
        self.assertEqual(self.save({"output.prompt": "late"}, snapshot=snapshot).failure.code, "configuration_revision_conflict")

    def test_permission_revocation_blocks_write_replay_and_adoption(self) -> None:
        self.service.start_consumer("output", expected_generation=0)
        snapshot = self.read()
        operation = self.operation(WINDOW_TARGET)
        self.save({"output.prompt": "accepted"}, snapshot=snapshot, operation=operation).unwrap()
        other = PersistentIdentityDirectory(self.open_runtime())
        other.revoke_grant("grant-2-configuration.write", revoked_at=NOW, expected_revision=other.revision)
        self.assertEqual(self.save({"output.prompt": "accepted"}, snapshot=snapshot, operation=operation).failure.code, "authorization_revoked")
        latest = self.read()
        other.revoke_grant("grant-2-configuration.read", revoked_at=NOW, expected_revision=other.revision)
        self.assertEqual(self.report(latest).failure.code, "authorization_revoked")

    def test_unknown_key_type_and_out_of_range_do_not_partially_save(self) -> None:
        for bad in ({"unknown": 1}, {"output.probability": 100}, {"output.enabled": 1},
                    {"output.probability": True}, {"output.probability": float("nan")},
                    {"output.probability": ""}, {"output.probability": None}):
            with self.subTest(bad=bad):
                self.assertFalse(self.save({"output.prompt": "must-not-save", **bad}).is_success)
        self.assertEqual(self.read().values["output.prompt"], "default")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) AS n FROM operations", ())["n"], 0)

    def test_new_process_restores_configuration_and_identity_but_not_runtime_adoption(self) -> None:
        self.save({"output.probability": 0.01, "output.enabled": False, "output.prompt": ""}).unwrap()
        self.service.start_consumer("output", expected_generation=0)
        self.report(self.read()).unwrap()
        self.runtime.close()
        script = """
import json, sys
from tests.test_configuration import INSTALLATION, PRINCIPAL, NOW, WINDOW_TARGET, registry
from companion_v2.storage.runtime import StorageRuntime
from companion_v2.configuration.service import ConfigurationService
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
with StorageRuntime.open(data_root=sys.argv[1], installation_id=INSTALLATION) as runtime:
    identity = PersistentIdentityDirectory(runtime)
    actor = identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
    service = ConfigurationService(runtime, registry())
    data = service.read(actor, target=WINDOW_TARGET, group_id='output', observed_at=NOW).unwrap()
    state = service.application_status(actor, target=WINDOW_TARGET, group_id='output', observed_at=NOW).unwrap()
    print(json.dumps({'values': data.values, 'state': state.state, 'binding': actor.binding_id}))
"""
        result = subprocess.run([sys.executable, "-c", script, str(self.root)], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding="utf-8", timeout=20, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["values"], {"output.probability": 0.01, "output.enabled": False, "output.prompt": ""})
        self.assertEqual(data["binding"], "binding-a")
        self.assertEqual(data["state"], "consumer_not_started")

    def test_group_read_work_is_bounded_with_700_and_1500_registered_fields(self) -> None:
        counts = []
        for total in (700, 1500):
            fields = tuple(FieldDefinition(f"field.{i}", f"group.{i // 20}", f"consumer.{i // 20}", ValueKind.INTEGER, i) for i in range(total))
            service = ConfigurationService(self.runtime, FieldRegistry(version="scale.v1", fields=fields))
            targets = (ROLE_TARGET,) + tuple(
                ConfigTarget(INSTALLATION, ConfigLayer.ROLE, SubjectRef(INSTALLATION, SubjectKind.BOT, f"scale-role-{i}"))
                for i in range(9)
            )
            with self.runtime.transaction() as connection:
                connection.execute("DELETE FROM configuration_values WHERE field_id LIKE 'field.%'")
                for target in targets:
                    connection.execute("INSERT OR IGNORE INTO configuration_targets VALUES (?, ?, 1, ?)",
                                       (target.key, json.dumps(target.document()), NOW.isoformat()))
                    connection.executemany("INSERT INTO configuration_values VALUES (?, ?, ?, 1)",
                                           ((target.key, f"field.{i}", json.dumps(i + 1)) for i in range(total)))
            statements = []
            with self.runtime.read_snapshot() as connection:
                connection.set_trace_callback(statements.append)
                try:
                    snapshot = service.read(self.actor, target=WINDOW_TARGET, group_id="group.0", observed_at=NOW).unwrap()
                finally:
                    connection.set_trace_callback(None)
            self.assertEqual(len(snapshot.fields), 20)
            self.assertEqual(snapshot.values["field.0"], 1)
            self.assertEqual(snapshot.fields["field.0"].source, ROLE_TARGET)
            self.assertNotIn("field.20", snapshot.values)
            counts.append(len(statements))
            self.assertEqual(self.runtime.read_one("SELECT COUNT(*) AS n FROM configuration_values", ())["n"], total * 10)
        self.assertEqual(counts[0], counts[1])
        self.assertLessEqual(counts[0], 16)


class ConfigurationUnitTests(unittest.TestCase):
    def test_percent_round_trip_boundaries_and_weight_are_distinct(self) -> None:
        field = registry().fields["output.probability"]
        for shown, stored in (("0", 0), ("0.1", 0.001), ("1", 0.01), ("12.5", 0.125), ("100", 1)):
            with self.subTest(shown=shown):
                value = field.from_percent(shown)
                self.assertEqual(value, stored)
                for _ in range(10):
                    value = field.from_percent(field.to_percent(value))
                self.assertEqual(value, stored)
        for bad in ("", "NaN", "Infinity", "-1", "101", "0.00000001"):
            with self.assertRaises(ConfigurationError):
                field.from_percent(bad)
        weight = registry().fields["thought.weight"]
        self.assertEqual(weight.validate(10), 10)
        for bad in (0, True, float("inf")):
            with self.assertRaises(ConfigurationError):
                weight.validate(bad)
        with self.assertRaises(ConfigurationError):
            weight.from_percent("50")

    def test_legacy_one_uses_registered_unit_and_inheritance_is_explicit(self) -> None:
        field = registry().fields["output.probability"]
        percent = LegacyProbabilityRule("legacy-percent.v1", "voice_chance", LegacyProbabilityUnit.PERCENT, True)
        fraction = LegacyProbabilityRule("legacy-fraction.v1", "voice_chance", LegacyProbabilityUnit.FRACTION)
        self.assertEqual(percent.convert(source_version=percent.source_version, old_key="voice_chance", value=1, field=field), 0.01)
        self.assertEqual(fraction.convert(source_version=fraction.source_version, old_key="voice_chance", value=1, field=field), 1)
        self.assertIsNone(percent.convert(source_version=percent.source_version, old_key="voice_chance", value=-1, field=field))
        with self.assertRaises(ConfigurationError):
            percent.convert(source_version="unknown-version", old_key="voice_chance", value=1, field=field)
        with self.assertRaises(ConfigurationError):
            fraction.convert(source_version=fraction.source_version, old_key="voice_chance", value=-1, field=field)

    def test_registry_rejects_duplicate_fields_invalid_defaults_and_ambiguous_consumers(self) -> None:
        field = registry().fields["output.probability"]
        with self.assertRaises(ValueError):
            FieldRegistry(version="v1", fields=(field, field))
        with self.assertRaises(ConfigurationError):
            replace(field, default=100)
        with self.assertRaises(ValueError):
            FieldRegistry(version="v1", fields=(field, replace(field, field_id="other", consumer_id="different")))
