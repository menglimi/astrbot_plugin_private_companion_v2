"""One application serving private owners and independently authorized groups."""

import asyncio
from collections.abc import Mapping

from companion_v2.adapters.astrbot.application import AstrBotCompanionHost
from companion_v2.adapters.astrbot.memory_owner import memory_owner_provider
from companion_v2.adapters.astrbot.memory_push import memory_push_provider
from companion_v2.adapters.astrbot.native import NativePrivateBridge
from companion_v2.adapters.astrbot.group import NativeGroupBridge
from companion_v2.adapters.astrbot.onebot import OneBotPrivateSender
from companion_v2.adapters.astrbot.onebot_group import OneBotGroupSender
from companion_v2.adapters.astrbot.presence import OneBotPresencePort
from companion_v2.adapters.astrbot.provider import AstrBotTextProvider
from companion_v2.adapters.astrbot.provider_catalog import assemble_providers
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.content.authoring_tasks import authoring_profiles
from companion_v2.conversation.delivery import DeliveryReceipt, LocalSender
from companion_v2.conversation.messages import REPLY_KIND
from companion_v2.conversation.media.review_service import image_review_profile
from companion_v2.conversation.media.context_caption import context_caption_profile
from companion_v2.screen.interpretation import screen_interpretation_profile
from companion_v2.conversation.voice_reply import VoiceReplyDelivery
from companion_v2.execution.models import Lane, ProviderBinding, TaskError, digest, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.identity_policy.personas import RuntimeIdentity
from companion_v2.model_gateway.models import ModelTaskProfile
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.memory.reflection import reflection_profile
from companion_v2.proactive.service import contact_profile, persona_judge_profile
from companion_v2.role_work.journal.writing import writing_profiles
from companion_v2.role_work.reader import reading_profile
from companion_v2.role_work.state.maintenance import state_profile
from companion_v2.agenda.planning import planning_profile
from .qweather_weather import configured_qweather_weather_port
from .qweather_alerts import configured_qweather_alert_port
from .service_balance import configured_balance_port
from companion_v2.role_work.growth.progress import growth_progress_profile
from .multi_authority import HOST_ID
from .group_settings import GroupTarget
from .voice import NativeVoiceReply


def persona_conversation(conversation_id, role):
    # Native conversation IDs alone would let raw sources from persona A appear
    # to belong to B after a switch. Preserve an immutable scope for each role.
    return conversation_id + ":v2-role:" + digest(role.subject_id)


class MultiPrivateBridge(NativePrivateBridge):
    def __init__(self, *args, settings, authority, group_quote_loader=None, group_forward_loader=None,
                 group_component_reader=None, **kwargs):
        self.settings, self.authority = settings, authority
        # 上一次"因为没有对话权限而被拒"的对象；控制器据此在事务之外回一句。
        self.last_refusal = None
        self.targets = {target.route_key: target for target in settings.targets}
        super().__init__(*args, **kwargs)
        group_options = {**kwargs, "quote_loader": group_quote_loader, "component_reader": group_component_reader,
                         "reply_type": kwargs.get("reply_type") if group_quote_loader is not None else None,
                         "forward_loader": group_forward_loader,
                         "forward_type": kwargs.get("forward_type") if group_forward_loader is not None else None}
        self.groups = MultiGroupBridge(*args, group_targets=settings.group_targets, authority=authority, **group_options)

    def target_for_scope(self, scope):
        if scope.kind is ScopeKind.GROUP:
            return self.groups.target_for_scope(scope)
        target = self.targets.get((scope.platform, scope.account_id, scope.native_scope_id))
        if scope.kind is not ScopeKind.PRIVATE or target is None or target.bot_id != scope.bot_id:
            raise TaskError("host_target_unavailable", "the native private target is not configured")
        return target

    def client(self, scope):
        if scope.kind is ScopeKind.GROUP:
            return self.groups.client(scope)
        self.target_for_scope(scope)
        return super().client(scope)

    async def capture(self, event):
        if getattr(getattr(event.message_obj, "type", None), "value", None) == "GroupMessage":
            return await self.groups.capture(event)
        return await super().capture(event)

    async def _role(self, account, sender_id):
        conversation, role, instruction = await super()._role(account, sender_id)
        return persona_conversation(conversation, role), role, instruction

    async def verify_role(self, scope, binding, instruction=None):
        if scope.kind is ScopeKind.GROUP:
            return await self.groups.verify_role(scope, binding, instruction)
        result = await super().verify_role(scope, binding, instruction)
        current = require(self.authority.personas.resolve(scope, observed_at=self.now())).binding
        if current != binding:
            raise TaskError("role_binding_changed", "the native role context was replaced")
        return result


