"""C2-1 reference material: registrations, digests at use time, and the 24 ceiling.

The service's authority check is injectable, so these tests drive it directly; the
production wiring into the task supervisor is covered where assembly is tested.
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigurationError
from companion_v2.execution.models import TaskError
from companion_v2.foundation.refs import ReferenceValidationError
from companion_v2.references.models import (ContentDigest, ReferenceKind, ReferenceRole,
                                            ReferenceSource, ReferenceState, WardrobeItem)
from companion_v2.references.repositories import ReferenceAssetRepository
from companion_v2.references.service import ReferenceAssetService
from companion_v2.storage.reference_asset_schema import reference_limit
from companion_v2.storage.runtime import StorageRuntime
from tests.test_conversation_messages import MessageFixture


class TasksStub:
    """Only what the service asks the supervisor for, with the guard observable."""

    def __init__(self, runtime, *, now, allowed=True):
        self.runtime = runtime
        self._now = now
        self.allowed = allowed
        self.checked = []

    def now(self):
        return self._now

    def authorize_context(self, context, *, action, observed_at):
        self.checked.append(action)
        return self.allowed


class SettingsStub:
    """Stands in for ReferenceSettings so a switch can be flipped per test."""

    def __init__(self, **options):
        from companion_v2.references.configuration import DEFAULTS
        self.options = {**DEFAULTS, **options}
        self.reads = 0

    def read(self, context, at):
        self.reads += 1
        return dict(self.options)


def payload_for(text: str) -> bytes:
    return text.encode("utf-8")


def digest_of(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ReferenceAssetServiceTests(MessageFixture):
    def setUp(self):
        super().setUp()
        self.service = ReferenceAssetService(self.runtime, self.tasks,
                                            authorize=lambda context, **kwargs: self.authorized)
        self.authorized = True
        self.owner = self.service.owner(self.context)
        self.bytes_ = payload_for("portrait-bytes")
        self.digest = digest_of(self.bytes_)

    def register(self, asset_id="asset-1", *, role=ReferenceRole.IDENTITY, payload=None, **changes):
        payload = self.bytes_ if payload is None else payload
        arguments = dict(asset_id=asset_id, kind=ReferenceKind.REFERENCE_IMAGE, role=role,
                         content_hash=changes.pop("content_hash", digest_of(payload)),
                         size_bytes=changes.pop("size_bytes", len(payload)),
                         mime_type="image/png", media_ref="media-" + asset_id,
                         payload=payload)
        arguments.update(changes)
        return self.service.register_asset(self.context, **arguments).unwrap()

    def refusal(self, call):
        """A refused write surfaces through the outcome wrapper as a RuntimeError."""
        with self.assertRaises(RuntimeError) as caught:
            call()
        return str(caught.exception)

    # --- registration ------------------------------------------------------------

    def test_a_registration_stores_the_asserted_digest_and_not_the_bytes(self):
        asset = self.register()
        self.assertEqual(asset.asset_id, "asset-1")
        self.assertEqual(asset.content_hash.sha256, self.digest)
        self.assertEqual(asset.size_bytes, len(self.bytes_))
        self.assertEqual(asset.role, ReferenceRole.IDENTITY)
        self.assertEqual(asset.state, ReferenceState.ACTIVE)
        # The row carries a reference, never the picture itself.
        row = self.runtime.read_one("SELECT * FROM reference_assets WHERE owner_key = ?", (self.owner,))
        self.assertEqual(row["media_ref"], "media-asset-1")
        self.assertNotIn(b"portrait-bytes", str(dict(row)).encode("utf-8"))

    def test_a_digest_that_does_not_match_the_payload_is_refused(self):
        message = self.refusal(lambda: self.register(content_hash="a" * 64))
        self.assertIn("reference_digest_mismatch", message)
        self.assertEqual(self.service.list_assets(self.context), ())

    def test_a_size_that_does_not_match_the_payload_is_refused(self):
        message = self.refusal(lambda: self.register(size_bytes=len(self.bytes_) + 1))
        self.assertIn("reference_size_mismatch", message)

    def test_an_asserted_digest_must_be_a_real_sha256(self):
        for bad in ("abc", "", "A" * 64, "g" * 64, 5):
            with self.assertRaises(ReferenceValidationError):
                ContentDigest(bad)

    # --- the ceiling is enforced on write ----------------------------------------

    def test_the_registration_ceiling_is_refused_rather_than_truncated(self):
        for index in range(reference_limit()):
            self.register(f"asset-{index:02d}")
        self.assertEqual(len(self.service.list_assets(self.context)), reference_limit())
        message = self.refusal(lambda: self.register("asset-overflow"))
        self.assertIn("reference_limit_reached", message)
        # Nothing was written and nothing was dropped.
        self.assertEqual(len(self.service.list_assets(self.context)), reference_limit())
        self.assertIsNone(self.service.assets.get(self.owner, "asset-overflow"))

    def test_re_registering_the_same_asset_is_not_blocked_by_the_ceiling(self):
        for index in range(reference_limit()):
            self.register(f"asset-{index:02d}")
        replaced = self.register("asset-00", label="updated")
        self.assertEqual(replaced.label, "updated")
        self.assertEqual(self.service.assets.count_active(self.owner), reference_limit())

    # --- digest checked at use time ----------------------------------------------

    def test_tampered_material_is_refused_when_it_is_used(self):
        self.register()
        # One byte different is enough: the registration no longer describes reality.
        tampered = payload_for("portrait-byteS")
        self.assertEqual(len(tampered), len(self.bytes_))
        self.service.verify_asset(self.context, "asset-1", self.bytes_)
        with self.assertRaises(TaskError) as caught:
            self.service.verify_asset(self.context, "asset-1", tampered)
        self.assertEqual(caught.exception.code, "reference_fingerprint_mismatch")

    def test_a_withdrawn_material_cannot_be_used(self):
        self.register()
        self.service.withdraw_asset(self.context, "asset-1").unwrap()
        with self.assertRaises(TaskError) as caught:
            self.service.verify_asset(self.context, "asset-1", self.bytes_)
        self.assertEqual(caught.exception.code, "reference_asset_withdrawn")

    def test_an_unregistered_material_cannot_be_used(self):
        with self.assertRaises(TaskError) as caught:
            self.service.verify_asset(self.context, "never-registered", self.bytes_)
        self.assertEqual(caught.exception.code, "reference_asset_missing")

    # --- roles are declared, never implied ---------------------------------------

    def test_extra_roles_are_explicit_rows(self):
        self.register(role=ReferenceRole.IDENTITY)
        self.assertEqual(self.service.assets.roles_of(self.owner, "asset-1"), ("identity",))
        roles = self.service.add_role(self.context, "asset-1", ReferenceRole.OUTFIT).unwrap()
        self.assertEqual(roles, ("identity", "outfit"))
        self.assertEqual(len(self.service.list_assets(self.context, role=ReferenceRole.OUTFIT)), 1)
        self.assertEqual(len(self.service.list_assets(self.context, role=ReferenceRole.POSE)), 0)

    def test_adding_a_role_to_missing_material_is_refused(self):
        message = self.refusal(
            lambda: self.service.add_role(self.context, "asset-gone", ReferenceRole.POSE).unwrap())
        self.assertIn("reference_asset_missing", message)

    # --- authority is re-checked -------------------------------------------------

    def test_every_entry_re_checks_authority(self):
        self.register()
        self.authorized = False
        for call in (lambda: self.service.list_assets(self.context),
                     lambda: self.service.get_asset(self.context, "asset-1"),
                     lambda: self.service.verify_asset(self.context, "asset-1", self.bytes_),
                     lambda: self.register("asset-2")):
            with self.assertRaises(Exception):
                call()
        self.authorized = True
        self.assertEqual(len(self.service.list_assets(self.context)), 1)

    def test_the_guard_runs_for_both_reads_and_writes(self):
        seen = []
        service = ReferenceAssetService(self.runtime, self.tasks,
                                        authorize=lambda context, **kwargs: seen.append(kwargs["action"]) or True)
        service.list_assets(self.context)
        service.register_asset(self.context, asset_id="guard-1", kind=ReferenceKind.REFERENCE_IMAGE,
                               role=ReferenceRole.IDENTITY, content_hash=self.digest,
                               size_bytes=len(self.bytes_), mime_type="image/png",
                               media_ref="media-guard", payload=self.bytes_).unwrap()
        self.assertEqual(seen, ["reference.use", "reference.register"])

    # --- wardrobe shares the asset layer -----------------------------------------

    def test_a_wardrobe_item_may_stand_alone_or_reference_registered_material(self):
        plain = self.service.register_item(self.context, item_id="item-1", name="米色针织衫",
                                           description="常穿", tags=("针织", "秋季")).unwrap()
        self.assertIsNone(plain.asset_id)
        self.assertEqual(plain.tags, ("秋季", "针织"))
        self.register("asset-look")
        linked = self.service.register_item(self.context, item_id="item-2", name="长裙",
                                            asset_id="asset-look").unwrap()
        self.assertEqual(linked.asset_id, "asset-look")
        self.assertEqual(len(self.service.list_items(self.context)), 2)

    def test_a_wardrobe_item_cannot_point_at_unregistered_material(self):
        message = self.refusal(
            lambda: self.service.register_item(self.context, item_id="item-x", name="外套",
                                               asset_id="no-such-asset").unwrap())
        self.assertIn("reference_asset_missing", message)

    def test_wardrobe_tags_are_bounded_and_unique(self):
        with self.assertRaises(ReferenceValidationError):
            WardrobeItem(item_id="i", name="n", tags=("a", "a"))
        with self.assertRaises(ReferenceValidationError):
            WardrobeItem(item_id="i", name="n", tags=tuple(f"t{n}" for n in range(17)))

    def test_withdrawing_a_provider_withdraws_only_that_provider(self):
        self.register("asset-operator", source=ReferenceSource.OPERATOR)
        self.register("asset-provider", source=ReferenceSource.PROVIDER, payload=payload_for("vendor"))
        withdrawn = self.service.withdraw_source(self.context, ReferenceSource.PROVIDER).unwrap()
        self.assertEqual(withdrawn, 1)
        remaining = [asset.asset_id for asset in self.service.list_assets(self.context)]
        self.assertEqual(remaining, ["asset-operator"])

    def test_registrations_survive_a_restart(self):
        self.register()
        self.service.register_item(self.context, item_id="item-1", name="米色针织衫")
        reopened = StorageRuntime.open(data_root=self.root,
                                       installation_id=self.context.scope.installation_id)
        self.addCleanup(reopened.close)
        repository = ReferenceAssetRepository(reopened)
        self.assertIsNotNone(repository.get(self.owner, "asset-1"))
        self.assertIsNotNone(repository.get_item(self.owner, "item-1"))


class ReferenceGateTests(ReferenceAssetServiceTests):
    """The C2-1 switches must change behaviour, not merely exist."""

    def setUp(self):
        super().setUp()
        # Start from the switches on, so each test can turn one off deliberately.
        self.options = SettingsStub(enabled=True, daily_outfit_enabled=True)
        self.gated = ReferenceAssetService(self.runtime, self.tasks, settings=self.options,
                                           authorize=lambda context, **kwargs: True)

    def test_the_switch_is_read_on_every_entry(self):
        self.gated.list_assets(self.context)
        before = self.options.reads
        self.gated.list_assets(self.context)
        self.assertEqual(self.options.reads, before + 1)

    def test_reference_material_is_refused_while_the_switch_is_off(self):
        self.options.options["enabled"] = False
        with self.assertRaises(TaskError) as caught:
            self.gated.list_assets(self.context)
        self.assertEqual(caught.exception.code, "photo_reference_disabled")

    def test_the_switch_does_not_stop_an_operator_withdrawing_material(self):
        # Reading and registering are gated; shutting the switch off must not trap
        # the operator's own material behind it.
        asset = self.register(asset_id="gated-1")
        self.assertEqual(asset.asset_id, "gated-1")
        self.options.options["enabled"] = False
        withdrawn = self.gated.withdraw_asset(self.context, "gated-1").unwrap()
        self.assertEqual(withdrawn, 1)

    def test_registration_is_refused_while_the_switch_is_off(self):
        self.options.options["enabled"] = False
        message = self.refusal(lambda: self.gated.register_asset(
            self.context, asset_id="blocked", kind=ReferenceKind.REFERENCE_IMAGE,
            role=ReferenceRole.IDENTITY, content_hash=self.digest, size_bytes=len(self.bytes_),
            mime_type="image/png", media_ref="media-blocked", payload=self.bytes_).unwrap())
        self.assertIn("photo_reference_disabled", message)
        self.assertIsNone(self.gated.assets.get(self.owner, "blocked"))

    def test_the_daily_outfit_path_has_its_own_switch(self):
        # Turning on reference pictures is not agreement to a picture every day.
        self.options.options["enabled"] = True
        self.options.options["daily_outfit_enabled"] = False
        with self.assertRaises(TaskError) as caught:
            self.gated.daily_outfit_options(self.context)
        self.assertEqual(caught.exception.code, "daily_outfit_disabled")
        self.options.options["daily_outfit_enabled"] = True
        self.options.options["daily_outfit_rotation_days"] = 30
        self.assertEqual(self.gated.daily_outfit_options(self.context),
                         {"rotation_days": 30, "enabled": True})

    def test_daily_outfit_candidates_need_both_switches(self):
        self.gated.register_asset(
            self.context, asset_id="look-1", kind=ReferenceKind.REFERENCE_IMAGE,
            role=ReferenceRole.OUTFIT, content_hash=self.digest, size_bytes=len(self.bytes_),
            mime_type="image/png", media_ref="media-look", payload=self.bytes_).unwrap()
        self.gated.register_item(self.context, item_id="item-1", name="米色针织衫")
        self.options.options.update(enabled=True, daily_outfit_enabled=True)
        self.assertEqual(len(self.gated.recent_outfit_items(self.context)), 1)
        self.options.options["enabled"] = False
        self.assertEqual(self.gated.recent_outfit_items(self.context), ())


class ReferenceConfigurationTests(unittest.TestCase):
    def test_the_defaults_keep_the_old_behaviour(self):
        from companion_v2.references import configuration as group
        self.assertEqual(group.DEFAULTS["enabled"], False)
        self.assertEqual(group.DEFAULTS["daily_outfit_enabled"], False)
        # With the group off, nothing about an installation's behaviour changes.
        self.assertFalse(group.validate(dict(group.DEFAULTS))["enabled"])

    def test_the_registered_fields_are_closed_and_bounded(self):
        from companion_v2.references import configuration as group
        fields = {field.field_id: field for field in group.configuration_fields()}
        self.assertEqual(set(fields), {f"{group.GROUP}.{name}" for name in group.DEFAULTS})
        rotation = fields[f"{group.GROUP}.daily_outfit_rotation_days"]
        self.assertEqual((rotation.minimum, rotation.maximum), (1, 365))
        self.assertEqual(rotation.default, 14)
        for field in fields.values():
            self.assertEqual(field.owner_id, group.OWNER)
            self.assertEqual(field.layers, (ConfigLayer.ROLE,))

    def test_an_out_of_range_or_wrongly_typed_value_is_rejected(self):
        from companion_v2.references import configuration as group
        for name, value in (("daily_outfit_rotation_days", 0), ("daily_outfit_rotation_days", 366),
                            ("daily_outfit_rotation_days", True), ("enabled", 1),
                            ("daily_outfit_enabled", "yes")):
            with self.assertRaises(ConfigurationError, msg=name):
                group.validate({**group.DEFAULTS, name: value})

    def test_an_incomplete_document_is_rejected(self):
        from companion_v2.references import configuration as group
        with self.assertRaises(ConfigurationError):
            group.validate({"enabled": True})


class WardrobeSettingsStub:
    """Stands in for WardrobeSettings so one switch can be flipped per test."""

    def __init__(self, **options):
        from companion_v2.references.wardrobe import DEFAULTS
        self.options = {**DEFAULTS, **options}
        self.reads = 0

    def read(self, context, at):
        self.reads += 1
        return dict(self.options)


class WardrobeMaterialTests(ReferenceAssetServiceTests):
    """C2-2: the wardrobe contributes material only when its own switches allow."""

    def setUp(self):
        super().setUp()
        self.options = WardrobeSettingsStub()
        self.wardrobe = ReferenceAssetService(self.runtime, self.tasks,
                                             settings=SettingsStub(enabled=True),
                                             authorize=lambda context, **kwargs: True,
                                             wardrobe=self.options)

    def seed(self, count):
        for index in range(count):
            self.wardrobe.register_item(self.context, item_id=f"item-{index:02d}",
                                        name=f"衣物{index:02d}").unwrap()

    def test_the_switch_is_read_on_every_call(self):
        self.wardrobe.wardrobe_options(self.context)
        before = self.options.reads
        self.wardrobe.wardrobe_options(self.context)
        self.assertEqual(self.options.reads, before + 1)

    def test_material_is_empty_while_the_wardrobe_is_off(self):
        self.seed(3)
        self.options.options["enabled"] = False
        self.assertEqual(self.wardrobe.wardrobe_material(self.context), {"tendency": "", "items": ()})

    def test_material_is_empty_while_the_prompt_switch_is_off(self):
        # Entries stay readable and maintainable; they simply do not enter a prompt.
        self.seed(3)
        self.options.options.update(enabled=True, prompt_enabled=False)
        self.assertEqual(self.wardrobe.wardrobe_material(self.context)["items"], ())
        self.assertEqual(len(self.wardrobe.list_items(self.context)), 3)

    def test_the_prompt_ceiling_bounds_material_without_truncating_storage(self):
        self.seed(20)
        self.options.options.update(enabled=True, prompt_enabled=True, prompt_max_items=12)
        material = self.wardrobe.wardrobe_material(self.context)
        self.assertEqual(len(material["items"]), 12)
        # The ceiling bounds one prompt; the stored wardrobe is untouched.
        self.assertEqual(len(self.wardrobe.list_items(self.context)), 20)

    def test_the_tendency_rides_along_with_the_items(self):
        self.options.options.update(enabled=True, prompt_enabled=True, tendency="偏爱素色针织")
        self.assertEqual(self.wardrobe.wardrobe_material(self.context)["tendency"], "偏爱素色针织")

    def test_the_image_budget_comes_from_the_group(self):
        self.options.options["image_max_count"] = 5
        self.assertEqual(self.wardrobe.outfit_image_budget(self.context), 5)

    def test_an_unwired_wardrobe_stays_permissive_rather_than_silently_off(self):
        # No group wired means no switch was consulted; saying "off" would invent one.
        bare = ReferenceAssetService(self.runtime, self.tasks,
                                     authorize=lambda context, **kwargs: True)
        self.assertTrue(bare.wardrobe_options(self.context)["enabled"])
        self.assertEqual(bare.outfit_image_budget(self.context), 3)


class WardrobeConfigurationTests(unittest.TestCase):
    def test_the_defaults_keep_the_old_behaviour(self):
        from companion_v2.references import wardrobe as group
        self.assertFalse(group.DEFAULTS["enabled"])
        self.assertFalse(group.DEFAULTS["prompt_enabled"])
        self.assertEqual(group.DEFAULTS["prompt_max_items"], 12)
        self.assertEqual(group.DEFAULTS["image_max_count"], 3)

    def test_all_six_settings_register_as_scalars(self):
        from companion_v2.references import wardrobe as group
        from companion_v2.configuration.registry import FieldRegistry
        fields = group.configuration_fields()
        self.assertEqual({f.field_id.split(".")[-1] for f in fields}, set(group.DEFAULTS))
        registry = FieldRegistry(version="wardrobe.probe", fields=fields)
        self.assertEqual(len(registry.group(group.GROUP)), len(group.DEFAULTS))
        for field in fields:
            self.assertEqual(field.owner_id, group.OWNER)
            self.assertEqual(field.layers, (ConfigLayer.ROLE,))

    def test_the_two_text_bounds_are_published_as_metadata(self):
        from companion_v2.references import wardrobe as group
        fields = {f.field_id.split(".")[-1]: f for f in group.configuration_fields()}
        # The registry cannot enforce a text length, so it publishes the bound and
        # validate() enforces it; both facts are asserted together.
        self.assertEqual(fields["tendency"].maximum, group.MAX_TENDENCY)
        self.assertEqual(fields["image_prompt"].maximum, group.MAX_IMAGE_PROMPT)

    def test_an_over_long_note_is_refused_and_never_truncated(self):
        from companion_v2.references import wardrobe as group
        for name, maximum in (("tendency", group.MAX_TENDENCY), ("image_prompt", group.MAX_IMAGE_PROMPT)):
            with self.assertRaises(ConfigurationError, msg=name):
                group.validate({**group.DEFAULTS, name: "长" * (maximum + 1)})
            at_bound = group.validate({**group.DEFAULTS, name: "长" * maximum})
            self.assertEqual(len(at_bound[name]), maximum)

    def test_out_of_range_and_wrongly_typed_values_are_rejected(self):
        from companion_v2.references import wardrobe as group
        for name, value in (("prompt_max_items", 0), ("prompt_max_items", 25),
                            ("image_max_count", 0), ("image_max_count", 9),
                            ("image_max_count", True), ("enabled", 1), ("tendency", 5)):
            with self.assertRaises(ConfigurationError, msg=name):
                group.validate({**group.DEFAULTS, name: value})

    def test_an_incomplete_document_is_rejected(self):
        from companion_v2.references import wardrobe as group
        with self.assertRaises(ConfigurationError):
            group.validate({"enabled": True})


if __name__ == "__main__":
    unittest.main()
