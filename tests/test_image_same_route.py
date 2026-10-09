"""Matching image and reply routes use the captured image in one model request."""

from dataclasses import replace
import base64
import unittest
from unittest.mock import patch

from companion_v2.adapters.astrbot.model_wire import build_wire
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.media.image_narration import image_narration_profile
from companion_v2.conversation.foreground import ModelDraft
from companion_v2.model_gateway.models import Amount, ModelEnvelope, ProviderResponse
from companion_v2.model_gateway.routing import configuration_fields
from tests.test_conversation_images import ImageFixture, image_bytes


class SameImageRouteTests(ImageFixture, unittest.IsolatedAsyncioTestCase):
    async def test_matching_image_route_does_not_start_a_separate_narration(self):
        seen = []

        async def reply(envelope):
            seen.append(envelope)
            return ProviderResponse("generated", ModelDraft("图片里有一片红色。", ()),
                                    Amount(15, 40), "same-image-reply")

        provider = replace(self.native_model.local_provider(), generate=reply)
        profile = image_narration_profile(provider.binding.provider, max_output_tokens=100)
        self.profiles += (profile,)
        self.registry = FieldRegistry(version="image-direct.v1",
            fields=tuple(self.registry.fields.values()) + configuration_fields((profile,)))
        host = await self.setup_host(providers=(provider,))
        batch = host.receive(await self.capture(self.image_event())).unwrap()

        with patch.object(host.application.image_narration, "summarize",
                          side_effect=AssertionError("same-route image must bypass narration")):
            self.assertEqual((await self.done(host.application, batch))["state"], "complete")

        self.assertEqual(len(seen), 1)
        request = seen[0].original
        self.assertEqual(len(request.images), 1)
        wire = build_wire(ModelEnvelope(request, "fixture", 100, "fixture"))
        user_content = next(message["content"] for message in wire.messages if message["role"] == "user")
        image_part, = [item for item in user_content if item.get("type") == "image_url"]
        self.assertEqual(image_part["image_url"]["url"].split(",", 1)[1],
                         base64.b64encode(image_bytes()).decode("ascii"))


if __name__ == "__main__":
    unittest.main()