class MultiGroupBridge(NativeGroupBridge):
    def __init__(self, *args, authority, **kwargs):
        self.authority = authority
        super().__init__(*args, **kwargs)

    async def _role(self, account, session_id):
        conversation, role, instruction = await super()._role(account, session_id)
        return persona_conversation(conversation, role), role, instruction

    async def verify_role(self, scope, binding, instruction=None):
        result = await super().verify_role(scope, binding, instruction)
        if require(self.authority.personas.resolve(scope, observed_at=self.now())).binding != binding:
            raise TaskError("role_binding_changed", "the native group role context was replaced")
        return result


class MultiPresence:
    def __init__(self, session):
        self.session = session

    def port(self, context):
        session = self.session
        return OneBotPresencePort(session.bridge, reverse_api_type=session.types.reverse_api,
            authorize=lambda: session.authorize(context), now=session.now)

    async def typing(self, context, **kwargs):
        return await self.port(context).typing(context, **kwargs)

    async def custom_status(self, context, wording, **kwargs):
        return await self.port(context).custom_status(context, wording, **kwargs)

    async def online_status(self, context, mode, **kwargs):
        return await self.port(context).online_status(context, mode, **kwargs)


class ReviewFallbackRoutes:
    """Resolve a group member's own configured private route, or nothing.

    A group member is never given a private conversation implicitly. The route
    exists only when the same account already runs one of the installation's
    configured private targets for that member, that target still has current
    delivery authorization, and the group itself is an explicit group target.
    Anything else keeps the reviewed image out of every channel.
    """

    def __init__(self, session):
        self.session = session

    def __call__(self, group):
        session = self.session
        authority, settings = session.authority, session.settings
        try:
            group_target = session.bridge.target_for_scope(group.scope)
            if not isinstance(group_target, GroupTarget):
                return None
            member = group.actor.principal.native_account_id
            for target in settings.targets:
                if (target.platform_id, target.account_id, target.bot_id, target.participant_id) != (
                        group.scope.platform, group.scope.account_id, group.scope.bot_id, member):
                    continue
                # 正式版没有"投递授权"这道闸：解析到目标即可用（见 multi_authority.delivery_access）。
                try:
                    authority.delivery_access(target)
                except TaskError:
                    return None
                context = authority.context(target.target_id, group.role_binding.role.subject_id)
                return context.document()
            return None
        except TaskError:
            return None


