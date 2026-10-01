"""Verified group text and original media, including per-member sessions."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.group_audience import group_audience
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.conversation.media.models import MAX_INPUT_IMAGES, fits_budget
from companion_v2.conversation.media.audio.models import CapturedAudio, MAX_INPUT_AUDIOS
from companion_v2.conversation.media.video.models import CapturedVideo, MAX_VIDEOS, fits_video_budget
from companion_v2.conversation.forwards.models import CapturedForward, fits_forwards
from companion_v2.conversation.quotes.models import CapturedQuote, event_images, event_audios, event_videos, message_number
from companion_v2.conversation.quotes.forward_models import CapturedQuoteMedia, CapturedForwardQuote, CapturedForwardQuoteMedia
from .native import (NativeAudioLocator, NativeConversationInput, NativePrivateBridge, NativeVideoLocator,
                     MEDIA_PREPARE_TIMEOUT, account_number, native_id)
from .quotes import NativeQuoteLocator, image_locator
from .forwards import NativeForwardLocator, resource_id
from .group_quotes import mention_text


@dataclass(frozen=True)
class GroupEventRoute:
    platform_id: str
    account_id: str
    sender_id: str
    group_id: str
    session_id: str
    event_id: str

    @property
    def route_key(self):
        return self.platform_id, self.account_id, self.group_id


def group_event_route(event):
    """Cross-check normalized fields against the original authenticated OneBot event."""
    message, meta, session = event.message_obj, event.platform_meta, event.session
    if (getattr(message.type, "value", None) != "GroupMessage"
            or getattr(session.message_type, "value", None) != "GroupMessage"):
        raise TaskError("host_scene_unsupported", "group capture requires a native group event")
    sender, login, group = (account_number(message.sender.user_id), account_number(message.self_id),
                            account_number(message.group_id))
    event_id = native_id(message.message_id)
    raw = getattr(message, "raw_message", None)
    if (not isinstance(raw, Mapping) or raw.get("post_type") != "message" or raw.get("message_type") != "group"
            or raw.get("anonymous") is not None or raw.get("sub_type") == "anonymous"
            or not isinstance(raw.get("sender"), Mapping)
            or tuple(account_number(raw.get(key)) for key in ("self_id", "user_id", "group_id")) != (login, sender, group)
            or account_number(raw["sender"].get("user_id")) != sender or native_id(raw.get("message_id")) != event_id
            or sender == login):
        raise TaskError("host_group_identity_mismatch", "group sender and route must match the original OneBot message")
    if (meta.name != "aiocqhttp" or session.platform_id != meta.id or session.platform_name != meta.id
            or session.session_id not in (group, sender + "_" + group)
            or message.session_id != group
            or event.unified_msg_origin != f"{meta.id}:GroupMessage:{session.session_id}"):
        raise TaskError("host_route_mismatch", "group fields do not identify one native conversation")
    return GroupEventRoute(meta.id, login, sender, group, session.session_id, event_id)


class NativeGroupBridge(NativePrivateBridge):
    scope_kind = ScopeKind.GROUP

    def __init__(self, *args, group_targets, **kwargs):
        self.group_targets = {t.route_key: t for t in group_targets}
        super().__init__(*args, **kwargs)

    @staticmethod
    def _umo(platform_id, session_id):
        return f"{platform_id}:GroupMessage:{session_id}"

    def target_for_scope(self, scope):
        target = self.group_targets.get((scope.platform, scope.account_id, scope.native_scope_id))
        if scope.kind is not ScopeKind.GROUP or target is None or scope.bot_id != target.bot_id:
            raise TaskError("host_target_unavailable", "the native group target is not configured")
        return target

    def client(self, scope):
        self.target_for_scope(scope)
        return super().client(scope)

    async def verify_role(self, scope, binding, instruction=None):
        self.client(scope)
        parts = scope.session_id.split("_")
        if (len(parts) not in (1, 2) or any(account_number(part) != part for part in parts)
                or parts[-1] != scope.native_scope_id or binding.scope != scope):
            raise TaskError("host_route_changed", "original group session is inconsistent")
        cid, role, prompt = await self._role(self.accounts[(scope.platform, scope.account_id)], scope.session_id)
        self.client(scope)
        if cid != scope.conversation_id or role != binding.role or (instruction is not None and prompt != instruction):
            raise TaskError("host_persona_changed", "group conversation/persona differs from the original turn")
        return prompt

    async def capture(self, event):
        try:
            if type(event) is not self.event_type:
                raise TaskError("host_event_unsupported", "group capture requires the verified native event class")
            route = group_event_route(event)
            target = self.group_targets.get(route.route_key)
            account = self.accounts.get((route.platform_id, route.account_id))
            if target is None or account is None or target.bot_id != account.bot_id:
                raise TaskError("host_target_unavailable", "group and account require an explicit target mapping")
            original_parts = event.message_obj.raw_message.get("message")
            if original_parts is not None and (not isinstance(original_parts, list)
                    or not 1 <= len(original_parts) <= 128
                    or any(not isinstance(p, Mapping) or not isinstance(p.get("data"), Mapping)
                           or p.get("type") not in ("text", "at", "image", "reply", "forward", "record", "video") for p in original_parts)):
                # Host STT can replace Record with Plain before this plugin runs.
                # Such text cannot bypass the original group media contract.
                raise TaskError("host_group_media_unsupported", "original group components need their own source adapter")
            parts = self.component_reader(event) if self.component_reader is not None else tuple(event.message_obj.message)
            if not parts or len(parts) > 128:
                raise TaskError("host_media_unsupported", "message components are empty or exceed the intake budget")
            text_parts, image_locators, quote_locators, forward_locators = [], [], [], []
            audio_locators, video_locators = [], []
            for position, part in enumerate(parts):
                kind = getattr(part.type, "value", part.type)
                if kind == "Plain" and isinstance(part.text, str):
                    text_parts.append(part.text)
                elif kind == "At":
                    text_parts.append(mention_text(part.qq, route.account_id))
                elif kind == "Image" and self.image_type is not None and type(part) is self.image_type:
                    image_locators.append(image_locator(position, part.file, part.url))
                    text_parts.append("\n[图片 " + str(len(image_locators)) + "]\n")
                elif kind == "Reply" and self.reply_type is not None and type(part) is self.reply_type:
                    quote_locators.append(NativeQuoteLocator(position, message_number(part.id)))
                    text_parts.append("\n[引用消息]\n")
                elif kind == "Forward" and self.forward_type is not None and type(part) is self.forward_type:
                    forward_locators.append(NativeForwardLocator(position, resource_id(part.id)))
                    text_parts.append("\n[合并转发 " + str(len(forward_locators)) + "]\n")
                elif kind == "Record" and self.audio_type is not None and type(part) is self.audio_type:
                    value = part.file if type(part.file) is str and part.file.startswith("base64://") else part.url or part.file
                    if type(value) is not str or not value:
                        raise TaskError("host_audio_unavailable", "group voice has no original host attachment")
                    audio_locators.append(NativeAudioLocator(position, value))
                    text_parts.append("\n[语音 " + str(len(audio_locators)) + "]\n")
                elif kind == "Video" and self.video_type is not None and type(part) is self.video_type:
                    value = part.file if type(part.file) is str and part.file.startswith("base64://") else part.url or part.file
                    if type(value) is not str or not value:
                        raise TaskError("host_video_unavailable", "group video has no original host attachment")
                    video_locators.append(NativeVideoLocator(position, value))
                    text_parts.append("\n[视频 " + str(len(video_locators)) + "]\n")
                else:
                    raise TaskError("host_group_media_unsupported", "this group component needs its own source adapter")
            if original_parts is not None:
                raw_forwards = tuple((position, part["data"].get("id"))
                    for position, part in enumerate(original_parts) if part.get("type") == "forward")
                if raw_forwards and self.forward_type is None:
                    raise TaskError("host_group_media_unsupported", "group forward source adapter is not installed")
                try:
                    original_forwards = tuple((position, resource_id(identifier)) for position, identifier in raw_forwards)
                except TaskError:
                    raise TaskError("host_group_media_unsupported", "original group forward identifier is unavailable") from None
                if original_forwards != tuple((item.position, item.resource) for item in forward_locators):
                    raise TaskError("host_group_media_unsupported", "host-preprocessed forwards need their original native component")
                for kind, locators in (("record", audio_locators), ("video", video_locators)):
                    originals = []
                    for position, part in enumerate(original_parts):
                        if part["type"] != kind:
                            continue
                        data = part["data"]
                        value = data.get("file")
                        if not (type(value) is str and value.startswith("base64://")):
                            value = data.get("url") or value
                        originals.append((position, value))
                    if tuple(originals) != tuple((item.position, item.locator) for item in locators):
                        raise TaskError("host_group_media_unsupported", "group media differs from its original component")
            elif audio_locators or video_locators:
                raise TaskError("host_group_media_unsupported", "group media requires original OneBot components")
            if (len(image_locators) > MAX_INPUT_IMAGES or len(quote_locators) > 1
                    or len(forward_locators) > self.forward_intake.max_forwards or len(audio_locators) > MAX_INPUT_AUDIOS
                    or len(video_locators) > MAX_VIDEOS):
                raise TaskError("host_group_media_limit", "group attachments exceed the input budget")
            text = "".join(text_parts)
            if not text.strip() or len(text) > 65536:
                raise TaskError("host_text_invalid", "group input must be bounded nonempty text")
            at, event_client = datetime.fromtimestamp(event.created_at, timezone.utc), event.bot
            principal = AuthenticatedHostPrincipal(self.installation_id, self.host_id, route.platform_id,
                route.sender_id, account.bot_id, route.account_id)
            # All mutable native fields above are frozen before host I/O. Identity
            # enrollment happens only in the later atomic, authorized admission.
            cid, role, instruction = await self._role(account, route.session_id)
            scope = ScopeRef(self.installation_id, route.platform_id, ScopeKind.GROUP, route.group_id,
                             account.bot_id, route.account_id, cid, route.session_id)
            if event_client is not self.client(scope) or not event_client._wsr_api_clients.get(route.account_id):
                raise TaskError("host_client_mismatch", "group event did not originate from the connected account client")
            connection = event_client._wsr_api_clients[route.account_id]
            frozen_images, frozen_quotes, frozen_forwards = (tuple(image_locators), tuple(quote_locators),
                                                               tuple(forward_locators))
            frozen_audios, frozen_videos = tuple(audio_locators), tuple(video_locators)

            async def prepare():
                images = await self._capture_images(frozen_images)
                quotes = []
                for locator in frozen_quotes:
                    if locator.message_id == route.event_id:
                        raise TaskError("host_quote_invalid", "a group input cannot quote itself")
                    quote = await self.quote_loader(locator, client=event_client, scope=scope,
                                                    intake=self.forward_intake)
                    if (type(quote) not in (CapturedQuote, CapturedQuoteMedia, CapturedForwardQuote, CapturedForwardQuoteMedia)
                            or quote.position != locator.position
                            or quote.message_id != locator.message_id
                            or (quote.sent_at is not None and quote.sent_at > at.timestamp())):
                        raise TaskError("host_quote_invalid", "group quote lost its original attribution or time")
                    quotes.append(quote)
                forwards = ()
                if frozen_forwards:
                    if self.forward_loader is None or self.forward_type is None:
                        raise TaskError("host_group_media_unsupported", "group forward source adapter is unavailable")
                    retained = tuple(i.descriptor for i in images) + tuple(
                        i.descriptor for quote in quotes for i in event_images(quote))
                    forwards = await self.forward_loader(frozen_forwards, message_id=route.event_id,
                        sender_id=route.sender_id, client=event_client, scope=scope, retained=retained,
                        intake=self.forward_intake)
                    if (not isinstance(forwards, tuple) or len(forwards) != len(frozen_forwards)
                            or any(type(f) is not CapturedForward or
                                (f.position, f.resource_hash) != (l.position, digest(l.resource))
                                for f, l in zip(forwards, frozen_forwards)) or not fits_forwards(forwards)):
                        raise TaskError("host_forward_invalid", "group forward loader changed the captured manifest")
                if not fits_forwards((*forwards, *(f for quote in quotes for f in getattr(quote, "forwards", ())))):
                    raise TaskError("host_forward_limit", "direct and quoted group forwards share one input budget")
                all_images = tuple(i.descriptor for i in images) + tuple(
                    i.descriptor for quote in quotes for i in event_images(quote)) + tuple(
                    i.descriptor for forward in forwards for node in forward.nodes for i in node.images)
                if not fits_budget(all_images):
                    raise TaskError("host_group_media_limit", "direct, quoted and forwarded group images share one input budget")
                audio_descriptors = [getattr(item, "descriptor", item) for quote in quotes for item in event_audios(quote)]
                audio_descriptors.extend(item.descriptor for forward in forwards for node in forward.nodes for item in node.audios)
                video_descriptors = [getattr(item, "descriptor", item) for quote in quotes for item in event_videos(quote)]
                video_descriptors.extend(item.descriptor for forward in forwards for node in forward.nodes for item in node.videos)
                if not fits_video_budget(tuple(video_descriptors), all_images, tuple(audio_descriptors)):
                    raise TaskError("host_group_media_limit", "group attachments exceed their shared input budget")
                audios = []
                for locator in frozen_audios:
                    audio = await self.audio_loader(locator)
                    if type(audio) is not CapturedAudio or audio.descriptor.position != locator.position:
                        raise TaskError("host_audio_invalid", "group audio loader changed the original component position")
                    audios.append(audio)
                    audio_descriptors.append(audio.descriptor)
                    if not fits_video_budget(tuple(video_descriptors), all_images, tuple(audio_descriptors)):
                        raise TaskError("host_group_media_limit", "group voice and visual attachments exceed the input budget")
                videos = []
                for locator in frozen_videos:
                    video = await self.video_loader(locator)
                    if type(video) is not CapturedVideo or video.descriptor.position != locator.position:
                        raise TaskError("host_video_invalid", "group video loader changed the original component position")
                    videos.append(video)
                    video_descriptors.append(video.descriptor)
                    if not fits_video_budget(tuple(video_descriptors), all_images, tuple(audio_descriptors)):
                        raise TaskError("host_group_media_limit", "group video and other attachments exceed the input budget")
                if not fits_video_budget(tuple(video_descriptors), all_images, tuple(audio_descriptors)):
                    raise TaskError("host_group_media_limit", "direct, quoted and forwarded media share one input budget")
                return images, tuple(quotes), forwards, tuple(audios), tuple(videos)

            images, quotes, forwards, audios, videos = (), (), (), (), ()
            if frozen_images or frozen_quotes or frozen_forwards or frozen_audios or frozen_videos:
                try:
                    images, quotes, forwards, audios, videos = await asyncio.wait_for(prepare(), MEDIA_PREPARE_TIMEOUT)
                except asyncio.TimeoutError:
                    raise TaskError("host_media_timeout", "group attachment preparation exceeded its intake time") from None
                if await self._role(account, route.session_id) != (cid, role, instruction):
                    raise TaskError("host_persona_changed", "group role changed while preparing attachments")
                if (event_client is not self.client(scope)
                        or event_client._wsr_api_clients.get(route.account_id) is not connection):
                    raise TaskError("host_client_mismatch", "original group account connection changed")
            speaker = SubjectRef(self.installation_id, SubjectKind.HUMAN, "onebot-user:" + route.sender_id)
            return Outcome.success(NativeConversationInput(route.event_id, principal,
                ConversationRoute(scope, group_id=route.group_id), group_audience(scope, speaker), text, at, role, instruction,
                images, quotes, forwards, audios, videos))
        except TaskError as error:
            return Outcome.failed(error.code, str(error))
        except Exception:
            return Outcome.failed("host_capture_failed", "group route, sender or persona could not be verified")
