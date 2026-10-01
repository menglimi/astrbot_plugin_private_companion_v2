"""Shared-installation lifecycle and explicit native multi-target admission."""

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from uuid import uuid4

from companion_v2.adapters.astrbot.native import HostPersona, NativePrivateBridge, account_number, persona_instruction
from companion_v2.adapters.astrbot.group import group_event_route
from companion_v2.adapters.astrbot.provider import provider_fingerprint
from companion_v2.adapters.astrbot.provider_catalog import assemble_providers
from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.conversation.pokes import PokePolicy
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, SubjectKind, SubjectRef
from .integration_registry import IntegrationRegistry
from companion_v2.storage.runtime import StorageRuntime
from .multi_authority import HOST_ID, MANIFEST, MultiAuthority
from .multi_session import MultiHostSession, persona_conversation
from .multi_settings import MultiHostSettings
from .group_settings import GroupTarget
from .native import installed_native_types
from .backup_api import apply_staged_restore
from .native_extensions import NativeExtensionRegistry, together_execution_binding
from .settings import DELIVERY_AUTHORIZATION_TTL, HostControlError
from .binding import describe_pin, event_identity, is_private_message, message_text, parse_bind_command
from .binding_store import PendingBinding, binding_path, clear_binding, read_binding, write_binding
from .news import configured_news_port
from .qzone_transport import build_qzone_transport
from .solar_terms import configured_solar_term_port


logger = logging.getLogger(__name__)


