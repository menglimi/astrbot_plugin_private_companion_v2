"""Shared frozen media capture after a private or group original is verified."""

from companion_v2.conversation.media.models import CapturedImage, MAX_INPUT_IMAGES, check_manifest
from companion_v2.conversation.media.audio.models import CapturedAudio, MAX_INPUT_AUDIOS, fits_audio_budget
from companion_v2.conversation.media.video.models import CapturedVideo, MAX_VIDEOS, fits_video_budget
from companion_v2.conversation.quotes.models import CapturedQuote
from companion_v2.conversation.quotes.forward_models import (
    CapturedForwardQuote, CapturedForwardQuoteMedia, CapturedQuoteMedia,
)
from companion_v2.conversation.forwards.models import ForwardIntakePolicy
from companion_v2.execution.models import TaskError
from .forwards import NativeForwardLocator, resource_id, freeze_forward_cards, capture_forward_cards
from .quotes import image_locator, audio_locator, video_locator


async def capture_quote_content(locator, sender, sent_at, parts, *, current, image_loader,
                                audio_loader=None, video_loader=None, mention=None,
                                intake=ForwardIntakePolicy()):
    if not isinstance(parts, list) or not parts:
        raise TaskError("host_quote_unsupported", "quote requires a native component array")
    if len(parts) > 128:
        raise TaskError("host_quote_limit", "quote exceeds its component budget")
    text, locators, audio_locators, video_locators, forward_locators, cards = [], [], [], [], [], []
    for position, part in enumerate(parts):
        if not isinstance(part, dict) or not isinstance(part.get("data"), dict):
            raise TaskError("host_quote_unsupported", "quoted component is not supported")
        data = part["data"]
        if part.get("type") == "text" and type(data.get("text")) is str:
            text.append(data["text"])
        elif part.get("type") == "image":
            locators.append(image_locator(position, data.get("file"), data.get("url")))
            text.append("\n[图片 " + str(len(locators)) + "]\n")
        elif part.get("type") == "forward":
            forward_locators.append(NativeForwardLocator(position, resource_id(data.get("id"))))
            cards.append(data)
            text.append("\n[合并转发 " + str(len(forward_locators)) + "]\n")
        elif part.get("type") == "record":
            if audio_loader is None:
                raise TaskError("host_quote_unsupported", "quoted voice decoder is unavailable")
            audio_locators.append(audio_locator(position, data.get("file"), data.get("url")))
            text.append("\n[语音 " + str(len(audio_locators)) + "]\n")
        elif part.get("type") == "video":
            if video_loader is None:
                raise TaskError("host_quote_unsupported", "quoted video decoder is unavailable")
            video_locators.append(video_locator(position, data.get("file"), data.get("url")))
            text.append("\n[视频 " + str(len(video_locators)) + "]\n")
        elif part.get("type") == "at" and mention is not None:
            text.append(mention(data.get("qq")))
        else:
            raise TaskError("host_quote_unsupported", "nested replies and unsupported components need their own adapter")
    body = "".join(text)
    if not body.strip():
        raise TaskError("host_quote_unsupported", "quoted content is unavailable")
    if (len(body) > 65536 or len(locators) > MAX_INPUT_IMAGES
            or len(audio_locators) > MAX_INPUT_AUDIOS or len(video_locators) > MAX_VIDEOS):
        raise TaskError("host_quote_limit", "quoted content exceeds its intake budget")
    # Freeze the entire returned message before the first image await.
    plans = (freeze_forward_cards(tuple(forward_locators), cards,
                audio_enabled=audio_loader is not None, video_enabled=video_loader is not None, intake=intake)
             if forward_locators else ())
    planned = [n for _, nodes in plans for n in nodes]
    if (len(locators) + sum(len(n.images) for n in planned) > MAX_INPUT_IMAGES
            or len(audio_locators) + sum(len(n.audios) for n in planned) > MAX_INPUT_AUDIOS
            or len(video_locators) + sum(len(n.videos) for n in planned) > MAX_VIDEOS):
        raise TaskError("host_quote_limit", "quoted originals exceed their shared media budget")
    images = []
    for item in locators:
        current()
        captured = await image_loader(item)
        current()
        if not isinstance(captured, CapturedImage) or captured.descriptor.position != item.position:
            raise TaskError("host_image_invalid", "quote loader changed the original image position")
        images.append(captured)
        check_manifest(tuple(i.descriptor for i in images))
    audios = []
    for item in audio_locators:
        if audio_loader is None:
            raise TaskError("host_quote_unsupported", "quoted voice decoder is unavailable")
        current()
        captured = await audio_loader(item)
        current()
        if type(captured) is not CapturedAudio or captured.descriptor.position != item.position:
            raise TaskError("host_audio_invalid", "quote loader changed the original voice position")
        audios.append(captured)
        if not fits_audio_budget(tuple(i.descriptor for i in audios), tuple(i.descriptor for i in images)):
            raise TaskError("host_quote_limit", "quoted voice and images exceed their shared media budget")
    videos = []
    for item in video_locators:
        if video_loader is None:
            raise TaskError("host_quote_unsupported", "quoted video decoder is unavailable")
        current()
        captured = await video_loader(item)
        current()
        if type(captured) is not CapturedVideo or captured.descriptor.position != item.position:
            raise TaskError("host_video_invalid", "quote loader changed the original video position")
        videos.append(captured)
        if not fits_video_budget(tuple(i.descriptor for i in videos), tuple(i.descriptor for i in images),
                                 tuple(i.descriptor for i in audios)):
            raise TaskError("host_quote_limit", "quoted video and other attachments exceed their shared media budget")
    if plans:
        forwards = await capture_forward_cards(plans, image_loader=image_loader, audio_loader=audio_loader,
            video_loader=video_loader, current=current, retained=tuple(i.descriptor for i in images),
            retained_audios=tuple(i.descriptor for i in audios), retained_videos=tuple(i.descriptor for i in videos))
        kind = CapturedForwardQuoteMedia if audios or videos else CapturedForwardQuote
        return kind(locator.position, locator.message_id, sender, sent_at, body, tuple(images), forwards,
                    **({"audios": tuple(audios), "videos": tuple(videos)} if audios or videos else {}))
    current()
    if audios or videos:
        return CapturedQuoteMedia(locator.position, locator.message_id, sender, sent_at, body, tuple(images),
                                  tuple(audios), tuple(videos))
    return CapturedQuote(locator.position, locator.message_id, sender, sent_at, body, tuple(images))
