"""Cover associations and share material: the Content↔Image and Content→sharing seams."""

import unittest

from companion_v2.conversation.content import cover_assets
from companion_v2.execution.models import TaskError
from companion_v2.foundation.refs import ReferenceValidationError
from companion_v2.sharing.models import ROLE_OWNED_KINDS, ShareMaterial, ShareMaterialKind
from tests.content_orchestration_support import ContentOrchestrationFixture, NOW


def asset(identifier="asset-1", content_hash="a" * 64):
    return {"asset_id": identifier, "owner": "image.native", "content_hash": content_hash}


class CoverAssociationTests(ContentOrchestrationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.covers = cover_assets.ContentCoverService(self.runtime, context=self.context)

    def enable(self, **changes):
        self.configure(cover_assets.ALL_FIELDS,
                       **{cover_assets.AUTHORING_GROUP + ".cover_enabled": True,
                          **{cover_assets.AUTHORING_GROUP + "." + name: value for name, value in changes.items()}})

    def attach(self, **changes):
        return self.covers.associate(work_id="work-1", version_id="v-1", basis_hash="h-1",
                                     asset=asset(), at=NOW, **changes)

    def test_covers_are_off_until_the_role_enables_them(self):
        with self.assertRaises(TaskError) as error:
            self.attach()
        self.assertEqual(error.exception.code, "content_cover_disabled")
        self.enable()
        self.assertEqual(self.attach().state, "active")

    def test_an_association_carries_its_own_basis_and_revision(self):
        self.enable()
        first = self.attach()
        self.assertEqual((first.work_id, first.version_id, first.basis_hash), ("work-1", "v-1", "h-1"))
        self.assertEqual(first.revision, 1)
        self.assertEqual(self.covers.effective("work-1").asset["asset_id"], "asset-1")

    def test_a_material_change_makes_the_picture_belong_to_its_own_version(self):
        self.enable()
        self.attach()
        (retired,) = self.covers.recheck("work-1", head_version="v-2", head_hash="h-1", head_basis="h-2", at=NOW)
        self.assertEqual(retired.state, "historical")
        self.assertEqual(retired.revision, 2)
        self.assertIsNone(self.covers.effective("work-1"))
        # The picture is neither lost nor silently attached to the new draft.
        self.assertEqual([item.version_id for item in self.covers.list("work-1")], ["v-1"])

    def test_a_title_only_change_re_attests_the_same_picture_without_redrawing(self):
        self.enable()
        self.attach()
        # The same text portion still stands, so the association follows the new revision.
        (refreshed,) = self.covers.recheck("work-1", head_version="v-2", head_hash="h-9", head_basis="h-1", at=NOW)
        self.assertEqual((refreshed.state, refreshed.version_id, refreshed.basis_version), ("active", "v-2", "v-2"))
        self.assertEqual(refreshed.revision, 2)
        self.assertEqual(refreshed.asset, asset())
        self.assertEqual(self.covers.effective("work-1").version_id, "v-2")

    def test_a_late_image_stays_with_the_version_that_asked_for_it(self):
        self.enable()
        self.attach()
        self.covers.recheck("work-1", head_version="v-2", head_hash="h-2", head_basis="h-2", at=NOW)
        late = self.covers.record_late(work_id="work-1", version_id="v-1", basis_hash="h-1",
                                       asset=asset("asset-late", "b" * 64), at=NOW)
        self.assertEqual(late.state, "historical")
        self.assertEqual(late.version_id, "v-1")
        self.assertEqual(late.reason, "late result kept with the version that requested it")

    def test_a_work_may_exist_without_any_cover(self):
        self.enable()
        self.assertIsNone(self.covers.effective("work-without-cover"))
        self.assertEqual(self.covers.list("work-without-cover"), ())

    def test_the_active_picture_ceiling_is_enforced(self):
        self.enable()
        self.attach(purpose="cover")
        self.covers.associate(work_id="work-1", version_id="v-1", basis_hash="h-1", purpose="cover",
                              asset=asset("asset-2"), at=NOW)
        with self.assertRaises(TaskError) as error:
            self.covers.associate(work_id="work-1", version_id="v-1", basis_hash="h-1", purpose="cover",
                                  asset=asset("asset-3"), at=NOW)
        self.assertEqual(error.exception.code, "content_cover_limit")
        # Illustrations have their own allowance, and one active cover is the ceiling here.
        self.covers.associate(work_id="work-1", version_id="v-1", basis_hash="h-1", purpose="illustration",
                              asset=asset("asset-4"), at=NOW)

    def test_a_work_that_moved_on_accepts_a_late_association_as_historical(self):
        self.enable()
        self.attach()
        self.covers.recheck("work-1", head_version="v-2", head_hash="h-2", head_basis="h-2", at=NOW)
        # Retiring the picture does not move the manuscript: the work still stands on v-2.
        self.assertEqual(self.covers.head_version("work-1"), "v-2")
        late = self.covers.associate(work_id="work-1", version_id="v-1", basis_hash="h-1", asset=asset("asset-late-2"),
                                     at=NOW)
        self.assertEqual(late.state, "historical")
        self.assertEqual(self.covers.head_version("work-1"), "v-2")


class ContentShareMaterialTests(ContentOrchestrationFixture, unittest.TestCase):
    def material(self, **changes):
        values = {"work_id": "work-1", "version_id": "v-1"} | changes
        return ShareMaterial.from_content_work(
            source=self.work_source(), role_owner=self.role_owner(), created_at=NOW, **values)

    def test_a_manuscript_version_becomes_its_own_share_material(self):
        material = self.material()
        self.assertIs(material.kind, ShareMaterialKind.CONTENT_WORK)
        self.assertIn(ShareMaterialKind.CONTENT_WORK, ROLE_OWNED_KINDS)
        self.assertEqual(material.material_id, "work-material-work-1-v-1")
        self.assertEqual(material.scope, self.context.scope)
        # The invitation names one fixed version, so a later update cannot rewrite it.
        other = self.material(version_id="v-2")
        self.assertNotEqual(material.material_id, other.material_id)

    def test_a_role_owned_work_must_name_its_owner(self):
        with self.assertRaises(ReferenceValidationError):
            ShareMaterial(material_id="m-1", kind=ShareMaterialKind.CONTENT_WORK, source=self.work_source(),
                          created_at=NOW)
        with self.assertRaises(ReferenceValidationError):
            self.material(work_id="  ")

    def test_a_cover_may_travel_with_the_material_but_is_never_required(self):
        from companion_v2.foundation.refs import AssetRef, VersionRef
        covered = self.material(asset=AssetRef("asset-1", "image.native", self.context.scope,
                                               VersionRef("asset-1", 1), "a" * 64))
        self.assertEqual(covered.asset.asset_id, "asset-1")
        self.assertIsNone(self.material().asset)

    def test_the_material_is_not_a_disclosure(self):
        before = {row["key"] for row in self.runtime.read_all("SELECT key FROM runtime_metadata", ())}
        material = self.material()
        after = {row["key"] for row in self.runtime.read_all("SELECT key FROM runtime_metadata", ())}
        # Building material records nothing: the candidate proves acceptance later, and
        # only a delivery receipt proves disclosure. Content never writes here itself.
        self.assertEqual(after, before)
        self.assertNotIn("content.", " ".join(after))
        self.assertIsNone(material.published_at)
        self.assertIsNone(material.fetched_at)


if __name__ == "__main__":
    unittest.main()