class AstrBotMultiController:
    def __init__(self, context, config, data_root, *, native_types=None, now=None):
        self.config = config
        self.context, self.data_root = context, Path(data_root).resolve()
        self.integration = IntegrationRegistry(context)
        self.native_types = native_types or installed_native_types()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.runtime = self.authority = self.session = self.last_session = None
        # 上一次开库时应用过的暂存还原（可能为空）。与单目标控制器同名同义，
        # 让「还原到底生效了没有」在两个模式下读法一致。
        self.last_restore = None
        self.native_extensions = None
        self._accepting = self._terminated = False
        self._control_lock = asyncio.Lock()
        self.last_failure = None
        self.poke_policy = PokePolicy()
        try:
            self.settings = MultiHostSettings.parse(config)
            self.poke_policy = PokePolicy.parse(config.get("poke"))
            self.settings_error = None
        except (HostControlError, ValueError) as error:
            self.settings = None
            self.settings_error = (error if isinstance(error, HostControlError) else
                                   HostControlError("host_poke_settings_invalid", str(error)))
        from .multi_api import MultiHostWebAPI
        self.web_api = MultiHostWebAPI(self)

    def refresh_settings(self):
        try:
            self.settings = MultiHostSettings.parse(self.config)
            self.poke_policy = PokePolicy.parse(self.config.get("poke"))
            self.settings_error = None
        except (HostControlError, ValueError) as error:
            self.settings = None
            self.settings_error = (error if isinstance(error, HostControlError) else
                                   HostControlError("host_poke_settings_invalid", str(error)))

    def _settings(self):
        if self._terminated:
            raise TaskError("host_terminated", "the shared host is stopping or terminated")
        if self.settings_error is not None:
            raise self.settings_error
        self.settings.require_ready()
        return self.settings

    @property
    def profile_root(self):
        return self.data_root / "installations" / self.settings.installation_key if self.settings else None

    @property
    def _multi_host(self):
        """This controller owns a shared installation with one core admin window."""
        return True

    @property
    def binding_root(self):
        return self.data_root / "setup"

    def _parked_binding(self):
        return read_binding(self.binding_root)

    def binding_state(self):
        parked = self._parked_binding()
        if parked is None:
            return {"bound": False, "pinned": False, "pending": False, "confirmed": False}
        try:
            identity = parked.identity()
        except HostControlError as error:
            return {"bound": False, "pinned": False, "pending": False, "error": error.code}
        configured_target = self._core_target(parked) is not None
        return {"bound": parked.confirmed, "pinned": False, "pending": not parked.confirmed,
                "confirmed": parked.confirmed, "configured_target": configured_target,
                **{name: identity[name] for name in
                   ("platform_id", "account_id", "participant_id", "bot_id", "role_id", "persona_id")}}

    def _core_target(self, binding):
        settings = self.settings
        if settings is None:
            return None
        match = next((target for target in settings.targets
                      if (target.platform_id, target.account_id, target.participant_id)
                      == (binding.platform_id, binding.account_id, binding.participant_id)), None)
        if match is None:
            return None
        if binding.persona_id and not any(persona.bot_id == match.bot_id
                                           and persona.persona_id == binding.persona_id
                                           for persona in settings.personas):
            return None
        return match

    def _register_core_binding(self, binding):
        """Seed the first shared target from the Dashboard-confirmed private window."""
        from copy import deepcopy
        from .identity_derivation import derive_role_id

        if binding.persona_id:
            native = self.context.persona_manager.get_persona_v3_by_id(binding.persona_id)
            if native is None or native.get("name") != binding.persona_id:
                raise TaskError("host_persona_unavailable", "choose a persona that is currently loaded in AstrBot")
        if self._core_target(binding):
            return
        save = getattr(self, "save_plugin_config", None)
        if not callable(save):
            raise TaskError("setup_config_save_unavailable", "restart the plugin with Dashboard configuration support")
        if not isinstance(self.config, dict):
            raise TaskError("setup_config_unavailable", "the plugin configuration cannot be edited here")

        candidate = deepcopy(self.config)
        section = candidate.setdefault("multi_host", {})
        if type(section) is not dict:
            raise TaskError("setup_config_invalid", "the shared host settings have an invalid shape")
        targets = section.setdefault("targets", [])
        personas = section.setdefault("personas", [])
        group_targets = section.setdefault("group_targets", [])
        if any(type(items) is not list for items in (targets, personas, group_targets)):
            raise TaskError("setup_config_invalid", "the account and persona mappings have an invalid shape")

        account_rows = [item for item in [*targets, *group_targets]
                        if type(item) is dict
                        and item.get("platform_id") == binding.platform_id
                        and item.get("account_id") == binding.account_id]
        bot_ids = {item.get("bot_id") for item in account_rows if type(item.get("bot_id")) is str}
        if len(bot_ids) > 1:
            raise TaskError("host_mappings_conflict", "this Bot account is already assigned to conflicting V2 identities")
        identity = binding.identity()
        bot_id = next(iter(bot_ids), identity["bot_id"])
        target = next((item for item in targets if type(item) is dict
                       and (item.get("platform_id"), item.get("account_id"), item.get("participant_id"))
                       == (binding.platform_id, binding.account_id, binding.participant_id)), None)
        if target is None:
            used_ids = {item.get("target_id") for item in targets if type(item) is dict}
            base_id = "setup-core-" + binding.account_id
            target_id = base_id
            suffix = 2
            while target_id in used_ids:
                target_id = f"{base_id}-{suffix}"
                suffix += 1
            targets.append({"target_id": target_id, "platform_id": binding.platform_id,
                            "account_id": binding.account_id, "bot_id": bot_id,
                            "participant_id": binding.participant_id})
        elif target.get("bot_id") != bot_id:
            raise TaskError("host_mappings_conflict", "the core administrator window has a conflicting Bot identity")

        persona_id = binding.persona_id or "[%None]"
        persona = next((item for item in personas if type(item) is dict
                        and (item.get("bot_id"), item.get("persona_id")) == (bot_id, persona_id)), None)
        if persona is None:
            personas.append({"bot_id": bot_id, "persona_id": persona_id,
                             "role_id": derive_role_id(binding.account_id, binding.persona_id)})

        from .multi_settings import MultiHostSettings
        MultiHostSettings.parse(candidate)
        save(candidate)
        self.refresh_settings()
        if self.settings_error is not None:
            raise TaskError(self.settings_error.code, str(self.settings_error))

    def handles_binding(self, event):
        from .recalls import is_notice_event
        return (not is_notice_event(event) and is_private_message(event)
                and parse_bind_command(message_text(event)).kind != "ignore")

    async def receive_binding(self, event):
        request = parse_bind_command(message_text(event))
        if request.kind == "ignore":
            return {"handled": False}
        identity = event_identity(event)
        if identity is None:
            return {"handled": True, "ok": False, "reason": "host_identity_unreadable",
                    "reply": "这条消息读不到平台、Bot 账号或发送者，无法作为绑定。"}
        existing = self._parked_binding()
        if request.kind == "unbind":
            if existing is not None and existing.confirmed:
                return {"handled": True, "ok": False, "reason": "host_binding_exists",
                        "reply": "核心管理员窗口已确认；请先在「开始使用」重置首次设置，再更换窗口。"}
            removed = clear_binding(self.binding_root)
            return {"handled": True, "ok": True, "removed": removed,
                    "reply": "已清除待绑定窗口。" if removed else "当前没有待绑定窗口。",
                    "binding": self.binding_state()}
        if request.reason == "host_identity_invalid":
            return {"handled": True, "ok": False, "reason": request.reason,
                    "reply": "人格名不能包含换行或过长，请用一行短名字重发。"}
        candidate = PendingBinding(identity["platform_id"], identity["account_id"],
                                   identity["participant_id"], request.persona_id)
        if request.kind == "confirm":
            if existing is None:
                return {"handled": True, "ok": False, "reason": "host_binding_missing",
                        "reply": "还没有待确认的核心管理员窗口，先发送 companion_bind。"}
            expected = (existing.platform_id, existing.account_id, existing.participant_id)
            actual = (identity["platform_id"], identity["account_id"], identity["participant_id"])
            return {"handled": True, "ok": expected == actual,
                    "reason": None if expected == actual else "host_binding_confirmation_mismatch",
                    "reply": "已核对这条私聊的来源。请回到「开始使用」，由 Dashboard 管理员完成确认。"
                    if expected == actual else "确认消息与待绑定的平台、Bot 账号或私聊对象不一致。"}
        if existing is not None:
            same = (existing.platform_id, existing.account_id, existing.participant_id,
                    existing.persona_id) == (candidate.platform_id, candidate.account_id,
                                               candidate.participant_id, candidate.persona_id)
            if same:
                return {"handled": True, "ok": True, "confirmed": existing.confirmed,
                        "reply": "这条核心管理员窗口已经待确认。请回到「开始使用」查看并确认。",
                        "binding": self.binding_state()}
            return {"handled": True, "ok": False, "reason": "host_binding_candidate_exists",
                    "reply": "已有待确认的核心管理员窗口。请先发送 companion_unbind，再重新绑定。"}
        try:
            write_binding(self.binding_root, candidate)
            identity = candidate.identity()
        except (HostControlError, OSError, ValueError) as error:
            code = getattr(error, "code", "host_binding_write_failed")
            return {"handled": True, "ok": False, "reason": code,
                    "reply": "这条绑定无法成立，请回到「开始使用」查看原因。"}
        return {"handled": True, "ok": True, "confirmed": False,
                "reply": describe_pin(identity), "binding": self.binding_state()}

    def confirm_binding(self):
        parked = self._parked_binding()
        if parked is None:
            return {"confirmed": False, "reason": "setup_binding_missing",
                    "detail": "send companion_bind from the core administrator private window first"}
        try:
            self._register_core_binding(parked)
        except (TaskError, HostControlError, ValueError, TypeError) as error:
            return {"confirmed": False, "reason": getattr(error, "code", "setup_core_window_not_configured"),
                    "detail": str(error)}
        if not self._core_target(parked):
            return {"confirmed": False, "reason": "setup_core_window_not_configured",
                    "detail": "the confirmed private window could not be added to the shared host"}
        if not parked.confirmed:
            write_binding(self.binding_root, PendingBinding(parked.platform_id, parked.account_id,
                parked.participant_id, parked.persona_id, confirmed=True))
        return {"confirmed": True, "binding": self.binding_state()}

    def _failure(self, error):
        code = error.code if isinstance(error, (TaskError, HostControlError)) else "host_control_failed"
        self.last_failure = {"code": code}
        return Outcome.failed(code, "shared host configuration, native route or authority could not be verified")

    async def _probe(self):
        settings = self._settings()
        personas = []
        for mapping in settings.personas:
            native = (None if mapping.persona_id == "[%None]" else
                      self.context.persona_manager.get_persona_v3_by_id(mapping.persona_id))
            if mapping.persona_id != "[%None]" and (native is None or native.get("name") != mapping.persona_id):
                raise TaskError("host_persona_unavailable", "a configured native persona could not be resolved")
            personas.append(HostPersona(mapping.bot_id, mapping.persona_id,
                SubjectRef(settings.installation_id, SubjectKind.BOT, mapping.role_id), digest(persona_instruction(native))))
        bridge = NativePrivateBridge(self.context, version=self.native_types.version, event_type=self.native_types.event,
            installation_id=settings.installation_id, host_id=HOST_ID, identities=None,
            accounts=settings.accounts, personas=tuple(personas), now=self.now)
        conversations = {}
        for target in settings.all_targets:
            account = bridge.accounts[(target.platform_id, target.account_id)]
            client = bridge.platforms[target.platform_id][1]
            if not getattr(client, "_wsr_api_clients", {}).get(target.account_id):
                raise TaskError("host_account_unavailable", "a configured account is not connected")
            if target in settings.targets:
                conversation, _, _ = await bridge._role(account, target.participant_id)
                conversations[target.target_id] = conversation
            # Groups resolve the actual event's UMO, including member sessions,
            # at admission. No human speaker is fabricated during startup.
        provider = self.context.get_provider_by_id(settings.common.provider_id)
        if type(provider) is not self.native_types.provider:
            raise TaskError("host_provider_unavailable", "the configured model has no verified native adapter")
        assemble_providers(self.context, bridge=None, native_types=self.native_types,
                           primary_id=settings.common.provider_id, additional=settings.common.additional_providers)
        manifest = {"binding_contract": settings.binding_contract,
                    "settings_fingerprint": settings.fingerprint, "provider_fingerprint": provider_fingerprint(provider),
                    "personas": [asdict(persona) for persona in personas]}
        manifest["fingerprint"] = digest(manifest)
        self._settings()  # termination may have started while native reads awaited
        return manifest, conversations

    def _open(self):
        settings = self._settings()
        if self.runtime is None:
            root = self.profile_root
            if root is None:
                raise HostControlError("staging_settings_invalid", "a profile directory could not be resolved")
            # 暂存还原在这里生效，和单目标控制器同一处、同一个函数、同一个理由：
            # 这是数据库文件唯一能在不留下孤儿连接的情况下被替换的时刻（开库之前）。
            # 少了这一步，多目标下「还原暂存成功、重启永远不生效」——比入口点不动更糟。
            self.last_restore = apply_staged_restore(root / "runtime", installation_id=settings.installation_id)
            self.runtime = StorageRuntime.open(data_root=root / "runtime", installation_id=settings.installation_id)
            self.authority = MultiAuthority(self.runtime, settings, now=self.now)

    def _assemble(self, manifest):
        personas = tuple(HostPersona(item["bot_id"], item["persona_id"],
            SubjectRef(item["role"]["installation_id"], SubjectKind.BOT, item["role"]["subject_id"]), item["instruction_hash"])
            for item in manifest["personas"])
        if self.native_extensions is not None:
            self.native_extensions.close()
        self.native_extensions = NativeExtensionRegistry(self.context, now=self.now,
            together_execution=together_execution_binding(self.settings.common),
            image_settings_path=self.data_root / "model_image_routes.json")
        self.session = MultiHostSession(self.runtime, self.context, settings=self.settings, personas=personas,
            authority=self.authority, native_types=self.native_types, provider_fingerprint=manifest["provider_fingerprint"],
            runtime_instance_id="astrbot-multi-" + uuid4().hex, native_tool_port=self.native_extensions, now=self.now,
            news_port=configured_news_port(self.config),
            qzone_transport=build_qzone_transport(self.context, data_root=self.data_root),
            solar_term_port=configured_solar_term_port(
                self.config.get("solar_terms") if isinstance(self.config, dict) else None))
        from .semantic_models import NativeSemanticModels, configured_slang_search_port
        self.session.application.attach_semantics(NativeSemanticModels(self.context, self.settings.common.provider_id,
                                                                      configured_slang_search_port()))

    def _idle(self):
        if self.session is not None and self.session.application.state not in ("new", "stopped"):
            raise TaskError("host_must_stop", "stop the shared host and its outstanding work before changing configuration")

    async def probe(self):
        async with self._control_lock:
            try:
                manifest, _ = await self._probe()
                return Outcome.success({"installation_id": self.settings.installation_id,
                    "configuration_fingerprint": manifest["fingerprint"], "targets": len(self.settings.all_targets),
                    "group_targets": len(self.settings.group_targets),
                    "personas": len(self.settings.personas), "model_request_sent": False, "platform_message_sent": False})
            except Exception as error:
                return self._failure(error)

    async def initialize_profile(self):
        async with self._control_lock:
            try:
                self._idle()
                manifest, conversations = await self._probe()
                self._open()
                with self.runtime.transaction():
                    receipt = self.authority.initialize(manifest)
                    for target in self.settings.targets:
                        for item in manifest["personas"]:
                            if item["bot_id"] != target.bot_id:
                                continue
                            role = SubjectRef(self.settings.installation_id, SubjectKind.BOT, item["role"]["subject_id"])
                            from companion_v2.foundation.refs import ScopeKind, ScopeRef
                            scope = ScopeRef(self.settings.installation_id, target.platform_id, ScopeKind.PRIVATE,
                                target.participant_id, target.bot_id, target.account_id,
                                persona_conversation(conversations[target.target_id], role), target.participant_id)
                            self.authority.provision_scope(target, scope, role)
                self._assemble(manifest)
                self.last_failure = None
                return Outcome.success(receipt)
            except Exception as error:
                return self._failure(error)

    async def load_existing(self):
        async with self._control_lock:
            try:
                self._settings()
                if not (self.profile_root / "runtime" / StorageRuntime.DATABASE_FILENAME).is_file():
                    return Outcome.success({"loaded": False, "started": False})
                self._idle()
                self._open()
                manifest = self.authority.require_manifest()
                probed, _ = await self._probe()
                self.authority.require_manifest(probed)
                self._assemble(probed)
                return Outcome.success({"loaded": True, "started": False})
            except Exception as error:
                return self._failure(error)

    async def start(self):
        async with self._control_lock:
            try:
                self._settings()
                if self.session is not None and self.session.application.state == "running":
                    return Outcome.success({"state": "running", "replayed": True})
                self._idle()
                if not (self.profile_root / "runtime" / StorageRuntime.DATABASE_FILENAME).is_file():
                    raise TaskError("host_not_initialized", "initialize the shared installation first")
                self._open()
                manifest, _ = await self._probe()
                self.authority.require_manifest(manifest)
                if self.session is None or self.session.application.state != "new":
                    self._assemble(manifest)
                task = self.runtime.read_one("SELECT generation FROM task_supervisor WHERE singleton = 1", ())
                model = self.runtime.read_one("SELECT generation FROM configuration_consumers WHERE consumer_id = ?", ("model_gateway",))
                result = await self.session.start(expected_task_generation=task["generation"] if task else 0,
                                                  expected_model_generation=model["generation"] if model else 0)
                require(result)
                self._settings()
                self._accepting, self.last_failure = True, None
                return Outcome.success({"state": "running", "targets": len(self.settings.all_targets), "startup": result.unwrap()})
            except Exception as error:
                self._accepting = False
                return self._failure(error)

    def target_for_event(self, event):
        if type(event) is not self.native_types.event or self.settings is None:
            return None
        try:
            message, session, meta = event.message_obj, event.session, event.platform_meta
            if getattr(message.type, "value", None) == "GroupMessage":
                route = group_event_route(event)
                target = next((t for t in self.settings.group_targets if t.route_key == route.route_key), None)
                platform = self.context.get_platform_inst(meta.id)
                if (target is None or platform is None or platform.get_client() is not event.bot
                        or not event.bot._wsr_api_clients.get(route.account_id)):
                    return None
                return target
            sender, login = account_number(message.sender.user_id), account_number(message.self_id)
            if (message.group_id or getattr(message.type, "value", None) != "FriendMessage"
                    or getattr(session.message_type, "value", None) != "FriendMessage"
                    or meta.name != "aiocqhttp" or session.platform_id != meta.id or session.platform_name != meta.id
                    or session.session_id != sender or event.unified_msg_origin != f"{meta.id}:FriendMessage:{sender}"):
                return None
            target = next((target for target in self.settings.targets if target.route_key == (meta.id, login, sender)), None)
            if target is None or self.context.get_platform_inst(meta.id).get_client() is not event.bot:
                return None
            return target
        except (ValueError, AttributeError, TypeError):
            return None

    def claims(self, event):
        from .recalls import is_notice_event
        if is_notice_event(event):
            return False
        return bool(self._accepting and not self._terminated and self.session is not None
                    and self.session.application.state == "running" and self.target_for_event(event) is not None)

    async def receive_notice(self, event):
        from .pokes import is_poke_notice, receive_poke
        if is_poke_notice(event):
            return await receive_poke(self, event)
        from .recalls import receive_notice
        return await receive_notice(self, event)

    async def receive_claimed(self, event):
        session, target = self.session, self.target_for_event(event)
        if not self.claims(event) or session is None or target is None:
            return Outcome.failed("host_not_claimed", "the native event is outside the active configured targets")
        try:
            result = await session.receive(event, target)
            if result.failure is not None and result.failure.code == "private_access_dialogue_denied":
                # 没有对话权限：按配置回一句（真实投递模式才发）。发送失败不影响"拒绝"本身。
                await self._refuse_private(session, event)
            return result
        except Exception as error:
            return self._failure(error)

    async def _refuse_private(self, session, event):
        """一句话的礼拒；任何失败都只当"没回话"，不改写拒绝结论。"""
        from .private_notice import notify_refusal

        try:
            return await notify_refusal(self, session, event,
                                        context=getattr(session, "last_refusal", None))
        except (TaskError, ValueError, TypeError, AttributeError, KeyError):
            return None
        finally:
            session.last_refusal = None

    async def authorize_delivery(self, target_id):
        async with self._control_lock:
            try:
                self._settings()
                if self.authority is None:
                    raise TaskError("host_not_initialized", "initialize the shared installation first")
                self.authority.require_manifest()
                return Outcome.success(self.authority.authorize_delivery(target_id, self.now() + DELIVERY_AUTHORIZATION_TTL))
            except Exception as error:
                return self._failure(error)

    async def _group_delivery_control(self, target_id, *, authorize):
        async with self._control_lock:
            try:
                self._settings()
                if self.authority is None:
                    raise TaskError("host_not_initialized", "initialize the shared installation first")
                self.authority.require_manifest()
                groups = self.authority.group_delivery
                result = (groups.authorize(target_id, self.now() + DELIVERY_AUTHORIZATION_TTL) if authorize
                          else groups.revoke(target_id))
                return Outcome.success(result)
            except Exception as error:
                return self._failure(error)

    async def authorize_group_delivery(self, target_id):
        return await self._group_delivery_control(target_id, authorize=True)

    async def revoke_group_delivery(self, target_id):
        return await self._group_delivery_control(target_id, authorize=False)

    def preview(self, target_id, batch_id):
        try:
            self._settings()
            target = self.settings.target(target_id)
            session = self.session or self.last_session
            if session is None or self.runtime is None:
                raise TaskError("host_not_initialized", "initialize or load the shared installation first")
            if type(batch_id) is not str or not 1 <= len(batch_id) <= 128:
                raise TaskError("host_request_invalid", "select an original input batch")
            messages = session.application.messages
            with session.application.tasks.read_only_context():
                batch = messages.batch(batch_id)
                context = TaskContext.restore(json.loads(batch["context_json"]))
                if session.bridge.target_for_scope(context.scope) != target:
                    raise TaskError("host_target_mismatch", "the batch belongs to another target")
                batch = messages.owned(context, batch_id)
                if batch["state"] in ("cancelled", "invalidated"):
                    raise TaskError("staging_draft_unavailable", "the original draft has been invalidated")
                request = messages._request(batch, context, self.now()) if batch["state"] == "ready" else None
                parts = [dict(row) for row in self.runtime.read_all(
                    "SELECT part_id, sequence, text, state, operation_id, receipt_ref, platform_ref, delivered_at "
                    "FROM conversation_parts WHERE batch_id = ? ORDER BY sequence", (batch_id,))]
                if batch["state"] == "ready":
                    parts = messages.reply_images.project_parts(parts, batch, context, self.now(), request=request)
                return Outcome.success({"target_id": target_id, "batch_id": batch_id, "scope_kind": context.scope.kind.value,
                    "role_id": context.role_binding.role.subject_id, "speaker_id": context.actor.principal.native_account_id,
                    "delivery_mode": (self.authority.group_delivery.mode(batch_id) if context.scope.kind is ScopeKind.GROUP
                                      else self.settings.common.delivery_mode),
                    "configured_delivery_mode": self.settings.delivery_mode_for(target),
                    "preview_ready": bool(parts), "sent": any(p["state"] == "delivered" for p in parts), "parts": parts})
        except Exception as error:
            return self._failure(error)

    def batches(self, target_id):
        try:
            self._settings()
            target = self.settings.target(target_id)
            if self.runtime is None:
                raise TaskError("host_not_initialized", "initialize or load the shared installation first")
            group = isinstance(target, GroupTarget)
            rows = self.runtime.read_all("""SELECT batch_id, state, created_at, part_count, context_json
                FROM conversation_batches WHERE json_extract(context_json, '$.audience.scope.platform') = ?
                AND json_extract(context_json, '$.audience.scope.account_id') = ?
                AND json_extract(context_json, '$.audience.scope.bot_id') = ?
                AND json_extract(context_json, '$.audience.scope.kind') = ?
                AND json_extract(context_json, '$.audience.scope.native_scope_id') = ?
                ORDER BY created_at DESC, rowid DESC LIMIT 21""", (target.platform_id, target.account_id, target.bot_id,
                    "group" if group else "private", target.group_id if group else target.participant_id))
            items = []
            for row in rows[:20]:
                context = TaskContext.restore(json.loads(row["context_json"]))
                items.append({**{name: row[name] for name in ("batch_id", "state", "created_at", "part_count")},
                    "role_id": context.role_binding.role.subject_id, "speaker_id": context.actor.principal.native_account_id})
            return Outcome.success({"target_id": target_id, "items": items, "has_older": len(rows) > 20})
        except Exception as error:
            return self._failure(error)

    async def revoke_delivery(self, target_id):
        async with self._control_lock:
            try:
                self._settings()
                if self.authority is None:
                    raise TaskError("host_not_initialized", "initialize the shared installation first")
                return Outcome.success(self.authority.revoke_delivery(target_id))
            except Exception as error:
                return self._failure(error)

    async def stop(self, *, grace_seconds=0.5):
        self._accepting = False
        async with self._control_lock:
            self._accepting = False
            try:
                if self.session is None:
                    return Outcome.success({"state": "stopped", "pending_handles": []})
                report = await self.session.close(grace_seconds=grace_seconds)
                if report.state == "stopped":
                    self.last_session, self.session = self.session, None
                return Outcome.success(report)
            except Exception as error:
                return self._failure(error)

    def status(self):
        session = self.session or self.last_session
        return {"mode": "multi", "enabled": self.settings.enabled if self.settings else False,
                "installation_id": self.settings.installation_id if self.settings else None,
                # 保留在状态文档中，方便旧版小屋和诊断页识别当前群目标形态。
                # 正式版的 onebot_group 只是配置描述，不是额外的投递授权闸门。
                "group_delivery_mode": (
                    self.settings.group_delivery_mode if self.settings else None
                ),
                "state": session.application.state if session else "uninitialized", "accepting": self._accepting,
                "targets": self.web_api.target_inventory(), "last_failure": self.last_failure,
                "settings_error": getattr(self.settings_error, "code", None)}

    def register_routes(self):
        self.web_api.register()

    def unregister_routes(self):
        self.web_api.unregister()

    async def terminate(self):
        self._terminated, self._accepting = True, False
        try:
            result = await self.stop(grace_seconds=2)
            if result.is_success:
                report = result.unwrap()
                state = report.get("state") if isinstance(report, dict) else report.state
            else:
                state = None
            if self.runtime is not None:
                if state != "stopped":
                    # 卸载时把 SQLite 句柄留在进程里，会让下一次 staged 还原的
                    # os.replace 在 Windows 上永久失败，所以未达 stopped 也必须关。
                    logger.warning("[CompanionV2] multi 停机未达 stopped，仍关闭存储 runtime 释放文件句柄")
                self.runtime.close()
                self.runtime = None
        finally:
            if self.native_extensions is not None:
                self.native_extensions.close()
                self.native_extensions = None
            self.unregister_routes()
