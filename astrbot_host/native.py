"""Read native host objects without model calls, platform sends or storage writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiocqhttp.api_impl import WebSocketReverseApi
from astrbot import __version__ as ASTRBOT_VERSION
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.message.components import Image, Reply, Forward, Record, Video, File

from companion_v2.adapters.astrbot.native import (
    HostPersona, NativePrivateBridge, account_number, bounded_native_lookup, persona_instruction,
)
from companion_v2.adapters.astrbot.provider import provider_fingerprint
from companion_v2.adapters.astrbot.provider_catalog import TextProviderSettings, assemble_providers
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.adapters.astrbot.staging_config import REQUIRED_CAPABILITIES, StagingConfiguration
from companion_v2.execution.models import digest
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef

from .settings import HostControlError, HostSettings, INSTALLATION_PREFIX
from .media import load_native_image
from .audio.loader import load_native_audio
from .media_components import group_components, private_components
from .video.loader import load_native_video
from .files.loader import load_native_file
from .video.gemini_provider import GeminiNativeVideoProvider
from .quotes import load_native_quote, load_native_group_quote
from .forwards import load_native_forwards, load_native_group_forwards


HOST_ID = "astrbot-local-staging"
ECOSYSTEM_ID = "companion-v2"


def _native_video_provider(context, bridge, native_types, native, settings):
    return GeminiNativeVideoProvider(context, bridge, native_types, native, settings=settings)


def installed_native_types() -> NativeAdapterTypes:
    return NativeAdapterTypes(
        ASTRBOT_VERSION,
        AiocqhttpMessageEvent,
        ProviderOpenAIOfficial,
        FunctionTool,
        ToolSet,
        WebSocketReverseApi,
        Image,
        load_native_image,
        Reply,
        load_native_quote,
        Forward,
        load_native_forwards,
        Record,
        load_native_audio,
        private_components,
        group_quote_loader=load_native_group_quote,
        group_forward_loader=load_native_group_forwards,
        video=Video,
        video_loader=load_native_video,
        group_component_reader=group_components,
        file=File,
        file_loader=load_native_file,
        video_provider_type=ProviderGoogleGenAI,
        video_provider_factory=_native_video_provider,
    )


@dataclass(frozen=True)
class NativeProbe:
    configuration: StagingConfiguration
    platform_kind: str
    account_connected: bool
    conversation_open: bool
    persona_selected: str | None
    provider_type: str
    streaming_requested: bool
    streaming_transport_available: bool

    @property
    def streaming_report(self) -> dict[str, Any]:
        available = self.streaming_transport_available
        return {
            "requested": self.streaming_requested,
            "available": available,
            "ready": not self.streaming_requested or available,
            "transport": "astrbot_native_query_stream" if available else None,
            "reason": None if not self.streaming_requested or available else "streaming_transport_unavailable",
        }

    def report(self, *, pinned: bool) -> dict[str, Any]:
        config = self.configuration
        return {
            "profile_id": config.scope.installation_id.removeprefix(INSTALLATION_PREFIX),
            "delivery_mode": config.delivery_mode,
            "platform_id": config.scope.platform,
            "platform_kind": self.platform_kind,
            "account_id": config.scope.account_id,
            "account_connected": self.account_connected,
            "participant_id": config.scope.native_scope_id,
            "conversation_id": config.scope.conversation_id,
            "conversation_open": self.conversation_open,
            "persona_id": self.persona_selected,
            "role_id": config.persona.role.subject_id,
            "persona_instruction_hash": config.persona.instruction_hash,
            "provider_id": config.provider_id,
            "provider_type": self.provider_type,
            "provider_fingerprint": config.provider_fingerprint,
            "configuration_fingerprint": config.fingerprint,
            "streaming": self.streaming_report,
            "pinned": pinned,
            "model_request_sent": False,
            "platform_message_sent": False,
        }


class NativeProbeService:
    """Resolve the configured host target without owning the staging lifecycle."""

    def __init__(self, context, native_types, now):
        self.context = context
        self.native_types = native_types
        self.now = now

    def _streaming_report(self, settings: HostSettings, provider) -> dict[str, Any]:
        available = type(provider) is self.native_types.provider and callable(
            getattr(provider, "_query_stream", None)
        )
        return {
            "requested": settings.streaming,
            "available": available,
            "ready": not settings.streaming or available,
            "transport": "astrbot_native_query_stream" if available else None,
            "reason": None if not settings.streaming or available else "streaming_transport_unavailable",
        }

    def discover(self, settings: HostSettings) -> dict[str, Any]:
        platform = self.context.get_platform_inst(settings.platform_id)
        if platform is None:
            raise HostControlError("staging_platform_unavailable", "the configured OneBot platform is unavailable")
        metadata = platform.meta()
        if metadata.name != "aiocqhttp" or metadata.id != settings.platform_id:
            raise HostControlError("staging_platform_unsupported", "the configured platform is not the selected OneBot instance")
        client = platform.get_client()
        clients = getattr(client, "_wsr_api_clients", {})
        if not isinstance(clients, dict):
            clients = {}
        connected_accounts = []
        for value in clients:
            try:
                connected_accounts.append(account_number(value))
            except (TypeError, ValueError):
                continue
        connected_accounts = sorted(set(connected_accounts), key=int)

        provider = self.context.get_provider_by_id(settings.provider_id) if settings.provider_id else None
        if provider is None and not settings.provider_id:
            provider = self.context.get_using_provider()
        provider_id = ""
        provider_hash = None
        if provider is not None:
            native_config = getattr(provider, "provider_config", {})
            candidate = native_config.get("id") if isinstance(native_config, dict) else None
            provider_id = candidate if isinstance(candidate, str) else ""
            if type(provider) is self.native_types.provider:
                provider_hash = provider_fingerprint(provider)
        return {
            "platform_id": metadata.id,
            "platform_kind": metadata.name,
            "connected_account_ids": connected_accounts,
            "configured_account_id": settings.account_id or None,
            "configured_participant_id": settings.participant_id or None,
            "configured_provider_id": settings.provider_id or None,
            "resolved_provider_id": provider_id or None,
            "provider_type": type(provider).__module__ + "." + type(provider).__qualname__ if provider else None,
            "provider_fingerprint": provider_hash,
            "provider_supported": type(provider) is self.native_types.provider,
            "streaming": self._streaming_report(settings, provider),
            "target_ready": bool(
                settings.account_id and settings.participant_id and settings.provider_id
            ),
            "enabled": settings.enabled,
            "model_request_sent": False,
            "platform_message_sent": False,
        }

    async def probe(
        self, settings: HostSettings, *, valid_from: datetime | None = None, require_enabled: bool = True
    ) -> NativeProbe:
        settings.require_ready(require_enabled=require_enabled)
        self.discover(settings)
        platform = self.context.get_platform_inst(settings.platform_id)
        assert platform is not None
        metadata = platform.meta()
        client = platform.get_client()
        clients = getattr(client, "_wsr_api_clients", {})
        if not clients.get(settings.account_id):
            raise HostControlError("staging_account_unavailable", "the configured OneBot account is not connected")

        umo = f"{settings.platform_id}:FriendMessage:{settings.participant_id}"
        manager = self.context.conversation_manager
        conversation_id = await bounded_native_lookup(manager.get_curr_conversation_id(umo), operation="conversation_id")
        conversation = (
            await bounded_native_lookup(manager.get_conversation(umo, conversation_id, create_if_not_exists=False),
                                        operation="conversation")
            if conversation_id is not None
            else None
        )
        if conversation_id is not None and conversation is None:
            raise HostControlError("staging_conversation_missing", "the selected AstrBot conversation is unavailable")
        provider_settings = self.context.get_config(umo=umo).get("provider_settings", {})
        selected, persona, _, special = await bounded_native_lookup(
            self.context.persona_manager.resolve_selected_persona(
                umo=umo,
                conversation_persona_id=conversation.persona_id if conversation is not None else None,
                platform_name="aiocqhttp",
                provider_settings=provider_settings,
            ), operation="persona"
        )
        if await bounded_native_lookup(manager.get_curr_conversation_id(umo), operation="conversation_verify") != conversation_id:
            raise HostControlError("staging_conversation_changed", "the AstrBot conversation changed during the probe")
        if special or persona is None and selected not in (None, "[%None]"):
            raise HostControlError("staging_persona_unsupported", "the selected AstrBot persona cannot be pinned")
        if persona is not None and persona.get("name") != selected:
            raise HostControlError("staging_persona_invalid", "AstrBot returned an inconsistent persona")
        if settings.persona_id and settings.persona_id != (selected or ""):
            raise HostControlError("staging_persona_mismatch", "the configured persona does not match the target conversation")
        instruction = persona_instruction(persona)

        provider = self.context.get_provider_by_id(settings.provider_id)
        if type(provider) is not self.native_types.provider:
            raise HostControlError("staging_provider_unsupported", "the configured provider does not use the verified AstrBot adapter")
        assemble_providers(self.context, bridge=None, native_types=self.native_types,
                           primary_id=settings.provider_id, additional=settings.additional_providers,
                           defaults=TextProviderSettings(settings.provider_id, settings.tariff,
                               settings.max_output_tokens, settings.maximum_input_estimate,
                               settings.output_parameter, settings.streaming))

        installation_id = settings.installation_id
        scope = ScopeRef(
            installation_id,
            settings.platform_id,
            ScopeKind.PRIVATE,
            settings.participant_id,
            settings.bot_id,
            settings.account_id,
            NativePrivateBridge._conversation_key(umo, conversation_id),
            settings.participant_id,
        )
        role = SubjectRef(installation_id, SubjectKind.BOT, settings.role_id)
        configuration = StagingConfiguration(
            scope=scope,
            host_id=HOST_ID,
            ecosystem_id=ECOSYSTEM_ID,
            subject=SubjectRef(installation_id, SubjectKind.HUMAN, "onebot-user:" + settings.participant_id),
            persona=HostPersona(settings.bot_id, selected, role, digest(instruction)),
            authority_ref="astrbot-dashboard:" + settings.profile_id,
            valid_from=valid_from or self.now(),
            expires_at=None,
            capabilities=tuple(sorted(REQUIRED_CAPABILITIES)),
            provider_id=settings.provider_id,
            provider_fingerprint=provider_fingerprint(provider),
            tariff=settings.tariff,
            budget=settings.budget,
            budget_soft=settings.budget_soft,
            task_prompt=settings.task_prompt,
            delivery_mode=settings.delivery_mode,
            max_output_tokens=settings.max_output_tokens,
            maximum_input_estimate=settings.maximum_input_estimate,
            output_parameter=settings.output_parameter,
            streaming=settings.streaming,
            segmentation=settings.segmentation,
            forward_intake=settings.forward_intake,
            policy=settings.policy,
            limits=settings.limits,
        )
        return NativeProbe(
            configuration,
            metadata.name,
            True,
            conversation_id is not None,
            selected,
            type(provider).__module__ + "." + type(provider).__qualname__,
            settings.streaming,
            callable(getattr(provider, "_query_stream", None)),
        )
