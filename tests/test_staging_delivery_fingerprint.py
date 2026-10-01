"""Legacy delivery values do not change the official OneBot private binding.

Two properties are load-bearing here and easy to break by accident:

1. Old documents can carry ``"delivery_mode": "preview"`` or omit the field. They still
   load as the official sender and reproduce their historical document hash.
2. Delivery mode is not part of route identity, so a legacy value cannot block a fixed
   account, participant and persona from reconnecting.

The stored document shape is retained only to reproduce receipts written by older
V2 releases.
"""

import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone

from companion_v2.adapters.astrbot.native import HostPersona
from companion_v2.adapters.astrbot.provider import UsageTariff
from companion_v2.adapters.astrbot.staging_config import StagingConfiguration
from companion_v2.execution.models import digest
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.model_gateway.models import Amount, BudgetPolicy


INSTALLATION = "astrbot-private-companion-v2:preview-1"


def configuration(**overrides):
    scope = ScopeRef(INSTALLATION, "default", ScopeKind.PRIVATE, "10001", "bot1", "10002", "conv", "10001")
    values = {
        "scope": scope,
        "host_id": "host",
        "ecosystem_id": "ecosystem",
        "subject": SubjectRef(INSTALLATION, SubjectKind.HUMAN, "onebot-user:10001"),
        "persona": HostPersona("bot1", "persona", SubjectRef(INSTALLATION, SubjectKind.BOT, "role"), digest("i")),
        "authority_ref": "astrbot-dashboard:preview-1",
        "valid_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "expires_at": None,
        "capabilities": ("text", "conversation.reply", "configuration.read"),
        "provider_id": "provider",
        "provider_fingerprint": digest("p"),
        "tariff": UsageTariff(0, 0, 0),
        "budget": BudgetPolicy(*[Amount(1, 1)] * 5),
        "task_prompt": "prompt",
    }
    values.update(overrides)
    return StagingConfiguration(**values)


def round_trip(document):
    return StagingConfiguration.parse(json.dumps(document, ensure_ascii=False, sort_keys=True))


class DeliveryFingerprintTests(unittest.TestCase):
    def test_a_new_profile_uses_the_official_private_sender(self):
        self.assertEqual(configuration().document()["delivery_mode"], "onebot_private")

    def test_a_new_profile_includes_the_key_once_it_may_send(self):
        self.assertEqual(configuration(delivery_mode="onebot_private").document()["delivery_mode"],
                         "onebot_private")

    def test_a_legacy_preview_profile_reloads_at_its_original_hash(self):
        """The whole point: an installation pinned before this change still opens."""
        legacy = {**configuration().document(), "delivery_mode": "preview"}
        original = digest(legacy)
        restored = round_trip(legacy)
        self.assertEqual(restored.fingerprint, original)
        self.assertEqual(restored.delivery_mode, "onebot_private")
        self.assertEqual(restored.rebinding_differences(configuration()), ())

    def test_a_legacy_profile_keeps_its_document_shape_when_it_enables_delivery(self):
        """Switching a legacy profile to delivery must not drop the key either."""
        legacy = {**configuration().document(), "delivery_mode": "onebot_private"}
        restored = round_trip(legacy)
        self.assertEqual(restored.fingerprint, digest(legacy))
        self.assertEqual(restored.document()["delivery_mode"], "onebot_private")

    def test_a_new_profile_is_stable_across_a_round_trip(self):
        fresh = configuration()
        restored = round_trip(fresh.document())
        self.assertEqual(restored.fingerprint, fresh.fingerprint)

    def test_binding_fields_stay_in_the_hash_but_delivery_does_not_rebind(self):
        base = configuration().document()
        for path, value in ((("scope", "native_scope_id"), "20002"),
                            (("persona", "persona_id"), "other"),
                            (("model", "provider_id"), "other-provider"),
                            (("model", "task_prompt"), "different")):
            with self.subTest(path=path):
                changed = deepcopy(base)
                node = changed
                for part in path[:-1]:
                    node = node[part]
                node[path[-1]] = value
                self.assertNotEqual(digest(changed), digest(base))

    def test_a_missing_delivery_key_is_read_as_official_private_delivery(self):
        document = configuration().document()
        document.pop("delivery_mode")
        restored = round_trip(document)
        self.assertEqual(restored.delivery_mode, "onebot_private")
        self.assertEqual(restored.fingerprint, digest(document))

    def test_an_unknown_delivery_value_is_still_rejected(self):
        with self.assertRaises(Exception):
            round_trip({**configuration().document(), "delivery_mode": "send"})


if __name__ == "__main__":
    unittest.main()
