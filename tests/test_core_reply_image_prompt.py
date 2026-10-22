"""Natural image instructions and role references reach the native SDK request."""

from datetime import datetime, timezone
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from tests import astrbot_data_root
from astrbot.core.agent.message import Message, TextPart, dump_messages_with_checkpoints
from astrbot.core.provider.entities import ProviderRequest

from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA
from astrbot_host.core_reply_image_prompt import core_image_tools, inject_core_image_prompt
from astrbot_host.core_reply_perception import inject_core_reply_perception_context
from astrbot_host.core_reply_tools import native_tool_name
from astrbot_host.native_extensions.host_events import prepare_native_host_request
from companion_v2.conversation.media.output_settings import DEFAULTS
from companion_v2.execution.models import TaskError


class CoreReplyImagePromptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.references = Mock()
        self.references.prompt_material.return_value = {
            "references": [{"id": "role-face", "label": "角色脸部", "roles": ["identity"],
                            "usage": {"base_identity": True}}],
            "wardrobe": {"tendency": "居家", "items": []},
            "daily_outfit": {"name": "米色家居服"},
        }
        self.prepared = {
            "context": NS(scope=NS(platform="qq-main")),
            "native_input": NS(text="来张自拍看看", at=datetime(2026, 10, 20, 16, 5, tzinfo=timezone.utc)),
            "perception_context": json.dumps({"current_local_time": {"timezone": "America/Los_Angeles"}}),
        }
        self.state = {"prepared": self.prepared}
        self.application = NS(runtime=object(), tasks=NS(now=Mock()), messages=NS(
            reference_materials=self.references, timezone_name="Asia/Shanghai"))
        self.session = NS(application=self.application, context=self.prepared["context"],
                          prepared=self.prepared, state=self.state)
        self.offered = tuple(NS(spec=NS(action=action)) for action in ("memory.query", "image.generate", "image.edit"))
        self.request = ProviderRequest(prompt="来张自拍看看", system_prompt="当前 AstrBot 人格。",
            extra_user_content_parts=[TextPart(text="其他插件的材料")])
        self.event = NS(get_extra=lambda key, default=None:
            self.state if key == CORE_REPLY_CONTEXT_EXTRA else default)

    def inject(self, offered=None, values=None):
        inject_core_image_prompt(self.session, self.request, offered or self.offered,
                                 values if values is not None else DEFAULTS)

    def payload(self):
        part = next(part for part in self.request.extra_user_content_parts
                    if part.text.startswith("<companion_v2_context>"))
        return json.loads(part.text.removeprefix("<companion_v2_context>\n")
                          .removesuffix("\n</companion_v2_context>"))

    def test_disabled_modes_hide_only_image_tools_in_the_request(self):
        for values in ({**DEFAULTS, "allow_user_requests": False}, {**DEFAULTS, "trigger_mode": "off"}):
            with patch("astrbot_host.core_reply_image_prompt.effective_settings", return_value=values):
                offered, preferences = core_image_tools(self.session, self.offered)
            self.assertEqual([item.spec.action for item in offered], ["memory.query"])
            self.assertIsNone(preferences)
        self.assertEqual(len(self.offered), 3)

    def test_without_image_tools_no_preferences_or_references_are_read(self):
        with patch("astrbot_host.core_reply_image_prompt.effective_settings") as settings:
            offered, values = core_image_tools(self.session, self.offered[:1])
        self.assertEqual(offered, self.offered[:1])
        self.assertIsNone(values)
        settings.assert_not_called()
        self.references.prompt_material.assert_not_called()

    def test_unavailable_image_preferences_preserve_other_tools(self):
        with patch("astrbot_host.core_reply_image_prompt.effective_settings", side_effect=TaskError("unavailable", "settings unavailable")):
            offered, values = core_image_tools(self.session, self.offered)
        self.assertEqual([item.spec.action for item in offered], ["memory.query"])
        self.assertIsNone(values)

    def test_native_tool_names_and_actual_delivery_step_are_explained(self):
        self.inject(values={**DEFAULTS, "prompt_format": "natural"})
        prompt = self.request.system_prompt
        self.assertIn(native_tool_name("image.generate"), prompt)
        self.assertIn(native_tool_name("image.edit"), prompt)
        self.assertNotIn(native_tool_name("image.mask_edit"), prompt)
        self.assertIn("来张自拍看看", prompt)
        self.assertIn("连贯的自然语言", prompt)
        self.assertIn("send_message_to_user", prompt)
        self.assertIn('"type":"image"', prompt)
        self.assertIn("session 留空", prompt)
        self.assertIn('reference_indices=[]', prompt)
        self.assertNotIn("role-face", prompt)

    async def test_reference_changes_only_update_temporary_user_context(self):
        self.inject()
        first_system = self.request.system_prompt
        self.references.prompt_material.assert_called_once_with(self.session.context, local_date="2026-10-20")
        prepare_native_host_request(NS(), self.event, self.request)
        await inject_core_reply_perception_context(self.event, self.request)
        self.assertEqual(self.payload()["image_reference_material"]["daily_outfit"]["name"], "米色家居服")
        self.references.prompt_material.return_value = {
            "references": [{"id": "new-face", "roles": ["identity"]}],
            "wardrobe": None, "daily_outfit": {"name": "蓝色衬衫"},
        }
        self.inject()
        await inject_core_reply_perception_context(self.event, self.request)
        self.assertEqual(self.request.system_prompt, first_system)
        self.assertEqual(self.payload()["image_reference_material"]["daily_outfit"]["name"], "蓝色衬衫")
        self.assertNotIn("new-face", self.request.system_prompt)
        self.assertEqual(len(self.request.extra_user_content_parts), 2)
        self.assertEqual(self.request.extra_user_content_parts[0].text, "其他插件的材料")
        self.assertTrue(self.state["_perception_material_injected"])
        content = [TextPart(text="来张自拍看看"), *self.request.extra_user_content_parts]
        saved = dump_messages_with_checkpoints([Message(role="user", content=content)])
        self.assertNotIn("new-face", json.dumps(saved, ensure_ascii=False))
        self.assertIn("来张自拍看看", json.dumps(saved, ensure_ascii=False))

    def test_generate_only_provider_does_not_offer_unavailable_edit_or_reference_tools(self):
        self.inject(offered=self.offered[:2])
        self.assertIn(native_tool_name("image.generate"), self.request.system_prompt)
        self.assertNotIn(native_tool_name("image.edit"), self.request.system_prompt)
        self.assertNotIn("reference_ids", self.request.system_prompt)
        self.references.prompt_material.assert_not_called()

    def test_optional_reference_failure_keeps_natural_image_generation(self):
        self.references.prompt_material.side_effect = TaskError("unavailable", "reference unavailable")
        self.inject()
        self.assertIn(native_tool_name("image.generate"), self.request.system_prompt)
        self.assertNotIn("_image_reference_material", self.state)

    async def test_disabling_images_removes_only_owned_instruction_and_reference_suffix(self):
        self.inject()
        await inject_core_reply_perception_context(self.event, self.request)
        inject_core_image_prompt(self.session, self.request, self.offered[:1], None)
        await inject_core_reply_perception_context(self.event, self.request)
        self.assertEqual(self.request.system_prompt, "当前 AstrBot 人格。")
        self.assertNotIn("image_reference_material", self.payload())
        self.assertEqual(self.request.extra_user_content_parts[0].text, "其他插件的材料")


if __name__ == "__main__":
    unittest.main()
