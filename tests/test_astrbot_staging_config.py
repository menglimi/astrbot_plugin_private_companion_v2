from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from companion_v2.adapters.astrbot.staging_config import (
    MAX_CONFIG_BYTES, REBINDING_FIELDS, SCOPE_IDENTITY_KEYS, StagingConfiguration,
    StagingConfigurationError,
)
from companion_v2.conversation.segmentation import SegmentationPolicy
from companion_v2.execution.models import SupervisorLimits, digest
from companion_v2.model_gateway.budget import BudgetSoftPolicy
from companion_v2.model_gateway.models import Amount, BudgetPolicy
from tests.native_adapter_support import FakeHostContext
from tests.staging_bootstrap_support import synthetic_configuration


class StagingConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = synthetic_configuration(FakeHostContext())
        self.document = self.config.document()
        # The soft ceiling is a late field: it belongs to the current document shape and
        # is absent from a profile an older host already pinned.
        self.document["budget_soft"] = {"enabled": False, "tokens": 0, "kinds": []}

    def parse(self, document):
        return StagingConfiguration.parse(json.dumps(document, ensure_ascii=False))

    def test_roundtrip_is_order_independent_and_normalizes_timezone(self):
        doc = self.document
        doc["access"]["valid_from"] = "2026-09-21T08:00:00+08:00"
        doc["access"]["capabilities"].reverse()
        restored = self.parse(dict(reversed(list(doc.items()))))
        self.assertEqual(restored, self.config)
        self.assertEqual(restored.fingerprint, self.config.fingerprint)
        self.assertEqual(self.parse(restored.document()).document(), restored.document())

    def test_legacy_budget_amount_shape_is_optional_and_keeps_its_hash(self):
        legacy = deepcopy(self.document)
        detail_fields = ("input_tokens", "cached_input_tokens", "cache_creation_tokens", "output_tokens")
        for amount in legacy["budget"].values():
            for name in detail_fields:
                amount.pop(name)

        restored = self.parse(legacy)

        self.assertEqual(restored.fingerprint, digest(legacy))
        for amount in (restored.budget.installation, restored.budget.bot, restored.budget.role,
                       restored.budget.window, restored.budget.background):
            self.assertTrue(all(getattr(amount, name) is None for name in detail_fields))

    def test_explicit_empty_prompt_and_zero_cost_budget_and_timing_are_preserved(self):
        doc = self.document
        doc["model"]["task_prompt"] = ""
        doc["model"]["tariff"] = dict.fromkeys(("input", "cached_input", "output"), 0)
        for amount in doc["budget"].values():
            amount.update(tokens=0, cost_microusd=0)
        config = self.parse(doc)
        self.assertEqual(config.task_prompt, "")
        self.assertEqual(config.budget.window.tokens, 0)
        self.assertEqual(config.tariff.output, 0)
        self.assertEqual(config.policy.quiet_seconds, 0)
        self.assertEqual(config.document(), doc)

    def test_daily_token_soft_limit_round_trips_and_stays_optional(self):
        doc = deepcopy(self.document)
        doc["budget_soft"] = {"enabled": True, "tokens": 800_000, "kinds": ["role.journal.write"]}
        config = self.parse(doc)
        self.assertEqual((config.budget_soft.enabled, config.budget_soft.tokens), (True, 800_000))
        self.assertTrue(config.budget_soft.is_deferrable("role.journal.write"))
        self.assertEqual(config.document()["budget_soft"], doc["budget_soft"])
        # A profile pinned before the field existed keeps the soft ceiling disabled and
        # keeps the hash of the document it was pinned with.
        legacy = deepcopy(self.document)
        del legacy["budget_soft"]
        restored = self.parse(legacy)
        self.assertFalse(restored.budget_soft.enabled)
        self.assertEqual(restored.fingerprint, digest(legacy))
        for broken in ({"enabled": "yes", "tokens": 0, "kinds": []}, {"enabled": False, "tokens": -1, "kinds": []},
                       {"enabled": False, "tokens": 0, "kinds": "role.journal.write"},
                       {"enabled": False, "tokens": 0}):
            with self.subTest(broken=broken):
                doc = deepcopy(self.document)
                doc["budget_soft"] = broken
                with self.assertRaises(StagingConfigurationError):
                    self.parse(doc)

    def test_disabled_hard_budget_round_trips_without_changing_legacy_pins(self):
        disabled = replace(self.config, budget=replace(self.config.budget, enabled=False))
        document = disabled.document()
        self.assertIs(document["budget"]["enabled"], False)
        restored = self.parse(document)
        self.assertEqual(restored, disabled)
        self.assertEqual(restored.fingerprint, digest(document))
        self.assertIs(self.parse(self.document).budget.enabled, True)
        self.assertEqual(self.parse(self.document).fingerprint, digest(self.document))
        document["budget"]["enabled"] = "yes"
        with self.assertRaises(StagingConfigurationError):
            self.parse(document)

    def test_a_pinned_document_keeps_its_own_hash_whatever_shape_it_has(self):
        """The receipt recorded at initialization hashes the document that was pinned.

        A profile written by an older host may express schema defaults, and it may
        lack blocks added since. Today's writer emits a different shape for exactly
        the same settings — that difference must not move the fingerprint, or every
        existing profile fails to reopen.
        """
        legacy = deepcopy(self.document)
        legacy.pop("budget_soft")  # block added after this profile was pinned
        legacy["segmentation"] = asdict(SegmentationPolicy())  # defaults the old writer spelled out
        legacy["policy"].pop("defer_seconds", None)  # timing field added later

        restored = self.parse(legacy)

        self.assertEqual(restored.fingerprint, digest(legacy))
        # Today's writer rebuilds a different shape for the same settings, which is
        # exactly why the hash has to reproduce the stored shape.
        self.assertNotEqual(restored.document(), legacy)
        self.assertTrue(restored.same_contract(self.config))

    def test_same_contract_compares_settings_not_the_stored_shape(self):
        legacy = deepcopy(self.document)
        legacy.pop("budget_soft")
        restored = self.parse(legacy)

        self.assertTrue(restored.same_contract(self.config))
        self.assertEqual(restored.budget_soft, BudgetSoftPolicy())
        self.assertFalse(restored.same_contract(replace(self.config, task_prompt="另一份提示词")))
        self.assertFalse(restored.same_contract(replace(self.config, streaming=not self.config.streaming)))

    def test_the_busy_deferral_round_trips_and_stays_optional(self):
        doc = deepcopy(self.document)
        doc["policy"]["defer_seconds"] = 120.0
        config = self.parse(doc)
        self.assertEqual(config.policy.defer_seconds, 120.0)
        self.assertEqual(config.document()["policy"]["defer_seconds"], 120.0)
        self.assertEqual(config.fingerprint, digest(doc))

        # A profile pinned before the field existed reads as "no deferral" and keeps
        # the hash of the document it was pinned with.
        legacy = deepcopy(self.document)
        restored = self.parse(legacy)
        self.assertEqual(restored.policy.defer_seconds, 0.0)
        self.assertNotIn("defer_seconds", restored.document()["policy"])
        self.assertEqual(restored.fingerprint, digest(legacy))

        for broken in (True, "120", -1, 901):
            with self.subTest(broken=broken):
                with self.assertRaises(StagingConfigurationError):
                    self.parse({**deepcopy(self.document),
                                "policy": {**self.document["policy"], "defer_seconds": broken}})

    def test_unknown_missing_duplicate_and_secret_fields_are_rejected_without_echo(self):
        for path in ((), ("host",), ("scope",), ("access",), ("model",), ("model", "tariff"), ("budget", "window"),
                     ("budget_soft",)):
            with self.subTest(path=path):
                doc = deepcopy(self.document)
                node = doc
                for part in path:
                    node = node[part]
                node["api_key-private-marker"] = "sensitive-value-marker"
                with self.assertRaises(StagingConfigurationError) as raised:
                    self.parse(doc)
                self.assertNotIn("private-marker", str(raised.exception))
                self.assertNotIn("sensitive-value", str(raised.exception))
        text = json.dumps(self.document)
        for invalid in (text.replace('"host_id": "host"', '"host_id": "host", "host_id": "duplicate"'),
                        text.replace('"tokens": 100000000', '"tokens": 100000000, "tokens": 0', 1)):
            with self.assertRaises(StagingConfigurationError):
                StagingConfiguration.parse(invalid)
        # ``delivery_mode`` is optional on the wire for older profiles. Missing and
        # legacy preview values both resolve to the official private sender.
        wire_optional = deepcopy(self.document)
        wire_optional.pop("delivery_mode", None)
        self.assertEqual(self.parse(wire_optional).delivery_mode, "onebot_private")
        self.assertEqual(self.parse(deepcopy(self.document)).delivery_mode, "onebot_private")
        for required in ("schema_version", "scope", "host", "subject_id", "persona",
                         "access", "model", "budget", "policy", "limits"):
            with self.subTest(required=required):
                broken = deepcopy(self.document)
                del broken[required]
                with self.assertRaises(StagingConfigurationError):
                    self.parse(broken)

    def test_invalid_types_references_and_authority_are_rejected(self):
        changes = (
            (("schema_version",), "unknown"), (("host",), []), (("scope", "kind"), "group"),
            (("scope", "account_id"), "0100"), (("scope", "native_scope_id"), "0200"),
            (("scope", "session_id"), "201"), (("scope", "conversation_id"), None),
            (("subject_id",), ""), (("persona", "instruction_hash"), "not-a-hash"),
            (("model", "provider_fingerprint"), "F" * 64), (("access", "valid_from"), "2026-09-21"),
            (("access", "expires_at"), "2026-09-20T00:00:00Z"), (("access", "capabilities"), []),
            (("access", "capabilities"), "text"), (("access", "capabilities"), [None]),
            (("access", "capabilities"), ["text", "text", "conversation.reply", "configuration.read"]),
            (("access", "capabilities"), ["text", "conversation.reply", "configuration.read", "access.policy.set"]),
            (("model", "max_output_tokens"), True), (("model", "maximum_input_estimate"), 1),
            (("model", "output_parameter"), "custom"), (("model", "task_prompt"), 1),
            (("model", "tariff", "input"), -1), (("model", "tariff", "cached_input"), False),
            (("budget", "installation", "tokens"), 0), (("budget", "window", "cost_microusd"), 1.0),
            (("budget_soft", "enabled"), "on"), (("budget_soft", "tokens"), 1.5),
            (("budget_soft", "kinds"), "role.journal.write"), (("budget_soft", "kinds"), [7]),
            (("policy", "quiet_seconds"), True), (("policy", "turn_timeout_seconds"), float("inf")),
            (("limits", "foreground_slots"), 0), (("delivery_mode",), "send"),
        )
        for path, value in changes:
            with self.subTest(path=path, value=value):
                doc = deepcopy(self.document)
                node = doc
                for part in path[:-1]:
                    node = node[part]
                node[path[-1]] = value
                with self.assertRaises(StagingConfigurationError):
                    self.parse(doc)

    def test_malformed_nonfinite_oversized_and_non_utf8_documents_are_bounded(self):
        for text in ("{", "[]", "null", '"str"', "NaN", "Infinity", "1e999", "[" * 1500,
                     " " * (MAX_CONFIG_BYTES + 1), "\ud800", b"{}"):
            with self.subTest(kind=type(text).__name__, length=len(text)):
                with self.assertRaises(StagingConfigurationError):
                    StagingConfiguration.parse(text)
        self.document["model"]["task_prompt"] = "\ud800"
        with self.assertRaises(StagingConfigurationError):
            StagingConfiguration.parse(json.dumps(self.document, ensure_ascii=True))

    def test_validation_command_reads_only_explicit_file_and_never_claims_host_verification(self):
        repo = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(prefix="companion-v2-config-") as directory:
            path = Path(directory) / "试运行.json"
            path.write_text(json.dumps(self.document, ensure_ascii=False), encoding="utf-8")
            def invoke():
                return subprocess.run([sys.executable, "-X", "utf8", str(repo / "tools/validate_staging_config.py"), str(path)],
                    cwd=directory, capture_output=True, encoding="utf-8", timeout=15)
            result = invoke()
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["fingerprint"], self.config.fingerprint)
            self.assertFalse(report["native_host_verified"])
            self.assertFalse(report["initialized"])
            self.assertFalse(report["started"])
            self.assertNotIn(self.config.task_prompt, result.stdout)
            path.write_bytes(b"\xff")
            result = invoke()
            self.assertEqual(result.returncode, 2)
            self.assertFalse(json.loads(result.stderr)["valid"])
            self.assertEqual(list(Path(directory).iterdir()), [path])

