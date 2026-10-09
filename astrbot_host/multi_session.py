"""One application serving private owners and independently authorized groups."""

import asyncio
from collections import defaultdict
from collections.abc import Mapping
import json
import logging

from companion_v2.adapters.astrbot.application import AstrBotCompanionHost
from companion_v2.adapters.astrbot.memory_owner import memory_owner_provider
from companion_v2.adapters.astrbot.memory_push import memory_push_provider
from companion_v2.adapters.astrbot.native import NativePrivateBridge, account_number
from companion_v2.adapters.astrbot.group import NativeGroupBridge
from companion_v2.adapters.astrbot.onebot import OneBotPrivateSender
from companion_v2.adapters.astrbot.onebot_group import OneBotGroupSender
from companion_v2.adapters.astrbot.presence import OneBotPresencePort
from companion_v2.adapters.astrbot.provider import AstrBotTextProvider
from companion_v2.adapters.astrbot.provider_catalog import TextProviderSettings, assemble_providers, loaded_routing
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.content.authoring_tasks import authoring_profiles
from companion_v2.conversation.delivery import DeliveryReceipt, LocalSender
from companion_v2.conversation.messages import REPLY_KIND
from companion_v2.conversation.participation import group_participation_settings
from companion_v2.conversation.media.review_service import image_review_profile
from companion_v2.conversation.media.context_caption import context_caption_profile
from companion_v2.conversation.media.image_narration import image_narration_profile
from companion_v2.conversation.media.video.narration import video_narration_profile
from companion_v2.conversation.media.understanding import intake_settings as file_intake_settings
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
from .weather_settings import configured_weather_ports
from companion_v2.role_work.growth.progress import growth_progress_profile
from companion_v2.role_work.journal.self_review_service import self_review_profile
from companion_v2.expression.style_service import expression_learning_profile
from companion_v2.expression.review import expression_review_profile
from .multi_authority import HOST_ID
from .model_settings import conversation_provider_resolver
from .group_settings import GroupTarget
from .group_admission import group_trigger_facts
from .voice import NativeVoiceReply


logger = logging.getLogger(__name__)


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
        self.groups = MultiGroupBridge(*args, group_targets=settings.group_targets, authority=authority,
                                       settings=settings, **group_options)

    def target_for_scope(self, scope):
        if scope.kind is ScopeKind.GROUP:
            return self.groups.target_for_scope(scope)
        target = self.targets.get((scope.platform, scope.account_id, scope.native_scope_id))
        if target is None and scope.kind is ScopeKind.PRIVATE:
            target = self.settings.private_target(scope.platform, scope.account_id, scope.native_scope_id)
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
            return await self.groups.capture(event, allow_text_fallback=True)
        message, session, meta = event.message_obj, event.session, event.platform_meta
        if (type(event) is not self.event_type
                or getattr(getattr(message, "type", None), "value", None) != "FriendMessage"
                or getattr(getattr(session, "message_type", None), "value", None) != "FriendMessage"
                or getattr(message, "group_id", None)):
            return await super().capture(event)
        try:
            sender, login = account_number(message.sender.user_id), account_number(message.self_id)
            if (meta.name != "aiocqhttp" or session.platform_id != meta.id or session.platform_name != meta.id
                    or session.session_id != sender or event.unified_msg_origin != f"{meta.id}:FriendMessage:{sender}"):
                return await super().capture(event)
            target = self.settings.private_target(meta.id, login, sender)
            if target is None:
                return await super().capture(event)
            account = self.accounts.get((meta.id, login))
            platform = self.context.get_platform_inst(meta.id)
            if (account is None or account.bot_id != target.bot_id or platform is None
                    or platform.get_client() is not event.bot or not event.bot._wsr_api_clients.get(login)):
                raise TaskError("host_client_mismatch", "private event did not originate from its registered Bot account")
            self.authority.ensure_actor(target)
        except (ValueError, AttributeError, TypeError):
            return await super().capture(event)
        return await super().capture(event)

    async def capture_text_only(self, event):
        """Keep authenticated group text when optional native media is unavailable."""
        if getattr(getattr(event.message_obj, "type", None), "value", None) != "GroupMessage":
            return Outcome.failed("host_scene_unsupported", "text-only fallback requires a native group event")
        return await self.groups.capture_text_only(event)

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
    def __init__(self, *args, authority, settings, **kwargs):
        self.authority, self.settings = authority, settings
        super().__init__(*args, **kwargs)

    def target_for_route(self, platform_id, account_id, group_id):
        return (super().target_for_route(platform_id, account_id, group_id)
                or self.settings.group_target(platform_id, account_id, group_id))

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
                return context
            return None
        except TaskError:
            return None


