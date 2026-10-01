"""Synthetic group originals shared by quote capture and governance tests."""

from copy import deepcopy
from dataclasses import replace
from functools import partial

from astrbot.api.message_components import Forward
from astrbot_host.audio.loader import load_native_audio
from astrbot_host.media import load_native_image
from astrbot_host.video.loader import load_native_video
from companion_v2.adapters.astrbot.forwards import read_private_forwards
from companion_v2.adapters.astrbot.group_forwards import read_group_forwards
from tests.audio_support import audio_bytes
from tests.forward_support import node_raw
from tests.group_media_support import GroupMediaFixture, group_raw, Plain, Reply, FakeRecord, FakeVideo


def raw_parts(parts):
    result = []
    for part in parts:
        kind = getattr(part.type, "value", part.type).lower()
        if kind == "plain":
            result.append({"type": "text", "data": {"text": part.text}})
        elif kind in ("forward", "reply"):
            result.append({"type": kind, "data": {"id": part.id}})
        elif kind == "at":
            result.append({"type": kind, "data": {"qq": part.qq}})
        elif kind in ("image", "record", "video"):
            result.append({"type": kind, "data": {"file": part.file}})
        else:
            raise AssertionError("unsupported synthetic group component")
    return result


class GroupQuoteMediaFixture(GroupMediaFixture):
    # Repeated original/media governance reads across confirmed quote history
    # exceed the ordinary four-second fixture on the local SDK runtime.
    batch_timeout_seconds = 15

    def setUp(self):
        super().setUp()
        loaders = dict(reverse_api_type=type(self.api), image_loader=load_native_image,
                       audio_loader=load_native_audio, video_loader=load_native_video)
        self.types = replace(self.types, forward=Forward,
            forward_loader=partial(read_private_forwards, **loaders),
            group_forward_loader=partial(read_group_forwards, **loaders))
        self.controller = self.make_controller(self.config)

    def media_event(self, parts, **options):
        event = super().media_event(parts, **options)
        event.message_obj.raw_message["message"] = raw_parts(parts)
        return event

    def store(self, identifier="345", *, sender="201", parts=None, nodes=None):
        parts = parts if parts is not None else [Plain("原群资料"), FakeRecord(), FakeVideo(), Forward(id="group-quoted-forward")]
        raw = group_raw(message_id=identifier, sender=sender, count=0)
        raw["message"] = raw_parts(parts)
        for part in raw["message"]:
            if part["type"] == "forward":
                part["data"]["content"] = deepcopy(nodes if nodes is not None else [
                    node_raw("外层显示资料", sender="888", nested=[node_raw("嵌套语音", sender="999", audios=(audio_bytes(),))])])
        self.records[identifier] = raw
        return parts

    async def original(self, identifier="345", *, sender="201", parts=None, nodes=None, **options):
        parts = self.store(identifier, sender=sender, parts=parts, nodes=nodes)
        return await self.receive_parts(parts, identifier=identifier, sender=sender, **options)

    async def quoted(self, identifier="345", **options):
        return await self.receive_parts([Reply(id=identifier), Plain("讨论引用资料")], **options)

    async def restart(self):
        await self.controller.terminate()
        self.controller = self.make_controller(self.config)
        (await self.controller.load_existing()).unwrap()
        (await self.controller.start()).unwrap()
