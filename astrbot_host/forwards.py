"""Install the real account-pinned OneBot readers for Forward components."""

from aiocqhttp.api_impl import WebSocketReverseApi

from companion_v2.adapters.astrbot.forwards import read_private_forwards
from companion_v2.adapters.astrbot.group_forwards import read_group_forwards
from companion_v2.conversation.forwards.models import ForwardIntakePolicy

from .media import load_native_image
from .audio.loader import load_native_audio
from .video.loader import load_native_video


async def load_native_forwards(locators, *, message_id, client, scope, intake=ForwardIntakePolicy()):
    return await read_private_forwards(locators, message_id=message_id, client=client, scope=scope,
        reverse_api_type=WebSocketReverseApi, image_loader=load_native_image,
        audio_loader=load_native_audio, video_loader=load_native_video, intake=intake)


async def load_native_group_forwards(locators, *, message_id, sender_id, client, scope, retained=(),
                                     intake=ForwardIntakePolicy()):
    return await read_group_forwards(locators, message_id=message_id, sender_id=sender_id,
        client=client, scope=scope, reverse_api_type=WebSocketReverseApi,
        image_loader=load_native_image, audio_loader=load_native_audio, video_loader=load_native_video,
        retained=retained, intake=intake)