class RebindingClassificationTests(unittest.TestCase):
    """Only a rebinding refuses to load; environment drift is reported and loads.

    Pinning exists so a stray command or an edit cannot quietly repoint who the role
    is or who it talks to. A provider renamed upstream, a re-tuned budget or a field
    AstrBot added in an upgrade repoints nothing, and treating those as a conflict
    took the whole installation offline for a change nobody made in this profile.
    """

    def setUp(self):
        self.config = synthetic_configuration(FakeHostContext())

    def test_an_identical_profile_is_not_a_conflict(self):
        self.assertEqual(self.config.contract_differences(self.config), ())
        self.assertEqual(self.config.rebinding_differences(self.config), ())

    def test_environment_drift_is_reported_but_is_not_a_rebinding(self):
        aged = replace(self.config, provider_id="renamed-upstream", max_output_tokens=999)
        self.assertEqual(sorted(aged.contract_differences(self.config)),
                         ["max_output_tokens", "provider_id"])
        self.assertEqual(aged.rebinding_differences(self.config), ())

    def test_a_different_persona_is_a_rebinding(self):
        moved = replace(self.config, persona=replace(self.config.persona, persona_id="someone-else"))
        self.assertEqual(moved.rebinding_differences(self.config), ("persona",))

    def test_editing_the_selected_persona_text_does_not_rebind_the_role(self):
        edited = replace(self.config, persona=replace(self.config.persona, instruction_hash="b" * 64))
        self.assertEqual(edited.contract_differences(self.config), ("persona",))
        self.assertEqual(edited.rebinding_differences(self.config), ())
        self.assertEqual(edited.identity_fingerprint, self.config.identity_fingerprint)

    def test_a_legacy_delivery_mode_is_not_a_rebinding(self):
        # Preview was a historical stored value; the formal host always uses the same
        # private sender, so it cannot make an existing target look rebound.
        legacy = replace(self.config, delivery_mode="preview")
        self.assertEqual(legacy.delivery_mode, "onebot_private")
        self.assertEqual(legacy.contract_differences(self.config), ())
        self.assertEqual(legacy.rebinding_differences(self.config), ())

    def test_a_conversation_the_platform_opened_is_not_a_rebinding(self):
        """A new conversation must not take the role offline.

        ``conversation_id``/``session_id`` are read live from AstrBot on every probe, so
        they are conversation-scoped runtime values, not provisioning conditions. They
        used to be hashed into the identity, which meant opening a conversation made the
        role refuse to load -- an ordinary thing a person does, and something V1 never
        reacted to. They stay in the stored document and are still crossed against the
        live probe when a message lands; they just no longer gate the profile.
        """
        moved = replace(self.config, scope=replace(self.config.scope,
                                                  conversation_id="astrbot-conversation:opened-since"))
        self.assertEqual(moved.contract_differences(self.config), ())
        self.assertEqual(moved.rebinding_differences(self.config), ())
        self.assertTrue(moved.same_contract(self.config))

    def test_the_account_behind_the_conversation_is_still_a_rebinding(self):
        """The other half: dropping the conversation must not drop the durable target."""
        moved = replace(self.config, scope=replace(self.config.scope, account_id="9999999999"))
        self.assertEqual(moved.rebinding_differences(self.config), ("scope",))

    def test_scope_identity_keys_match_the_identity_document(self):
        """Both sides of the "does this profile still point at the same place" question
        must read the same keys, or the receipt and the controller would disagree."""
        scope_keys = set(self.config.scope.document())
        self.assertEqual(set(SCOPE_IDENTITY_KEYS) | {"conversation_id", "session_id"}, scope_keys)
        hashed = self.config.identity_document()["scope"]
        self.assertEqual(set(hashed), set(SCOPE_IDENTITY_KEYS))

    def test_a_mixed_change_refuses_and_names_only_the_identity_field(self):
        aged = replace(self.config, provider_id="renamed-upstream")
        moved = replace(aged, persona=replace(aged.persona, persona_id="someone-else"))
        self.assertEqual(sorted(moved.contract_differences(self.config)),
                         ["persona", "provider_id"])
        self.assertEqual(moved.rebinding_differences(self.config), ("persona",))