class MultiHostSession:
    def __init__(self, runtime, native_context, *, settings, personas, authority, native_types,
                 provider_fingerprint, runtime_instance_id, now, native_tool_port=None, news_port=None,
                 solar_term_port=None, qzone_transport=None, balance_port=None, weather_ports=None):
        self.runtime, self.settings, self.authority, self.types, self.now = runtime, settings, authority, native_types, now
        self.native_tool_port = native_tool_port
        common = settings.common
        weather_port, weather_alert_port = weather_ports or configured_weather_ports(None)
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
            video_type=native_types.video, video_loader=native_types.video_loader,
            file_type=native_types.file, file_loader=native_types.file_loader,
            file_settings=lambda scope, role: file_intake_settings(runtime, scope, role))
        self.model = AstrBotTextProvider(native_context, bridge=self.bridge,
            binding=ProviderBinding("model.text", common.provider_id, native_types.version, provider_fingerprint),
            provider_id=common.provider_id, version=native_types.version, provider_type=native_types.provider,
            function_tool_type=native_types.function_tool, tool_set_type=native_types.tool_set,
            tariff=common.tariff, maximum_output_tokens=common.max_output_tokens,
            maximum_input_estimate=common.maximum_input_estimate, output_parameter=common.output_parameter,
            streaming=common.streaming)
        self.model._current()
        self.models = (self.model,) + assemble_providers(native_context, bridge=self.bridge,
            native_types=native_types, primary_id=common.provider_id, additional=common.additional_providers,
            defaults=TextProviderSettings(common.provider_id, common.tariff, common.max_output_tokens,
                common.maximum_input_estimate, common.output_parameter, common.streaming))
        fallback_provider_id, replacement_rules = loaded_routing(common.fallback_provider_id,
            common.replacement_rules, (model.binding.provider for model in self.models))
        profiles = (ModelTaskProfile(REPLY_KIND, Lane.FOREGROUND, common.provider_id, common.task_prompt,
                    default_fallback=fallback_provider_id, replacement_rules=replacement_rules,
                    fallback_on_refusal=common.fallback_on_refusal,
                    max_output_tokens=common.max_output_tokens, capabilities=("text", "tools")),
                    contact_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    persona_judge_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    reflection_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    state_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    planning_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    growth_progress_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    self_review_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    expression_learning_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    expression_review_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    expression_review_profile(common.provider_id, max_output_tokens=common.max_output_tokens, contact=True),
                    reading_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
                    image_review_profile(common.provider_id),
                    context_caption_profile(common.provider_id),
                    screen_interpretation_profile(common.provider_id),
                    *authoring_profiles(common.provider_id, draft_tokens=common.max_output_tokens),
                    *writing_profiles(common.provider_id, max_output_tokens=common.max_output_tokens),
                    *((image_narration_profile(next(model.binding.provider for model in self.models
                        if "image" in model.local_provider().capabilities)),)
                      if any("image" in model.local_provider().capabilities for model in self.models) else ()),
                    *((video_narration_profile(next(model.binding.provider for model in self.models
                        if "video" in model.local_provider().capabilities)),)
                      if any("video" in model.local_provider().capabilities for model in self.models) else ()))
        modes = ["onebot_private", "onebot_group"]
        self.sender_binding = ProviderBinding("message.delivery", "astrbot-multi." + ".".join(modes),
            native_types.version, digest([runtime.installation_id, *modes]))
        self.host = AstrBotCompanionHost(runtime, event_port=self.bridge.ports, identity_port=self.bridge.ports,
            role_port=self.bridge.ports, runtime_identity=RuntimeIdentity("companion", runtime_instance_id, "astrbot", HOST_ID),
            registry=FieldRegistry(version="astrbot-multi.v1", fields=configuration_fields(profiles)),
            profiles=profiles, providers=tuple(model.local_provider() for model in self.models), budget=common.budget,
            budget_soft=common.budget_soft,
            default_provider_resolver=conversation_provider_resolver(native_context),
            sender=LocalSender(self.sender_binding, self.send, supports_images=True, supports_poke=True), policy=common.policy, limits=common.limits, now=now,
            tool_port=native_tool_port, segmentation=common.segmentation,
            # 记忆归属读的是别家插件自己公开的声明；跨插件读取只在这一个适配函数里，
            # 核心不反向导入宿主包。写入端口复用同一条发现路径：日记、梦境与主动
            # 消息完成后推给当前对外表达记忆的一方，失败不影响已完成的领域动作。
            memory_owner=memory_owner_provider(native_context),
            memory_push=memory_push_provider(native_context),
            weather_port=weather_port,
            weather_alert_port=weather_alert_port,
            balance_port=balance_port,
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
        self._intake = defaultdict(asyncio.Lock, {target.target_id: asyncio.Lock() for target in settings.all_targets})

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

    def _prepared_wildcard_private_targets(self):
        """Return real private windows already materialized from a wildcard.

        A wildcard is an admission rule, never a person.  During startup we
        may nevertheless have concrete, authenticated scopes from the probe.
        Reusing those stored scopes lets background routines bind immediately
        without inventing a participant or waiting for the next message.
        """
        prefix = "host.multi.context:"
        wildcard_accounts = {
            (target.platform_id, target.account_id, target.bot_id)
            for target in self.settings.targets if target.participant_id == "*"
        }
        if not wildcard_accounts or self.runtime is None:
            return ()
        found = {}
        for row in self.runtime.read_all(
                "SELECT key, value FROM runtime_metadata WHERE substr(key, 1, ?) = ?",
                (len(prefix), prefix)):
            try:
                scope = ScopeRef.restore(json.loads(row["value"]))
            except (TypeError, ValueError, KeyError):
                continue
            account = (scope.platform, scope.account_id, scope.bot_id)
            if (scope.kind is not ScopeKind.PRIVATE or scope.native_scope_id == "*"
                    or account not in wildcard_accounts):
                continue
            target = self.settings.private_target(scope.platform, scope.account_id, scope.native_scope_id)
            if target is None or target.participant_id == "*":
                continue
            template = self.settings.template_for(target)
            if template is None or template.participant_id != "*":
                continue
            resolution = self.authority.personas.resolve(scope, observed_at=self.now())
            if resolution.failure is not None:
                continue
            role_id = resolution.unwrap().binding.role.subject_id
            if not any(persona.bot_id == target.bot_id and persona.role_id == role_id
                       for persona in self.settings.personas):
                continue
            found[target.target_id] = target
        return tuple(found.values())

    async def start(self, *, expected_task_generation, expected_model_generation):
        targets = [target for target in self.settings.targets if target.participant_id != "*"]
        targets.extend(self._prepared_wildcard_private_targets())
        seen = set()
        for target in targets:
            if target.target_id in seen:
                continue
            seen.add(target.target_id)
            try:
                context, instruction = await self.synchronize(target)
            except TaskError as error:
                if error.code == "host_persona_unmapped":
                    continue
                raise
            self.application.life_runtime.bind(context, instruction, guard=self.bridge.verify_role)
            self.application.state_maintenance.bind(context, instruction, guard=self.bridge.verify_role)
            self.application.contact_schedule.bind_context(context)
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

    async def receive(self, event, target, *, group_admission=None):
        async with self._intake[target.target_id]:
            captured = None
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
                            if group_admission is not None:
                                if (group_admission["context_key"] != original.key
                                        or group_admission["event_id"] != captured.event_id):
                                    raise TaskError("group_admission_changed", "group reply candidate changed during capture")
                                self.application.tools.group_participation.admission.record(
                                    original, batch_id, reason=group_admission["reason"],
                                    mentioned=group_admission["mentioned"])
                    result = require(self.host.receive(captured, on_admitted=admitted))
                self._record_platform_names(event, context)
                if context.scope.kind is ScopeKind.PRIVATE:
                    self.application.life_runtime.bind(context, captured.instruction, guard=self.bridge.verify_role)
                    self.application.state_maintenance.bind(context, captured.instruction, guard=self.bridge.verify_role)
                    self.application.contact_schedule.bind_context(context)
                return Outcome.success(result)
            except TaskError as error:
                if isinstance(target, GroupTarget):
                    scope = getattr(captured, "route", None)
                    scope = getattr(scope, "scope", None)
                    logger.warning(
                        "[CompanionV2] 群入站拒绝 code=%s target=%s platform=%s account=%s group=%s session=%s conversation=%s role=%s",
                        error.code, target.target_id, target.platform_id, target.account_id,
                        target.group_id, getattr(getattr(event, "session", None), "session_id", ""),
                        getattr(scope, "conversation_id", ""),
                        getattr(getattr(captured, "role", None), "subject_id", ""),
                    )
                return Outcome.failed(error.code, str(error))
            except Exception as error:
                if isinstance(target, GroupTarget):
                    logger.error("[CompanionV2] 群入站异常 target=%s error_type=%s",
                                 target.target_id, type(error).__name__)
                    return Outcome.failed("host_group_receive_failed", "group input could not be admitted")
                raise

    async def prepare_group(self, event, target, *, reply_candidate=False):
        """Authenticate a group route before the normal inbound pipeline.

        AstrBot resolves the selected persona again while the V2 inbound
        adapter publishes the source.  Group routes used to create their
        persona binding only inside ``receive``; if that second resolution
        happened before the savepoint was visible, the whole message was
        rejected as ``role_binding_missing``.  V1's early observer avoided
        this coupling.  Materialize the same authenticated group binding here
        and commit it before the reply path starts.  No source, model call or
        platform send happens in this preflight.
        """
        if not isinstance(target, GroupTarget):
            return Outcome.failed("host_scene_unsupported", "group preflight requires a configured group target")
        async with self._intake[target.target_id]:
            try:
                self.application.require_running()
                captured = require(await self.bridge.capture_text_only(event))
                if (captured.route.scope.kind is not ScopeKind.GROUP
                        or self.bridge.target_for_scope(captured.route.scope) != target):
                    raise TaskError("host_target_mismatch", "input changed its configured native group route")
                # Keep this transaction independent from the later source and
                # batch transaction.  The role binding must already be visible
                # when AstrBotInboundAdapter resolves the persona a second time.
                with self.runtime.transaction():
                    context = self.authority.groups.select(target, captured)
                # V1 records the bounded group observation before its reply
                # handlers run.  Do the same after the authenticated binding is
                # committed, so a later media/model failure cannot erase this
                # message from the next group turn's reference material.
                participation = getattr(getattr(self.application, "tools", None),
                                        "group_participation", None)
                observe_early = getattr(participation, "observe_early", None)
                if callable(observe_early):
                    observe_early(context, text=captured.text,
                                  speaker_id=captured.principal.native_account_id,
                                  received_at=captured.at)
                self._record_platform_names(event, context)
                if reply_candidate:
                    settings = self.application.reply_settings.capture(context, self.now())["settings"]
                    values = group_participation_settings(self.runtime, context)
                    projection = next((persona for persona in self.bridge.groups.personas.values()
                                       if persona.bot_id == context.scope.bot_id and persona.role == captured.role), None)
                    facts = group_trigger_facts(event, context.scope.account_id)
                    reason = participation.admission.candidate(context, text=captured.text,
                        instruction=captured.instruction, at=captured.at, settings=settings, participation=values,
                        persona_name=projection.persona_id if projection is not None else "", **facts)
                    return Outcome.success({"admitted": bool(reason), "reason": reason,
                        "mentioned": facts["mentioned"], "context_key": context.key, "event_id": captured.event_id})
                return Outcome.success(context)
            except TaskError as error:
                return Outcome.failed(error.code, str(error))
            except Exception as error:
                logger.error("[CompanionV2] 群消息早期预处理异常 target=%s error_type=%s",
                             target.target_id, type(error).__name__)
                return Outcome.failed("host_group_preflight_failed", "group route preflight failed")

    async def plan_calendar(self, event, target, *, mode, refresh=False):
        from companion_v2.foundation.refs import ScopeKind

        async with self._intake[target.target_id]:
            self.application.require_running()
            captured = require(await self.bridge.capture(event))
            if (captured.route.scope.kind is not ScopeKind.PRIVATE
                    or self.bridge.target_for_scope(captured.route.scope) != target):
                raise TaskError("host_target_mismatch", "calendar generation requires its configured private target")
            context = self.authority.select(target, captured.route.scope, captured.role)
            if self.application.private_access_gate.denied(context, at=self.now()):
                raise TaskError("private_access_dialogue_denied", "this private user has no dialogue permission")
            binding = self.application.state_maintenance.bindings.get(context.key)
            if binding is None:
                raise TaskError("planning_role_changed", "original role binding is unavailable")
            return await self.application.calendar_planning.run(context, binding[1], mode=mode,
                slot="manual:" + mode + ":" + captured.event_id, manual=True, refresh=refresh)

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
            if group:
                # Keep platform names in the same group relationship projection
                # as the acquaintance card; both remain display clues, never
                # identity proof.
                self.application.messages.group_network.record_names(
                    context, nickname=sender.get("nickname"), card=sender.get("card"), at=self.now())
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
