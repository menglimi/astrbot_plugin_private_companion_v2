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

    def test_natural_language_requests_include_selfies_and_pending_followups(self):
        for mode in ("tool", "rules"):
            with self.subTest(mode=mode):
                instruction = prompt_instruction({**DEFAULTS, "trigger_mode": mode, "prompt_format": "natural"})
                self.assertIn("来张自拍看看", instruction)
                self.assertIn("尚未完成的同一请求", instruction)
                self.assertIn("已完成的请求", instruction)
                self.assertIn("自拍画面在 prompt 中写明 selfie", instruction)
                self.assertIn("连贯的自然语言", instruction)
                self.assertNotIn("只在本轮", instruction)

    def test_disabled_image_requests_do_not_invite_a_tool_call(self):
        for values in ({**DEFAULTS, "trigger_mode": "off"}, {**DEFAULTS, "allow_user_requests": False}):
            self.assertIn("已关闭用户请求生图和改图", prompt_instruction(values))
            self.assertNotIn("场景预设", prompt_instruction(values))

    def test_selfie_prompt_preserves_the_selected_format_and_role_defaults(self):
        values = {**DEFAULTS, "prompt_format": "natural", "selfie_fixed_prompt": "角色外观锚点",
                  "style": "anime", "style_prompt": "柔和夜间光线", "selfie_negative_prompt": "错误人物"}
        result = apply_prompts({"prompt": "selfie，穿家居服坐在书桌边"}, "image.generate", values)
        self.assertEqual(result["prompt"], "角色外观锚点\nanime illustration\n柔和夜间光线\nselfie，穿家居服坐在书桌边")
        self.assertEqual(result["negative_prompt"], "错误人物")

    def test_scene_presets_reject_duplicate_and_unbounded_values(self):
        duplicate = '[{"id":"home","name":"居家","prompt":"room"},{"id":"home","name":"卧室","prompt":"bedroom"}]'
        with self.assertRaises(TaskError):
            parse_scene_presets(duplicate)
        with self.assertRaises(TaskError):
            parse_scene_presets("[] " + " " * 4000)


if __name__ == "__main__":
    unittest.main()