class IdentitySubHashTests(unittest.TestCase):
    """The provisioning receipt splits identity from environment at write time.

    A store cannot keep a copy of the pinned document to diff against later: that copy
    would carry every value, and its shape would drift with the writer. So the receipt
    records an identity sub-hash plus one digest per field, and those two decisions
    decide everything downstream: a sub-hash that swallowed an environment field would
    put a re-tuned budget back on the "connection failed" path, and one that missed an
    identity field would let a stray edit quietly repoint the role.
    """

    def setUp(self):
        self.config = synthetic_configuration(FakeHostContext())

    def test_environment_drift_never_moves_the_identity_sub_hash(self):
        changes = {
            "provider_id": "renamed-upstream",
            "provider_fingerprint": "a" * 64,
            "max_output_tokens": 999,
            "maximum_input_estimate": 4096,
            "output_parameter": "max_completion_tokens",
            "task_prompt": "另一份提示词",
            "streaming": True,
            "host_id": "another-host",
            "budget": BudgetPolicy(*(Amount(10 ** 7, 10 ** 8) for _ in range(5))),
            "limits": SupervisorLimits(foreground_slots=1, background_slots=3,
                                       queued_per_lane=16, retained_tasks=64),
        }
        for name, value in changes.items():
            with self.subTest(field=name):
                drifted = replace(self.config, **{name: value})
                self.assertNotEqual(drifted.fingerprint, self.config.fingerprint)
                self.assertNotIn(name, REBINDING_FIELDS)
                self.assertEqual(drifted.identity_fingerprint, self.config.identity_fingerprint)

    def test_every_binding_field_moves_the_identity_sub_hash(self):
        cases = {
            "scope": replace(self.config, scope=replace(self.config.scope,
                                                        native_scope_id="201", session_id="201")),
            "subject": replace(self.config, subject=replace(self.config.subject,
                                                            subject_id="another-participant")),
            "persona": replace(self.config, persona=replace(self.config.persona,
                                                           persona_id="someone-else",
                                                           instruction_hash="b" * 64)),
        }
        # 子指纹覆盖的字段集必须与「什么算改指」完全一致，否则建库收据这道闸门会和
        # rebinding_differences 对同一次改动给出互相矛盾的结论。
        self.assertEqual(set(cases), set(REBINDING_FIELDS))
        for name, moved in cases.items():
            with self.subTest(field=name):
                self.assertNotEqual(moved.identity_fingerprint, self.config.identity_fingerprint)
                self.assertEqual(moved.rebinding_differences(self.config), (name,))
                self.assertEqual(moved.contract_differences(self.config), (name,))

    def test_the_sub_hash_ignores_the_writer_shape_the_document_hash_must_reproduce(self):
        """A profile pinned by an older writer still matches on identity.

        ``fingerprint`` deliberately reproduces the stored shape so an existing receipt
        stays valid; the sub-hash must not inherit that coupling, or the same settings
        would look like a rebinding right after a writer upgrade.
        """
        legacy = {**self.config.document(), "delivery_mode": "preview"}
        legacy["segmentation"] = asdict(SegmentationPolicy())
        legacy.pop("budget_soft", None)
        restored = StagingConfiguration.parse(json.dumps(legacy, ensure_ascii=False))

        self.assertNotEqual(restored.fingerprint, self.config.fingerprint)
        self.assertEqual(restored.identity_fingerprint, self.config.identity_fingerprint)

    def test_field_digests_name_the_field_that_moved_without_carrying_its_value(self):
        moved = replace(self.config, task_prompt="另一份提示词")
        recorded, current = self.config.field_fingerprints(), moved.field_fingerprints()

        self.assertEqual(set(recorded), set(current))
        self.assertEqual([name for name in current if current[name] != recorded[name]], ["task_prompt"])
        serialized = json.dumps(current, ensure_ascii=False)
        self.assertNotIn("另一份提示词", serialized)
        self.assertNotIn(self.config.subject.subject_id, serialized)
        self.assertNotIn(self.config.persona.instruction_hash, serialized)
