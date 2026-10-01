"""Run one isolated V2 model request against an already saved Screen original."""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import replace
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from PIL import Image


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--astrbot-config", type=Path, required=True)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    return parser.parse_args()


async def run(args):
    from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial

    from companion_v2.adapters.astrbot.model_wire import build_wire
    from companion_v2.adapters.astrbot.provider import AstrBotTextProvider, UsageTariff
    from companion_v2.conversation.foreground import PromptMaterial, SealedForegroundContext
    from companion_v2.conversation.media.models import ImageDescriptor
    from companion_v2.conversation.media.screen import INSTRUCTION, ScreenPromptImage
    from companion_v2.foundation.refs import SourceRef, VersionRef
    from tests.native_adapter_support import NativeFixture
    from tests.test_management_access import NOW

    body = args.image.read_bytes()
    actual_hash = hashlib.sha256(body).hexdigest()
    if actual_hash != args.sha256:
        raise ValueError("saved original SHA-256 mismatch")
    with Image.open(io.BytesIO(body)) as image:
        if image.format != "JPEG":
            raise ValueError("saved Screen original is not JPEG")
        width, height = image.size

    config = json.loads(args.astrbot_config.read_text(encoding="utf-8-sig"))
    model = next(item for item in config["provider"] if item.get("id") == args.provider_id)
    source = next(item for item in config["provider_sources"]
                  if item.get("id") == model.get("provider_source_id"))
    provider_config = {**source, **model, "id": model["id"]}
    if not any(provider_config.get("key", ())):
        raise ValueError("configured provider has no API key")

    class InspectedProvider(ProviderOpenAIOfficial):
        result_summary = None

        async def _query(self, payload, tools, *, request_max_retries=None):
            response = await super()._query(payload, tools,
                                            request_max_retries=request_max_retries)
            choice = response.raw_completion.choices[0]
            type(self).result_summary = {
                "finish_reason": choice.finish_reason,
                "content_preview": (choice.message.content or "")[:1200],
            }
            return response

    fixture = NativeFixture("runTest")
    fixture.setUp()
    try:
        fixture.native.provider = InspectedProvider(provider_config, config["provider_settings"])
        fixture.native.get_provider_by_id = lambda provider_id: (
            fixture.native.provider if provider_id == args.provider_id else None)
        adapter = AstrBotTextProvider(
            fixture.native, bridge=fixture.bridge, binding=fixture.providers[0].binding,
            provider_id=args.provider_id, version="4.27.2", provider_type=InspectedProvider,
            function_tool_type=object, tool_set_type=object, tariff=UsageTariff(0, 0, 0),
            maximum_output_tokens=args.max_output_tokens,
        )
        envelope = await fixture.envelope()
        scope = envelope.original.event.scope
        parent = SourceRef("saved-screen-tool", "screen", scope,
                           VersionRef("saved-screen-tool", 1), NOW)
        image_source = SourceRef("saved-screen-original", "screen", scope,
                                 VersionRef("saved-screen-original", 1), NOW)
        descriptor = ImageDescriptor(0, "image/jpeg", width, height, len(body), actual_hash)
        prompt_image = ScreenPromptImage(image_source, parent, descriptor,
            base64.b64encode(body).decode("ascii"), "saved Screen original")
        materials = envelope.original.context.materials + (
            PromptMaterial("screen", "screen_capture", "已保存的本轮设备屏幕截图。", parent),
            PromptMaterial("screen", "screen_capture:image", "屏幕图像原件。", image_source),
        )
        request = replace(envelope.original,
            context=SealedForegroundContext(materials, (), ()),
            instruction="请描述截图中清楚可见的内容。" + INSTRUCTION,
            images=(prompt_image,))
        envelope = replace(envelope, original=request,
                           task_prompt="只依据截图回答，简短描述。",
                           max_output_tokens=args.max_output_tokens)
        wire = build_wire(envelope)
        image_parts = (part for message in wire.messages
                       if isinstance(message["content"], list)
                       for part in message["content"])
        if wire.image_count != 1 or not any(
                part.get("type") == "image_url" for part in image_parts):
            raise ValueError("V2 model wire omitted the Screen original")
        result = await adapter.generate(envelope)
        print(json.dumps({
            "status": result.status,
            "failure": result.failure.value if result.failure else None,
            "image_sha256": actual_hash,
            "model_image_inputs": wire.image_count,
            "max_output_tokens": args.max_output_tokens,
            "usage_tokens": result.usage.tokens if result.usage else None,
            "draft_text": result.draft.text if result.draft else None,
            "claim_count": len(result.draft.claims) if result.draft else None,
            "native_result": fixture.native.provider.result_summary if result.status != "generated" else None,
            "platform_messages": 0,
        }, ensure_ascii=False))
        return result.status == "generated" and result.draft is not None
    finally:
        fixture.tearDown()
        fixture.doCleanups()


def main():
    args = arguments()
    if not 1024 <= args.max_output_tokens <= 4096:
        raise ValueError("acceptance output budget must be between 1024 and 4096")
    with TemporaryDirectory(prefix="companion-v2-saved-screen-") as root:
        os.environ["ASTRBOT_ROOT"] = root
        for name in ("openai", "httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        if not asyncio.run(run(args)):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
