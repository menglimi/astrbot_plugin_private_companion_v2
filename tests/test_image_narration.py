from types import SimpleNamespace
import unittest

from companion_v2.conversation.media.image_narration import (
    KIND,
    PROMPT,
    PrivateImageNarrationService,
)
from companion_v2.conversation.media.models import OWNER as IMAGE_OWNER
from companion_v2.conversation.media.models import INSTRUCTION as IMAGE_INSTRUCTION
from companion_v2.conversation.media.context_caption import PROMPT as HISTORY_IMAGE_PROMPT
from companion_v2.foundation.refs import ScopeKind


class ImageNarrationTests(unittest.IsolatedAsyncioTestCase):
    def test_current_and_historical_image_prompts_distinguish_expression_from_content(self):
        for instruction in (PROMPT, IMAGE_INSTRUCTION, HISTORY_IMAGE_PROMPT):
            self.assertIn("表情包", instruction)
            self.assertIn("普通", instruction)
        self.assertIn("图像表达意图", PROMPT)
        self.assertIn("图片类型", PROMPT)
        self.assertIn("不从文件名或格式猜测", PROMPT)
        self.assertIn("用户的问题", IMAGE_INSTRUCTION)
        self.assertIn("不确定", IMAGE_INSTRUCTION)
        self.assertIn("不要自动把重点放在认出自己", IMAGE_INSTRUCTION)
        self.assertIn("最多顺带提一个显眼细节", IMAGE_INSTRUCTION)
        self.assertIn("只有用户本轮文字明确", IMAGE_INSTRUCTION)
        self.assertIn("组合结果", PROMPT)
        self.assertIn("不要把普通多图强行合并", PROMPT)

    def test_direct_image_reply_instruction_survives_without_self_recognition(self):
        instruction = PrivateImageNarrationService.reply_instruction({})
        self.assertIn("最多顺带提一个显眼细节", instruction)
        self.assertIn("具体回复限制优先", instruction)
        self.assertIn("没有可靠视觉材料时不要假装看过", instruction)

    async def test_same_reply_route_uses_native_image_without_secondary_narration(self):
        image = SimpleNamespace(source=SimpleNamespace(owner=IMAGE_OWNER))
        context = SimpleNamespace(scope=SimpleNamespace(kind=ScopeKind.PRIVATE))
        request = SimpleNamespace(images=(image,))
        parent_run = SimpleNamespace(task=SimpleNamespace(spec=SimpleNamespace(context=context)))

        class Router:
            profiles = {KIND: object()}

            def selected_route(self, _context, task, _request, *, at):
                self.at = at
                if task == KIND:
                    return "provider", "model", ()
                return "provider", "model", (SimpleNamespace(capabilities=("image",)),)

        router = Router()
        service = PrivateImageNarrationService(None)
        service.tasks = SimpleNamespace(now=lambda: "now")
        service.gateway = SimpleNamespace(router=router)
        service.app = SimpleNamespace(messages=SimpleNamespace(request=lambda _run: request))
        settings = {
            "enable_private_image_self_recognition": True,
            "image_understanding_private_enabled": True,
        }

        result = await service.summarize(parent_run, "batch", settings)

        self.assertEqual(result, "")
        self.assertEqual(router.at, "now")
        self.assertIn("角色自我识别线索", service.reply_instruction({
            **settings, "private_image_self_recognition_hint": "蓝色月牙水印",
        }))


if __name__ == "__main__":
    unittest.main()
