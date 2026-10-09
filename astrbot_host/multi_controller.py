"""Shared-installation lifecycle and explicit native multi-target admission."""

import asyncio
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import traceback
from uuid import uuid4

from companion_v2.adapters.astrbot.native import (
    HostPersona, NativePrivateBridge, account_number, persona_instruction,
)
from companion_v2.adapters.astrbot.group import group_event_route
from companion_v2.adapters.astrbot.provider import provider_fingerprint
from companion_v2.adapters.astrbot.provider_catalog import TextProviderSettings, assemble_providers
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
from .storage_location import selected_backup_directory
from .native_extensions import NativeExtensionRegistry, together_execution_binding
from .native_extensions.builtins import MANAGED_EXTENSIONS, create_bundled_extensions
from .settings import DELIVERY_AUTHORIZATION_TTL, INSTALLATION_PREFIX, PROFILE_PATTERN, HostControlError
from .binding import describe_pin, event_identity, is_private_message, message_text, parse_bind_command
from .calendar_command import receive_calendar_command
from .binding_store import PendingBinding, binding_path, clear_binding, read_binding, write_binding
from .news import configured_news_port
from .service_balance import configured_balance_port
from .weather_settings import configured_weather_ports
from .qzone_transport import build_qzone_transport
from .solar_terms import configured_solar_term_port
from .session_topology import SessionTopology
from .shared_host_migration import recover_repeated_single_target


logger = logging.getLogger(__name__)


def laya_target_id_for_scope(settings, scope):
    if getattr(scope, "kind", None) is not ScopeKind.PRIVATE:
        return "installation"
    target = settings.private_target(scope.platform, scope.account_id, scope.native_scope_id)
    configured_target = settings.template_for(target) if target is not None else None
    return configured_target.target_id if configured_target is not None else "installation"


