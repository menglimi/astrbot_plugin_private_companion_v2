"""Native artifacts keep their receipt and must decode as the declared image."""

import hashlib
import io
import json
from types import SimpleNamespace as NS
import unittest

from PIL import Image

from astrbot_host.native_extensions.images import image_result_handler
from companion_v2.capabilities.native import NativeArtifact, NativeResult
from companion_v2.execution.models import ProviderBinding, TaskError, encode
from companion_v2.foundation.refs import AudienceRef, SourceRef, VersionRef
from tests.animation_support import animation_bytes
from tests.test_conversation_images import image_bytes
from tests.test_management_access import NOW, ROLE, SCOPE
from tests.test_native_provider_contract import FakeContext


class NativeImageResultHandlerTests(unittest.TestCase):
    def invocation(self, action="image.generate"):
        binding = ProviderBinding(action, "image.native", "0.5.0", "stable-image-revision")
        return NS(invocation_id="native-test", arguments_hash="original-arguments",
            context=FakeContext(SCOPE, AudienceRef(SCOPE, (ROLE,))),
            descriptor=NS(tool=NS(action=action), binding=binding, source_owner="image.native"))

    def result(self, content=None, mime="image/png"):
        content = content if content is not None else image_bytes()
        artifact = NativeArtifact("image-original", "image-operation", hashlib.sha256(content).hexdigest(), mime,
                                  len(content), content)
        return NativeResult("succeeded", "committed", "image-operation", "image-receipt", encode({"saved": True}), (artifact,))

    @staticmethod
    def pixels(size, values, mode="RGB"):
        stream = io.BytesIO()
        image = Image.new(mode, size)
        image.putdata(values)
        image.save(stream, format="PNG")
        return stream.getvalue()

    @staticmethod
    def opened(raw):
        image = Image.open(io.BytesIO(raw))
        image.load()
        return image

    def mask_references(self, source, mask):
        def ref(identifier):
            return SourceRef(identifier, "conversation.image", SCOPE, VersionRef(identifier, 1), NOW)

        return ({"role": "edit_source", "content_hash": hashlib.sha256(source).hexdigest(),
                 "image": NS(content=source), "reference": ref("source-ref"), "parent": ref("source-parent")},
                {"role": "edit_mask", "content_hash": hashlib.sha256(mask).hexdigest(),
                 "image": NS(content=mask), "reference": ref("mask-ref"), "parent": ref("mask-parent")})

    def test_verified_image_and_receipt_metadata_are_kept_without_inline_bytes(self):
        invocation, native = self.invocation(), self.result()
        response = image_result_handler(invocation, native, observed_at=NOW)
        self.assertEqual(response.images[0].content, image_bytes())
        self.assertEqual(json.loads(response.source.payload)["native"], native.metadata(invocation.descriptor.binding))
        self.assertEqual(response.source.reference.issued_at, NOW)
        self.assertEqual(response.receipt_ref, native.receipt_ref)
        self.assertNotIn("base64", response.source.payload)

    def test_mime_mismatch_invalid_bytes_and_animation_do_not_become_sendable_images(self):
        for result in (self.result(mime="image/jpeg"), self.result(b"not an image"),
                       self.result(animation_bytes(), "image/gif")):
            with self.subTest(mime=result.artifacts[0].mime_type):
                with self.assertRaises(TaskError):
                    image_result_handler(self.invocation(), result, observed_at=NOW)

    def test_other_actions_cannot_adopt_image_artifacts(self):
        with self.assertRaises(TaskError) as rejected:
            image_result_handler(self.invocation("content.read"), self.result(), observed_at=NOW)
        self.assertEqual(rejected.exception.code, "native_artifact_unadopted")

    def test_successful_image_action_without_original_is_not_silently_text_only(self):
        result = NativeResult("succeeded", "committed", "operation", "receipt", "{}")
        with self.assertRaises(TaskError) as rejected:
            image_result_handler(self.invocation(), result, observed_at=NOW)
        self.assertEqual(rejected.exception.code, "native_artifact_unavailable")

    def test_failure_and_unknown_keep_outcome_without_success_material(self):
        for state, effect, receipt in (("failed", "not_committed", "failed-receipt"), ("unknown", "unknown", None)):
            with self.subTest(state=state):
                result = NativeResult(state, effect, "operation", receipt, "null")
                response = image_result_handler(self.invocation(), result, observed_at=NOW)
                self.assertEqual((response.state, response.effect), (state, effect))
                self.assertIsNone(response.source)
                self.assertFalse(response.images)

    def test_mask_edit_preserves_every_pixel_outside_mask_and_records_protection(self):
        source = self.pixels((3, 2), [(10, 20, 30), (40, 50, 60), (70, 80, 90),
                                      (100, 110, 120), (130, 140, 150), (160, 170, 180)])
        mask = self.pixels((3, 2), [0, 255, 0, 0, 255, 0], mode="L")
        output = self.pixels((3, 2), [(1, 2, 3)] * 6)
        refs = self.mask_references(source, mask)
        response = image_result_handler(self.invocation("image.mask_edit"), self.result(output),
                                        observed_at=NOW, input_references=refs)
        source_image, result_image = self.opened(source), self.opened(response.images[0].content)
        for index, mask_value in enumerate((0, 255, 0, 0, 255, 0)):
            self.assertEqual(result_image.getpixel((index % 3, index // 3)),
                             source_image.getpixel((index % 3, index // 3)) if mask_value == 0 else (1, 2, 3))
        payload = json.loads(response.source.payload)
        self.assertEqual(payload["image_protection"][0]["outside_mask"], "exact_rgb")
        self.assertEqual(tuple(reference.source_id for reference in response.dependencies),
                         ("source-ref", "source-parent", "mask-ref", "mask-parent"))

    def test_invalid_mask_dimensions_and_empty_regions_never_produce_images(self):
        source = self.pixels((3, 2), [(10, 20, 30)] * 6)
        valid = self.pixels((3, 2), [0, 255, 0, 0, 255, 0], mode="L")
        cases = ((self.pixels((2, 2), [0, 255, 0, 255], mode="L"), "mask_dimension_mismatch"),
                 (self.pixels((3, 2), [0] * 6, mode="L"), "edit_mask_empty"),
                 (self.pixels((3, 2), [255] * 6, mode="L"), "edit_mask_empty"),
                 (self.pixels((3, 2), [127] * 6, mode="L"), "edit_mask_empty"))
        for mask, code in cases:
            with self.subTest(code=code, size=self.opened(mask).size):
                with self.assertRaises(TaskError) as rejected:
                    image_result_handler(self.invocation("image.mask_edit"), self.result(), observed_at=NOW,
                                         input_references=self.mask_references(source, mask))
                self.assertEqual(rejected.exception.code, code)
        with self.assertRaises(TaskError) as output_size:
            image_result_handler(self.invocation("image.mask_edit"),
                self.result(self.pixels((2, 2), [(1, 2, 3)] * 4)), observed_at=NOW,
                input_references=self.mask_references(source, valid))
        self.assertEqual(output_size.exception.code, "mask_output_dimension_mismatch")


if __name__ == "__main__":
    unittest.main()
