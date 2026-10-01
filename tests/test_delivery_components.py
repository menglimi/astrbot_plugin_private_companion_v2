"""Direct contract tests for V2 outbound component ordering."""

import unittest

from companion_v2.delivery.components import build_component_plan, ordered_components


RECORD = {"type": "record", "data": {"file": "base64://YQ=="}}


class OutboundComponentPlanTests(unittest.TestCase):
    def test_all_supported_positions_keep_text_image_order(self):
        images = ("image-1", "image-2")
        expected = {
            "before_text": ("voice", "text", "image", "image"),
            "after_text": ("text", "voice", "image", "image"),
            "after_media": ("text", "image", "image", "voice"),
        }
        for position, kinds in expected.items():
            plan = build_component_plan("visible", images, RECORD, position=position, speech="spoken")
            self.assertEqual(plan.kinds, kinds)
            self.assertEqual(tuple(component.value for component in plan.components if component.kind == "image"),
                             images)
            self.assertTrue(plan.voice_included)
            self.assertFalse(plan.text_hidden)

    def test_voice_only_hides_text_only_for_complete_speech(self):
        full = build_component_plan("visible", ("image",), RECORD, position="after_media",
                                    voice_only=True, speech=" visible ")
        self.assertEqual(full.kinds, ("image", "voice"))
        self.assertTrue(full.text_hidden)

        partial = build_component_plan("visible", ("image",), RECORD, position="after_media",
                                       voice_only=True, speech="vis")
        self.assertEqual(partial.kinds, ("text", "image", "voice"))
        self.assertFalse(partial.text_hidden)

    def test_leading_images_keep_voice_adjacent_to_text_and_fallback_order(self):
        images = ("image-1", "image-2")
        for position, kinds in {
                "before_text": ("image", "image", "voice", "text"),
                "after_text": ("image", "image", "text", "voice"),
                "after_media": ("image", "image", "text", "voice")}.items():
            with self.subTest(position=position):
                plan = build_component_plan("visible", images, RECORD, position=position,
                                            image_position="before_text", speech="spoken")
                self.assertEqual(plan.kinds, kinds)
                self.assertEqual(tuple(c.value for c in plan.components if c.kind == "image"), images)
        for record, kinds in ((RECORD, ("image", "image", "voice")),
                              (None, ("image", "image", "text"))):
            plan = build_component_plan("visible", images, record, position="before_text",
                                        image_position="before_text", voice_only=True, speech="visible")
            self.assertEqual(plan.kinds, kinds)

    def test_invalid_voice_falls_back_without_changing_media_order(self):
        invalid = {"type": "record", "data": {"file": "   "}}
        plan = build_component_plan("visible", ("first", "second"), invalid,
                                    position="before_text", voice_only=True, speech="visible")
        self.assertEqual(plan.kinds, ("text", "image", "image"))
        self.assertFalse(plan.voice_included)
        self.assertFalse(plan.text_hidden)
        self.assertEqual(ordered_components("visible", ("first",), None), plan.components[:2])

    def test_unknown_position_degrades_to_after_media(self):
        plan = build_component_plan("visible", (), RECORD, position="stale-position", speech="spoken")
        self.assertEqual(plan.kinds, ("text", "voice"))

    def test_image_only_part_has_no_empty_text_component(self):
        plan = build_component_plan("", ("reaction",))
        self.assertEqual(plan.kinds, ("image",))
        with self.assertRaises(ValueError):
            build_component_plan("")


if __name__ == "__main__":
    unittest.main()
