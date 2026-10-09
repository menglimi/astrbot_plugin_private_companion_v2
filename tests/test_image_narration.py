from types import SimpleNamespace
import unittest

from companion_v2.conversation.media.image_narration import (
    KIND,
    PrivateImageNarrationService,
)
from companion_v2.conversation.media.models import OWNER as IMAGE_OWNER
from companion_v2.foundation.refs import ScopeKind


class ImageNarrationTests(unittest.IsolatedAsyncioTestCase):
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
