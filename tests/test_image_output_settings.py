import unittest

from companion_v2.conversation.media.output_settings import (
    DEFAULTS, apply_prompts, parse_scene_presets, prompt_instruction,
)
from companion_v2.execution.models import TaskError


class ImageOutputSettingsTests(unittest.TestCase):
    def test_proactive_images_are_occasional_by_default_with_one_daily_cap(self):
        self.assertEqual(DEFAULTS["proactive_probability"], 0.35)
        self.assertEqual(DEFAULTS["proactive_max_daily"], 1)

    def test_scene_marker_injects_the_selected_role_preset(self):
        values = dict(DEFAULTS)
        result = apply_prompts(
            {"prompt": "portrait at home [场景预设:睡前居家]"}, "image.generate", values)
        self.assertIn("cozy bedroom", result["prompt"])
        self.assertIn("portrait at home", result["prompt"])
        self.assertNotIn("[场景预设", result["prompt"])

    def test_scene_prompt_instruction_uses_configured_names(self):
        self.assertIn("校园日常", prompt_instruction(DEFAULTS))
        self.assertIn("[场景预设:名称]", prompt_instruction(DEFAULTS))

    def test_scene_presets_reject_duplicate_and_unbounded_values(self):
        duplicate = '[{"id":"home","name":"居家","prompt":"room"},{"id":"home","name":"卧室","prompt":"bedroom"}]'
        with self.assertRaises(TaskError):
            parse_scene_presets(duplicate)
        with self.assertRaises(TaskError):
            parse_scene_presets("[] " + " " * 4000)


if __name__ == "__main__":
    unittest.main()