class AstrBotMultiController:
    def __init__(self, context, config, data_root, *, native_types=None, now=None):
        self.config = config
        self.context, self.data_root = context, Path(data_root).resolve()
        self.integration = IntegrationRegistry(context)
        self.native_types = native_types or installed_native_types()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.runtime = self.authority = self.session = self.last_session = None
        # The dashboard can report whether a staged restore was applied at open.
        self.last_restore = None
        self.native_extensions = None
        self._accepting = self._terminated = False
        # Lifecycle work may wait on AstrBot; keep that wait out of the lock
        # shared by Dashboard data APIs.
        self._control_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self.session_topology = SessionTopology(self)
        self._storage_profile_root = None
        self._adopting_legacy_profile = False
        self.last_failure = None
        self._termination_task = None
        self.poke_policy = PokePolicy()
        try:
            self.settings, self._storage_profile_root, self._adopting_legacy_profile = self._resolve_settings(config)
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
            self.settings, self._storage_profile_root, self._adopting_legacy_profile = self._resolve_settings(self.config)
            self.poke_policy = PokePolicy.parse(self.config.get("poke"))
            self.settings_error = None
        except (HostControlError, ValueError) as error:
            self.settings = None
            self._storage_profile_root = None
            self._adopting_legacy_profile = False
            self.settings_error = (error if isinstance(error, HostControlError) else
                                   HostControlError("host_poke_settings_invalid", str(error)))

    def _resolve_settings(self, config):
        settings = MultiHostSettings.parse(config)
        shared_root = self.data_root / "installations" / settings.installation_key
        legacy = config.get("staging", {}) if isinstance(config, dict) else {}
        legacy_id = legacy.get("profile_id") if isinstance(legacy, dict) else None
        if type(legacy_id) is str and PROFILE_PATTERN.fullmatch(legacy_id):
            legacy_root = self.data_root / "profiles" / legacy_id
            legacy_database = legacy_root / "runtime" / StorageRuntime.DATABASE_FILENAME
            shared_database = shared_root / "runtime" / StorageRuntime.DATABASE_FILENAME
            if legacy_database.is_file() and not shared_database.is_file():
                return (replace(settings, _storage_installation_id=INSTALLATION_PREFIX + legacy_id),
                        legacy_root, True)
        return settings, shared_root, False

    def _settings(self):
        if self._terminated:
            raise TaskError("host_terminated", "the shared host is stopping or terminated")
        if self.settings_error is not None:
            raise self.settings_error
        self.settings.require_ready()
        return self.settings

    def startup_readiness(self):
        """Return a retryable readiness code until every configured Bot is online."""
        for account in self._settings().accounts:
            platform = self.context.get_platform_inst(account.platform_id)
            if platform is None:
                return "host_platform_unavailable"
            meta = platform.meta()
            if meta.name != "aiocqhttp" or meta.id != account.platform_id:
                return "host_platform_changed"
            client = platform.get_client()
            if not getattr(client, "_wsr_api_clients", {}).get(account.self_id):
                return "host_account_unavailable"
        return None

    @property
    def profile_root(self):
        return self._storage_profile_root if self.settings else None

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

        candidate = deepcopy(dict(self.config))
        section = candidate.setdefault("multi_host", {})
        if type(section) is not dict:
            raise TaskError("setup_config_invalid", "the shared host settings have an invalid shape")
        section["enabled"] = True
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

    def _failure(self, error, *, operation=""):
        code = (error.code if isinstance(error, (TaskError, HostControlError)) else
                "host_module_unavailable" if isinstance(error, ImportError) else "host_control_failed")
        if code in ("host_control_failed", "host_module_unavailable"):
            # Keep the failing source locations, without logging exception values
            # or locals that may contain native credentials or conversation text.
            logger.error("[CompanionV2] 宿主操作异常 operation=%s code=%s error_type=%s\n%s",
                         operation or "control", code, type(error).__name__,
                         "".join(traceback.format_tb(error.__traceback__)))
        reason = ("插件模块未能导入，请重新加载 V2 插件；若仍失败，请检查安装包是否完整并查看 AstrBot 日志。"
                  if code == "host_module_unavailable" else
                  str(error) if code.split("__", 1)[0] == "host_native_lookup_timeout"
                  or code in ("host_binding_changed", "account_config_save_failed", "account_config_persistence_unavailable") else
                  "shared host configuration, native route or authority could not be verified")
        self.last_failure = {"code": code, "reason": reason}
        if operation:
            self.last_failure["operation"] = operation
        return Outcome.failed(code, reason)

    async def _probe(self, settings=None, *, include_conversations=True):
        settings = settings or self._settings()
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
        for account in settings.accounts:
            platform = self.context.get_platform_inst(account.platform_id)
            client = bridge.platforms[account.platform_id][1]
            if (platform is None or platform.get_client() is not client
                    or not getattr(client, "_wsr_api_clients", {}).get(account.self_id)):
                raise TaskError("host_account_unavailable", "a configured account is not connected")
        for target in (settings.all_targets if include_conversations else ()):
            account = bridge.accounts[(target.platform_id, target.account_id)]
            peer = target.participant_id if hasattr(target, "participant_id") else target.group_id
            if peer == "*":
                continue
            if target in settings.targets:
                umo = bridge._umo(target.platform_id, target.participant_id)
                conversation_id, _, _, _ = await bridge._selected_persona(account, umo)
                conversations[target.target_id] = {
                    "target": target, "conversation_id": bridge._conversation_key(umo, conversation_id),
                    "role_ids": tuple(sorted({item.role_id for item in settings.personas if item.bot_id == target.bot_id})),
                }
            # Groups resolve the actual event's UMO, including member sessions,
            # at admission. No human speaker is fabricated during startup.
        if include_conversations and any(target.participant_id == "*" for target in settings.targets):
            inventory = await self.session_topology.inventory(settings=settings, scope_kind="private")
            for window in inventory:
                if window.get("native") is not True or window.get("scope_kind") != "private":
                    continue
                target = settings.private_target(window.get("platform_id"), window.get("account_id"),
                                                 window.get("participant_id"))
                if target is None or target.participant_id == "*" or window.get("bot_id") != target.bot_id:
                    continue
                mapping = next((item for item in settings.personas if item.bot_id == target.bot_id
                                and item.persona_id == window.get("persona_id")), None)
                if mapping is None:
                    continue
                conversations[target.target_id] = {
                    "target": target,
                    "conversation_id": bridge._conversation_key(window["unified_msg_origin"], window.get("conversation_id")),
                    "role_ids": (mapping.role_id,),
                }
        provider = self.context.get_provider_by_id(settings.common.provider_id)
        if type(provider) is not self.native_types.provider:
            raise TaskError("host_provider_unavailable", "the configured model has no verified native adapter")
        assemble_providers(self.context, bridge=None, native_types=self.native_types,
                           primary_id=settings.common.provider_id, additional=settings.common.additional_providers,
                           defaults=TextProviderSettings(settings.common.provider_id, settings.common.tariff,
                               settings.common.max_output_tokens, settings.common.maximum_input_estimate,
                               settings.common.output_parameter, settings.common.streaming))
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
            # Apply restores before opening SQLite, while replacing the database is safe.
            storage = self.config.get("storage", {}) if isinstance(self.config, dict) else {}
            backup_directory = selected_backup_directory(
                root / "runtime", storage.get("backup_path", "") if isinstance(storage, dict) else "",
                settings.installation_id, plugin_root=self.data_root)
            self.last_restore = apply_staged_restore(root / "runtime", installation_id=settings.installation_id,
                                                     backup_directory=backup_directory)
            self.runtime = StorageRuntime.open(data_root=root / "runtime", installation_id=settings.installation_id)
            self.runtime.backup_directory = backup_directory
            self.authority = MultiAuthority(self.runtime, settings, now=self.now)

    def _assemble(self, manifest):
        personas = tuple(HostPersona(item["bot_id"], item["persona_id"],
            SubjectRef(item["role"]["installation_id"], SubjectKind.BOT, item["role"]["subject_id"]), item["instruction_hash"])
            for item in manifest["personas"])
        if self.native_extensions is not None:
            self.native_extensions.close()
        bundled_extensions, bundled_issues = create_bundled_extensions(self.runtime.data_root, now=self.now)
        self.native_extensions = NativeExtensionRegistry(self.context, now=self.now,
            together_execution=together_execution_binding(self.settings.common),
            image_settings_path=self.data_root / "model_image_routes.json",
            bundled_extensions=bundled_extensions, bundled_issues=bundled_issues,
            managed_extensions=MANAGED_EXTENSIONS)
        self.session = MultiHostSession(self.runtime, self.context, settings=self.settings, personas=personas,
            authority=self.authority, native_types=self.native_types, provider_fingerprint=manifest["provider_fingerprint"],
            runtime_instance_id="astrbot-multi-" + uuid4().hex, native_tool_port=self.native_extensions, now=self.now,
            news_port=configured_news_port(self.config),
            balance_port=configured_balance_port(self.config),
            weather_ports=configured_weather_ports(self.config),
            qzone_transport=build_qzone_transport(self.context, data_root=self.data_root),
            solar_term_port=configured_solar_term_port(
                self.config.get("solar_terms") if isinstance(self.config, dict) else None))
        from .worker_lifecycle import AstrBotWorkerLifecycle
        self.session.application.tasks.bind_worker_lifecycle(AstrBotWorkerLifecycle())
        from .knowledge_sources import attach_official_knowledge
        attach_official_knowledge(self.session.application, self.context)
        from .semantic_models import NativeSemanticModels, configured_slang_search_port
        self.session.application.attach_semantics(NativeSemanticModels(self.context, self.settings.common.provider_id,
                                                                      configured_slang_search_port()))
        from companion_v2.decision import LayaDecisionService, LayaSettingsStore

        def laya_for_context(context):
            scope = context.scope
            role = context.role_binding.role
            # `native_scope_id` identifies the peer, while the Dashboard
            # persists settings under the configured target id.  Resolve the
            # same target mapping used during admission, including templates.
            target_id = laya_target_id_for_scope(self.settings, scope)
            return LayaDecisionService(LayaSettingsStore(
                self.data_root, target_id,
                getattr(role, "subject_id", "default")))

        self.session.application.attach_laya_decision(laya_for_context)

    def _idle(self):
        if self.session is not None and self.session.application.state not in ("new", "stopped"):
            raise TaskError("host_must_stop", "stop the shared host and its outstanding work before changing configuration")

    async def probe(self):
        async with self._lifecycle_lock:
            try:
                manifest, _ = await self._probe()
                return Outcome.success({"installation_id": self.settings.installation_id,
                    "configuration_fingerprint": manifest["fingerprint"], "targets": len(self.settings.all_targets),
                    "group_targets": len(self.settings.group_targets),
                    "personas": len(self.settings.personas), "model_request_sent": False, "platform_message_sent": False})
            except Exception as error:
                return self._failure(error, operation="probe")

    async def initialize_profile(self):
        async with self._lifecycle_lock:
            try:
                self._idle()
                manifest, conversations = await self._probe()
                async with self._control_lock:
                    if self._terminated:
                        raise TaskError("host_terminated", "the shared host is stopping or terminated")
                    self._idle()
                    receipt = self._initialize_manifest_locked(manifest, conversations)
                self.last_failure = None
                return Outcome.success(receipt)
            except Exception as error:
                return self._failure(error, operation="initialize_profile")

    def _initialize_manifest_locked(self, manifest, conversations):
        self._open()
        with self.runtime.transaction():
            receipt = self.authority.initialize(manifest, allow_legacy_staging=self._adopting_legacy_profile)
            for conversation in conversations.values():
                target = conversation["target"]
                for role_id in conversation["role_ids"]:
                    role = SubjectRef(self.settings.installation_id, SubjectKind.BOT, role_id)
                    from companion_v2.foundation.refs import ScopeKind, ScopeRef
                    scope = ScopeRef(self.settings.installation_id, target.platform_id, ScopeKind.PRIVATE,
                        target.participant_id, target.bot_id, target.account_id,
                        persona_conversation(conversation["conversation_id"], role), target.participant_id)
                    self.authority.provision_scope(target, scope, role)
        self._assemble(manifest)
        return receipt

    async def apply_bindings(self, candidate):
        """Apply Dashboard-reviewed routes while retaining existing native owners."""
        result = None
        settings = None
        async with self._lifecycle_lock:
            # A reviewed mapping change is itself a lifecycle operation.  Stop
            # the current runtime inside this operation and bring the new
            # mapping back up before returning to the page, so a save never
            # leaves the Dashboard showing a stale or half-loaded host.
            async with self._control_lock:
                if self._terminated:
                    raise TaskError("host_terminated", "the shared host is stopping or terminated")
                settings, profile_root, adopting_legacy_profile = self._resolve_settings(candidate)
                save = getattr(self, "save_plugin_config", None)
                if not callable(save):
                    raise TaskError("account_config_persistence_unavailable", "the host has no plugin configuration writer")
            manifest, _ = await self._probe(settings, include_conversations=False)
            self._accepting = False
            session = self.session
            if session is not None:
                report = await session.close(grace_seconds=2)
                if report.state != "stopped":
                    raise TaskError("host_must_stop", "the current session is still stopping")
            async with self._control_lock:
                if self._terminated:
                    raise TaskError("host_terminated", "the shared host is stopping or terminated")
                self._idle()
                root = profile_root / "runtime"
                if self.runtime is not None and (self.runtime.data_root != root.resolve()
                        or self.runtime.installation_id != settings.installation_id):
                    raise TaskError("host_storage_changed", "stop and reload before changing the active V2 data installation")
                opened_here = self.runtime is None
                if self.runtime is None and (root / StorageRuntime.DATABASE_FILENAME).is_file():
                    self.runtime = StorageRuntime.open(data_root=root, installation_id=settings.installation_id)
                    storage = self.config.get("storage", {}) if isinstance(self.config, dict) else {}
                    self.runtime.backup_directory = selected_backup_directory(
                        root, storage.get("backup_path", "") if isinstance(storage, dict) else "",
                        settings.installation_id, plugin_root=self.data_root)
                try:
                    if self.runtime is not None:
                        authority = MultiAuthority(self.runtime, settings, now=self.now)
                        with self.runtime.transaction():
                            authority.initialize(manifest, reviewed=True,
                                                 allow_legacy_staging=adopting_legacy_profile)
                            save(candidate)
                        self.runtime.close()
                        self.runtime = self.authority = None
                    else:
                        save(candidate)
                except Exception:
                    if opened_here and self.runtime is not None:
                        self.runtime.close()
                        self.runtime = self.authority = None
                    raise
                if self.native_extensions is not None:
                    self.native_extensions.close()
                    self.native_extensions = None
                self.session = self.last_session = None
                self.refresh_settings()
                self._accepting = False
                self.last_failure = None
                registered = bool(self.web_api._registered_routes)
                if registered:
                    self.unregister_routes()
                    self.register_routes()
                result = {"saved": True, "requires_reload": False, "requires_initialize": False,
                          "started": False}
        # The old runtime is released before this point.  Re-enter the public
        # lifecycle methods only after the apply lock has been released; both
        # methods acquire the same lifecycle lock themselves.
        if settings.enabled:
            initialized = await self.initialize_profile()
            if initialized.failure is not None:
                result.update(requires_initialize=True, started=False,
                              startup_error=initialized.failure.code)
                return result
            started = await self.start()
            if started.failure is not None:
                result.update(started=False, startup_error=started.failure.code)
                return result
            result["started"] = True
        return result

    async def load_existing(self):
        async with self._lifecycle_lock:
            try:
                self._settings()
                if not (self.profile_root / "runtime" / StorageRuntime.DATABASE_FILENAME).is_file():
                    return Outcome.success({"loaded": False, "started": False})
                self._idle()
                # Loading verifies the saved account/persona manifest. Window
                # provisioning belongs to start(), after the host is assembled.
                probed, _ = await self._probe(include_conversations=False)
                async with self._control_lock:
                    if self._terminated:
                        raise TaskError("host_terminated", "the shared host is stopping or terminated")
                    self._idle()
                    self._open()
                    try:
                        self.authority.require_manifest(probed)
                    except TaskError as error:
                        if error.code != "host_binding_changed":
                            raise
                        saved = self.authority.require_manifest()
                        candidate, repaired = recover_repeated_single_target(self.config, saved.get("binding_contract"))
                        if not repaired:
                            raise
                        probed = self._recover_saved_mapping(candidate, probed)
                    self._assemble(probed)
                self.last_failure = None
                return Outcome.success({"loaded": True, "started": False})
            except Exception as error:
                return self._failure(error, operation="load_existing")

    def _recover_saved_mapping(self, candidate, manifest):
        """Restore a migration-generated extra route to the durable reviewed map."""
        settings, root, adopting_legacy_profile = self._resolve_settings(candidate)
        if (root / "runtime" != self.runtime.data_root or settings.installation_id != self.runtime.installation_id):
            raise TaskError("host_storage_changed", "the recovered mapping must keep the existing V2 installation")
        restored = {**manifest, "binding_contract": settings.binding_contract,
                    "settings_fingerprint": settings.fingerprint}
        restored.pop("fingerprint", None)
        restored["fingerprint"] = digest(restored)
        self.authority.require_manifest(restored)
        save = getattr(self, "save_plugin_config", None)
        if not callable(save):
            raise TaskError("account_config_persistence_unavailable", "恢复已保存映射需要可用的插件配置保存接口。")
        try:
            save(candidate)
        except Exception as error:
            raise TaskError("account_config_save_failed", "自动恢复角色映射时保存失败，请检查插件配置文件是否可写。") from error
        self.settings, self.settings_error = settings, None
        self._storage_profile_root, self._adopting_legacy_profile = root, adopting_legacy_profile
        self.authority.settings = settings
        if self.web_api._registered_routes:
            self.unregister_routes()
            self.register_routes()
        logger.info("[CompanionV2] 已移除重复迁移的旧私聊目标，恢复已保存的角色映射")
        return restored

    async def start(self):
        async with self._lifecycle_lock:
            try:
                self._settings()
                if self.session is not None and self.session.application.state == "running":
                    return Outcome.success({"state": "running", "replayed": True})
                self._idle()
                manifest, conversations = await self._probe()
                async with self._control_lock:
                    if self._terminated:
                        raise TaskError("host_terminated", "the shared host is stopping or terminated")
                    self._settings()
                    self._idle()
                    self._open()
                    try:
                        self.authority.require_manifest(manifest)
                    except TaskError as error:
                        if error.code != "host_not_initialized":
                            raise
                        self._initialize_manifest_locked(manifest, conversations)
                        self.authority.require_manifest(manifest)
                    if self.session is None or self.session.application.state != "new":
                        self._assemble(manifest)
                    session = self.session
                    task = self.runtime.read_one("SELECT generation FROM task_supervisor WHERE singleton = 1", ())
                    model = self.runtime.read_one("SELECT generation FROM configuration_consumers WHERE consumer_id = ?", ("model_gateway",))
                    task_generation = task["generation"] if task else 0
                    model_generation = model["generation"] if model else 0
                result = await session.start(expected_task_generation=task_generation,
                                             expected_model_generation=model_generation)
                require(result)
                async with self._control_lock:
                    self._settings()
                    self._accepting, self.last_failure = True, None
                    targets = len(self.settings.all_targets)
                return Outcome.success({"state": "running", "targets": targets, "startup": result.unwrap()})
            except Exception as error:
                self._accepting = False
                return self._failure(error, operation="start")

    def target_for_event(self, event):
        if type(event) is not self.native_types.event or self.settings is None:
            return None
        try:
            message, session, meta = event.message_obj, event.session, event.platform_meta
            if getattr(message.type, "value", None) == "GroupMessage":
                route = group_event_route(event)
                target = self.settings.group_target(route.platform_id, route.account_id, route.group_id)
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
            target = self.settings.private_target(meta.id, login, sender)
            platform = self.context.get_platform_inst(meta.id)
            if target is None or platform is None or platform.get_client() is not event.bot:
                return None
            return target
        except (ValueError, AttributeError, TypeError):
            return None

    async def persona_mapping_for_event(self, event):
        """Return the registered character for this event's current AstrBot persona."""
        target = self.target_for_event(event)
        session = self.session
        if target is None or session is None:
            return None
        if isinstance(target, GroupTarget):
            route = group_event_route(event)
            bridge = session.bridge.groups
            native_scope_id = route.session_id
        else:
            bridge = session.bridge
            native_scope_id = target.participant_id
        account = bridge.accounts.get((target.platform_id, target.account_id))
        if account is None or account.bot_id != target.bot_id:
            return None
        umo = bridge._umo(target.platform_id, native_scope_id)
        _, persona_id, _, special = await bridge._selected_persona(account, umo)
        if special or type(persona_id) is not str:
            return None
        return next((mapping for mapping in self.settings.personas
                     if mapping.bot_id == target.bot_id and mapping.persona_id == persona_id), None)

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

    async def observe_context_reset(self, event):
        from .conversation_reset import observe_context_reset
        return await observe_context_reset(self, event)

    async def observe_group_early(self, event):
        """Run the V1-style group preflight before reply admission.

        The early hook is deliberately limited to an exact configured,
        authenticated group route.  It only captures the bounded text
        skeleton and materializes the group persona binding; attachment
        preparation, model generation and delivery remain in ``receive``.
        """
        from .group_settings import GroupTarget

        if (not self._accepting or self._terminated or self.session is None
                or self.session.application.state != "running"):
            return Outcome.failed("host_not_claimed", "the shared host is not accepting group input")
        try:
            target = self.target_for_event(event)
        except (TaskError, ValueError, AttributeError, TypeError):
            target = None
        if not isinstance(target, GroupTarget):
            return Outcome.failed("host_target_unavailable", "the native group route is not configured")
        return await self.session.prepare_group(event, target)

    async def group_reply_candidate(self, event):
        session, target = self.session, self.target_for_event(event)
        if not self.claims(event) or session is None or not isinstance(target, GroupTarget):
            return Outcome.failed("host_not_claimed", "group reply candidate requires an active configured target")
        return await session.prepare_group(event, target, reply_candidate=True)

    async def receive_claimed(self, event, *, on_refusal=None, group_admission=None):
        session, target = self.session, self.target_for_event(event)
        if not self.claims(event) or session is None or target is None:
            return Outcome.failed("host_not_claimed", "the native event is outside the active configured targets")
        try:
            command_result = await receive_calendar_command(self, event, session,
                target=target if is_private_message(event) else None)
            if command_result is not None:
                return command_result
            result = await session.receive(event, target, group_admission=group_admission)
            if result.failure is not None and result.failure.code == "private_access_dialogue_denied":
                # 没有对话权限：按配置回一句（真实投递模式才发）。发送失败不影响"拒绝"本身。
                receipt = await self._refuse_private(session, event)
                if callable(on_refusal):
                    on_refusal(receipt)
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
        async with self._lifecycle_lock:
            self._accepting = False
            try:
                async with self._control_lock:
                    session = self.session
                if session is None:
                    return Outcome.success({"state": "stopped", "pending_handles": []})
                report = await session.close(grace_seconds=grace_seconds)
                async with self._control_lock:
                    if report.state == "stopped" and self.session is session:
                        self.last_session, self.session = session, None
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
                "state": session.application.state if session else "uninitialized",
                "accepting": self._accepting and session is not None and session.application.state == "running",
                "failure_code": session.application.failure_code if session else None,
                "failure_detail": session.application.failure_detail if session else None,
                "targets": self.web_api.target_inventory(), "last_failure": self.last_failure,
                "settings_error": getattr(self.settings_error, "code", None)}

    def register_routes(self):
        self.web_api.register()

    def unregister_routes(self):
        self.web_api.unregister()

    async def terminate(self):
        self._terminated, self._accepting = True, False
        if self._termination_task is not None:
            return
        try:
            result = await self.stop(grace_seconds=2)
            if result.is_success:
                report = result.unwrap()
                state = report.get("state") if isinstance(report, dict) else report.state
            else:
                state = None
            if state != "stopped" and self.session is not None:
                logger.warning("[CompanionV2] 工作任务仍在退出，保留存储直到停止证明写入完成")
                self._termination_task = asyncio.create_task(self._finish_termination(),
                    name="companion:host-drain")
            else:
                await self._release_runtime()
        finally:
            self.unregister_routes()

    async def _release_runtime(self):
        async with self._control_lock:
            if self.runtime is not None:
                self.runtime.close()
                self.runtime = self.authority = None
            if self.native_extensions is not None:
                self.native_extensions.close()
                self.native_extensions = None

    async def _finish_termination(self):
        try:
            while True:
                report = await self.session.close(grace_seconds=0)
                if report.state == "stopped":
                    self.last_session, self.session = self.session, None
                    await self._release_runtime()
                    logger.info("[CompanionV2] 延迟停机完成，工作任务停止证明已保存")
                    return
                await asyncio.sleep(0.25)
        except Exception as error:
            self._failure(error, operation="terminate_drain")
            self._termination_task = None