class MultiHostSession:
    def __init__(self, runtime, native_context, *, settings, personas, authority, native_types,
                 provider_fingerprint, runtime_instance_id, now, native_tool_port=None, news_port=None,
                 solar_term_port=None, qzone_transport=None):
        self.runtime, self.settings, self.authority, self.types, self.now = runtime, settings, authority, native_types, now
        self.native_tool_port = native_tool_port
        common = settings.common
        self.voice = NativeVoiceReply(native_context).render
        self.voice_delivery = VoiceReplyDelivery(runtime, now)
        self.bridge = MultiPrivateBridge(native_context, settings=settings, authority=authority,
            version=native_types.version, event_type=native_types.event, installation_id=runtime.installation_id,
            host_id=HOST_ID, identities=authority.identities, accounts=settings.accounts, personas=personas,
            image_type=native_types.image, image_loader=native_types.image_loader,
            reply_type=native_types.reply, quote_loader=native_types.quote_loader,
            group_quote_loader=native_types.group_quote_loader,
            group_forward_loader=native_types.group_forward_loader,
            group_component_reader=native_types.group_component_reader,
            forward_type=native_types.forward, forward_loader=native_types.forward_loader, now=now,
            forward_intake=common.forward_intake,
            audio_type=native_types.audio, audio_loader=native_types.audio_loader, component_reader=native_types.component_reader,
            video_type=native_types.video, video_loader=native_types.video_loader)
        self.model = AstrBotTextProvider(native_context, bridge=self.bridge,
            binding=ProviderBinding("model.text", common.provider_id, native_types.version, provider_fingerprint),
            provider_id=common.provider_id, version=native_types.version, provider_type=native_types.provider,
            function_tool_type=native_types.function_tool, tool_set_type=native_types.tool_set,
            tariff=common.tariff, maximum_output_tokens=common.max_output_tokens,
            maximum_input_estimate=common.maximum_input_estimate, output_parameter=common.output_parameter,
            streaming=common.streaming)
        self.model._current()
        self.models = (self.model,) + assemble_providers(native_context, bridge=self.bridge,
            native_types=native_types, primary_id=common.provider_id, additional=common.additional_providers)
        profiles = (ModelTaskProfile(REPLY_KIND, Lane.FOREGROUND, common.provider_id, common.task_prompt,
                    default_fallback=common.fallback_provider_id, replacement_rules=common.replacement_rules,
                    fallback_on_refusal=common.fallback_on_refusal,
                    max_output_tokens=common.max_output_tokens, capabilities=("text", "tools")),
                    contact_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    persona_judge_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    reflection_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    state_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    planning_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    growth_progress_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    reading_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    image_review_profile(common.provider_id),
                    context_caption_profile(common.provider_id),
                    screen_interpretation_profile(common.provider_id),
                    *authoring_profiles(common.provider_id, draft_tokens=common.max_output_tokens),
                    *writing_profiles(common.provider_id, max_output_tokens=common.max_output_tokens))
        modes = ["onebot_private", "onebot_group"]
        self.sender_binding = ProviderBinding("message.delivery", "astrbot-multi." + ".".join(modes),
            native_types.version, digest([runtime.installation_id, *modes]))
        self.host = AstrBotCompanionHost(runtime, event_port=self.bridge.ports, identity_port=self.bridge.ports,
            role_port=self.bridge.ports, runtime_identity=RuntimeIdentity("companion", runtime_instance_id, "astrbot", HOST_ID),
            registry=FieldRegistry(version="astrbot-multi.v1", fields=configuration_fields(profiles)),
            profiles=profiles, providers=tuple(model.local_provider() for model in self.models), budget=common.budget,
            budget_soft=common.budget_soft,
            sender=LocalSender(self.sender_binding, self.send, supports_images=True), policy=common.policy, limits=common.limits, now=now,
            tool_port=native_tool_port, segmentation=common.segmentation,
            # 记忆归属读的是别家插件自己公开的声明；跨插件读取只在这一个适配函数里，
            # 核心不反向导入宿主包。写入端口复用同一条发现路径：日记、梦境与主动
            # 消息完成后推给当前对外表达记忆的一方，失败不影响已完成的领域动作。
            memory_owner=memory_owner_provider(native_context),
            memory_push=memory_push_provider(native_context),
            weather_port=configured_qweather_weather_port(),
            weather_alert_port=configured_qweather_alert_port(),
            balance_port=configured_balance_port(),
            news_port=news_port,
            solar_term_port=solar_term_port,
            qzone_transport=qzone_transport,
            voice_policy=common.voice_reply_policy if common.voice_reply_enabled else None,
            presence_port=MultiPresence(self))
        self.application = self.host.application
        self.application.image_fallback.attach_port(ReviewFallbackRoutes(self))
        # 私聊权限的**默认值**要在签发那一刻就读到：新用户一开始有没有对话/主动权限，
        # 由 `private_access` 那一组决定（见 companion_v2/relationships/private_access.py）。
        self.authority.attach_private_access(self.application.private_access_settings)
        if callable(getattr(native_tool_port, "bind_role_guard", None)):
            native_tool_port.bind_role_guard(self.bridge.verify_role, self.bridge.verified_persona)
        self._intake = {target.target_id: asyncio.Lock() for target in settings.all_targets}

    def scope(self, target, conversation_id):
        return ScopeRef(self.runtime.installation_id, target.platform_id, ScopeKind.PRIVATE, target.participant_id,
                        target.bot_id, target.account_id, conversation_id, target.participant_id)

    async def synchronize(self, target):
        account = self.bridge.accounts[(target.platform_id, target.account_id)]
        cid, role, instruction = await self.bridge._role(account, target.participant_id)
        scope = self.scope(target, cid)
        self.bridge.client(scope)
        context = self.authority.select(target, scope, role)
        return context, instruction

    async def start(self, *, expected_task_generation, expected_model_generation):
        for target in self.settings.targets:
            context, instruction = await self.synchronize(target)
            self.application.life_runtime.bind(context, instruction, guard=self.bridge.verify_role)
            self.application.state_maintenance.bind(context, instruction, guard=self.bridge.verify_role)
            if self.application.presence is not None:
                self.application.presence.bind(context)
        for model in self.models:
            model._current()
        if self.application.state != "new":
            raise TaskError("host_not_running", "shared host was closed during native preflight")
        if callable(getattr(self.native_tool_port, "register_catalog", None)):
            require(self.native_tool_port.register_catalog(observed_at=self.now()))
        return await self.application.start(expected_task_generation=expected_task_generation,
                                            expected_model_generation=expected_model_generation)

    async def receive(self, event, target):
        async with self._intake[target.target_id]:
            try:
                self.application.require_running()
                captured = require(await self.bridge.capture(event))
                if self.bridge.target_for_scope(captured.route.scope) != target:
                    raise TaskError("host_target_mismatch", "input changed its configured native route")
                self.application.require_running()
                # Admission, active-role fencing and input publication are one
                # transaction. Rejected inputs cannot change another task's role.
                with self.runtime.transaction():
                    context = (self.authority.groups.select(target, captured) if captured.route.scope.kind is ScopeKind.GROUP
                               else self.authority.select(target, captured.route.scope, captured.role))
                    if context.scope.kind is ScopeKind.PRIVATE:
                        # 私聊：对话权限按人判定。没有权限时不进对话；回话由控制器
                        # 在事务之外发（那里才有平台客户端），这里只记下对象。
                        if self.application.private_access_gate.denied(context, at=self.now()):
                            self.last_refusal = context
                            raise TaskError("private_access_dialogue_denied",
                                            "this private user has no dialogue permission")
                    else:
                        require(self.application.tasks.check_context_access(context, action="conversation.reply", observed_at=self.now()))
                    def admitted(original, batch_id, *, replayed):
                        if original.scope.kind is ScopeKind.GROUP:
                            self.authority.group_delivery.admit(target, original, batch_id,
                                self.sender_binding, replayed=replayed)
                    result = require(self.host.receive(captured, on_admitted=admitted))
                self._record_platform_names(event, context)
                if context.scope.kind is ScopeKind.PRIVATE:
                    self.application.life_runtime.bind(context, captured.instruction, guard=self.bridge.verify_role)
                    self.application.state_maintenance.bind(context, captured.instruction, guard=self.bridge.verify_role)
                return Outcome.success(result)
            except TaskError as error:
                return Outcome.failed(error.code, str(error))

    def _record_platform_names(self, event, context):
        """Record platform display names from the already authenticated OneBot
        event. Optional derivation: any failure only costs a name, never intake."""
        try:
            raw = getattr(event.message_obj, "raw_message", None)
            sender = raw.get("sender") if isinstance(raw, Mapping) else None
            if not isinstance(sender, Mapping):
                return
            group = context.scope.kind is ScopeKind.GROUP
            if not group and context.scope.native_scope_id != context.actor.principal.native_account_id:
                return
            self.application.messages.acquaintance.record_platform_names(
                context, group_id=context.scope.native_scope_id if group else None,
                nickname=sender.get("nickname"), card=sender.get("card"))
        except Exception:
            pass

    def authorize(self, context):
        self.application.require_running()
        target = self.bridge.target_for_scope(context.scope)
        require(self.application.tasks.check_context_access(context, action="conversation.reply", observed_at=self.now()))
        return (self.authority.group_delivery.access(target) if context.scope.kind is ScopeKind.GROUP
                else self.authority.delivery_access(target))

    def authorize_group(self, envelope):
        self.authorize(envelope.context)
        target = self.bridge.target_for_scope(envelope.context.scope)
        return self.authority.group_delivery.authorize_envelope(target, envelope)

    async def send(self, envelope):
        # 正式版：不再有"预览/草稿"这一档，也不再需要投递授权——一律真发。
        group = envelope.context.scope.kind is ScopeKind.GROUP
        sender_type = OneBotGroupSender if group else OneBotPrivateSender
        sender = sender_type(self.bridge, binding=self.sender_binding, version=self.types.version,
            reverse_api_type=self.types.reverse_api,
            authorize=lambda: self.authorize_group(envelope) if group else self.authorize(envelope.context), now=self.now,
            voice=self.voice, voice_delivery=self.voice_delivery,
            reaction_image_format=lambda: self.application.semantics.store.settings()["reactions_image_format"]
                if self.application.semantics is not None else "image")
        return await sender.send(envelope)

    async def close(self, *, grace_seconds=0.5):
        if callable(getattr(self.native_tool_port, "close", None)):
            self.native_tool_port.close()
        return await self.application.close(grace_seconds=grace_seconds)
